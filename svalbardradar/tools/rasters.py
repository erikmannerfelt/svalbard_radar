from pathlib import Path

import geopandas as gpd
import numpy as np
import rasterio as rio
import scipy.spatial
import shapely.geometry


def bounds_dict(dataset: rio.DatasetBase) -> dict[str, float]:
    return dict(zip(["left", "bottom", "right", "top"], dataset.bounds))


def interpolate_raster(
    out_filepath: Path,
    points: gpd.GeoDataFrame,
    zcol: str,
    res: float = 10.0,
    outline: shapely.geometry.Polygon | None = None,
    extrapolation_distance: float = 200.0,
    vmin: float | None = None,
    vmax: float | None = None,
    _rec: int = 0,
) -> tuple[np.ndarray, dict[str, float]]:
    import rasterio as rio

    if _rec > 2:
        raise RecursionError()

    if out_filepath.is_file() and _rec >= 0:
        with rio.open(out_filepath) as raster:
            return raster.read(1, masked=True).filled(np.nan), bounds_dict(raster)
    points = points.copy()

    bounds = points.total_bounds

    if outline is not None:
        bounds = outline.bounds

    transform = rio.transform.from_origin(bounds[0], bounds[3], res, res)

    eastings = np.arange(bounds[0] - res, bounds[2] + res, res)
    northings = np.arange(bounds[1] - res, bounds[3] + res, res)

    points["easting"] = points.geometry.x
    points["northing"] = points.geometry.y

    points["xbin"] = np.digitize(points.geometry.x, eastings)
    points["ybin"] = np.digitize(points.geometry.y, northings)

    points["bin"] = points["ybin"] * northings.shape[0] + points["xbin"]
    points = points.select_dtypes(np.number).groupby("bin").mean()

    x_x, y_y = np.meshgrid(eastings, northings[::-1])
    data_distance = (
        scipy.spatial.KDTree(points[["easting", "northing"]])
        .query(np.transpose([x_x.ravel(), y_y.ravel()]))[0]
        .reshape(y_y.shape)
    )

    mask = data_distance < extrapolation_distance
    if outline is not None:
        import rasterio.features

        outline_mask = (
            rasterio.features.rasterize(
                [outline], out_shape=y_y.shape, transform=transform
            )
            == 1
        )
        mask = mask & outline_mask

    rbf = scipy.interpolate.RBFInterpolator(
        points[["easting", "northing"]], points[zcol], smoothing=0.02
    )
    interp = rbf(np.transpose([x_x.ravel(), y_y.ravel()])).reshape(y_y.shape)

    if vmin is not None:
        interp[interp < vmin] = vmin
    if vmax is not None:
        interp[interp > vmax] = vmax

    # plt.imshow(interp, extent=[bounds[0], bounds[2],bounds[1],bounds[3]], vmin=0, vmax=1)
    # plt.scatter(points["easting"], points["
    # plt.show()

    out_filepath.parent.mkdir(exist_ok=True, parents=True)
    with rio.open(
        out_filepath,
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
        bounds = bounds_dict(raster)

    return np.where(mask, interp, np.nan), bounds
