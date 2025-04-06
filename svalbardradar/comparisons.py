import pandas as pd
import numpy as np
import rasterio as rio
import matplotlib.pyplot as plt
import requests
import zipfile
import geopandas as gpd
import scipy.spatial

from pathlib import Path
import os
import shutil

from svalbardradar.tools import paths

CACHE_PATH = paths.BASE_CACHE_PATH / "comparisons"

def download_large_file(output_filepath: Path, url: str):

    temp_path =output_filepath.with_suffix(f".{output_filepath.suffix}.part")
    if temp_path.is_file():
        os.remove(temp_path)

    if output_filepath.is_file():
        return

    with requests.get(url, stream=True) as response:
        response.raise_for_status()


        temp_path.parent.mkdir(exist_ok=True, parents=True)
        
        with open(temp_path, "wb") as outfile:
            for chunk in response.iter_content(chunk_size=8192 * 4):
                outfile.write(chunk)
        

        shutil.move(temp_path,output_filepath)

def get_vanpelt() -> Path:
    out_path = CACHE_PATH / "vanpelt/vanpelt_thickness.tif"
    url = "https://zenodo.org/records/11239460/files/Thickness_map.tif?download=1"

    download_large_file(out_path, url)
    return out_path


def get_furst() -> Path:

    out_path = CACHE_PATH / "furst/furst_thickness.vrt"

    if out_path.is_file():
        return out_path

    tar_path = out_path.with_name("svift_v11.tar.gz")
    url = "https://next.api.npolar.no/dataset/57fd0db4-afbf-4c94-ac1c-191c714f1224/attachment/ec2d911f-97c6-4d78-8602-7539b97470a6/_blob"

    download_large_file(tar_path, url)

    from osgeo import gdal
    gdal.UseExceptions()
    gdal.BuildVRT(
        out_path.absolute(),
        f"/vsitar/{tar_path.absolute()}/svift_v11/svift_v11_thickness.nc",
    )

    return out_path


def get_millan() -> Path:


    out_path = CACHE_PATH / "millan/millan_thickness.tif"
    url = "https://cluster.klima.uni-bremen.de/~oggm/velocities/millan22/thickness/RGI-7/THICKNESS_RGI-7.1_2021July09.tif"

    download_large_file(out_path, url)

    return out_path



def get_farinotti() -> Path:

    out_path = CACHE_PATH / "farinotti/farinotti_thickness.vrt"


    if out_path.is_file():
        return out_path

    from osgeo import gdal

    zip_path = out_path.parent / "composite_thickness_RGI60-07.zip"
    url = "https://www.research-collection.ethz.ch/bitstream/handle/20.500.11850/315707/composite_thickness_RGI60-07.zip?sequence=9&isAllowed=y"

    download_large_file(zip_path, url)

    warped_vrt_dir = out_path.parent / "warped"
    warped_vrt_dir.mkdir(exist_ok=True, parents=True)

    gdal.UseExceptions()

    filepaths = []
    with zipfile.ZipFile(zip_path) as zip_file:
        for entry in zip_file.filelist:
            if not entry.filename.endswith(".tif"):
                continue


            vsi_path = f"/vsizip/{zip_path.absolute()}/{entry.filename}"

            with rio.open(vsi_path) as raster:
                crs_epsg = raster.crs.to_epsg()

            if crs_epsg == 32633:
                filepaths.append(vsi_path)
                continue
            
            warp_path =warped_vrt_dir / entry.filename.split("/")[-1].replace(".tif", ".vrt")
            gdal.Warp(
                str(warp_path.absolute()),
                vsi_path,
                format="VRT",
                dstSRS="EPSG:32633",
            )

            filepaths.append(warp_path)

            # filepaths_per_crs.append(vsi_path)


    gdal.BuildVRT(
        out_path.absolute(),
        filepaths,
        srcNodata=0,
    )
    return out_path
    

def get_glathida():

    out_path = CACHE_PATH / "glathida/glathida_pts.feather"

    read_func = gpd.read_file if "feather" not in out_path.suffix else gpd.read_feather

    if out_path.is_file():
        return read_func(out_path)

    zip_path = out_path.parent / "glathida-3.1.0.zip"

    url = f"https://www.gtn-g.ch/database/{zip_path.name}"

    download_large_file(zip_path, url)

    west = 9
    east = 29
    south = 76

    with zipfile.ZipFile(zip_path) as zip_file:
        with zip_file.open("glathida-3.1.0/data/TTT.csv") as infile:
            data = pd.read_csv(infile)

    data = data[data["POINT_LAT"] > south]
    data = data[(data["POINT_LON"] > west) & (data["POINT_LON"] < east)]

    data = data.convert_dtypes()

    data["POINT_ID"] = data["POINT_ID"].astype(str)
    # data = pd.read_csv(f"zip:/{zip_path}/glathida-3.1.0/data/TTT.csv")
    #
    data = gpd.GeoDataFrame(data, geometry=gpd.points_from_xy(data["POINT_LON"], data["POINT_LAT"], crs=4326)).to_crs(32633)


    if "feather" in out_path.suffix:
        data.to_feather(out_path)
    else:
        data.to_file(out_path)

    return read_func(out_path)

def sample_glathida():
    import svalbardradar.interpretations

    data = svalbardradar.interpretations.merge_all_interpretations()
    glathida = get_glathida()

    tree = scipy.spatial.KDTree(np.transpose([glathida.geometry.x, glathida.geometry.y]))

    distances, indices = tree.query(data[["easting", "northing"]])

    distance_mask = distances < 50

    data = data[distance_mask]
    data["glathida_thickness"] = glathida["THICKNESS"].values[indices[distance_mask]]
    data["glathida_date"] = glathida["SURVEY_DATE"].values[indices[distance_mask]]

    data["glathida_year"] = data["glathida_date"].astype(str).str.slice(0, 4).astype(int)
    data["glathida_diff"] = data["glathida_thickness"] - data["thickness"]

    return data

    

def sample_models():
    import svalbardradar.interpretations

    out_path = CACHE_PATH / "interp_thickness_sampled.gpkg"

    if out_path.is_file():
        return gpd.read_file(out_path)

    # data = gpd.read_file(Path("cache/interpretations/quick_interp_all.gpkg"))
    data = svalbardradar.interpretations.merge_all_interpretations()
    # data = data[data["kind"].str.contains("bed_") & (data["kind"] != "bed_missing")]

    model_paths = {
        "farinotti": get_farinotti(),
        "furst": get_furst(),
        "millan": get_millan(),
        "vanpelt": get_vanpelt(),
    }

    for key in model_paths:

        with rio.open(model_paths[key]) as raster:
            data[f"{key}_thickness"] = np.fromiter(raster.sample(data[["easting", "northing"]].values), dtype=raster.dtypes[0], count=data.shape[0])

    data = data.dropna(subset=[f"{key}_thickness" for key in model_paths], how="all")

    data.to_file(out_path)
    return gpd.read_file(out_path)
