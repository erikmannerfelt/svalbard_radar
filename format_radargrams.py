from numpy._core.multiarray import set_datetimeparse_function
import xarray as xr
import matplotlib.pyplot as plt
from pathlib import Path
import numpy as np
from PIL import Image
import geopandas as gpd
import shapely
import scipy.interpolate
import scipy
import warnings
import tqdm
import hashlib
import json
import functools

def checksum(objects: list[object]) -> str:
    return hashlib.sha256("".join(map(str, objects)).encode()).hexdigest()

def normalize(data: np.ndarray, gain_strength: float = 0.02):
    data_abs = np.abs(data)
    minval_abs, maxval_abs = np.percentile(np.abs(data_abs[50:]), [1, 97])
    data_abs = np.clip((data - minval_abs) / (maxval_abs - minval_abs), 0, 1)
    maxval = np.percentile(np.abs(data[50:]), 99)
    minval = -maxval
    data = np.clip((data - minval) / (maxval - minval), 0, 1)

    return {
        "classic": (data * 255).astype("uint8"),
        "abslog": (data_abs * 255).astype("uint8"),
    }
    

def get_radargram_cache_path(src_filepath: Path) -> tuple[Path, Path]:

    filename_for_key = "/".join(src_filepath.parts[-3:])
    with xr.open_dataset(src_filepath) as data:
        
        checksum = hashlib.md5((filename_for_key + data.attrs["processing-datetime"]).encode()).hexdigest()

    static_path = (Path("static/radargrams/") / filename_for_key).with_suffix("")
    cache_path = Path(f"cache/radargrams/{filename_for_key.replace('/', '-')}-{checksum}/")

    return static_path, cache_path

    

def parse_radargram(src_filepath: Path, chunksize: int = 1000, override_cache: bool = False) -> dict[str, object]:
    src_filepath = Path(src_filepath)

    radar_key = "-".join(src_filepath.with_suffix("").parts[-3:])
    # static_dir = (Path("static/radargrams/") / "/".join(src_filepath.parts[-3:])).with_suffix("")
    static_dir, cache_dir = get_radargram_cache_path(src_filepath)

    meta_cache_path = cache_dir / "meta.json"
    # These are run with slower settings and need stretching to be usable.
    xscale = {
        "rugaasfonna-20220222-DAT_0738_A1_9": 5,
        "rugaasfonna-20220218-DAT_0728_A1_3": 5,
        "rugaasfonna-20220218-DAT_0723_A1_1": 5,
        "rugaasfonna-20220218-DAT_0727_A1_1": 5,
        "svellnosbreen-20220218-DAT_0735_A1_2": 5,
        "winsnesbreen-20240503-DAT_0013_A1_1": 3,
        "moysalbreen-20220222-DAT_0760_A1_1": 5,
        "moysalbreen-20220222-DAT_0750_A1_6": 5,
        "moysalbreen-20220222-DAT_0749_A1_1": 5,
        "dronbreen-20200226-DAT_0086_A1_1": 0.3,

        "amenfonna-20240510-DAT_0044_A1_1": 3,
        "etonbreen-20240503-DAT_0011_A1_1": 3,
        "bergmesterbreen-20230222-DAT_0017_A1_4": 3,
        "bergmesterbreen-20230222-DAT_0036_A1_1": 2,
        "scott_turnerbreen-20240207-DAT_0457_A1_3": 2,
    }

    if meta_cache_path.is_file() and not override_cache:
        return json.loads(meta_cache_path.read_text())

    with xr.open_dataset(src_filepath) as data:

        d_t = data["time"].diff("x").values
        d_t[d_t == 0] = np.nan

        if not np.any(np.isfinite(d_t)):
            median_dt = 0.2
        else:
            median_dt = np.nanmedian(d_t)

        break_mask = (data["distance"].diff("x") > 100) | (d_t > (median_dt * 50))
        break_idx = np.unique(np.r_[[0, break_mask.values.shape[0]], np.argwhere(break_mask.values).ravel() + 1])

        length = 0.
        tracks = []

        distances = data["distance"].values
        x_indexes = np.arange(data["data"].shape[1])
        
        interval_indicators = []
        for i, upper in enumerate(break_idx[1:], start=1):
            lower = break_idx[i - 1]
            if (upper - lower) < 10:
                continue
            interval_indicators.append([int(lower), int(upper)])

            interval_slice = slice(lower, upper)

            dist_subset = distances[interval_slice]
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                x_ind_model = scipy.interpolate.interp1d(dist_subset, x_indexes[interval_slice], fill_value="extrapolate")

                x_x = np.r_[np.arange(dist_subset.min(), dist_subset.max(), step=5), [dist_subset.max()]]

                if len(x_x) == 1:
                    continue
                x_inds = x_ind_model(x_x)

                x_inds = np.clip(np.where(np.isfinite(x_inds), x_inds, 0), lower, upper - 1).astype(int)

            # Construct interpolated points for the track in the native crs
            points = gpd.points_from_xy(data["easting"].isel(x=x_inds), data["northing"].isel(x=x_inds), crs=data.attrs["crs"])

            track_length = np.sum(np.sqrt(np.sum(np.power([np.diff(points.x), np.diff(points.y)], 2), axis=0)))

            # Append the track to the output in WGS84
            tracks.append(
                {
                    "i": len(interval_indicators) - 1,
                    "n_traces": int(upper - lower),
                    "length": round(track_length, 2),
                    "geometry": shapely.geometry.LineString(points.to_crs(4326))
                }
            )
            # Lazy way of measuring the length in native units
            length += track_length

        images: dict[str, np.ndarray] | None = None
        # image = normalize(data["data"].values)
        tiles = []
        for col in range(0, data["data"].shape[1], chunksize):
            col_slice = slice(col, min(col + chunksize, data["data"].shape[1]))
            for row in range(0, data["data"].shape[0], chunksize):
                row_slice = slice(row, min(row + chunksize, data["data"].shape[0]))
                filepaths = {}
                for key in ["abslog", "classic"]:
                    filepath = static_dir / f"tiles/{key}/tile_{str(row).zfill(5)}_{str(col).zfill(5)}.jpg"

                    if (not filepath.is_file()) or override_cache:
                        if images is None:
                            images = normalize(data["data"].values)
                        tile_arr = images[key][row_slice, col_slice]
                        filepath.parent.mkdir(exist_ok=True, parents=True)

                        Image.fromarray(tile_arr).save(filepath)
                    filepaths[key] = "/" + str(filepath)

                tiles.append({
                    "filepaths": filepaths,
                    "minx": col,
                    "maxx": col_slice.stop,
                    "miny": data["data"].shape[0] - row_slice.stop,
                    "maxy": data["data"].shape[0] - row,
                })

        thumbnail_path = static_dir / "thumbnail.jpg"

        if (not thumbnail_path.is_file()) or override_cache:
            if images is None:
                images = normalize(data["data"].values)

            image = images["abslog"]

            max_height = 512
            # Note to myself: PIL uses (width, height) and not the more common opposite
            if image.shape[1] <= max_height:
                new_shape = image.shape
            else:
                new_width = int((image.shape[1] / image.shape[0]) * max_height)
                new_shape = (new_width, max_height)

            if radar_key in xscale:
                new_shape = (int(new_shape[0] * xscale[radar_key]), new_shape[1])

            thumb = Image.fromarray(image).resize(new_shape, resample=Image.Resampling.LANCZOS)

            # Stretch it to use the full 0-255 range.
            thumb = np.array(thumb, dtype="float32")
            minval, maxval = np.percentile(thumb, [0.5, 99])
            thumb = Image.fromarray((255 * np.clip((thumb - minval) / (maxval - minval), 0, 1)).astype("uint8"))
            thumb.save(thumbnail_path)

        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", message=".*invalid value encountered in divide.*")
            warnings.filterwarnings("ignore", message=".*divide by zero encountered in divide.*")
            warnings.filterwarnings("ignore", message=".*All-NaN slice*")

            speeds = np.diff(data.distance.values) / np.diff(data.time.values)
            speeds[~np.isfinite(speeds)] = np.nan

            speed = round(np.nanmedian(speeds), 3)

            if not np.isfinite(speed):
                speed = "-"
            else:
                speed = round(float(speed), 2)

        track_merged = shapely.geometry.MultiLineString([t["geometry"] for t in tracks])

        tracks_geojson = []
        for track in tracks:
            tracks_geojson.append(
                {
                    "type": "Feature",
                    "geometry": shapely.geometry.mapping(track["geometry"]),
                    "properties": {k: v for k, v in track.items() if k != "geometry"}
                }
            )

        trace_resolution_s = round(float(data.attrs.get("time-interval", np.median(np.diff(data.time.values)))), 3)


        meta = {
            "radar_key": radar_key,
            "width": data["data"].shape[1],
            "height": data["data"].shape[0],
            "thumbnail": str(thumbnail_path),
            "length": length,
            "length_km_rounded": round(length / 1000, 1),
            "max_depth": round(data.depth.max().item(), 2),
            "max_time": round(data["return-time"].max().item(), 2),
            "antenna": data.attrs["antenna"],
            "depth_resolution_m": round(float(np.diff(data.depth.values[-2:])[0]), 3),
            "trace_resolution_s": float(trace_resolution_s),
            "interval_indicators": interval_indicators,
            "average_speed": speed,
            "bounds": {
                "minlat": track_merged.bounds[1],
                "maxlat": track_merged.bounds[3],
                "minlon": track_merged.bounds[0],
                "maxlon": track_merged.bounds[2],
            },
            "track": tracks_geojson,
            "tiles": tiles,
        }
        meta["xscale"] = xscale.get(meta["radar_key"], 1.)
        meta_cache_path.parent.mkdir(exist_ok=True, parents=True)
        meta_cache_path.write_text(json.dumps(meta, indent=2))
        return meta


def parse_all_radargrams(progress: bool = False, redo_cache: bool = False):
    radargrams = {}

    glacier_dirs = list(Path("processed_radar").glob("*"))
    with tqdm.tqdm(total=len(glacier_dirs), disable=(not progress)) as progress_bar:
        for glacier_dir in glacier_dirs:
            if not glacier_dir.is_dir():
                continue
            radargrams[glacier_dir.stem] = {}
            for filepath in glacier_dir.rglob("*.nc"):
                progress_bar.set_description("/".join(filepath.parts[-3:]))
                radargram = parse_radargram(filepath, override_cache=redo_cache)
                radargrams[glacier_dir.stem][radargram["radar_key"]] = radargram
            progress_bar.update()

    return radargrams
    

if __name__ == "__main__":
    # parse_radargram(Path("./processed_radar/amenfonna/20240507/DAT_0042_A1.nc"), override_cache=True)
    # parse_radargram(Path("./processed_radar/ragna_mariebreen/20230305/DAT_0050_A1_6.nc"), override_cache=True)
    # parse_radargram(Path("./processed_radar/bergmesterbreen/20230222/DAT_0033_A1_3.nc"), override_cache=True)
    # parse_radargram(Path("./processed_radar/bergmesterbreen/20230222/DAT_0017_A1_4.nc"), override_cache=True)
    parse_radargram(Path("./processed_radar/rugaasfonna/20220222/DAT_0738_A1_9.nc"), override_cache=True)
    # parse_radargram(Path("./processed_radar/edvardbreen/20240411/DAT_0396_A1_1.nc"), override_cache=True)
