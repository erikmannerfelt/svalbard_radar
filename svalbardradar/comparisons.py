import os
import shutil
import zipfile
import tarfile
from pathlib import Path

import geopandas as gpd
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import rasterio as rio
import requests
import scipy.spatial

from svalbardradar.tools import paths, misc

CACHE_PATH = paths.BASE_CACHE_PATH / "comparisons"


STANDARD_YEAR = 2015



def get_vanpelt() -> Path:
    out_path = CACHE_PATH / "vanpelt/vanpelt_thickness.tif"
    url = "https://zenodo.org/records/11239460/files/Thickness_map.tif?download=1"

    misc.download_large_file(out_path, url)
    return out_path


def get_furst() -> Path:
    out_path = CACHE_PATH / "furst/furst_thickness.vrt"

    if out_path.is_file():
        return out_path

    tar_path = out_path.with_name("svift_v11.tar.gz")
    url = "https://next.api.npolar.no/dataset/57fd0db4-afbf-4c94-ac1c-191c714f1224/attachment/ec2d911f-97c6-4d78-8602-7539b97470a6/_blob"

    misc.download_large_file(tar_path, url)

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

    misc.download_large_file(out_path, url)

    return out_path


def get_farinotti() -> Path:
    out_path = CACHE_PATH / "farinotti/farinotti_thickness.vrt"

    if out_path.is_file():
        return out_path

    from osgeo import gdal

    zip_path = out_path.parent / "composite_thickness_RGI60-07.zip"
    url = "https://www.research-collection.ethz.ch/server/api/core/bitstreams/e855deb2-a2b3-47f1-8d2a-7ffc5c1a52dd/content"

    misc.download_large_file(zip_path, url)

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

            warp_path = warped_vrt_dir / entry.filename.split("/")[-1].replace(
                ".tif", ".vrt"
            )
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


def get_frank() -> Path:
    out_path = CACHE_PATH / "frank/frank_thickness.vrt"

    if out_path.is_file():
        return out_path

    from osgeo import gdal

    zip_path = Path("cache/comparisons/frank/RGI-07_thk.zip")

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

            warp_path = warped_vrt_dir / entry.filename.split("/")[-1].replace(
                ".tif", ".vrt"
            )
            gdal.Warp(
                str(warp_path.absolute()),
                vsi_path,
                format="VRT",
                dstSRS="EPSG:32633",
                srcNodata=0,
            )

            filepaths.append(warp_path)

            # filepaths_per_crs.append(vsi_path)

    gdal.BuildVRT(
        out_path.absolute(),
        filepaths,
        srcNodata=0,
    )
    return out_path

def get_hugonnet() -> Path:
    out_path = CACHE_PATH / "hugonnet/hugonnet_dhdt_2000-2020.vrt"
    if out_path.is_file():
        return out_path
    from osgeo import gdal
    gdal.UseExceptions()
    # url = "https://cluster.klima.uni-bremen.de/~oggm/velocities/millan22/thickness/RGI-7/THICKNESS_RGI-7.1_2021July09.tif"
    # url = "https://api.sedoo.fr/sedoo-glaciers-rest/data/v1_0/download/277e8d22-01c2-4617-89fc-53e4803573bc"
    url = "https://cluster.klima.uni-bremen.de/~oggm/geodetic_ref_mb_maps/07_rgi60_2000-01-01_2020-01-01.tar"

    # tar_path = out_path.parent / "07_rgi60_2000-01-01_2020-01-01.tar"
    tar_path = out_path.parent / url.split("/")[-1]
    misc.download_large_file(tar_path, url)

    warped_vrt_dir = out_path.parent / "warped"
    warped_vrt_dir.mkdir(exist_ok=True, parents=True)
    filepaths = []
    with tarfile.open(tar_path) as tar_file:

        for filename in tar_file.getnames():
            if "dhdt.tif" not in filename:
                continue

            vsi_path = f"/vsitar/{tar_path.absolute()}/{filename}"
            with rio.open(vsi_path) as raster:
                crs_epsg = raster.crs.to_epsg()

            if crs_epsg == 32633:
                filepaths.append(vsi_path)
                continue

            warp_path = warped_vrt_dir / filename.split("/")[-1].replace(
                ".tif", ".vrt"
            )
            gdal.Warp(
                str(warp_path.absolute()),
                vsi_path,
                format="VRT",
                dstSRS="EPSG:32633",
            )

            filepaths.append(warp_path)

    
    gdal.BuildVRT(
        out_path.absolute(),
        filepaths,
    )

    return out_path

def get_geyman() -> Path:
    out_path = CACHE_PATH / "geyman/geyman_dh_1936-2010.tif"
    if out_path.is_file():
        return out_path
    url = "https://next.api.npolar.no/dataset/f6afca5c-6c95-4345-9e52-cfe2f24c7078/attachment/678a2b36-0c6f-4eef-a207-7f56d6632c66/_blob"

    misc.download_large_file(out_path, url)
    return out_path
    


def get_glathida():
    out_path = CACHE_PATH / "glathida/glathida_pts.feather"

    if out_path.is_file():
        return gpd.read_feather(out_path)

    zip_path = out_path.parent / "glathida.zip"
    # url = "https://gitlab.com/wgms/glathida/-/archive/main/glathida-main.zip"
    url = "https://gitlab.com/wgms/glathida/-/archive/15fd559c84f849637522b8e21e316db958620c08/glathida-15fd559c84f849637522b8e21e316db958620c08.zip"

    misc.download_large_file(zip_path, url)

    data = pd.DataFrame()
    with zipfile.ZipFile(zip_path) as zip_file:
        for entry in zip_file.filelist:
            if "point.csv" not in entry.filename:
                continue
            with zip_file.open(entry.filename) as infile:
                data = pd.concat([data, pd.read_csv(infile, low_memory=False)], ignore_index=True).convert_dtypes()

    west = 9
    east = 29
    south = 76

    data = data[data["latitude"] > south]
    data = data[(data["longitude"] > west) & (data["longitude"] < east)]

    for col in ["profile_id", "point_id"]:
        data[col] = data[col].astype(str)
    data = gpd.GeoDataFrame(
        data,
        geometry=gpd.points_from_xy(data["longitude"], data["latitude"], crs=4326),
    ).to_crs(32633)

    data.to_feather(out_path)
    return gpd.read_feather(out_path)


def sample_glathida() -> pd.DataFrame:
    import svalbardradar.interpretations

    data = svalbardradar.interpretations.merge_all_interpretations()
    glathida = get_glathida()

    tree = scipy.spatial.KDTree(
        np.transpose([glathida.geometry.x, glathida.geometry.y])
    )

    distances, indices = tree.query(data[["easting", "northing"]])

    distance_mask = distances < 50

    data = data[distance_mask]
    data["glathida_thickness_uncorr"] = glathida["thickness"].values[indices[distance_mask]]
    data["glathida_date"] = glathida["date"].values[indices[distance_mask]]
    with rio.open(get_hugonnet()) as raster:
        arr = np.fromiter(
            raster.sample(data[["easting", "northing"]].values),
            dtype=raster.dtypes[0],
            count=data.shape[0],
        )
        data["hugonnet_dhdt"] = arr

    data["year"] = data["date_str"].str.slice(0, 4).astype(int)
    data["dt"] = data["year"] - STANDARD_YEAR

    data.rename(columns={"thickness": "thickness_uncorr"}, inplace=True)
    data["thickness"] = data["thickness_uncorr"] - (data["dt"] * data["hugonnet_dhdt"])

    data["glathida_year"] = (
        data["glathida_date"].astype(str).str.slice(0, 4).astype(int)
    )
    data["glathida_dt"] = data["glathida_year"] - STANDARD_YEAR
    data["glathida_thickness"] = data["glathida_thickness_uncorr"] - (data["glathida_dt"] * data["hugonnet_dhdt"])
    data["glathida_diff"] = data["glathida_thickness"] - data["thickness"]

    return data


def sample_models(overwrite_cache: bool = False):
    import svalbardradar.interpretations

    out_path = CACHE_PATH / "interp_thickness_sampled.feather"

    if out_path.is_file() and not overwrite_cache:
        return gpd.read_feather(out_path)

    # data = gpd.read_file(Path("cache/interpretations/quick_interp_all.gpkg"))
    data = svalbardradar.interpretations.merge_all_interpretations()
    # data = data[data["kind"].str.contains("bed_") & (data["kind"] != "bed_missing")]

    model_paths = {
        "farinotti": get_farinotti(),
        "furst": get_furst(),
        "millan": get_millan(),
        "vanpelt": get_vanpelt(),
        # "frank": get_frank(),
    }

    with rio.open(get_hugonnet()) as raster:
        data["hugonnet_dhdt"] =  np.fromiter(
            raster.sample(data[["easting", "northing"]].values),
            dtype=raster.dtypes[0],
            count=data.shape[0],
        )
        

    for key in model_paths:
        with rio.open(model_paths[key]) as raster:
            arr = np.fromiter(
                raster.sample(data[["easting", "northing"]].values),
                dtype=raster.dtypes[0],
                count=data.shape[0],
            )
            # There seem to be extreme outliers now and then.
            arr[(arr < 0) | (arr > 1000)] = np.nan

            data[f"{key}_thickness"] = arr

    data = data.dropna(subset=[f"{key}_thickness" for key in model_paths], how="all")

    data = data[data["date_str"] != "nan"]

    data["year"] = data["date_str"].str.slice(0, 4).astype(int)
    data["dt"] = data["year"] - STANDARD_YEAR

    data.rename(columns={"thickness": "thickness_uncorr"}, inplace=True)
    data["thickness"] = data["thickness_uncorr"] - (data["dt"] * data["hugonnet_dhdt"])

    data.to_feather(out_path)
    return gpd.read_feather(out_path)


def sample_for_karlijn(overwrite_cache: bool = False):

    model_cmps = sample_models()
    glathida_cmps = sample_glathida()

    for df in [model_cmps, glathida_cmps]:
        df["glacier"] = df["radar_key"].str.split("-", expand=True).iloc[:, 0]

    Path("temp/").mkdir(exist_ok=True)
    model_cmps.to_csv("temp/karlijn_model_cmps.csv")
    glathida_cmps.to_csv("temp/karlijn_glathida_cmps.csv")

