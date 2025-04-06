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
import tqdm
import xarray as xr

import svalbardradar.tools.statistics as statistics
from svalbardradar.tools import paths, statistics


def plot_dronbreen_examples(show: bool = True):
    import svalbardradar.interpretations
    import svalbardradar.tools.rasters

    # data = gpd.read_feather(Path("cache/interpretations/interp_all.feather"))

    dronbreen_outline = gpd.read_file("temp/dronbreen_outline_20240828.geojson")

    data = svalbardradar.interpretations.merge_all_interpretations()
    data = data[data.intersects(dronbreen_outline.geometry[0])]

    interp_kwargs = {
        "res": 25.0,
        "outline": dronbreen_outline.geometry,
    }
    # out_filepath = Path("cache/interpretations/gridded/dronbreen_thickness.tif")
    # thickness, bounds = svalbardradar.tools.rasters.interpolate_raster(out_filepath, zcol="thickness", points=data.query("thickness_std < 30"), extrapolation_distance=500., **interp_kwargs)
    # out_filepath = out_filepath.with_stem(out_filepath.stem.replace("_thickness", "_temperate_frac"))
    # temperate_frac, _ = svalbardradar.tools.rasters.interpolate_raster(out_filepath,points=data.query("temperate_frac_std < 0.5"), zcol="temperate_frac",vmin=0., vmax=1., **interp_kwargs)

    gridded = svalbardradar.interpretations.grid_interpretations(
        "dronbreen", outline=dronbreen_outline.geometry[0]
    )

    fig = plt.figure(figsize=(9, 7))
    axes = fig.subplots(2, 2, height_ratios=[0.6, 0.4], sharey="row", sharex="row")

    outline_polygon = lambda: plt.Polygon(
        np.array(dronbreen_outline.geometry[0].exterior.xy).T,
        zorder=1,
        color="black",
        alpha=0.3,
    )

    for i in range(axes.shape[1]):
        axis: plt.Axes = axes[0, i]

        axis.add_patch(outline_polygon())

        extent = extent = (
            gridded["bounds"]["left"],
            gridded["bounds"]["right"],
            gridded["bounds"]["bottom"],
            gridded["bounds"]["top"],
        )
        if i == 0:
            img = axis.imshow(
                gridded["thickness"], cmap="Blues", zorder=2, extent=extent, vmin=0
            )
        else:
            img = axis.imshow(
                gridded["temperate_frac"] * 100,
                vmin=0,
                vmax=100,
                extent=extent,
                cmap="Reds",
                zorder=2,
            )

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

        with xr.open_dataset(paths.processed_radar_path(info["radar-key"])) as dataset:
            dataset.coords["trace_n"] = "x", np.arange(dataset.x.shape[0])
            dataset = dataset.swap_dims(x="trace_n", y="depth").sel(
                trace_n=slice(info["start_trace"], None)
            )

            diffs = dataset[["easting", "northing"]].diff("trace_n").fillna(0)

            dataset["distance"] = (
                (diffs["easting"] ** 2 + diffs["northing"] ** 2) ** 0.5
            ).cumsum("trace_n")
            dataset["distance"] += np.linspace(0, 1e-3, dataset.data.shape[1])

            for standstill in info["standstills"]:
                dataset = dataset.drop_sel(trace_n=np.arange(*standstill))

            dataset = dataset.swap_dims(trace_n="distance").sel(
                distance=dataset["distance"]
                .where(dataset["distance"] < 2050, drop=True)
                .values
            )

            if "max_depth" in info:
                dataset = dataset.sel(depth=slice(info["max_depth"]))

            dataset["data"] = np.abs(dataset.data)

            # vmin, vmax = np.percentile(dataset["data"].values[50:], [5, 99])

            axis.imshow(
                dataset.data,
                extent=(
                    dataset["distance"].min().item(),
                    dataset["distance"].max().item(),
                    dataset["depth"].max(),
                    dataset["depth"].min(),
                ),
                cmap="Greys_r",
                aspect="auto",
                vmin=0.2,
                vmax=2,
                interpolation="lanczos",
            )

            if i == 0:
                axis.set_ylabel("Depth (m)")

            axis.set_xlabel("Distance (m)")

            for j in range(axes.shape[1]):
                axis2: plt.Axes = axes[0, j]

                for idx, ext in [(0, ""), (-1, "'")]:
                    axis2.annotate(
                        "de"[i] + ext,
                        (
                            dataset.isel(distance=idx)["easting"],
                            dataset.isel(distance=idx)["northing"],
                        ),
                        ha="center",
                        va="center",
                        path_effects=[
                            matplotlib.patheffects.withStroke(
                                linewidth=2, foreground="white"
                            )
                        ],
                    )
                axis2.plot(dataset["easting"], dataset["northing"], color="black")

    plt.tight_layout()
    inset: plt.Axes = axes[0, 0].inset_axes((0.0, 0.6, 0.4, 0.4))
    inset.set_xticks([])
    inset.set_yticks([])
    inset.add_patch(outline_polygon())
    for _, line in data.groupby("radar-key"):
        line = line.sort_values("distance")
        inset.plot(
            line.geometry.x, line.geometry.y, linewidth=0.5, color="black", zorder=2
        )

    for i, axis in enumerate([inset, *axes.ravel()]):
        axis.text(
            0.41 if i == 1 else 0.01,
            0.99,
            "abcde"[i],
            transform=axis.transAxes,
            fontsize=10,
            va="top",
            path_effects=[
                matplotlib.patheffects.withStroke(linewidth=2, foreground="white")
            ],
        )

    Path("figures").mkdir(exist_ok=True)
    plt.savefig("figures/dronbreen_example.jpg", dpi=600)

    if show:
        plt.show()


def plot_interp_profiles(show: bool = True):
    import svalbardradar.interpretations

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
        },
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

        # data = gpd.read_feather(Path(f"cache/interpretations/per_radargram/{radar_key}.feather"))
        data = svalbardradar.interpretations.merge_interpretations(radar_key)

        radar_meta = meta.get(radar_key, {})

        data = data.sort_values("distance")

        glacier, date_str, file_stem = radar_key.split("-")
        filepath = Path(f"processed_radar/{glacier}/{date_str}/{file_stem}.nc")
        with xr.open_dataset(filepath) as dataset:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                models = {
                    key: scipy.interpolate.interp1d(
                        dataset["distance"].values,
                        dataset[key].values,
                        bounds_error=False,
                    )
                    for key in ["elevation"]
                }

                data["elevation"] = models["elevation"](data["distance"])

        if "start_distance" in radar_meta:
            data = data[data["distance"] > radar_meta["start_distance"]]
        if "stop_distance" in radar_meta:
            data = data[data["distance"] < radar_meta["stop_distance"]]

        if data.iloc[10]["elevation"] > data.iloc[-10]["elevation"]:
            data["distance"] = data["distance"].max() - data["distance"]
            data = data.sort_values("distance")

        data["distance"] = (
            (data[["easting", "northing"]].diff(axis="rows").fillna(0) ** 2).sum(
                axis="columns"
            )
            ** 0.5
        ).cumsum() / 1e3

        data["bed_elevation"] = data["elevation"] - data["thickness"]

        data["temp_elevation"] = (
            data["bed_elevation"] + data["thickness"] * data["temperate_frac"]
        )

        axis.fill_between(
            data["distance"],
            data["bed_elevation"].min() - 50,
            data["bed_elevation"],
            color="gray",
        )
        axis.fill_between(
            data["distance"],
            data["temp_elevation"],
            data["elevation"],
            color="lightblue",
            alpha=0.5,
        )
        axis.fill_between(
            data["distance"],
            data["bed_elevation"],
            data["temp_elevation"],
            color="red",
            alpha=0.5,
        )
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
        axis.set_ylim(
            data["bed_elevation"].min() - 20, data["bed_elevation"].min() - 20 + yrange
        )

        axis.text(
            0.5,
            0.95,
            nice_names.get(glacier, glacier.replace("_", " ").capitalize()),
            ha="center",
            va="top",
            transform=axis.transAxes,
        )
        axis.text(
            0.02,
            0.98,
            "abcdefghijklmnopqrs"[i],
            transform=axis.transAxes,
            fontsize=9,
            va="top",
        )

    plt.tight_layout()
    plt.savefig("figures/centerline_profiles.jpg", dpi=600)

    if show:
        plt.show()


def plot_model_comparison(show: bool = True):
    import svalbardradar.comparisons

    data = svalbardradar.comparisons.sample_models()

    models = [str(col).replace("_thickness", "") for col in data if "_thickness" in col]

    ref_names = {
        "furst": "Fürst et al., (2018)",
        "farinotti": "Farinotti et al., (2019)",
        "millan": "Millan et al., (2022)",
        "vanpelt": "van Pelt & Frank (2025)",
    }

    fig = plt.figure(figsize=(7, 7))
    axes = fig.subplots(nrows=2, ncols=2, sharex=True, sharey=True)

    max_thickness = (
        data[["thickness", *[f"{model}_thickness" for model in models]]].max().max()
    )

    step_size = 7.5
    thickness_bins = np.arange(
        0, max_thickness - (max_thickness % step_size) + step_size * 2, step_size
    )

    for i, model in enumerate(ref_names):
        col = i % 2
        row = int((i - col) / 2)
        axis: plt.Axes = axes[row, col]

        hist2 = np.histogram2d(
            data[f"{model}_thickness"], data["thickness"], bins=thickness_bins
        )[0][::-1, :]
        hist2 = np.ma.masked_array(hist2, mask=hist2 == 0)

        axis.set_title(ref_names[model])
        axis.imshow(hist2, extent=(0.0, thickness_bins[-1], 0.0, thickness_bins[-1]))

        xlim = axis.get_ylim()
        axis.plot([xlim[0], xlim[1]], [xlim[0], xlim[1]], color="black")

        diff = data[f"{model}_thickness"] - data["thickness"]

        axis.text(
            x=0.05,
            y=0.95,
            s="\n".join(
                [
                    f"Median: {diff.median():.1f} m",
                    f"NMAD: {1.426 * np.median(np.abs(diff - np.median(diff))): .1f} m",
                    f"r = {data['thickness'].corr(data[f'{model}_thickness']):.2f}",
                ]
            ),
            transform=axis.transAxes,
            va="top",
            path_effects=[
                matplotlib.patheffects.withStroke(
                    linewidth=4, foreground="white"
                )
            ],
        )

        if row == 1:
            axis.set_xlabel("Measured thickness (m)")

        if col == 0:
            axis.set_ylabel("Modelled thickness (m)")

    plt.tight_layout()

    Path("figures/").mkdir(exist_ok=True)
    plt.savefig("figures/thickness_vs_models.jpg", dpi=400)

    if show:
        plt.show()


def plot_glathida_comparison(show: bool = True):
    import scipy.spatial

    import svalbardradar.comparisons

    data = svalbardradar.comparisons.sample_glathida()

    year_intervals = [1990, 2010, 2025]
    markers = ["x", "s", "o"]

    data["glathida_group"] = np.digitize(data["glathida_year"], year_intervals)

    plt.figure(figsize=(5, 5))
    for i, group in data.groupby("glathida_group"):
        stats = f"(n={group.shape[0]}, ΔT: {group['glathida_diff'].median():.1f}±{statistics.nmad(group['glathida_diff']):.1f} m)"

        if i == 0:
            label = f"<={year_intervals[0]} {stats}"
        else:
            label = f"{year_intervals[i - 1]}-{year_intervals[i]} {stats}"
        plt.scatter(
            group["thickness"],
            group["glathida_thickness"],
            label=label,
            marker=markers[i],
            s=9,
        )

    max_thickness = data[["glathida_thickness", "thickness"]].max().max()

    plt.ylabel("GlaThiDa thickness (m)")
    plt.xlabel("Our thickness (m)")

    plt.plot([0, max_thickness], [0, max_thickness], color="black")
    plt.legend()
    plt.tight_layout()
    Path("figures/").mkdir(exist_ok=True)
    plt.savefig("figures/thickness_vs_glathida.jpg", dpi=400)

    if show:
        plt.show()


def generate_all_figures(show: bool = True):
    plot_dronbreen_examples(show=show)
    plot_interp_profiles(show=show)
    plot_model_comparison(show=show)
    plot_glathida_comparison(show=show)


if __name__ == "__main__":
    generate_all_figures()
