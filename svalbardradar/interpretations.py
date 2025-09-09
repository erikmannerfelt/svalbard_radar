import warnings
from pathlib import Path
import io

import geopandas as gpd
import json
import matplotlib.patheffects
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import scipy.interpolate
import scipy.spatial
import shapely.geometry
import tqdm
import xarray as xr

from svalbardradar.tools import paths, rasters

CACHE_PATH = paths.BASE_CACHE_PATH / "interpretations"


def read_interpretation_xy(filepath: Path) -> pd.Series:

    # ---- load JSON ----
    text = Path(filepath).read_text()
    data = json.loads(text)

    # ---- resolve user and radar_key (JSON first, then path fallback) ----
    user = data.get("user")
    radar_key = data.get("radar_key")
    if user is None or radar_key is None:
        parts = filepath.parts
        # Expect .../<user>/<radar_key>/<file>.json
        # (IndexError will raise with clear message if structure is too short)
        if user is None:
            user = parts[-3]
        if radar_key is None:
            radar_key = parts[-2]

    features = data["features"]["features"]

    # ---- accumulators (arrays only; build pandas object once at the end) ----
    y_chunks: list[np.ndarray] = []
    x_chunks: list[np.ndarray] = []
    kind_chunks: list[np.ndarray] = []

    # ---- helper: compress contiguous duplicate x via mean ----
    def _compress_dupes_mean(xi: np.ndarray, yi: np.ndarray):
        # xi is non-decreasing; duplicates (if any) appear in contiguous runs
        if xi.size == 0:
            return xi, yi
        run_starts = np.r_[0, np.flatnonzero(xi[1:] != xi[:-1]) + 1]
        run_ends = np.r_[run_starts[1:], xi.size]
        x_u = xi[run_starts]
        # mean of each run (use reduceat for O(n) pass)
        sums = np.add.reduceat(yi, run_starts)
        counts = run_ends - run_starts
        y_u = sums / counts
        return x_u, y_u

    for feature in features:
        coords = feature["geometry"]["coordinates"]
        if not coords:
            continue

        arr = np.asarray(coords, dtype=float)  # shape (n, 2)
        if arr.ndim != 2 or arr.shape[1] != 2:
            continue  # skip malformed

        arr = arr[np.argsort(arr[:, 0])]
        x_raw = arr[:, 0]
        y_raw = arr[:, 1]

        # sanity: x must be non-decreasing (duplicates allowed)
        if x_raw.size >= 2 and np.any(x_raw[1:] < x_raw[:-1]):
            raise ValueError("x must be non-decreasing within each feature")

        # bankers rounding for x -> integer pixels
        x_int = np.rint(x_raw).astype(np.int64)

        # compress contiguous duplicates by mean
        x_u, y_u = _compress_dupes_mean(x_int, y_raw)
        if x_u.size == 0:
            continue

        # full integer x-grid for this feature, then interpolate linearly
        x_full = np.arange(x_u[0], x_u[-1] + 1, dtype=np.int64)
        y_full = np.interp(x_full, x_u, y_u)  # float64 for accuracy

        # round to nearest (bankers) and cast to uint16 (safe for < 65536)
        y_full = np.rint(y_full)
        # Clip defensively to avoid casting surprises if anyone scribbles negatives
        y_full = np.clip(y_full, 0, np.iinfo(np.uint16).max).astype(np.uint16, copy=False)

        # x level: store as uint16 to save memory
        x_full_u = np.clip(x_full, 0, np.iinfo(np.uint16).max).astype(np.uint16, copy=False)

        if "kind" in feature["properties"]:
            kind = feature["properties"]["kind"]
        else:
            kind = {"Glacier bed": "bed_unspecified", "Cold glacier bed": "bed_cold", "Glacier bed missing": "bed_missing", "Temperate ice": "temperate_ice"}[feature["properties"]["name"]]

        # stash
        y_chunks.append(y_full)
        x_chunks.append(x_full_u)
        kind_chunks.append(np.repeat(kind, x_full.size))

    if not y_chunks:
        # Empty series with proper name and index names; dtypes not critical here
        empty_index = pd.MultiIndex.from_arrays(
            [[], [], [], []], names=["radar_key", "user", "kind", "x"]
        )
        return pd.Series([], index=empty_index, name="y", dtype=np.uint16)

    # ---- concatenate once ----
    y_all = np.concatenate(y_chunks)  # uint16
    x_all = np.concatenate(x_chunks)  # uint16
    kind_all = np.concatenate(kind_chunks)  # object

    n_total = y_all.size

    # Build the MultiIndex (repeat constant labels once; minimal overhead)
    mi = pd.MultiIndex.from_arrays(
        [
            np.repeat(radar_key, n_total),  # object
            np.repeat(user, n_total),       # object
            kind_all,                       # object
            x_all,                          # uint16
        ],
        names=["radar_key", "user", "kind", "x"],
    )

    return pd.Series(y_all, index=mi, name="y")


def read_interpretation_xy(filepath: Path, x_vals: np.ndarray | None = None) -> pd.Series:
    """
    Read digitized interpretation from a JSON feature collection and return y-values per pixel x.

    If `x_vals` is None (default), behaves like the original: for each feature,
    it fills every integer pixel between the first and last x with interpolated y.

    If `x_vals` (np.uint16) is provided, the function samples only at those pixels
    (per feature) that lie within that feature's [xmin, xmax] span.
    Pixels outside the span are skipped (no extrapolation).

    Returns
    -------
    pd.Series with name 'y' and MultiIndex ['radar_key', 'user', 'kind', 'x'] where
    'x' is dtype uint16 and 'y' is dtype uint16.
    """
    # ---- load JSON ----
    text = Path(filepath).read_text()
    data = json.loads(text)

    # ---- resolve user and radar_key (JSON first, then path fallback) ----
    user = data.get("user")
    radar_key = data.get("radar_key")
    if user is None or radar_key is None:
        parts = filepath.parts
        # Expect .../<user>/<radar_key>/<file>.json
        if user is None:
            user = parts[-3]
        if radar_key is None:
            radar_key = parts[-2]

    features = data["features"]["features"]

    # ---- accumulators ----
    y_chunks: list[np.ndarray] = []
    x_chunks: list[np.ndarray] = []
    kind_chunks: list[np.ndarray] = []

    # ---- helper: compress contiguous duplicate x via mean ----
    def _compress_dupes_mean(xi: np.ndarray, yi: np.ndarray):
        # xi is non-decreasing; duplicates (if any) appear in contiguous runs
        if xi.size == 0:
            return xi, yi
        run_starts = np.r_[0, np.flatnonzero(xi[1:] != xi[:-1]) + 1]
        run_ends = np.r_[run_starts[1:], xi.size]
        x_u = xi[run_starts]
        sums = np.add.reduceat(yi, run_starts)
        counts = run_ends - run_starts
        y_u = sums / counts
        return x_u, y_u
    # Normalize/prepare query x once (if provided)
    if x_vals is not None:
        # ensure array, clamp to uint16 domain, and work in int64 for math
        x_query_sorted_unique = np.unique(
            np.clip(np.asarray(x_vals, dtype=np.uint16),
                    0, np.iinfo(np.uint16).max).astype(np.int64, copy=False)
        )

    for feature in features:
        coords = feature["geometry"]["coordinates"]
        if not coords:
            continue

        arr = np.asarray(coords, dtype=float)  # shape (n, 2)
        if arr.ndim != 2 or arr.shape[1] != 2:
            continue  # skip malformed

        # sort by x
        arr = arr[np.argsort(arr[:, 0])]
        x_raw = arr[:, 0]
        y_raw = arr[:, 1]

        # sanity: x must be non-decreasing (duplicates allowed)
        if x_raw.size >= 2 and np.any(x_raw[1:] < x_raw[:-1]):
            raise ValueError("x must be non-decreasing within each feature")

        # bankers rounding for x -> integer pixels (int64 for math)
        x_int = np.rint(x_raw).astype(np.int64)

        # compress contiguous duplicates by mean
        x_u, y_u = _compress_dupes_mean(x_int, y_raw)
        if x_u.size == 0:
            continue

        # Determine which x to evaluate for this feature
        if x_vals is None:
            # Original behavior: full [x_min, x_max] integer grid
            x_eval = np.arange(x_u[0], x_u[-1] + 1, dtype=np.int64)
        else:
            # Only evaluate requested pixels that fall within this feature's span
            # (no extrapolation)
            # x_query_sorted_unique is ascending and unique so np.interp is efficient
            in_span = (x_query_sorted_unique >= x_u[0]) & (x_query_sorted_unique <= x_u[-1])
            x_eval = x_query_sorted_unique[in_span]
            if x_eval.size == 0:
                continue

        # Linear interpolation (float64), then banker-round and cast to uint16
        y_eval = np.interp(x_eval, x_u, y_u)
        y_eval = np.rint(y_eval)
        y_eval = np.clip(y_eval, 0, np.iinfo(np.uint16).max).astype(np.uint16, copy=False)

        # x level: store as uint16 to save memory
        x_eval_u16 = np.clip(x_eval, 0, np.iinfo(np.uint16).max).astype(np.uint16, copy=False)

        if "kind" in feature["properties"]:
            kind = feature["properties"]["kind"]
        else:
            kind = {
                "Glacier bed": "bed_unspecified",
                "Cold glacier bed": "bed_cold",
                "Glacier bed missing": "bed_missing",
                "Temperate ice": "temperate_ice",
            }[feature["properties"]["name"]]

        # stash
        y_chunks.append(y_eval)
        x_chunks.append(x_eval_u16)
        kind_chunks.append(np.repeat(kind, x_eval_u16.size))

    if not y_chunks:
        empty_index = pd.MultiIndex.from_arrays(
            [[], [], [], []], names=["radar_key", "user", "kind", "x"]
        )
        return pd.Series([], index=empty_index, name="y", dtype=np.uint16)

    # ---- concatenate once ----
    y_all = np.concatenate(y_chunks)  # uint16
    x_all = np.concatenate(x_chunks)  # uint16
    kind_all = np.concatenate(kind_chunks)  # object
    n_total = y_all.size

    mi = pd.MultiIndex.from_arrays(
        [
            np.repeat(radar_key, n_total),
            np.repeat(user, n_total),
            kind_all,
            x_all,
        ],
        names=["radar_key", "user", "kind", "x"],
    )

    return pd.Series(y_all, index=mi, name="y")


def standardize_along_distance(
    df: pd.DataFrame,
    new_indices,
    distance_level: str = 'distance',
    group_levels = ('radar_key', 'user', 'kind'),
    *,
    method: str = "linear",             # 'index' uses distance values for interpolation
    limit_direction: str = 'both',     # fill inner gaps both ways; ends still NaN
    dropna_how: str = 'all',           # drop rows where all columns are NaN
):
    """
    Reindex each (radar_key, user, kind) group onto `new_indices` along the
    `distance` level, using interpolation in the distance dimension.
    """
    new_idx = pd.Index(new_indices, name=distance_level)

    def _one_group(g: pd.DataFrame) -> pd.DataFrame:
        # Extract the group's distance values and build a union grid
        old = g.index.get_level_values(distance_level).to_numpy()
        union = np.unique(np.r_[old, new_idx.values])

        # (Optional but recommended) ensure strictly increasing distance
        # If duplicates at identical distance exist within the group, aggregate first:
        # g = g.groupby(level=g.index.names).mean()
        g = g.sort_index(level=distance_level)

        # Reindex to union (keeps original points + adds requested ones as NaN)
        g_union = g.reindex(union, level=distance_level)

        # Interpolate along the index (distance). Works per-column on numeric dtypes.
        g_interp = g_union.interpolate(method=method, limit_direction=limit_direction)

        # Finally, select the standardized grid
        out = g_interp.reindex(new_idx, level=distance_level)

        # Optionally drop rows where all columns are NaN (e.g., outside data range)
        return out.dropna(how=dropna_how)

    return (
        df.groupby(level=list(group_levels), group_keys=False, observed=True)
          .apply(_one_group)
    )


def read_all_interpretations(step_m: float = 5., overwrite_cache: bool = False):
    out_path = CACHE_PATH / "interp_all.feather"

    if out_path.is_file() and not overwrite_cache:
        return gpd.read_feather(out_path)

    radar_keys = paths.get_all_interpreted_radargrams()
    # testkey = "ragna_mariebreen-20240412-DAT_0404_A1_1"
    # testkey = "bergmesterbreen-20230222-DAT_0033_A1_3"
    # testkey = "amenfonna-20240510-DAT_0044_A1_1"
    # testkey = "dronbreen-20250327-DAT_0065_A1_1"

    all_data_list = []
    for radar_key in radar_keys:
        # if radar_key != testkey:
        #     continue
        # warnings.warn("Debug: filtering by key")
        interp_paths = paths.get_latest_submissions(radar_key)

        with xr.open_dataset(paths.processed_radar_path(radar_key)) as dataset, warnings.catch_warnings():


            depth_model = scipy.interpolate.interp1d(
                np.arange(dataset["data"].shape[0])[::-1],
                dataset["depth"].values,
                bounds_error=False,
            )

            diffs = np.r_[[0], np.diff(dataset["distance"].values)]
            dataset["distance"] = np.cumsum(np.where(diffs < 100, diffs, step_m))

            models = {
                key: scipy.interpolate.interp1d(
                    dataset["x"].values,
                    dataset[key].values,
                    bounds_error=False,
                )
                for key in ["easting", "northing", "distance", "elevation"]
            }

            warnings.filterwarnings("ignore", message="invalid value encountered")
            warnings.filterwarnings("ignore", message="divide by zero")
            distance_model = scipy.interpolate.interp1d(dataset["distance"].values, dataset["x"].values, bounds_error=False)
            distance_bins = np.arange(dataset["distance"].min(), dataset["distance"].max(), step_m)
            x_inds = np.unique(np.round(distance_model(distance_bins)).astype(np.uint16))

            # The part_idx represents potential jumps in location. So each idx should be treated as a separate radargram.
            models["part_idx"] = scipy.interpolate.interp1d(
                dataset["x"].values,
                np.cumsum(diffs > 100),
                bounds_error=False,
                kind="nearest",
            )
            antenna = dataset.attrs["antenna"].split("MHz")[0] + "MHz"
            crs = dataset.attrs["crs"]

        data = pd.concat([read_interpretation_xy(fp, x_vals=x_inds) for fp in interp_paths]).to_frame()

        data["depth"] = depth_model(data["y"].astype(float))
        for key in models:
            data[key] = models[key](data.index.get_level_values("x").astype(float))

        data = data.sort_values("distance").reset_index(level='x', drop=False).set_index('distance', append=True).drop(columns=["y"]).dropna(subset=["depth", "easting"])
        data = data[~data.index.duplicated(keep='first')]

        if crs != "EPSG:32633":
            points = gpd.points_from_xy(data["easting"], data["northing"], crs=crs).to_crs(
                32633
            )
            data["easting"] = points.x
            data["northing"] = points.y

        data["antenna"] = antenna
        all_data_list.append(data)
        # Ugly and slow way of standardizing the distance index to the exact step size
        # good_distances = np.arange(0, data.index.get_level_values("distance").max() + step_m, step_m)
        # for idxs, part in data.groupby(["radar_key", "user", "kind"]):
        #     part = part.reset_index().set_index("distance").drop(columns=part.index.names[:-1])
        #     resampled = part.reindex(np.unique(np.r_[good_distances, part.index.values])).interpolate().loc[good_distances].dropna(how="all")
        #     resampled.index = pd.MultiIndex.from_arrays([*[[str(idx)] * resampled.shape[0] for idx in idxs], resampled.index], names=data.index.names)
        #     all_data_list.append(resampled)

    data = pd.concat(all_data_list)

    bed_data_list = []
    for key in ["bed_cold", "bed_unspecified"]:
        try:
            bed_data_list.append(data.loc[(slice(None), slice(None), [key])])
        except KeyError:
            continue

    bed_data = pd.concat(bed_data_list)

    # bed_data = data.loc[(slice(None), slice(None), ["bed_cold", "bed_unspecified"])]
    bed_grouped = bed_data.select_dtypes(np.number).groupby(level=["radar_key", "distance"])

    out = bed_grouped.median().rename(columns={"depth": "thickness"})

    out = pd.merge(out, bed_data.select_dtypes(object).groupby(level=["radar_key", "distance"]).first(), right_index=True, left_index=True)
    out["date_str"] = out.index.get_level_values("radar_key").str.extract(r"(202\d{5})").iloc[:, 0].astype(str).values
    # out["distance"] = bed_grouped["distance"].first()
    out["thickness_std"] = bed_grouped["depth"].std()
    out["thickness_lower"] = bed_grouped["depth"].quantile(0.25)
    out["thickness_upper"] = bed_grouped["depth"].quantile(0.75)

    out["part_idx"] = out["part_idx"].round().astype(int)

    temperate_data_list = []
    for key in ["bed_cold", "temperate"]:
        try:
            temperate_data_list.append(data.loc[(slice(None), slice(None), [key])])
        except KeyError:
            continue
    # temperate_data = data.loc[(slice(None), slice(None), ["temperate", "bed_cold"])]
    temperate_data = pd.concat(temperate_data_list)
    temperate_grouped = temperate_data.select_dtypes(np.number).groupby(level=["radar_key", "distance"])

    out["temperate"] = np.clip(out["thickness"] - temperate_grouped["depth"].median(), min=0, max=out["thickness"])

    out.loc[out["temperate"].isna() & (~out["thickness"].isna()), "temperate"] = 0
    out["temperate_std"] = temperate_grouped["depth"].std()
    out["temperate_lower"] = np.clip(out["thickness"] - temperate_grouped["depth"].quantile(0.25), min=0, max=out["thickness"])
    out["temperate_upper"] = np.clip(out["thickness"] - temperate_grouped["depth"].quantile(0.75), min=0, max=out["thickness"])

    out["temperate_frac"] = out["temperate"] / out["thickness"]
    out["temperate_frac_std"] = out["temperate_std"] / out["thickness"]

    to_clamp = (out["temperate_frac"] > 0.5) & ((out["thickness"] - out["temperate"]) <= 17)
    out.loc[to_clamp, "temperate_frac"] = 1.
    for col in ["temperate", "temperate_upper"]:
        out.loc[to_clamp, col] = out["thickness"]
    
    out["bed_elevation"] = out["elevation"] - out["thickness"]
    out["temperate_elevation"] = out["bed_elevation"] + out["temperate"]
    
    out = gpd.GeoDataFrame(
        out,
        geometry=gpd.points_from_xy(
            out["easting"], out["northing"], crs=32633
        ),
    )
    # plt.hist(out["part_idx"])
    # plt.show()
    # print(out.reset_index().iloc[0])
    out.reset_index().to_feather(out_path)

    return gpd.read_feather(out_path)
    return

    out0 = out.loc[(testkey, slice(None))]

    plt.fill_between(out0.index, out0["bed_elevation"].min(), out0["bed_elevation"], color="grey")
    plt.fill_between(out0.index, out0["bed_elevation"], out0["temperate_elevation"], color="red", alpha=0.5)
    plt.fill_between(out0.index, out0["temperate_elevation"], out0["elevation"], color="blue", alpha=0.5)
    # plt.errorbar(out0.index, out0["bed_elevation"], yerr=out0["thickness_std"], color="blue", alpha=0.5)

    plt.fill_between(out0.index, out["bed_elevation"] + out0["temperate_lower"], out["bed_elevation"] + out0["temperate_upper"], color="red", alpha=0.3)
    plt.fill_between(out0.index, out["elevation"] - out0["thickness_lower"], out["elevation"] - out0["thickness_upper"], color="blue", alpha=0.3)
    # plt.errorbar(out0.index, out0["temperate_elevation"], yerr=np.clip((out0[["temperate_ice_upper", "temperate_ice_lower"]].values - np.repeat(out0["temperate_ice"].values[:, None], 2, axis=1)).T, min=0, max=None), color="red", alpha=0.5)
    plt.show()

def make_gp(length_scale_bounds=(1e-2, 2e2), mean: float | None = None):
    import sklearn.gaussian_process

    kernel = 1 * sklearn.gaussian_process.kernels.RBF(
        length_scale=np.mean(length_scale_bounds),
        length_scale_bounds=length_scale_bounds,
    )

    if mean is not None:
        kernel = kernel * sklearn.gaussian_process.kernels.ConstantKernel(mean)

    model = sklearn.gaussian_process.GaussianProcessRegressor(
        kernel=kernel,
        n_restarts_optimizer=5,
        normalize_y=True,
        alpha=1e-3,
    )
    return model

def read_interpretation_lines(filepath: Path) -> pd.DataFrame:
    interp = json.loads(filepath.read_text())

    data = gpd.read_file(io.StringIO(json.dumps(interp["features"])))

    if "kind" not in data:
        data["kind"] = data["name"].apply(
            lambda s: {"Glacier bed": "bed_unspecified", "Cold glacier bed": "bed_cold", "Glacier bed missing": "bed_missing", "Temperate ice": "temperate_ice"}[s]
        )
    return data
    

def read_interpretation(filepath: Path, step_size: int = 10) -> pd.DataFrame:
    data = pd.DataFrame()

    line_data = read_interpretation_lines(filepath=filepath)

    for kind, kind_data in line_data.groupby("kind"):
        for _, row in kind_data.iterrows():
            for distance in np.arange(0, row.geometry.length + step_size, step_size):
                point = row.geometry.interpolate(distance)

                out_data = {
                    "kind": kind,
                    "color": row["color"],
                    "x": point.x,
                    "y": point.y,
                }

                data.loc[data.shape[0], list(out_data.keys())] = list(out_data.values())

    return data


def merge_interpretations(
    radar_key: str, step_size: float = 30.0, cold_model_strength: float = 100.0, overwrite_cache: bool = False,
) -> gpd.GeoDataFrame:
    cache_path = CACHE_PATH / f"per_radargram/{radar_key}.feather"
    cache_path.parent.mkdir(exist_ok=True, parents=True)

    if cache_path.is_file() and not overwrite_cache:
        return gpd.read_feather(cache_path)

    glacier, date_str, file_stem = radar_key.split("-")
    filepath = paths.processed_radar_path(radar_key)
    if not filepath.is_file():
        return gpd.GeoDataFrame()

    data = pd.DataFrame()
    colors = {}
    interp_paths = paths.get_latest_submissions(radar_key)

    for interp_path in interp_paths:
        data = pd.concat(
            [data, read_interpretation(interp_path, step_size=step_size)],
            ignore_index=True,
        )

    if data.shape[0] == 0:
        return gpd.GeoDataFrame()

    with xr.open_dataset(filepath) as dataset:
        depth_model = scipy.interpolate.interp1d(
            np.arange(dataset["data"].shape[0])[::-1],
            dataset["depth"].values,
            bounds_error=False,
        )

        models = {
            key: scipy.interpolate.interp1d(
                dataset["x"].values,
                dataset[key].values,
                bounds_error=False,
            )
            for key in ["easting", "northing", "distance", "elevation"]
        }
        # The part_idx represents potential jumps in location. So each idx should be treated as a separate radargram.
        models["part_idx"] = scipy.interpolate.interp1d(
            dataset["x"].values,
            np.cumsum(np.r_[[0], np.diff(dataset["distance"].values)] > 100),
            bounds_error=False,
            kind="nearest",
        )
        antenna = dataset.attrs["antenna"].split("MHz")[0] + "MHz"
        crs = dataset.attrs["crs"]

    data["depth"] = depth_model(data["y"].astype(float))

    for key in models:
        data[key] = models[key](data["x"].astype(float))

    data = data.sort_values("distance")

    data = data.dropna(subset=["depth", "easting"])
    data["part_idx"] = data["part_idx"].astype(int)

    out_list = []
    for _, data in data.groupby("part_idx"):

        bed_model = make_gp()

        bed_data = data[data["kind"].isin(["bed_cold", "bed_unspecified"])]

        if bed_data.shape[0] < 5:
            continue
        with warnings.catch_warnings():
            warnings.filterwarnings("ignore")
            bed_model.fit(bed_data[["x"]].values, bed_data["depth"].values)

        cold_data = data[data["kind"].isin(["bed_cold", "temperate"])].copy()

        x_eval = np.arange(bed_data["x"].min(), bed_data["x"].max(), step_size)

        out = pd.DataFrame(index=x_eval)

        out["thickness"], out["thickness_std"] = bed_model.predict(
            x_eval[:, None], return_std=True
        )

        if cold_data.shape[0] > 2:
            bed_pred = bed_model.predict(cold_data[["x"]].values)
            cold_data["frac"] = np.clip((bed_pred - cold_data["depth"]) / bed_pred, 0, 1)
            temp_model = make_gp(mean=0, length_scale_bounds=(100, 1e3))
            with warnings.catch_warnings():
                warnings.filterwarnings("ignore")
                temp_model.fit(cold_data[["x"]].values, cold_data["frac"].values)

            out["temperate_frac"], out["temperate_frac_std"] = temp_model.predict(
                x_eval[:, None], return_std=True
            )

            out["temperate_frac"] = np.clip(out["temperate_frac"], 0, 1)

        for col in models:
            out[col] = models[col](x_eval)

        if crs != "EPSG:32633":
            points = gpd.points_from_xy(out["easting"], out["northing"], crs=crs).to_crs(
                32633
            )
            out["easting"] = points.x
            out["northing"] = points.y

        out_list.append(out)

    out = pd.concat(out_list)

    out["antenna"] = antenna
    out["radar-key"] = radar_key
    out["date_str"] = date_str
    out = gpd.GeoDataFrame(
        out, geometry=gpd.points_from_xy(out["easting"], out["northing"], crs=32633)
    )

    out.to_feather(cache_path)

    return gpd.read_feather(cache_path)


def merge_all_interpretations(
    step_size: float = 30.0,
    outlier_threshold: float = 200.0,
    cold_model_strength: float = 100.0,
    overwrite_cache: bool = False,
) -> gpd.GeoDataFrame:
    out_path = CACHE_PATH / "interp_all.feather"

    if out_path.is_file() and not overwrite_cache:
        return gpd.read_feather(out_path)

    # radar_keys = ["ragna_mariebreen-20230305-DAT_0068_A1_3", "filantropbreen-20240406-DAT_0373_A1_1", "ragna_mariebreen-20240412-DAT_0404_A1_1"][::-1]
    #
    radar_keys = paths.get_all_interpreted_radargrams()

    all_data = []
    for radar_key in tqdm.tqdm(radar_keys):
        out = merge_interpretations(
            radar_key=radar_key,
            step_size=step_size,
            cold_model_strength=cold_model_strength,
            overwrite_cache=overwrite_cache,
        )

        all_data.append(out)

    all_data = pd.concat(all_data)

    all_data = gpd.GeoDataFrame(
        all_data,
        geometry=gpd.points_from_xy(
            all_data["easting"], all_data["northing"], crs=32633
        ),
    )

    all_data.to_feather(out_path)

    return gpd.read_feather(out_path)


def grid_interpretations(
    name: str,
    outline: shapely.geometry.Polygon,
    cols: list[str] = ["thickness", "temperate_frac"],
) -> dict[str, np.ndarray | dict[str, float]]:
    cache_paths = {col: CACHE_PATH / f"gridded/{name}/{name}_{col}.tif" for col in cols}

    out = {}
    if all(fp.is_file() for fp in cache_paths.values()):
        for col in cache_paths:
            # This looks wrong but will just fetch the cache path and return its contents immediately
            raster, bounds = rasters.interpolate_raster(
                cache_paths[col], gpd.GeoDataFrame, col
            )
            out[col] = raster
            out["bounds"] = bounds
        return out

    data = merge_all_interpretations()
    data = data[data.intersects(outline, align=False)]

    for col in cols:
        cache_path = CACHE_PATH / f"gridded/{name}/{name}_{col}.tif"

        extrapolation_distance = 500
        vmin = vmax = None
        if col == "thickness":
            subset = data.query("thickness_std < 30")
        elif col == "temperate_frac":
            extrapolation_distance = 250
            subset = data.query("temperate_frac_std < 0.5")
            vmin = 0.0
            vmax = 1.0
        else:
            subset = data

        raster, bounds = rasters.interpolate_raster(
            cache_path,
            zcol=col,
            points=subset,
            extrapolation_distance=extrapolation_distance,
            res=25,
            outline=outline,
            vmin=vmin,
            vmax=vmax,
        )

        out[col] = raster
        out["bounds"] = bounds

    return out


def sample_brp_dronbreen():
    datasets = (
        [
            Path(f"processed_radar/dronbreen/20250327/DAT_00{num}_A1_1.nc")
            for num in [62, 63, 65, 66]
        ]
        + [
            Path(f"processed_radar/dronbreen/20250326/DAT_00{num}_A1_1.nc")
            for num in [44, 46, 50, 52, 53, 54, 58]
        ]
        + [Path(f"processed_radar/lofthusbreen/20250326/DAT_0057_A1_1.nc")]
    )

    for filepath in datasets:
        if "DAT_0065" not in filepath.name:
            continue
        with xr.open_dataset(filepath) as data:
            trace = data.isel(x=2500)
            # plt.plot(trace["data"].rolling(y=3, center=True).mean().values)

            # plt.plot(trace.data.values)
            # plt.imshow(data.data.values)
            # plt.show()
            # return

    points = []

    cache_filepath = Path("temp/dronbreen_brp.gpkg")
    # outline = gpd.read_file("temp/dronbreen_outline_20240828.geojson")
    outline = gpd.read_file("temp/dronbreen_pluslofhus_outline_20240828.geojson")

    if not cache_filepath.is_file():
        for filepath in datasets:
            radar_key = "-".join(filepath.parts[-3:]).replace(".nc", "")

            interp_path = sorted(Path(f"submitted/admin/{radar_key}/").glob("*.json"))[
                -1
            ]

            interp = read_interpretation(interp_path, step_size=50)

            interp = interp[
                interp["kind"].str.contains("bed_")
                & (~interp["kind"].str.contains("bed_missing"))
            ]
            interp[["y", "x"]] = interp[["y", "x"]].astype(int)

            airwave_len = 32
            brp_window_up = 20
            brp_window_down = 100 - brp_window_up
            with xr.open_dataset(filepath) as data:
                interp["y"] = data.data.shape[0] - interp["y"]
                data["data"] = np.abs(data.data) ** 2

                airwave_sum = data["data"].isel(y=slice(0, 32)).max("y")

                for idx, point in interp.iterrows():
                    point_data = data.isel(x=point["x"])

                    brp_y_min = point["y"] - brp_window_up
                    brp_y_max = point["y"] + brp_window_down

                    if brp_y_min < (airwave_len + 2):
                        continue
                    if brp_y_max > data.data.shape[0]:
                        continue

                    interp.loc[idx, "brp_uncorr"] = (
                        point_data.data.isel(y=slice(brp_y_min, brp_y_max))
                        .max("y")
                        .item()
                        / airwave_sum.isel(x=point["x"]).item()
                    )
                    # interp.loc[idx, "irp_uncorr"] = point_data.data.isel(y=slice(airwave_len, brp_y_min)).sum("y").item() / airwave_sum.isel(x=point["x"]).item()

                    interp.loc[idx, "depth"] = (
                        point_data["depth"].isel(y=point["y"]).item()
                    )

                    for key in ["easting", "northing", "elevation"]:
                        interp.loc[idx, key] = point_data[key].item()

                    # multiple_brp_y_min = point["y"] * 2 - brp_window_up
                    # multiple_brp_y_max = point["y"] * 2 + brp_window_down

                    # if multiple_brp_y_max > data.data.shape[0]:
                    #     continue

                    # interp.loc[idx, "brp_multiple_uncorr"] = point_data.data.isel(y=slice(multiple_brp_y_min, multiple_brp_y_max)).max("y").item() / airwave_sum.isel(x=point["x"]).item()

            points.append(interp)

        points = pd.concat(points).dropna(how="any", subset=["brp_uncorr"])

        outline_pts = pd.DataFrame()
        for _, polyg in outline.iterrows():
            polyg = polyg.geometry
            for d in np.arange(0, polyg.exterior.length, 10):
                point = polyg.exterior.interpolate(d)
                outline_pts.loc[outline_pts.shape[0], ["x", "y"]] = [point.x, point.y]

        tree = scipy.spatial.KDTree(outline_pts[["x", "y"]])

        points["margin_distance"] = tree.query(points[["easting", "northing"]])[0]

        points["terminus_distance"] = (
            (points["easting"] - 541821) ** 2 + (points["northing"] - 8675501) ** 2
        ) ** 0.5

        plt.scatter(
            points["depth"], points["brp_uncorr"], c=points["terminus_distance"]
        )
        pts_inside = points[points["margin_distance"] > 250]
        brp_model = np.polyfit(pts_inside["depth"], pts_inside["brp_uncorr"], deg=1)
        x_eval = np.linspace(0, points["depth"].max())
        plt.plot(x_eval, np.poly1d(brp_model)(x_eval), color="black")

        points["brp"] = points["brp_uncorr"] - points["depth"] * brp_model[0]
        # points["brp_multiple"] = points["brp_multiple_uncorr"] - points["depth"] * brp_model[0]
        # points["irp"] = (points["irp_uncorr"] - points["depth"] * brp_model[0]) / (points["depth"] / 10)

        points = gpd.GeoDataFrame(
            points,
            geometry=gpd.points_from_xy(
                points["easting"], points["northing"], crs=32633
            ),
        )

        points.to_file(cache_filepath)
        # plt.show()
    else:
        points = gpd.read_file(cache_filepath)

    fig = plt.figure(figsize=(8, 4.5))
    axes = fig.subplots(1, 2, sharex=True, sharey=True)

    axes[0].scatter(
        points["brp_uncorr"], points["depth"], c=points["margin_distance"], s=8
    )
    pts_inside = points[points["margin_distance"] > 250]
    brp_model = np.polyfit(pts_inside["depth"], pts_inside["brp_uncorr"], deg=1)
    x_eval = np.linspace(0, points["depth"].max())
    axes[0].plot(np.poly1d(brp_model)(x_eval), x_eval, color="black")
    axes[0].set_ylim(plt.gca().get_ylim()[::-1])
    axes[0].set_xlabel("Normalized BRP")
    axes[0].set_ylabel("Depth (m)")

    scatter = axes[1].scatter(
        points["brp"], points["depth"], c=points["margin_distance"], s=8
    )
    cbar = plt.colorbar(scatter)
    cbar.set_label("Distance to margin (m)")
    axes[1].set_xlabel("Normalized BRP")
    plt.tight_layout()
    plt.savefig("temp/dronbreen_brp_points.jpg", dpi=600)
    # plt.show()
    plt.close()
    # return
    # return
    # return
    import rasterio as rio
    import rasterio.features

    res = 50
    transform = rio.transform.from_origin(
        outline.total_bounds[0], outline.total_bounds[3], res, res
    )

    eastings = np.arange(outline.total_bounds[0], outline.total_bounds[2], res)
    northings = np.arange(outline.total_bounds[1], outline.total_bounds[3], res)

    points["xbin"] = np.digitize(points["easting"], eastings)
    points["ybin"] = np.digitize(points["northing"], northings)

    points["bin"] = points["ybin"] * northings.shape[0] + points["xbin"]

    x_x, y_y = np.meshgrid(eastings, northings[::-1])
    data_distance = (
        scipy.spatial.KDTree(points[["easting", "northing"]])
        .query(np.transpose([x_x.ravel(), y_y.ravel()]))[0]
        .reshape(y_y.shape)
    )

    points["easting_orig"] = points["easting"]
    points["northing_orig"] = points["northing"]

    points["easting"] -= eastings.min()
    eastings -= eastings.min()

    points["northing"] -= northings.min()
    northings -= northings.min()

    points["easting"] /= eastings.max()
    eastings /= eastings.max()

    points["northing"] /= northings.max()
    northings /= northings.max()

    points = points.select_dtypes(np.number).groupby("bin").mean()

    x_x, y_y = np.meshgrid(eastings, northings[::-1])

    glacier_mask = (
        rasterio.features.rasterize(
            outline["geometry"], out_shape=y_y.shape, transform=transform
        )
        == 1
    )

    mask = glacier_mask & (data_distance < 500)

    # kernel = 1 * sklearn.gaussian_process.kernels.RBF(length_scale=1)
    # model= sklearn.gaussian_process.GaussianProcessRegressor(
    #     kernel=kernel,
    #     n_restarts_optimizer=5,
    #     normalize_y=True,
    #     alpha=3e-1,
    # )
    # model.fit(points[["easting", "northing"]].values, points["brp"].values)
    # interp = model.predict(np.transpose([x_x.ravel(), y_y.ravel()])).reshape(y_y.shape)
    # print(model.kernel)

    rbf = scipy.interpolate.RBFInterpolator(
        points[["easting", "northing"]], points["brp"], smoothing=0.02
    )
    interp = rbf(np.transpose([x_x.ravel(), y_y.ravel()])).reshape(y_y.shape)

    with rio.open(
        "temp/dronbreen_brp.tif",
        "w",
        driver="GTiff",
        width=interp.shape[1],
        height=interp.shape[0],
        count=1,
        crs="EPSG:32633",
        transform=transform,
        dtype="float32",
        nodata=-9999,
        compress="deflate",
        zlevel=12,
    ) as raster:
        raster.write(np.where(mask, interp, -9999), 1)
    # interp[~mask] = np.nan
    interp = np.ma.masked_array(interp, mask=~mask)

    fig = plt.figure(figsize=(8, 4.5))
    axes = fig.subplots(1, 3, width_ratios=[0.49, 0.49, 0.02])

    extent = [
        outline.total_bounds[0],
        outline.total_bounds[2],
        outline.total_bounds[1],
        outline.total_bounds[3],
    ]
    axes[0].imshow(glacier_mask, extent=extent, cmap="RdBu", vmin=-2, vmax=2)
    axes[0].scatter(
        points["easting_orig"],
        points["northing_orig"],
        c=points["brp"],
        vmin=0.4,
        vmax=1.1,
        cmap="inferno",
        s=5,
    )
    axes[1].imshow(glacier_mask, extent=extent, cmap="RdBu", vmin=-2, vmax=2)
    img = axes[1].imshow(interp, extent=extent, vmin=0.4, vmax=1.1, cmap="inferno")

    cbar = plt.colorbar(img, cax=axes[2])
    cbar.set_label("Normalized BRP")

    axes[0].set_yticks(axes[0].get_yticks())
    axes[0].set_yticklabels(
        [
            "" if i not in [3, 7] else int(tick)
            for i, tick in enumerate(axes[0].get_yticks())
        ],
        rotation=90,
        ha="center",
        va="center",
    )
    axes[1].set_yticks(axes[0].get_yticks())
    axes[1].set_yticklabels([""] * len(axes[0].get_yticks()))

    for i in [0, 1]:
        axes[i].set_ylim(extent[2], extent[3])
        axes[i].set_xlim(extent[0], extent[1])
        axes[i].set_xticks(axes[i].get_xticks()[1:-1])
        axes[i].set_xticklabels(
            [
                "" if i not in [0, 1] else int(tick)
                for i, tick in enumerate(axes[0].get_xticks())
            ],
            ha="center",
        )

    plt.tight_layout()

    plt.savefig("temp/dronbreen_brp_map.jpg", dpi=600)

    # plt.scatter(points["easting"], points["northing"], c=points["brp"], vmin=0.4, vmax=1.1)
    plt.show()
    return
