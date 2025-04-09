import io
import json
import warnings
from pathlib import Path

import geopandas as gpd
import matplotlib.patheffects
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import scipy.interpolate
import scipy.spatial
import shapely.geometry
import tqdm
import xarray as xr

from svalbardradar.tools import paths, rasters

CACHE_PATH = paths.BASE_CACHE_PATH / "interpretations"


def make_gp(length_scale_bounds=(1e-2, 2e2), mean: float | None = None):
    import sklearn.gaussian_process

    kernel = 1 * sklearn.gaussian_process.kernels.RBF(
        length_scale=np.mean(length_scale_bounds),
        length_scale_bounds=length_scale_bounds,
    )

    if mean is not None:
        kernel = kernel * sklearn.gaussian_process.kernels.ConstantKernel(mean)

    model = sklearn.gaussian_process.GaussianProcessRegressor(
        kernel=kernel,
        n_restarts_optimizer=5,
        normalize_y=True,
        alpha=1e-3,
    )
    return model


def read_interpretation(filepath: Path, step_size: int = 10) -> pd.DataFrame:
    data = pd.DataFrame()
    interp = json.loads(filepath.read_text())

    new_data = gpd.read_file(io.StringIO(json.dumps(interp["features"])))

    if "kind" not in new_data:
        new_data["kind"] = new_data["name"].apply(
            lambda s: {"Glacier bed": "bed_unspecified", "Cold glacier bed": "bed_cold", "Glacier bed missing": "bed_missing", "Temperate ice": "temperate_ice"}[s]
        )

    for kind, kind_data in new_data.groupby("kind"):
        for _, row in kind_data.iterrows():
            for distance in np.arange(0, row.geometry.length + step_size, step_size):
                point = row.geometry.interpolate(distance)

                out_data = {
                    "kind": kind,
                    "color": row["color"],
                    "x": point.x,
                    "y": point.y,
                }

                data.loc[data.shape[0], list(out_data.keys())] = list(out_data.values())

    return data


def merge_interpretations(
    radar_key: str, step_size: float = 30.0, cold_model_strength: float = 100.0, overwrite_cache: bool = False,
) -> gpd.GeoDataFrame:
    cache_path = CACHE_PATH / f"per_radargram/{radar_key}.feather"
    cache_path.parent.mkdir(exist_ok=True, parents=True)

    if cache_path.is_file() and not overwrite_cache:
        return gpd.read_feather(cache_path)

    glacier, date_str, file_stem = radar_key.split("-")
    filepath = paths.processed_radar_path(radar_key)
    if not filepath.is_file():
        return gpd.GeoDataFrame()

    data = pd.DataFrame()
    colors = {}
    interp_paths = paths.get_latest_submissions(radar_key)

    for interp_path in interp_paths:
        data = pd.concat(
            [data, read_interpretation(interp_path, step_size=step_size)],
            ignore_index=True,
        )

    if data.shape[0] == 0:
        return gpd.GeoDataFrame()

    with xr.open_dataset(filepath) as dataset:
        depth_model = scipy.interpolate.interp1d(
            np.arange(dataset["data"].shape[0])[::-1],
            dataset["depth"].values,
            bounds_error=False,
        )

        models = {
            key: scipy.interpolate.interp1d(
                np.arange(dataset["data"].shape[1]),
                dataset[key].values,
                bounds_error=False,
            )
            for key in ["easting", "northing", "distance", "elevation"]
        }
        antenna = dataset.attrs["antenna"].split("MHz")[0] + "MHz"
        crs = dataset.attrs["crs"]

    data["depth"] = depth_model(data["y"].astype(float))

    for key in models:
        data[key] = models[key](data["x"].astype(float))

    data = data.dropna(subset=["depth", "easting"])

    bed_model = make_gp()

    bed_data = data[data["kind"].isin(["bed_cold", "bed_unspecified"])]
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore")
        bed_model.fit(bed_data[["x"]].values, bed_data["depth"].values)

    cold_data = data[data["kind"].isin(["bed_cold", "temperate"])].copy()

    x_eval = np.arange(0, bed_data["x"].max(), step_size)

    out = pd.DataFrame(index=x_eval)

    out["thickness"], out["thickness_std"] = bed_model.predict(
        x_eval[:, None], return_std=True
    )

    if cold_data.shape[0] > 2:
        bed_pred = bed_model.predict(cold_data[["x"]].values)
        cold_data["frac"] = np.clip((bed_pred - cold_data["depth"]) / bed_pred, 0, 1)
        temp_model = make_gp(mean=0, length_scale_bounds=(100, 1e3))
        with warnings.catch_warnings():
            warnings.filterwarnings("ignore")
            temp_model.fit(cold_data[["x"]].values, cold_data["frac"].values)

        out["temperate_frac"], out["temperate_frac_std"] = temp_model.predict(
            x_eval[:, None], return_std=True
        )

        out["temperate_frac"] = np.clip(out["temperate_frac"], 0, 1)

    for col in models:
        out[col] = models[col](x_eval)

    if crs != "EPSG:32633":
        points = gpd.points_from_xy(out["easting"], out["northing"], crs=crs).to_crs(
            32633
        )
        out["easting"] = points.x
        out["northing"] = points.y

    out["antenna"] = antenna
    out["radar-key"] = radar_key
    out["date_str"] = date_str
    out = gpd.GeoDataFrame(
        out, geometry=gpd.points_from_xy(out["easting"], out["northing"], crs=32633)
    )

    out.to_feather(cache_path)

    return gpd.read_feather(cache_path)


def merge_all_interpretations(
    step_size: float = 30.0,
    outlier_threshold: float = 200.0,
    cold_model_strength: float = 100.0,
    overwrite_cache: bool = False,
) -> gpd.GeoDataFrame:
    out_path = CACHE_PATH / "interp_all.feather"

    if out_path.is_file():
        return gpd.read_feather(out_path)

    # radar_keys = ["ragna_mariebreen-20230305-DAT_0068_A1_3", "filantropbreen-20240406-DAT_0373_A1_1", "ragna_mariebreen-20240412-DAT_0404_A1_1"][::-1]
    #
    radar_keys = paths.get_all_interpreted_radargrams()

    all_data = []
    for radar_key in tqdm.tqdm(radar_keys):
        out = merge_interpretations(
            radar_key=radar_key,
            step_size=step_size,
            cold_model_strength=cold_model_strength,
            overwrite_cache=overwrite_cache,
        )

        all_data.append(out)

    all_data = pd.concat(all_data)

    all_data = gpd.GeoDataFrame(
        all_data,
        geometry=gpd.points_from_xy(
            all_data["easting"], all_data["northing"], crs=32633
        ),
    )

    all_data.to_feather(out_path)

    return gpd.read_feather(out_path)


def grid_interpretations(
    name: str,
    outline: shapely.geometry.Polygon,
    cols: list[str] = ["thickness", "temperate_frac"],
) -> dict[str, np.ndarray | dict[str, float]]:
    cache_paths = {col: CACHE_PATH / f"gridded/{name}/{name}_{col}.tif" for col in cols}

    out = {}
    if all(fp.is_file() for fp in cache_paths.values()):
        for col in cache_paths:
            # This looks wrong but will just fetch the cache path and return its contents immediately
            raster, bounds = rasters.interpolate_raster(
                cache_paths[col], gpd.GeoDataFrame, col
            )
            out[col] = raster
            out["bounds"] = bounds
        return out

    data = merge_all_interpretations()
    data = data[data.intersects(outline, align=False)]

    for col in cols:
        cache_path = CACHE_PATH / f"gridded/{name}/{name}_{col}.tif"

        extrapolation_distance = 500
        vmin = vmax = None
        if col == "thickness":
            subset = data.query("thickness_std < 30")
        elif col == "temperate_frac":
            extrapolation_distance = 250
            subset = data.query("temperate_frac_std < 0.5")
            vmin = 0.0
            vmax = 1.0
        else:
            subset = data

        raster, bounds = rasters.interpolate_raster(
            cache_path,
            zcol=col,
            points=subset,
            extrapolation_distance=extrapolation_distance,
            res=25,
            outline=outline,
            vmin=vmin,
            vmax=vmax,
        )

        out[col] = raster
        out["bounds"] = bounds

    return out


def sample_brp_dronbreen():
    datasets = (
        [
            Path(f"processed_radar/dronbreen/20250327/DAT_00{num}_A1_1.nc")
            for num in [62, 63, 65, 66]
        ]
        + [
            Path(f"processed_radar/dronbreen/20250326/DAT_00{num}_A1_1.nc")
            for num in [44, 46, 50, 52, 53, 54, 58]
        ]
        + [Path(f"processed_radar/lofthusbreen/20250326/DAT_0057_A1_1.nc")]
    )

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

            interp_path = sorted(Path(f"submitted/admin/{radar_key}/").glob("*.json"))[
                -1
            ]

            interp = read_interpretation(interp_path, step_size=50)

            interp = interp[
                interp["kind"].str.contains("bed_")
                & (~interp["kind"].str.contains("bed_missing"))
            ]
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

                    interp.loc[idx, "brp_uncorr"] = (
                        point_data.data.isel(y=slice(brp_y_min, brp_y_max))
                        .max("y")
                        .item()
                        / airwave_sum.isel(x=point["x"]).item()
                    )
                    # interp.loc[idx, "irp_uncorr"] = point_data.data.isel(y=slice(airwave_len, brp_y_min)).sum("y").item() / airwave_sum.isel(x=point["x"]).item()

                    interp.loc[idx, "depth"] = (
                        point_data["depth"].isel(y=point["y"]).item()
                    )

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

        points["terminus_distance"] = (
            (points["easting"] - 541821) ** 2 + (points["northing"] - 8675501) ** 2
        ) ** 0.5

        plt.scatter(
            points["depth"], points["brp_uncorr"], c=points["terminus_distance"]
        )
        pts_inside = points[points["margin_distance"] > 250]
        brp_model = np.polyfit(pts_inside["depth"], pts_inside["brp_uncorr"], deg=1)
        x_eval = np.linspace(0, points["depth"].max())
        plt.plot(x_eval, np.poly1d(brp_model)(x_eval), color="black")

        points["brp"] = points["brp_uncorr"] - points["depth"] * brp_model[0]
        # points["brp_multiple"] = points["brp_multiple_uncorr"] - points["depth"] * brp_model[0]
        # points["irp"] = (points["irp_uncorr"] - points["depth"] * brp_model[0]) / (points["depth"] / 10)

        points = gpd.GeoDataFrame(
            points,
            geometry=gpd.points_from_xy(
                points["easting"], points["northing"], crs=32633
            ),
        )

        points.to_file(cache_filepath)
        # plt.show()
    else:
        points = gpd.read_file(cache_filepath)

    fig = plt.figure(figsize=(8, 4.5))
    axes = fig.subplots(1, 2, sharex=True, sharey=True)

    axes[0].scatter(
        points["brp_uncorr"], points["depth"], c=points["margin_distance"], s=8
    )
    pts_inside = points[points["margin_distance"] > 250]
    brp_model = np.polyfit(pts_inside["depth"], pts_inside["brp_uncorr"], deg=1)
    x_eval = np.linspace(0, points["depth"].max())
    axes[0].plot(np.poly1d(brp_model)(x_eval), x_eval, color="black")
    axes[0].set_ylim(plt.gca().get_ylim()[::-1])
    axes[0].set_xlabel("Normalized BRP")
    axes[0].set_ylabel("Depth (m)")

    scatter = axes[1].scatter(
        points["brp"], points["depth"], c=points["margin_distance"], s=8
    )
    cbar = plt.colorbar(scatter)
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
    transform = rio.transform.from_origin(
        outline.total_bounds[0], outline.total_bounds[3], res, res
    )

    eastings = np.arange(outline.total_bounds[0], outline.total_bounds[2], res)
    northings = np.arange(outline.total_bounds[1], outline.total_bounds[3], res)

    points["xbin"] = np.digitize(points["easting"], eastings)
    points["ybin"] = np.digitize(points["northing"], northings)

    points["bin"] = points["ybin"] * northings.shape[0] + points["xbin"]

    x_x, y_y = np.meshgrid(eastings, northings[::-1])
    data_distance = (
        scipy.spatial.KDTree(points[["easting", "northing"]])
        .query(np.transpose([x_x.ravel(), y_y.ravel()]))[0]
        .reshape(y_y.shape)
    )

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

    glacier_mask = (
        rasterio.features.rasterize(
            outline["geometry"], out_shape=y_y.shape, transform=transform
        )
        == 1
    )

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

    rbf = scipy.interpolate.RBFInterpolator(
        points[["easting", "northing"]], points["brp"], smoothing=0.02
    )
    interp = rbf(np.transpose([x_x.ravel(), y_y.ravel()])).reshape(y_y.shape)

    with rio.open(
        "temp/dronbreen_brp.tif",
        "w",
        driver="GTiff",
        width=interp.shape[1],
        height=interp.shape[0],
        count=1,
        crs="EPSG:32633",
        transform=transform,
        dtype="float32",
        nodata=-9999,
        compress="deflate",
        zlevel=12,
    ) as raster:
        raster.write(np.where(mask, interp, -9999), 1)
    # interp[~mask] = np.nan
    interp = np.ma.masked_array(interp, mask=~mask)

    fig = plt.figure(figsize=(8, 4.5))
    axes = fig.subplots(1, 3, width_ratios=[0.49, 0.49, 0.02])

    extent = [
        outline.total_bounds[0],
        outline.total_bounds[2],
        outline.total_bounds[1],
        outline.total_bounds[3],
    ]
    axes[0].imshow(glacier_mask, extent=extent, cmap="RdBu", vmin=-2, vmax=2)
    axes[0].scatter(
        points["easting_orig"],
        points["northing_orig"],
        c=points["brp"],
        vmin=0.4,
        vmax=1.1,
        cmap="inferno",
        s=5,
    )
    axes[1].imshow(glacier_mask, extent=extent, cmap="RdBu", vmin=-2, vmax=2)
    img = axes[1].imshow(interp, extent=extent, vmin=0.4, vmax=1.1, cmap="inferno")

    cbar = plt.colorbar(img, cax=axes[2])
    cbar.set_label("Normalized BRP")

    axes[0].set_yticks(axes[0].get_yticks())
    axes[0].set_yticklabels(
        [
            "" if i not in [3, 7] else int(tick)
            for i, tick in enumerate(axes[0].get_yticks())
        ],
        rotation=90,
        ha="center",
        va="center",
    )
    axes[1].set_yticks(axes[0].get_yticks())
    axes[1].set_yticklabels([""] * len(axes[0].get_yticks()))

    for i in [0, 1]:
        axes[i].set_ylim(extent[2], extent[3])
        axes[i].set_xlim(extent[0], extent[1])
        axes[i].set_xticks(axes[i].get_xticks()[1:-1])
        axes[i].set_xticklabels(
            [
                "" if i not in [0, 1] else int(tick)
                for i, tick in enumerate(axes[0].get_xticks())
            ],
            ha="center",
        )

    plt.tight_layout()

    plt.savefig("temp/dronbreen_brp_map.jpg", dpi=600)

    # plt.scatter(points["easting"], points["northing"], c=points["brp"], vmin=0.4, vmax=1.1)
    plt.show()
    return
