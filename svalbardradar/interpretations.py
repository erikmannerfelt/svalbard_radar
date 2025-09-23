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
    pd.DataFrame with the fields 'y' and 'i' and MultiIndex ['radar_key', 'user', 'kind', 'x'] where
    The field 'y' represents the y pixel, and i represents the line index.
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
    i_all = np.concatenate([[np.uint16(i)] * len(vals) for i, vals in enumerate(y_chunks)])
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

    return pd.DataFrame({"y": y_all, "i": i_all}, index=mi)


def read_interpretations(radar_key: str, step_m: float):
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

    data = pd.concat([read_interpretation_xy(fp, x_vals=x_inds) for fp in interp_paths]).rename(columns={"i": "line_i"})

    data["depth"] = depth_model(data["y"].astype(float))
    for key in models:
        data[key] = models[key](data.index.get_level_values("x").astype(float))

    data = data.sort_values("distance").reset_index(level='x', drop=False).set_index('distance', append=True).dropna(subset=["depth", "easting"])
    data = data[~data.index.duplicated(keep='first')]

    if crs != "EPSG:32633":
        points = gpd.points_from_xy(data["easting"], data["northing"], crs=crs).to_crs(
            32633
        )
        data["easting"] = points.x
        data["northing"] = points.y

    data["antenna"] = antenna
    return data
    


def merge_all_interpretations(step_m: float = 5., overwrite_cache: bool = False):
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
        all_data_list.append(read_interpretations(radar_key=radar_key, step_m=step_m))
    data = pd.concat(all_data_list).drop(columns=["line_i", "y"])

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

