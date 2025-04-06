import pandas as pd
import numpy as np
import rasterio as rio
import matplotlib.pyplot as plt
import requests
import zipfile
import geopandas as gpd


from pathlib import Path
import os
import shutil

def nmad(values):
    return 1.426 * np.median(np.abs(values - np.median(values)))

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
    out_path = Path("cache/thickness/vanpelt/vanpelt_thickness.tif")
    url = "https://zenodo.org/records/11239460/files/Thickness_map.tif?download=1"

    download_large_file(out_path, url)
    return out_path


def get_furst() -> Path:

    out_path = Path("cache/thickness/furst/furst_thickness.vrt")

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


    out_path = Path("cache/thickness/millan/millan_thickness.tif")
    url = "https://cluster.klima.uni-bremen.de/~oggm/velocities/millan22/thickness/RGI-7/THICKNESS_RGI-7.1_2021July09.tif"

    download_large_file(out_path, url)

    return out_path



def get_farinotti() -> Path:

    out_path = Path("cache/thickness/farinotti/farinotti_thickness.vrt")


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

    out_path = Path("cache/thickness/glathida/glathida_pts.feather")

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



def compare_glathida():
    data = gpd.read_file(Path("cache/interpretations/quick_interp_all.gpkg"))
    data = data[data["kind"].str.contains("bed_") & (data["kind"] != "bed_missing")]

    glathida = get_glathida()

    import scipy.spatial

    tree = scipy.spatial.KDTree(np.transpose([glathida.geometry.x, glathida.geometry.y]))

    distances, indices = tree.query(data[["easting", "northing"]])

    distance_mask = distances < 50

    data = data[distance_mask]

    data["glathida_thickness"] = glathida["THICKNESS"].values[indices[distance_mask]]
    data["glathida_date"] = glathida["SURVEY_DATE"].values[indices[distance_mask]]

    data["glathida_year"] = data["glathida_date"].astype(str).str.slice(0, 4).astype(int)
    data["glathida_diff"] = data["glathida_thickness"] - data["depth"]

    # data["glathida_group"] = 
    year_intervals = [1990, 2010, 2025]
    markers = ["x", "s", "o"]

    data["glathida_group"] = np.digitize(data["glathida_year"], year_intervals)

    plt.figure(figsize=(5, 5))
    for i, group in data.groupby("glathida_group"):

        stats = f"(n={group.shape[0]}, ΔT: {group['glathida_diff'].median():.1f}±{nmad(group['glathida_diff']):.1f} m)"

        if i == 0:
            label = f"<={year_intervals[0]} {stats}"
        else:
            label = f"{year_intervals[i - 1]}-{year_intervals[i]} {stats}"
        plt.scatter(group["depth"], group["glathida_thickness"], label=label, marker=markers[i])

    max_thickness = data[["glathida_thickness", "depth"]].max().max()

    plt.ylabel("GlaThiDa thickness (m)")
    plt.xlabel("Our thickness (m)")

    plt.plot([0, max_thickness], [0, max_thickness], color="black")
    plt.legend()
    plt.tight_layout()
    Path("figures/").mkdir(exist_ok=True)
    plt.savefig("figures/depth_vs_glathida.jpg", dpi=400)
    plt.show()


def sample_models():

    out_path = Path("cache/interpretations/quick_interp_thickness_sampled.gpkg")

    if out_path.is_file():
        return gpd.read_file(out_path)

    data = gpd.read_file(Path("cache/interpretations/quick_interp_all.gpkg"))
    data = data[data["kind"].str.contains("bed_") & (data["kind"] != "bed_missing")]

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




def compare_models():

    data = sample_models()

    models = [str(col).replace("_thickness", "") for col in data if "_thickness" in col]

    ref_names = {
        "millan": "Millan et al., (2019)",
        "furst": "Fürst et al., (2018)",
        "farinotti": "Farinotti et al., (2019)",
        "vanpelt": "van Pelt & Frank (2025)",

    }


    fig = plt.figure(figsize=(7, 7))
    axes = fig.subplots(nrows=2, ncols=2, sharex=True, sharey=True)

    max_thickness = data[["depth", *[f"{model}_thickness" for model in models]]].max().max()

    step_size = 7.5
    thickness_bins = np.arange(0, max_thickness - (max_thickness % step_size) + step_size * 2, step_size)

    for i, model in enumerate(models):
        col = i % 2
        row = int((i - col) / 2)
        axis: plt.Axes = axes[row, col]

        hist2 = np.histogram2d(data[f"{model}_thickness"],data["depth"], bins=thickness_bins)[0][::-1, :]
        hist2 = np.ma.masked_array(hist2, mask=hist2 < 2)

        axis.set_title(ref_names[model])
        axis.imshow(hist2, extent=(0., thickness_bins[-1], 0., thickness_bins[-1]))

        xlim = axis.get_ylim()
        axis.plot([xlim[0], xlim[1]], [xlim[0], xlim[1]], color="black")

        diff = data[f"{model}_thickness"] - data["depth"]

        axis.text(x=0.05, y=0.95, s="\n".join(
                [
                    f"Median: {diff.median():.1f} m", 
                    f"NMAD: {1.426 * np.median(np.abs(diff - np.median(diff))): .1f} m",
                    f"r = {data['depth'].corr(data[f'{model}_thickness']):.2f}", 

                ]
            ),
            transform=axis.transAxes,
            va="top",
        )

        if row == 1:
            axis.set_xlabel("Measured thickness (m)")

        if col == 0:
            axis.set_ylabel("Modelled thickness (m)")


    plt.tight_layout()
        
    Path("figures/").mkdir(exist_ok=True)
    plt.savefig("figures/depth_vs_models.jpg", dpi=400)
    plt.show()

