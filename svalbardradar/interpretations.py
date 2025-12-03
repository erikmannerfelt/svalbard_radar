import warnings
from pathlib import Path

import geopandas as gpd
import json
import numpy as np
import pandas as pd
import scipy.interpolate
import shapely.geometry
import xarray as xr

from svalbardradar.tools import paths, rasters, stats

CACHE_PATH = paths.BASE_CACHE_PATH / "interpretations"


def read_interpretation_xy(filepath: Path, x_vals: np.ndarray | None = None) -> pd.DataFrame:
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
            np.clip(np.asarray(x_vals, dtype=np.uint16), 0, np.iinfo(np.uint16).max).astype(np.int64, copy=False)
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
        empty_index = pd.MultiIndex.from_arrays([[], [], [], []], names=["radar_key", "user", "kind", "x"])
        return pd.DataFrame({"y": [], "i": []}, index=empty_index, dtype="uint16")

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


def read_interpretations(radar_key: str, step_m: float) -> pd.DataFrame:
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

    data["distance"] = (data["distance"] / step_m).round() * step_m

    data = (
        data.sort_values("distance")
        .reset_index(level="x", drop=False)
        .set_index("distance", append=True)
        .dropna(subset=["depth", "easting"])
    )
    data = data[~data.index.duplicated(keep="first")]

    if crs != "EPSG:32633":
        points = gpd.points_from_xy(data["easting"], data["northing"], crs=crs).to_crs(32633)
        data["easting"] = points.x
        data["northing"] = points.y

    data["antenna"] = antenna
    return data


def gpr_uncertainty(
    thickness: np.ndarray,
    frequency_mhz: np.ndarray | float,
    medium_velocity: float = 0.168,
    medium_velocity_uncertainty_frac: float = 0.02,
):
    """Calculate the GPR-component of uncertainty after Lapazaran et al., (2016)

    Parameters
    ----------
    thickness
        The thickness (or depth) of a reflector
    frequency_mhz
        The antenna center frequency in MHz
    medium_velocity
        The velocity of the radar wave in the medium
    medium_velocity_uncertainty_frac
        The uncertainty in the medium velocity as a fraction of the velocity itself


    Examples
    --------
    >>> thickness = np.array([100, 200])
    >>> err = gpr_uncertainty(thickness, frequency_mhz=25.)
    >>> err[0] < err[1]
    np.True_
    >>> 2. < err[0] < 2.1
    np.True_
    >>> 4. < err[1] < 4.1
    np.True_

    Returns
    -------
    An array of uncertainties.
    """
    twtt_ns = thickness * 2.0 / medium_velocity
    time_uncertainty_ns = 1000.0 / frequency_mhz

    part_a = twtt_ns**2 * (medium_velocity * medium_velocity_uncertainty_frac) ** 2
    part_b = medium_velocity**2 * time_uncertainty_ns

    return np.sqrt(part_a + part_b) / 2


def gnss_uncertainty(
    thickness: np.ndarray,
    distance: np.ndarray,
    speed_kmh: float = 15.0,
    gnss_timing_uncertainty_s: float = 1.0,
    gnss_fix_uncertainty_m: float = 10.0,
    min_x_step_m: float = 0.0,
):
    """Calculate the GNSS(positioning)-component of uncertainty after Lapazaran et al., (2016).

    Parameters
    ----------
    thickness
        The thickness (or depth) of a reflector in meters.
    distance
        Cumulative distance array to derive dx from in meters.
    speed_kmh
        The average survey speed in km/h.
    gnss_timing_uncertainty_s
        The timing uncertainty between GNSS and GPR measurements in seconds.
    gnss_fix_uncertainty_m
        The horizontal positioning uncertainty of the GNSS fix in meters.
    min_x_step_m
        The minimum distance value to clamp to. This is useful in case of sampling issues (e.g. if two subsequent
        points are roughly in the same place, then step ~= 0).

    Examples
    --------
    >>> thickness = np.array([100, 200])
    >>> distance = np.array([0, 1000])
    >>> err = gnss_uncertainty(thickness, distance)
    >>> err[0] == err[1]
    np.True_
    >>> 1. < err[0] < 1.1
    np.True_
    >>> err2 = gnss_uncertainty(thickness, distance / 2)
    >>> (err[0] * 2) == err2[0]
    np.True_

    Returns
    -------
    An array of uncertainties.
    """
    diffs = np.diff(thickness) / np.clip(np.abs(np.diff(distance)), a_min=min_x_step_m, a_max=None)
    gradient = np.r_[diffs[[0]], (diffs[1:] + diffs[:-1]) / 2.0, diffs[[-1]]]

    horizontal_timing_uncertainty_m = (speed_kmh / 3.6) * gnss_timing_uncertainty_s

    horizontal_pos_uncertainty_m = np.sqrt(horizontal_timing_uncertainty_m**2 + gnss_fix_uncertainty_m**2)

    return horizontal_pos_uncertainty_m * np.abs(gradient)


def merge_all_interpretations(
    step_m: float = 5.0, overwrite_cache: bool = False, _key_list: None | list[str] = None
) -> gpd.GeoDataFrame:
    out_path = CACHE_PATH / "interp_all.feather"

    if out_path.is_file() and not overwrite_cache:
        return gpd.read_feather(out_path)

    if _key_list is None:
        radar_keys = paths.get_all_interpreted_radargrams()
    else:
        radar_keys = _key_list

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

    bed_grouped = bed_data.select_dtypes(np.number).groupby(level=["radar_key", "distance"])

    # Identify areas where the majority of people say the bed is missing
    bed_existing_count = bed_grouped["depth"].count()
    bed_missing_count = data.loc[(slice(None), slice(None), "bed_missing")]["depth"].groupby(level=[0, 2]).count()
    missing_, existing_ = bed_missing_count.align(bed_existing_count, join="inner")
    mask = missing_ > existing_
    idx_missing = mask[mask].index

    # I'm taking the 49% percentile because in case of 50/50 splits, it will otherwise jump between the two solutions.
    out = bed_grouped.quantile(0.49, interpolation="lower").rename(columns={"depth": "thickness"}).drop(idx_missing)

    out = pd.merge(
        out,
        bed_data.select_dtypes(object).groupby(level=["radar_key", "distance"]).first(),
        right_index=True,
        left_index=True,
    )
    out["date_str"] = out.index.get_level_values("radar_key").str.extract(r"(202\d{5})").iloc[:, 0].astype(str).values

    out["part_idx"] = out["part_idx"].round().astype(int)

    temperate_data_list = []
    for key in ["bed_cold", "temperate"]:
        try:
            new_data = data.loc[(slice(None), slice(None), [key])].copy()  # type: ignore
            new_data["temperate_line"] = 1 if key == "temperate" else 0
            temperate_data_list.append(new_data)
        except KeyError:
            continue
    temperate_data = pd.concat(temperate_data_list)
    temperate_grouped = temperate_data.select_dtypes(np.number).groupby(level=["radar_key", "distance"])

    # I'm taking the 49% percentile because in case of 50/50 splits, it will otherwise jump between the two solutions.
    out["temperate"] = temperate_grouped["depth"].quantile(0.49, interpolation="lower")

    out.loc[out["temperate"].isna() & (~out["thickness"].isna()), "temperate"] = out["thickness"]
    for prefix, grouped in [("thickness", bed_grouped), ("temperate", temperate_grouped)]:
        out[f"{prefix}_user_lower"] = grouped["depth"].quantile(0.25, interpolation="lower")
        out[f"{prefix}_user_upper"] = grouped["depth"].quantile(0.75, interpolation="lower")

        out[f"{prefix}_user_std"] = grouped["depth"].std()
        out[f"{prefix}_user_nmad"] = grouped["depth"].apply(lambda v: stats.nmad(v))
        out[f"{prefix}_user_count"] = grouped["depth"].count().astype(int)
        if prefix == "temperate":
            out["temperate_user_temperate_line_count"] = grouped["temperate_line"].sum().astype(int)

        out[f"{prefix}_gpr_uncertainty"] = gpr_uncertainty(
            thickness=out[prefix], frequency_mhz=out["antenna"].str.replace(" MHz", "").astype(float)
        )
        out[f"{prefix}_gnss_uncertainty"] = gnss_uncertainty(
            thickness=out[prefix],
            distance=out.index.get_level_values("distance"),
            min_x_step_m=step_m**0.5,
        )

        out[f"{prefix}_nmad"] = (
            out[[f"{prefix}_gpr_uncertainty", f"{prefix}_gnss_uncertainty", f"{prefix}_user_nmad"]]
            .pow(2)
            .sum(axis="columns")
            .pow(0.5)
        )
        out[f"{prefix}_std"] = (
            out[[f"{prefix}_gpr_uncertainty", f"{prefix}_gnss_uncertainty", f"{prefix}_user_std"]]
            .pow(2)
            .sum(axis="columns")
            .pow(0.5)
        )

        instrument_unc = (
            out[[f"{prefix}_gpr_uncertainty", f"{prefix}_gnss_uncertainty"]].pow(2).sum(axis="columns").pow(0.5)
        )

        out[f"{prefix}_lower"] = out[f"{prefix}_user_lower"] - instrument_unc
        out[f"{prefix}_upper"] = out[f"{prefix}_user_upper"] + instrument_unc

    temperate_cols = ["temperate", "temperate_upper", "temperate_user_upper", "temperate_lower", "temperate_user_lower"]

    for col in temperate_cols:
        # Invert the temperate ice columns so that it starts at 0 at the base and increases going up
        out[col] = (out["thickness"] - out[col]).clip(lower=0, upper=out["thickness"])

    out["temperate_frac"] = out["temperate"] / out["thickness"]
    out["temperate_frac_std"] = out["temperate_user_std"] / out["thickness"]

    to_clamp = (out["temperate_frac"] > 0.5) & (out["temperate"] <= 17)
    out.loc[to_clamp, "temperate_frac"] = 1.0
    for col in temperate_cols:
        out.loc[to_clamp, col] = out["thickness"]

    out["bed_type"] = "unclear"
    certain_cold = (out["temperate_user_lower"] / out["thickness"]) < 0.01
    out.loc[certain_cold, "bed_type"] = "certain_cold"
    out.loc[(out["temperate_user_upper"] / out["thickness"]) > 0.01, "bed_type"] = "certain_temperate"
    out.loc[(out["bed_type"] == "unclear") & (out["temperate_frac"] < 0.01), "bed_type"] = "uncertain_cold"
    out.loc[(out["bed_type"] == "unclear") & (out["temperate_frac"] > 0.01), "bed_type"] = "uncertain_temperate"

    # If the bed is certainly cold, the temperate ice spread values default back to only user spread
    # This is because there would otherwise look like there is ambiguity everywhere.
    # Also, if there is no temperate ice line at all, it's cold. Otherwise, ambiguities in the
    # ... "Glacier bed (no temperate ice)" class would lead to an apparent temperate ice uncertainty.
    no_temp = (out["temperate_user_temperate_line_count"] == 0) | (
        (out["temperate_user_temperate_line_count"] / out["temperate_user_count"].clip(lower=1)) < 0.25
    )
    for key in ["nmad", "std", "lower", "upper"]:
        out.loc[certain_cold, f"temperate_{key}"] = out.loc[certain_cold, f"temperate_user_{key}"]
        out.loc[no_temp, f"temperate_{key}"] = 0.0
    out.loc[no_temp, "temperate"] = 0.0
    out.loc[no_temp, "temperate_frac"] = 0.0
    out.loc[no_temp, "temperate_frac_std"] = 0.0

    out["bed_elevation"] = out["elevation"] - out["thickness"]
    out["temperate_elevation"] = out["bed_elevation"] + out["temperate"]

    out = gpd.GeoDataFrame(
        out,
        geometry=gpd.points_from_xy(out["easting"], out["northing"], crs=32633),
    )
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
            raster, bounds = rasters.interpolate_raster(cache_paths[col], gpd.GeoDataFrame(), col)
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
