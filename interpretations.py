
from pathlib import Path
import warnings
import pandas as pd
import json
import geopandas as gpd
import io
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.patheffects
import xarray as xr
import scipy.interpolate
import tqdm
import geopandas as gpd
import scipy.spatial

import sklearn.gaussian_process

def main(step_size: float = 30., outlier_threshold: float = 200., cold_model_strength: float = 100.):

    out_path = Path("cache/interpretations/interp_all.feather")

    # if out_path.is_file():
    #     return gpd.read_feather(out_path)

    interpretations = {}

    for per_user_dir in Path("submitted/").glob("*"):
        if not per_user_dir.is_dir():
            continue
        for per_radar_dir in per_user_dir.glob("*"):
            if not per_radar_dir.is_dir():
                continue
            radar_key = per_radar_dir.stem
            if radar_key not in interpretations:
                interpretations[radar_key] = []

            latest = sorted(per_radar_dir.glob("*.json"))[-1]
            interpretations[radar_key].append(latest)

            
    # for interp_path in Path("submitted").rglob("*.json"):

    #     radar_key = interp_path.name.rsplit("-", 1)[0].replace("digitized-", "")
    #     if radar_key not in interpretations:
    #         interpretations[radar_key] = []

    #     interpretations[radar_key].append(interp_path)

    # radar_keys = ["ragna_mariebreen-20230305-DAT_0068_A1_3", "filantropbreen-20240406-DAT_0373_A1_1", "ragna_mariebreen-20240412-DAT_0404_A1_1"][::-1]

    all_data = []
    for radar_key in tqdm.tqdm(interpretations):

        glacier, date_str, file_stem = radar_key.split("-")
        filepath = Path(f"processed_radar/{glacier}/{date_str}/{file_stem}.nc")
        if not filepath.is_file():
            continue

        cache_path = out_path.parent / f"per_radargram/{radar_key}.feather"
        cache_path.parent.mkdir(exist_ok=True, parents=True)

        if cache_path.is_file():
            all_data.append(gpd.read_feather(cache_path))
            continue

        data = pd.DataFrame()
        colors = {}
        interp_paths =interpretations[radar_key]

        for interp_path in interp_paths:
            interp = json.loads(interp_path.read_text())

            # if len(interp["features"]["features"]) < 2:
            #     continue

            new_data = gpd.read_file(io.StringIO(json.dumps(interp["features"])))

            if "kind" not in new_data:
                new_data["kind"] = new_data["name"].apply(lambda s: {"Glacier bed": "bed_unspecified", "Cold glacier bed": "bed_cold", "Temperate ice": "temperate_ice"}[s])

            for kind, kind_data in new_data.groupby("kind"):
                for _, row in kind_data.iterrows():
                    if kind not in colors:
                        colors[kind] = row["color"]
                    for distance in np.arange(0, row.geometry.length + step_size, step_size):
                        point = row.geometry.interpolate(distance) 

                        out_data = {"kind": kind, "x": point.x, "y": point.y}

                        data.loc[data.shape[0], list(out_data.keys())] = list(out_data.values())

        if data.shape[0] == 0:
            continue



        with xr.open_dataset(filepath) as dataset:

            depth_model = scipy.interpolate.interp1d(np.arange(dataset["data"].shape[0])[::-1], dataset["depth"].values, bounds_error=False)

            models = {key: scipy.interpolate.interp1d(np.arange(dataset["data"].shape[1]), dataset[key].values, bounds_error=False) for key in ["easting", "northing", "distance", "elevation"]}
            antenna = dataset.attrs["antenna"].split("MHz")[0] + "MHz"
            crs = dataset.attrs["crs"]

        data["depth"] = depth_model(data["y"].astype(float))

        for key in models:
            data[key] = models[key](data["x"].astype(float))

        data = data.dropna(subset=["depth", "easting"])
        # return
        # for kind, kind_data in data.groupby("kind"):
        #     plt.scatter(kind_data["distance"], -kind_data["depth"], color=colors[kind], marker="s", s=8)
        # plt.show()

        def make_gp(length_scale_bounds=(1e-2, 2e2), mean: float | None = None):
            kernel = 1 * sklearn.gaussian_process.kernels.RBF(length_scale=np.mean(length_scale_bounds), length_scale_bounds=length_scale_bounds)

            if mean is not None:
                kernel = kernel * sklearn.gaussian_process.kernels.ConstantKernel(mean)
            return sklearn.gaussian_process.GaussianProcessRegressor(
                kernel=kernel,
                n_restarts_optimizer=5,
                normalize_y=True,
                alpha=1e-3,
            )
        bed_model = make_gp()

        bed_data = data[data["kind"].isin(["bed_cold", "bed_unspecified"])]
        with warnings.catch_warnings():
            warnings.filterwarnings("ignore")
            bed_model.fit(bed_data[["x"]].values, bed_data["depth"].values)


        cold_data = data[data["kind"].isin(["bed_cold", "temperate"])].copy()


        x_eval = np.arange(0, bed_data["x"].max(), step_size)

        out = pd.DataFrame(index=x_eval)

        out["thickness"], out["thickness_std"] = bed_model.predict(x_eval[:, None], return_std=True)

        if cold_data.shape[0] > 2:
            bed_pred = bed_model.predict(cold_data[["x"]].values)
            cold_data["frac"] = np.clip((bed_pred - cold_data["depth"]) / bed_pred, 0, 1)
            temp_model = make_gp(mean=0, length_scale_bounds=(100, 1e3))
            with warnings.catch_warnings():
                warnings.filterwarnings("ignore")
                temp_model.fit(cold_data[["x"]].values, cold_data["frac"].values) 

            out["temperate_frac"], out["temperate_frac_std"] = temp_model.predict(x_eval[:, None], return_std=True)

            out["temperate_frac"] = np.clip(out["temperate_frac"], 0, 1)

        # for ext in ["", "_std"]:
        #     out[f"temperate_frac{ext}"] = np.clip((out[f"temperate{ext}"]) / out["thickness"], 0, 1)

        # plt.plot(x_eval, -out["thickness"])
        # plt.plot(x_eval, -out["temperate"])
        # plt.show()

        for col in models:
            out[col] = models[col](x_eval)

        if crs != "EPSG:32633":
            points = gpd.points_from_xy(out["easting"], out["northing"], crs=crs).to_crs(32633)
            out["easting"] = points.x
            out["northing"] = points.y

        
        out["antenna"] = antenna
        out["radar-key"] = radar_key
        out["date_str"] = date_str
        out = gpd.GeoDataFrame(out, geometry=gpd.points_from_xy(out["easting"], out["northing"], crs=32633))

        out.to_feather(cache_path)
        all_data.append(out)

        # if len(all_data) > 3:
        #     break

        continue

        fig, axes = plt.subplots(2, 1, sharex=True,height_ratios=[0.2, 0.8])

        axes[0].plot(x_eval, np.clip(-(temp_model.predict(x_eval[:, None]) / bed_model.predict(x_eval[:, None])), 0, 1))
        for name, color, model in [("temperate", "red", temp_model), ("bed", "blue", bed_model)]:
            y_pred, y_std = model.predict(x_eval[:, None], return_std=True)

            if name == "temperate":

                y_pred += bed_model.predict(x_eval[:, None])
                # cold, cold_std = np.clip(cold_model.predict(x_eval[:, None], return_std=True), 0, 1)

                # axes[0].plot(x_eval,cold)

                # y_std += cold_model_strength * cold

                # cold_pred, cold_std = model.predict(cold_data[["x"]].values, return_std=True)

                # print(cold_pred, cold_std)

            mask = y_std < outlier_threshold
            axes[1].fill_between(x_eval, y_pred - y_std, y_pred + y_std, where=mask, alpha=0.5, color=color)
            y_pred[~mask] = np.nan
            axes[1].plot(x_eval, y_pred, color=color)

        for kind, kind_data in data.groupby("kind"):
            axes[1].scatter(kind_data["x"], kind_data["y"], color=colors[kind], marker="s", s=8)

        axes[0].set_ylabel("Cold likelihood")

        plt.xlabel("Width (px)")
        plt.ylabel("Height (px)")
        plt.show()


            

        print(data)

    all_data = pd.concat(all_data)

    all_data = gpd.GeoDataFrame(all_data, geometry=gpd.points_from_xy(all_data["easting"], all_data["northing"], crs=32633))


    all_data.to_feather(out_path)

    return gpd.read_feather(out_path)



def read_interpretation(filepath: Path, step_size: int = 10):
    
    data = pd.DataFrame()
    interp = json.loads(filepath.read_text())

    new_data = gpd.read_file(io.StringIO(json.dumps(interp["features"])))

    if "kind" not in new_data:
        new_data["kind"] = new_data["name"].apply(lambda s: {"Glacier bed": "bed_unspecified"}[s])

    for kind, kind_data in new_data.groupby("kind"):
        for _, row in kind_data.iterrows():
            for distance in np.arange(0, row.geometry.length + step_size, step_size):
                point = row.geometry.interpolate(distance) 

                out_data = {"kind": kind, "color": row["color"], "x": point.x, "y": point.y}

                data.loc[data.shape[0], list(out_data.keys())] = list(out_data.values())

    return data


def quick_get_thickness():

    out_path = Path("cache/interpretations/quick_interp_all.gpkg")

    if out_path.is_file():
        return gpd.read_file(out_path)

    all_data = []
    for dirname in tqdm.tqdm(list(Path("submitted/admin/").glob("*"))):
        if not dirname.is_dir():
            continue

        latest_filepath = sorted(dirname.glob("*.json"))[-1]

        radar_key = dirname.stem
        glacier, date_str, file_stem = radar_key.split("-")

        filepath = Path(f"processed_radar/{glacier}/{date_str}/{file_stem}.nc")

        data = read_interpretation(latest_filepath, step_size=50)
        with xr.open_dataset(filepath) as dataset:

            depth_model = scipy.interpolate.interp1d(np.arange(dataset["data"].shape[0])[::-1], dataset["depth"].values, bounds_error=False)

            models = {key: scipy.interpolate.interp1d(np.arange(dataset["data"].shape[1]), dataset[key].values, bounds_error=False) for key in ["easting", "northing", "distance", "elevation"]}
            crs = dataset.attrs["crs"]
            data["antenna"] = dataset.attrs["antenna"].split("MHz")[0] + "MHz"

        data["depth"] = depth_model(data["y"].astype(float))
        for key in models:
            data[key] = models[key](data["x"].astype(float))

        data = data.dropna(subset=["depth", "easting"])

        data: gpd.GeoDataFrame = gpd.GeoDataFrame(data, geometry=gpd.points_from_xy(data["easting"], data["northing"], crs=crs))

        if "32633" not in crs:
            data = data.to_crs("EPSG:32633")
            data["easting"] = data.geometry.x
            data["northing"] = data.geometry.y

        data["radar-key"] = radar_key
        data["date_str"] = date_str

        all_data.append(data)

    all_data = pd.concat(all_data)

    out_path.parent.mkdir(exist_ok=True, parents=True)
    all_data.to_file(out_path)

    return gpd.read_file(out_path)

    

    
def sample_brp():

    datasets = [
        Path(f"processed_radar/dronbreen/20250327/DAT_00{num}_A1_1.nc") for num in [62, 63, 65, 66]
    ] + [
        Path(f"processed_radar/dronbreen/20250326/DAT_00{num}_A1_1.nc") for num in [44, 46, 50, 52, 53, 54, 58] 
    ] + [
        Path(f"processed_radar/lofthusbreen/20250326/DAT_0057_A1_1.nc")
    ]

    for filepath in datasets:
        if "DAT_0065" not in filepath.name:
            continue
        with xr.open_dataset(filepath) as data:

            trace = data.isel(x=2500)
            # plt.plot(trace["data"].rolling(y=3, center=True).mean().values)
            
            # plt.plot(trace.data.values)
            # plt.imshow(data.data.values)
            # plt.show()
            # return

    points = []

    cache_filepath = Path("temp/dronbreen_brp.gpkg")
    # outline = gpd.read_file("temp/dronbreen_outline_20240828.geojson")
    outline = gpd.read_file("temp/dronbreen_pluslofhus_outline_20240828.geojson")

    if not cache_filepath.is_file():

        for filepath in datasets:
            radar_key = "-".join(filepath.parts[-3:]).replace(".nc", "")

            interp_path = sorted(Path(f"submitted/admin/{radar_key}/").glob("*.json"))[-1]

            interp = read_interpretation(interp_path, step_size=50)

            interp = interp[interp["kind"].str.contains("bed_") & (~interp["kind"].str.contains("bed_missing"))]
            interp[["y", "x"]] = interp[["y", "x"]].astype(int)



            airwave_len = 32
            brp_window_up = 20
            brp_window_down = 100 - brp_window_up
            with xr.open_dataset(filepath) as data:
                interp["y"] = data.data.shape[0] - interp["y"]
                data["data"] = np.abs(data.data) ** 2

                airwave_sum = data["data"].isel(y=slice(0, 32)).max("y")

                for idx, point in interp.iterrows():

                    point_data = data.isel(x=point["x"])

                    brp_y_min = point["y"] - brp_window_up
                    brp_y_max = point["y"] + brp_window_down

                    if brp_y_min < (airwave_len + 2):
                        continue
                    if brp_y_max > data.data.shape[0]:
                        continue

                    interp.loc[idx, "brp_uncorr"] = point_data.data.isel(y=slice(brp_y_min, brp_y_max)).max("y").item() / airwave_sum.isel(x=point["x"]).item()
                    # interp.loc[idx, "irp_uncorr"] = point_data.data.isel(y=slice(airwave_len, brp_y_min)).sum("y").item() / airwave_sum.isel(x=point["x"]).item() 

                    interp.loc[idx, "depth"] = point_data["depth"].isel(y=point["y"]).item()

                    for key in ["easting", "northing", "elevation"]:
                        interp.loc[idx, key] = point_data[key].item()


                    # multiple_brp_y_min = point["y"] * 2 - brp_window_up
                    # multiple_brp_y_max = point["y"] * 2 + brp_window_down

                    # if multiple_brp_y_max > data.data.shape[0]:
                    #     continue
                
                    # interp.loc[idx, "brp_multiple_uncorr"] = point_data.data.isel(y=slice(multiple_brp_y_min, multiple_brp_y_max)).max("y").item() / airwave_sum.isel(x=point["x"]).item()
                


            
            points.append(interp)


        points = pd.concat(points).dropna(how="any", subset=["brp_uncorr"])

        outline_pts = pd.DataFrame()
        for _, polyg in outline.iterrows():
            polyg = polyg.geometry
            for d in np.arange(0, polyg.exterior.length, 10):
                point = polyg.exterior.interpolate(d)
                outline_pts.loc[outline_pts.shape[0], ["x", "y"]] = [point.x, point.y]


        tree = scipy.spatial.KDTree(outline_pts[["x", "y"]])

        points["margin_distance"] = tree.query(points[["easting", "northing"]])[0]

        points["terminus_distance"] = ((points["easting"] - 541821) ** 2 + (points["northing"] - 8675501) ** 2) ** 0.5

        plt.scatter(points["depth"], points["brp_uncorr"], c=points["terminus_distance"])
        pts_inside = points[points["margin_distance"] > 250]
        brp_model = np.polyfit(pts_inside["depth"], pts_inside["brp_uncorr"], deg=1)
        x_eval = np.linspace(0, points["depth"].max())
        plt.plot(x_eval, np.poly1d(brp_model)(x_eval), color="black")

        points["brp"] = points["brp_uncorr"] - points["depth"] * brp_model[0] 
        # points["brp_multiple"] = points["brp_multiple_uncorr"] - points["depth"] * brp_model[0] 
        # points["irp"] = (points["irp_uncorr"] - points["depth"] * brp_model[0]) / (points["depth"] / 10)

        points = gpd.GeoDataFrame(points, geometry=gpd.points_from_xy(points["easting"], points["northing"], crs=32633))

        points.to_file(cache_filepath)
        # plt.show()
    else:
        points = gpd.read_file(cache_filepath)

 

    fig = plt.figure(figsize=(8, 4.5))
    axes = fig.subplots(1, 2, sharex=True, sharey=True)

    axes[0].scatter( points["brp_uncorr"],points["depth"], c=points["margin_distance"], s=8)
    pts_inside = points[points["margin_distance"] > 250]
    brp_model = np.polyfit(pts_inside["depth"], pts_inside["brp_uncorr"], deg=1)
    x_eval = np.linspace(0, points["depth"].max())
    axes[0].plot(np.poly1d(brp_model)(x_eval),x_eval, color="black")
    axes[0].set_ylim(plt.gca().get_ylim()[::-1])
    axes[0].set_xlabel("Normalized BRP")
    axes[0].set_ylabel("Depth (m)")

    scatter = axes[1].scatter(points["brp"],points["depth"], c=points["margin_distance"], s=8)
    cbar= plt.colorbar(scatter)
    cbar.set_label("Distance to margin (m)")
    axes[1].set_xlabel("Normalized BRP")
    plt.tight_layout()
    plt.savefig("temp/dronbreen_brp_points.jpg", dpi=600)
    # plt.show()
    plt.close()
    # return
    # return
    # return
    import rasterio as rio
    import rasterio.features
    
    res = 50
    transform = rio.transform.from_origin(outline.total_bounds[0], outline.total_bounds[3], res, res)

    eastings = np.arange(outline.total_bounds[0], outline.total_bounds[2], res)
    northings = np.arange(outline.total_bounds[1], outline.total_bounds[3], res)

    points["xbin"] = np.digitize(points["easting"], eastings)
    points["ybin"] = np.digitize(points["northing"], northings)

    points["bin"] = points["ybin"] * northings.shape[0] + points["xbin"]

    x_x, y_y = np.meshgrid(eastings, northings[::-1])
    data_distance = scipy.spatial.KDTree(points[["easting", "northing"]]).query(np.transpose([x_x.ravel(), y_y.ravel()]))[0].reshape(y_y.shape)

    points["easting_orig"] = points["easting"]
    points["northing_orig"] = points["northing"]

    points["easting"] -= eastings.min()
    eastings -= eastings.min()

    points["northing"] -= northings.min()
    northings -= northings.min()

    points["easting"] /= eastings.max()
    eastings /= eastings.max()
    
    points["northing"] /= northings.max()
    northings /= northings.max()

    points = points.select_dtypes(np.number).groupby("bin").mean()

    x_x, y_y = np.meshgrid(eastings, northings[::-1])

    glacier_mask = rasterio.features.rasterize(outline["geometry"], out_shape=y_y.shape, transform=transform) == 1

    mask = glacier_mask & (data_distance < 500)


    # kernel = 1 * sklearn.gaussian_process.kernels.RBF(length_scale=1)
    # model= sklearn.gaussian_process.GaussianProcessRegressor(
    #     kernel=kernel,
    #     n_restarts_optimizer=5,
    #     normalize_y=True,
    #     alpha=3e-1,
    # )
    # model.fit(points[["easting", "northing"]].values, points["brp"].values)
    # interp = model.predict(np.transpose([x_x.ravel(), y_y.ravel()])).reshape(y_y.shape)
    # print(model.kernel)

    rbf = scipy.interpolate.RBFInterpolator(points[["easting", "northing"]], points["brp"], smoothing=0.02)
    interp = rbf(np.transpose([x_x.ravel(), y_y.ravel()])).reshape(y_y.shape)

    with rio.open("temp/dronbreen_brp.tif", "w", driver="GTiff", width=interp.shape[1], height=interp.shape[0], count=1, crs="EPSG:32633", transform=transform, dtype="float32", nodata=-9999, compress="deflate", zlevel=12) as raster:
        raster.write(np.where(mask, interp, -9999), 1)
    # interp[~mask] = np.nan
    interp = np.ma.masked_array(interp, mask=~mask)

    fig = plt.figure(figsize=(8, 4.5))
    axes = fig.subplots(1, 3, width_ratios=[0.49, 0.49, 0.02])

    extent=[outline.total_bounds[0], outline.total_bounds[2],outline.total_bounds[1],outline.total_bounds[3]]
    axes[0].imshow(glacier_mask, extent=extent, cmap="RdBu", vmin=-2, vmax=2)
    axes[0].scatter(points["easting_orig"], points["northing_orig"], c=points["brp"], vmin=0.4, vmax=1.1, cmap="inferno", s=5)
    axes[1].imshow(glacier_mask, extent=extent, cmap="RdBu", vmin=-2, vmax=2)
    img = axes[1].imshow(interp, extent=extent, vmin=0.4, vmax=1.1, cmap="inferno")

    cbar = plt.colorbar(img,cax=axes[2])
    cbar.set_label("Normalized BRP")

    axes[0].set_yticks(axes[0].get_yticks())
    axes[0].set_yticklabels(["" if i not in [3, 7] else int(tick) for i, tick in enumerate(axes[0].get_yticks())], rotation=90, ha="center", va="center")
    axes[1].set_yticks(axes[0].get_yticks())
    axes[1].set_yticklabels([""] * len(axes[0].get_yticks()))

    for i in [0, 1]:
        axes[i].set_ylim(extent[2], extent[3])
        axes[i].set_xlim(extent[0], extent[1])
        axes[i].set_xticks(axes[i].get_xticks()[1:-1])
        axes[i].set_xticklabels(["" if i not in [0, 1] else int(tick) for i, tick in enumerate(axes[0].get_xticks())], ha="center")

    plt.tight_layout()

    plt.savefig("temp/dronbreen_brp_map.jpg", dpi=600)
    

    
    # plt.scatter(points["easting"], points["northing"], c=points["brp"], vmin=0.4, vmax=1.1)
    plt.show()
    return
    

    plt.scatter(points["margin_distance"], points["brp"])
    plt.show()


def interpolate_raster(out_filepath: Path, points: gpd.GeoDataFrame, zcol: str, res: float = 10., outline: gpd.GeoSeries | None = None, extrapolation_distance: float = 200., vmin: float | None = None, vmax: float | None = None, _rec: int = 0) -> tuple[np.ndarray, dict[str, float]]:
    import rasterio as rio

    if _rec > 2:
        raise RecursionError()

    if out_filepath.is_file() and _rec >= 0:
        with rio.open(out_filepath) as raster:
            return raster.read(1, masked=True).filled(np.nan), dict(zip(["left", "bottom", "right", "top"], raster.bounds))
    points = points.copy()

    bounds = points.total_bounds

    if outline is not None:
        bounds = outline.total_bounds
    
    transform = rio.transform.from_origin(bounds[0], bounds[3], res, res)

    eastings = np.arange(bounds[0] - res, bounds[2] + res, res)
    northings = np.arange(bounds[1] -res, bounds[3] + res, res)

    points["easting"] = points.geometry.x
    points["northing"] = points.geometry.y

    points["xbin"] = np.digitize(points.geometry.x, eastings)
    points["ybin"] = np.digitize(points.geometry.y, northings)

    points["bin"] = points["ybin"] * northings.shape[0] + points["xbin"]
    points = points.select_dtypes(np.number).groupby("bin").mean()

    x_x, y_y = np.meshgrid(eastings, northings[::-1])
    data_distance = scipy.spatial.KDTree(points[["easting", "northing"]]).query(np.transpose([x_x.ravel(), y_y.ravel()]))[0].reshape(y_y.shape)
        
    mask = data_distance < extrapolation_distance
    if outline is not None:
        import rasterio.features
        outline_mask = rasterio.features.rasterize(outline, out_shape=y_y.shape, transform=transform) == 1
        mask = mask & outline_mask

    rbf = scipy.interpolate.RBFInterpolator(points[["easting", "northing"]], points[zcol], smoothing=0.02)
    interp = rbf(np.transpose([x_x.ravel(), y_y.ravel()])).reshape(y_y.shape)

    if vmin is not None:
        interp[interp < vmin] = vmin
    if vmax is not None:
        interp[interp > vmax] = vmax

    # plt.imshow(interp, extent=[bounds[0], bounds[2],bounds[1],bounds[3]], vmin=0, vmax=1)
    # plt.scatter(points["easting"], points["
    # plt.show()

    out_filepath.parent.mkdir(exist_ok=True, parents=True)
    with rio.open(out_filepath, "w", driver="GTiff", width=interp.shape[1], height=interp.shape[0], count=1, crs="EPSG:32633", transform=transform, dtype="float32", nodata=-9999, compress="deflate", zlevel=12) as raster:
        raster.write(np.where(mask, interp, -9999), 1)

    return interpolate_raster(out_filepath=out_filepath, points=None, zcol="", _rec=_rec + 1)

    

def plot_gridded():

    data = gpd.read_feather(Path("cache/interpretations/interp_all.feather"))

    dronbreen_outline = gpd.read_file("temp/dronbreen_outline_20240828.geojson")

    data = data[data.intersects(dronbreen_outline.geometry[0])]


    interp_kwargs = {
        "res": 25.,
        "outline": dronbreen_outline.geometry,
    }
    out_filepath = Path("cache/interpretations/gridded/dronbreen_thickness.tif")
    thickness, bounds = interpolate_raster(out_filepath, zcol="thickness", points=data.query("thickness_std < 30"), extrapolation_distance=500., **interp_kwargs)
    out_filepath = out_filepath.with_stem(out_filepath.stem.replace("_thickness", "_temperate_frac"))
    temperate_frac, _ = interpolate_raster(out_filepath,points=data.query("temperate_frac_std < 0.5"), zcol="temperate_frac",vmin=0., vmax=1., **interp_kwargs)

    fig = plt.figure(figsize=(9, 7))
    axes = fig.subplots(2, 2, height_ratios=[0.6, 0.4], sharey="row", sharex="row")

    outline_polygon = lambda: plt.Polygon(np.array(dronbreen_outline.geometry[0].exterior.xy).T, zorder=1, color="black", alpha=0.3)

    for i in range(axes.shape[1]):
        axis: plt.Axes = axes[0, i]
     
        axis.add_patch(outline_polygon())

        extent = extent=(bounds["left"], bounds["right"], bounds["bottom"], bounds["top"])
        if i == 0:
            img = axis.imshow(thickness, cmap="Blues", zorder=2, extent=extent, vmin=0)
        else:
            img = axis.imshow(temperate_frac * 100, vmin=0, vmax=100, extent=extent, cmap="Reds", zorder=2)

        cbar = plt.colorbar(img)
        if i == 0:
            cbar.set_label("Thickness (m)")
            axis.set_ylabel("Northing (m)")
        else:
            cbar.set_label("Temperate fraction (%)")

        axis.set_xlabel("Easting (m)")

    examples = [
        {
            "radar-key": "dronbreen-20240209-DAT_0463_A1_3",
            "start_trace": 3540,
            # "stop_trace": 6420,
            "standstills": [(3983, 4038)],
            # "max_depth": 175,
        },
        {
            "radar-key": "dronbreen-20220328-DAT_0226_A1_1",
            "start_trace": 1100,
            # "stop_trace": 4100,
            "standstills": [],
        },
    ]

    for i, info in enumerate(examples):

        # info["stop_distance"] = 2600
        glacier, date_str, file_stem = info["radar-key"].split("-")
        axis: plt.Axes = axes[1, i]

        with xr.open_dataset(f"processed_radar/{glacier}/{date_str}/{file_stem}.nc") as dataset:
            dataset.coords["trace_n"] = "x", np.arange(dataset.x.shape[0])
            dataset = dataset.swap_dims(x="trace_n", y="depth").sel(trace_n=slice(info["start_trace"], None))

            diffs = dataset[["easting", "northing"]].diff("trace_n").fillna(0)

            dataset["distance"] = ((diffs["easting"] ** 2 + diffs["northing"] ** 2) ** 0.5).cumsum("trace_n")
            dataset["distance"] += np.linspace(0, 1e-3, dataset.data.shape[1]) 


            for standstill in info["standstills"]:
                dataset = dataset.drop_sel(trace_n=np.arange(*standstill))

            dataset = dataset.swap_dims(trace_n="distance").sel(distance=dataset["distance"].where(dataset["distance"] < 2050, drop=True).values)
            

            if "max_depth" in info:
                dataset = dataset.sel(depth=slice(info["max_depth"]))

            dataset["data"] = np.abs(dataset.data)

            # vmin, vmax = np.percentile(dataset["data"].values[50:], [5, 99])

            axis.imshow(dataset.data, extent=(dataset["distance"].min().item(), dataset["distance"].max().item(), dataset["depth"].max(), dataset["depth"].min()), cmap="Greys_r", aspect="auto", vmin=0.2, vmax=2, interpolation="lanczos")

            if i == 0:
                axis.set_ylabel("Depth (m)")

            axis.set_xlabel("Distance (m)")

            for j in range(axes.shape[1]):
                axis2: plt.Axes = axes[0, j]

                for idx, ext in [(0, ""), (-1, "'")]:
                    axis2.annotate("de"[i] + ext, (dataset.isel(distance=idx)["easting"], dataset.isel(distance=idx)["northing"]), ha="center", va="center", path_effects=[matplotlib.patheffects.withStroke(linewidth=2, foreground="white")])
                axis2.plot(dataset["easting"], dataset["northing"], color="black")

    plt.tight_layout()
    inset: plt.Axes = axes[0, 0].inset_axes((0., 0.6, 0.4, 0.4))
    inset.set_xticks([])
    inset.set_yticks([])
    inset.add_patch(outline_polygon())
    for _, line in data.groupby("radar-key"):
        line = line.sort_values("distance")
        inset.plot(line.geometry.x, line.geometry.y, linewidth=0.5, color="black", zorder=2)

    for i, axis in enumerate([inset, *axes.ravel()]):
        axis.text(0.41 if i == 1 else 0.01, 0.99, "abcde"[i], transform=axis.transAxes, fontsize=10, va="top", path_effects=[matplotlib.patheffects.withStroke(linewidth=2, foreground="white")])

    Path("figures").mkdir(exist_ok=True)
    plt.savefig("figures/dronbreen_example.jpg", dpi=600)
    plt.show()

    

    

def plot_interp_profiles():

    better_but_need_gps = [
        "dronbreen-20230220-DAT_0009_A1_1",

    ]

    radar_keys = [
        "mettebreen-20230305-DAT_0235_A1_8",
        "filantropbreen-20240406-DAT_0372_A1_1",
        "moysalbreen-20220222-DAT_0749_A1_1",
        # "rugaasfonna-20220218-DAT_0723_A1_1",
        "lofthusbreen-20250326-DAT_0057_A1_1",
        "jinnbreen-20240206-DAT_0448_A1_1",
        "ragna_mariebreen-20240412-DAT_0404_A1_1",
        "dronbreen-20250327-DAT_0065_A1_1",
        "kroppbreen-20230228-DAT_0042_A1_1",
        "slakbreen-20240310-DAT_0286_A1_1",
        "edvardbreen-20240411-DAT_0396_A1_1",
        # "winsnesbreen-20240503-DAT_0014_A1_1",
    ]

    n_cols = 2
    n_rows = int(np.ceil(len(radar_keys) / n_cols))

    meta = {
        "mettebreen-20230305-DAT_0235_A1_8": {
            "start_distance": 7180,
        },
        "dronbreen-20250327-DAT_0065_A1_1": {
            # "stop_distance": 5650,
            "start_distance": 200,
        }
    }

    nice_names = {
        "dronbreen": "Drønbreen",
        "moysalbreen": "Møysalbreen",
        "ragna_mariebreen": "Ragna Mariebreen",

    }

    fig = plt.figure(figsize=(6, 8))
    axes = fig.subplots(nrows=n_rows, ncols=n_cols)

    for i, radar_key in enumerate(radar_keys):

        row = int(i / n_cols)
        col = i - row * n_cols
        axis: plt.Axes = axes[row, col]

        data = gpd.read_feather(Path(f"cache/interpretations/per_radargram/{radar_key}.feather"))

        radar_meta = meta.get(radar_key, {})

            
        data = data.sort_values("distance")

      
        glacier, date_str, file_stem = radar_key.split("-")
        filepath = Path(f"processed_radar/{glacier}/{date_str}/{file_stem}.nc")
        with xr.open_dataset(filepath) as dataset:

            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                models = {key: scipy.interpolate.interp1d(dataset["distance"].values, dataset[key].values, bounds_error=False) for key in ["elevation"]}

                data["elevation"] = models["elevation"](data["distance"])

        if "start_distance" in radar_meta:
            data = data[data["distance"] > radar_meta["start_distance"]]
        if "stop_distance" in radar_meta:
            data = data[data["distance"] < radar_meta["stop_distance"]]

        if data.iloc[10]["elevation"] > data.iloc[-10]["elevation"]:
            data["distance"] = data["distance"].max() - data["distance"]
            data = data.sort_values("distance")

        data["distance"] = ((data[["easting", "northing"]].diff(axis="rows").fillna(0) ** 2).sum(axis="columns") ** 0.5).cumsum() / 1e3

        data["bed_elevation"] = data["elevation"] - data["thickness"]

        data["temp_elevation"] = data["bed_elevation"] + data["thickness"] * data["temperate_frac"]


        axis.fill_between(data["distance"], data["bed_elevation"].min() - 50, data["bed_elevation"], color="gray")
        axis.fill_between(data["distance"], data["temp_elevation"], data["elevation"], color="lightblue", alpha=0.5)
        axis.fill_between(data["distance"], data["bed_elevation"], data["temp_elevation"], color="red", alpha=0.5)
        axis.plot(data["distance"], data["bed_elevation"], color="black")
        axis.plot(data["distance"], data["elevation"], color="blue")

        xrange = data["distance"].max() - data["distance"].min()

        aspect = 8

        if row > 1:
            aspect = 12

        yrange = 1000 * xrange / aspect

        if col == (n_cols - 1):
            axis.yaxis.tick_right()
        if col == 0 and (row == int(n_rows / 2)):
            axis.set_ylabel("Elevation (m a.s.l.)")

        if row == (n_rows - 1):
            axis.set_xlabel("Distance (km)")
            

        axis.set_xlim(data["distance"].min(), data["distance"].max())
        # axis.set_ylim(data["bed_elevation"].min() - 20, data["elevation"].max() + 20) 
        axis.set_ylim(data["bed_elevation"].min() - 20, data["bed_elevation"].min() - 20 + yrange) 

        axis.text(0.5, 0.95, nice_names.get(glacier, glacier.replace("_", " ").capitalize()), ha="center", va="top", transform=axis.transAxes)
        axis.text(0.02, 0.98, "abcdefghijklmnopqrs"[i], transform=axis.transAxes, fontsize=9, va="top")

    plt.tight_layout()
    plt.savefig("figures/centerline_profiles.jpg", dpi=600)

    plt.show()
    return

           
    

    
if __name__ == "__main__":
    main()
    
