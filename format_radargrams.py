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

    butter = scipy.signal.butter(4,[0.08, 0.999], "bandpass", output="sos")
    data = scipy.signal.sosfilt(butter, data, axis=0)

    data *= (10 ** ((np.arange(data.shape[0]) ** 0.5) * gain_strength))[:, None]

    data -= np.median(data)

    data_abslog = np.log10(np.abs(data + 1e-4))

    minval_10, maxval_10 = np.percentile(np.abs(data_abslog[50:]), [5, 99])

    data_abslog = np.clip((data_abslog - minval_10) / (maxval_10 - minval_10), 0, 1)
    sign = np.sign(data)
    data = np.clip(np.log10(np.abs(data + 1e-9)) - 1, 0, None) * sign
    # plt.hist(data.ravel(), bins=50)
    # plt.show()

    # minval, maxval = np.percentile(data, [1, 99])
    maxval = np.percentile(np.abs(data[50:]), 99)
    minval = -maxval
    data = np.clip((data - minval) / (maxval - minval), 0, 1)

    return {
        "classic": (data * 255).astype("uint8"),
        "abslog": (data_abslog * 255).astype("uint8"),
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

    # static_dir = (Path("static/radargrams/") / "/".join(src_filepath.parts[-3:])).with_suffix("")
    static_dir, cache_dir = get_radargram_cache_path(src_filepath)

    meta_cache_path = cache_dir / "meta.json"

    if meta_cache_path.is_file() and not override_cache:
        return json.loads(meta_cache_path.read_text())

    with xr.open_dataset(src_filepath) as data:

        # plt.imshow(normalize(data["data"])["abslog"], cmap="Greys_r")
        # plt.show()
        # return

        d_t = data["time"].diff("x")

        break_mask = (data["distance"].diff("x") > 100) | (d_t > (d_t.median("x") * 5))
        break_idx = np.unique(np.r_[[0, break_mask.values.shape[0]], np.argwhere(break_mask.values).ravel()])

        length = 0.
        track = []

        interval_indicators = []
        for i, upper in enumerate(break_idx[1:], start=1):
            lower = break_idx[i - 1]
            if (upper - lower) < 3:
                continue
            interval_indicators.append([int(lower), int(upper)])

            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                x_inds = scipy.interpolate.interp1d(data["distance"].values, np.arange(data["data"].shape[1]))(np.r_[np.arange(0, data["distance"].values.max(), step=5), [data["distance"].max().item()]])
                x_inds = np.clip(np.where(np.isfinite(x_inds), x_inds, 0), 0, data["data"].shape[1] - 1).astype(int)

            # Construct interpolated points for the track in the native crs
            points = gpd.points_from_xy(data["easting"].isel(x=x_inds), data["northing"].isel(x=x_inds), crs=data.attrs["crs"])
            # Append the track to the output in WGS84
            track.append(shapely.geometry.LineString(points.to_crs(4326)))
            # Lazy way of measuring the length in native units
            length += shapely.geometry.LineString(points).length
            

        track = shapely.geometry.MultiLineString(track)
        images: dict[str, np.ndarray] | None = None
        # image = normalize(data["data"].values)
        tiles = []
        for row in range(0, data["data"].shape[0], chunksize):
            row_slice = slice(row, min(row + chunksize, data["data"].shape[0]))
            for col in range(0, data["data"].shape[1], chunksize):
                col_slice = slice(col, min(col + chunksize, data["data"].shape[1]))

                filepaths = {}
                for key in ["abslog", "classic"]:
                    filepath = static_dir / f"tiles/{key}/tile_{str(row).zfill(5)}_{str(col).zfill(5)}.jpg"

                    if not filepath.is_file():
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

        if not thumbnail_path.is_file():
            if images is None:
                images = normalize(data["data"].values)

            image = images["abslog"]

            max_height = 512
            if image.shape[0] <= max_height:
                new_shape = image.shape
            else:
                new_width = int((image.shape[0] / image.shape[1]) * max_height)
                new_shape = (max_height, new_width)
            Image.fromarray(image).resize(new_shape, resample=Image.Resampling.BILINEAR).save(thumbnail_path)

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

        meta = {
            "radar_key": "-".join(src_filepath.with_suffix("").parts[-3:]),
            "width": data["data"].shape[1],
            "height": data["data"].shape[0],
            "thumbnail": str(thumbnail_path),
            "length": length,
            "length_km_rounded": round(length / 1000, 1),
            "max_depth": round(data.depth.max().item(), 2),
            "max_time": round(data["return-time"].max().item(), 2),
            "antenna": data.attrs["antenna"],
            "depth_resolution_m": round(float(np.diff(data.depth.values[-2:])[0]), 3),
            "trace_resolution_s": round(float(np.median(np.diff(data.time.values))), 3),
            "interval_indicators": interval_indicators,
            "average_speed": speed,
            "bounds": {
                "minlat": track.bounds[1],
                "maxlat": track.bounds[3],
                "minlon": track.bounds[0],
                "maxlon": track.bounds[2],
            },
            "track": shapely.geometry.mapping(track),
            "tiles": tiles,
        }
        # for key in meta:
        #     if key not in ["track", "tiles"]:
        #         print(key, meta[key])
        # raise NotImplementedError()

        meta_cache_path.parent.mkdir(exist_ok=True, parents=True)
        meta_cache_path.write_text(json.dumps(meta, indent=2))
        return meta


def parse_all_radargrams(progress: bool = False):
    radargrams = {}
    for glacier_dir in tqdm.tqdm(list(Path("processed_radar").glob("*")), disable=(not progress)):
        if not glacier_dir.is_dir():
            continue
        radargrams[glacier_dir.stem] = {}
        for filepath in glacier_dir.rglob("*.nc"):
            radargram = parse_radargram(filepath)
            radargrams[glacier_dir.stem][radargram["radar_key"]] = radargram

    return radargrams
    

if __name__ == "__main__":
    # parse_radargram(Path("./processed_radar/amenfonna/20240507/DAT_0042_A1.nc"), override_cache=True)
    # parse_radargram(Path("./processed_radar/ragna_mariebreen/20230305/DAT_0050_A1_6.nc"), override_cache=True)
    parse_radargram(Path("./processed_radar/bergmesterbreen/20230222/DAT_0033_A1_3.nc"), override_cache=True)
