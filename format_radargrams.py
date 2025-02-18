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

def normalize(data: np.ndarray):

    butter = scipy.signal.butter(4,[0.08, 0.999], "bandpass", output="sos")
    data = scipy.signal.sosfilt(butter, data, axis=0)

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

def parse_radargram(src_filepath: Path, chunksize: int = 1000):
    src_filepath = Path(src_filepath)

    cache_dir = (Path("static/radargrams/") / "/".join(src_filepath.parts[-3:])).with_suffix("")

    with xr.open_dataset(src_filepath) as data:

        # vals = normalize(data["data"].values)
        # plt.hist(vals, bins=100)
        # plt.show()

        # plt.figure(figsize=(12, 6))
        # plt.imshow(vals, cmap="Grays")
        # plt.show()
        # return

        # distances = np.arange(0, data.attrs["total-distance"].item(), 5)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            x_inds = scipy.interpolate.interp1d(data["distance"].values, np.arange(data["data"].shape[1]))(np.r_[np.arange(0, data["distance"].values.max(), step=5), [data["distance"].max().item()]])
            x_inds = np.clip(np.where(np.isfinite(x_inds), x_inds, 0), 0, data["data"].shape[1] - 1).astype(int)

        track = gpd.points_from_xy(data["easting"].isel(x=x_inds), data["northing"].isel(x=x_inds), crs=data.attrs["crs"]).to_crs(4326)

        track = shapely.geometry.LineString(track)

        images: dict[str, np.ndarray] | None = None
        # image = normalize(data["data"].values)
        tiles = []
        for row in range(0, data["data"].shape[0], chunksize):
            row_slice = slice(row, min(row + chunksize, data["data"].shape[0]))
            for col in range(0, data["data"].shape[1], chunksize):
                col_slice = slice(col, min(col + chunksize, data["data"].shape[1]))

                filepaths = {}
                for key in ["abslog", "classic"]:
                    filepath = cache_dir / f"tiles/{key}/tile_{str(row).zfill(5)}_{str(col).zfill(5)}.jpg"

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

        thumbnail_path = cache_dir / "thumbnail.jpg"

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

        meta = {
            "radar_key": "-".join(src_filepath.with_suffix("").parts[-3:]),
            "width": data["data"].shape[1],
            "height": data["data"].shape[0],
            "thumbnail": str(thumbnail_path),
            "track": shapely.geometry.mapping(track),
            "length": data.attrs["total-distance"],
            "length_km_rounded": round(data.attrs["total-distance"] / 1000, 1),
            "bounds": {
                "minlat": track.bounds[1],
                "maxlat": track.bounds[3],
                "minlon": track.bounds[0],
                "maxlon": track.bounds[2],
            },
            "max_depth": data.depth.max().item(),
            "tiles": tiles,
        }
        return meta

def parse_all_radargrams():
    radargrams = {}
    for filepath in Path("processed_radar").rglob("*.nc"):
        radargram = parse_radargram(filepath)

        radargrams[radargram["radar_key"]] = radargram

    return radargrams
    

if __name__ == "__main__":
    parse_radargram(Path("./processed_radar/amenfonna/20240507/DAT_0042_A1.nc"))
