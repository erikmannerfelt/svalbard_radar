import xarray as xr
import matplotlib.pyplot as plt
from pathlib import Path
import numpy as np
from PIL import Image

def normalize(data: np.ndarray):

    minval, maxval = np.percentile(data, [1, 99])

    data = np.clip((data - minval) / (maxval - minval), 0, 1)
    return (data * 255).astype("uint8")

def main(chunksize: int = 1000):

    src_filepath = Path("./processed_radar/amenfonna/20240507/DAT_0042_A1.nc")

    cache_dir = (Path("static/radargrams/") / "/".join(src_filepath.parts[-3:])).with_suffix("")

    with xr.open_dataset(src_filepath) as data:

        image: np.ndarray | None = None
        # image = normalize(data["data"].values)
        tiles = []
        for row in range(0, data["data"].shape[0], chunksize):
            row_slice = slice(row, min(row + chunksize, data["data"].shape[0]))
            for col in range(0, data["data"].shape[1], chunksize):
                col_slice = slice(col, min(col + chunksize, data["data"].shape[1]))
                filepath = cache_dir / f"tiles/tile_{str(row).zfill(5)}_{str(col).zfill(5)}.jpg"

                if not filepath.is_file():
                    if image is None:
                        image = normalize(data["data"].values)
                    tile_arr = image[row_slice, col_slice]
                    filepath.parent.mkdir(exist_ok=True, parents=True)

                    Image.fromarray(tile_arr).save(filepath)

                tiles.append({
                    "filepath": "/" + str(filepath),
                    "minx": col,
                    "maxx": col_slice.stop,
                    "miny": data["data"].shape[0] - row_slice.stop,
                    "maxy": data["data"].shape[0] - row,
                })

        thumbnail_path = cache_dir / "thumbnail.jpg"

        if not thumbnail_path.is_file():
            if image is None:
                image = normalize(data["data"].values)

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
            "tiles": tiles,
        }

        return meta

if __name__ == "__main__":
    main()
