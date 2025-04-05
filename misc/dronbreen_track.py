from pathlib import Path

import geopandas as gpd
import pandas as pd
import xarray as xr
import numpy as np
import matplotlib.pyplot as plt
import shapely

def main():

    lines = []
    for filepath in Path("processed_radar/").rglob("*.nc"):
        if filepath.parts[-3] not in ["dronbreen"]:
            continue

        with xr.open_dataset(filepath) as data:

            parts = np.cumsum(np.r_[[0], (data["distance"].diff("x") > 100).astype(int).values])

            for i in np.unique(parts):
                mask = parts == i

                points = gpd.points_from_xy(data["easting"].values[mask], data["northing"].values[mask], crs=data.attrs["crs"]).to_crs(32633)

                if points.shape[0] < 2:
                    continue

                lines.append(
                    {
                        "filename": filepath.stem,
                        "antenna": data.attrs["antenna"],
                        "date": filepath.parts[-2],
                        "geometry": shapely.geometry.LineString(points),
                })


    lines = pd.DataFrame.from_records(lines)

    lines = gpd.GeoDataFrame(lines.drop(columns="geometry"), geometry=lines["geometry"], crs=32633)

    lines.to_file("temp/dronbreen_tracks.geojson")

                


if __name__ == "__main__":
    main()
