from pathlib import Path
import matplotlib.pyplot as plt
import numpy as np
import PIL.Image
import math

def load_tile(radar_key, yoff, xoff):
    """Load a tile based on its offset."""
    glacier, date_str, filename = radar_key.split("-")
    tile_name = Path(f"static/radargrams/{glacier}/{date_str}/{filename}/tiles/abslog/tile_{str(xoff).zfill(5)}_{str(yoff).zfill(5)}.jpg")

    if tile_name.is_file():
        return Image.open(tile_name)

    raise FileNotFoundError(f"Tile file not found: {tile_name}")

def sample_image(radar_key, width, height, x_left, y_top):
    """Sample an image by composing necessary tiles."""
    tile_size = 1000
    tiles_x = math.ceil((x_left + width) / tile_size)
    tiles_y = math.ceil((y_top + height) / tile_size)

    print(tiles_x, tiles_y)

    total_image = Image.new('L', (tiles_x * tile_size, tiles_y * tile_size))

    for y in range(tiles_y):
        for x in range(tiles_x):
            xoff = x * tile_size
            yoff = y * tile_size
            try:
                tile = load_tile(radar_key, yoff, xoff)
                total_image.paste(tile, (xoff, yoff))
            except FileNotFoundError:
                pass  # Ignore missing tiles, or handle as needed

    return total_image
    # Crop to the requested area
    cropped_image = total_image.crop((x_left, y_top, x_left + width, y_top + height))
    return cropped_image

def main():

    width = 1920
    height = 1080
    tile_size = 1000
    images = {
        "kroppbreen_cold_bed": {
            "radar-key": "kroppbreen-20230228-DAT_0042_A1_1",
            "xmin": 10500,
            "ymin": 50,
            "scale": 1.
        },
        "filantropbreen_double_bed": {
            "radar-key": "filantropbreen-20240406-DAT_0372_A1_1",
            "xmin": 620,
            "ymin": 120,
            "scale": 1.2,
        },
        "ragnamariebreen_no_bed": {
            "radar-key": "ragna_mariebreen-20240405-DAT_0359_A1_1",
            "xmin": 2000,
            "ymin": 60,
            "scale": 1.,
        },
        "dronbreen_temperate_ice": {
            "radar-key": "dronbreen-20230220-DAT_0009_A1_1",
            "xmin": 700,
            "ymin": 30,
            "scale": 1.15,
        },
        "bergmesterbreen_temperate_bed": {
            "radar-key": "bergmesterbreen-20230222-DAT_0033_A1_3",
            "xmin": 3200,
            "ymin": 50,
            "scale": 1.,
        },
        "dronbreen_cold_bed": {
            "radar-key": "dronbreen-20240209-DAT_0462_A1_1",
            "xmin": 0,
            "ymin": 30,
            "scale": 1.
        },
    }

    for image_name, props in images.items():
        glacier, date_str, filename = props["radar-key"].split("-")

        tiles_x = math.ceil((props["xmin"] + width * props["scale"]) / tile_size)
        tiles_y = math.ceil((props["ymin"] + height * props["scale"]) / tile_size)

        img = np.zeros((tiles_y * tile_size, tiles_x * tile_size), dtype="uint8")

        for i in range(tiles_y):
            row = i * tile_size
            for j in range(tiles_x):
                col = j * tile_size
                tile_name = Path(f"static/radargrams/{glacier}/{date_str}/{filename}/tiles/abslog/tile_{str(row).zfill(5)}_{str(col).zfill(5)}.jpg")
                if not tile_name.is_file():
                    raise ValueError(f"{image_name} requires {tile_name} but it does not exist.")

                tile = plt.imread(tile_name)
                img[row:row + tile.shape[0], col:col + tile.shape[1]] = tile


                
        img = img[props["ymin"]:props["ymin"] + int(height * props["scale"]), props["xmin"]:props["xmin"] + int(width * props["scale"])]

        img = np.clip((img * (235 / 255) + 20), 0, 255).astype("uint8")

        img = PIL.Image.fromarray(img)
        if props["scale"] != 1.:
            img = img.resize((width, height), PIL.Image.Resampling.LANCZOS)

        img.save(f"static/images/examples/{image_name}.jpg")

        plt.title(image_name)
        plt.imshow(img, cmap="Greys_r")
        plt.show()
        plt.close()
        # return
if __name__ == "__main__":
    main()
        
