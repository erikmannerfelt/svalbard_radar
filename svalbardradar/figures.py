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

from svalbardradar import interpretations
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

        glacier = radar_key.split("-")[0]

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
    max_thickness = data[["glathida_thickness", "thickness"]].max().max()

    fig = plt.figure(figsize=(9, 3.5))
    axes = fig.subplots(ncols=3, sharex=True, sharey=True)
    for i, group in data.groupby("glathida_group"):
        axis: plt.Axes = axes[i]
        stats = f"n={group.shape[0]}, ΔT: {group['glathida_diff'].median():.1f}±{statistics.nmad(group['glathida_diff']):.1f} m"


        if i == 0:
            label = f"–{year_intervals[0]}\n{stats}"
        elif i == (len(year_intervals) - 1):
            label = f"{year_intervals[-2]}–\n{stats}"
        else:
            label = f"{year_intervals[i - 1]}–{year_intervals[i]}\n{stats}"

        axis.text(
            0.5, 0.98,
            label,
            transform=axis.transAxes,
            ha="center",
            va="top",
            path_effects=[
                matplotlib.patheffects.withStroke(
                    linewidth=4, foreground="white"
                )
            ],
        ) 
        axis.scatter(
            group["thickness"],
            group["glathida_thickness"],
            # label=label,
            s=9,
            color="black",
        )
        axis.plot([0, max_thickness], [0, max_thickness], color="black")

        if i == 0:
            axis.set_ylabel("GlaThiDa thickness (m)")

        axis.set_xlabel("Our thickness (m)")



    # plt.legend()
    plt.tight_layout()
    Path("figures/").mkdir(exist_ok=True)
    plt.savefig("figures/thickness_vs_glathida.jpg", dpi=400)

    if show:
        plt.show()


def overview_map(show: bool = True):
    import scipy.interpolate
    import shapely.geometry

    interp = interpretations.merge_all_interpretations()

    tracks = []
    for radar_key, data in interp.groupby("radar-key"):

        easting_model = scipy.interpolate.interp1d(data["distance"], data["easting"])
        northing_model = scipy.interpolate.interp1d(data["distance"], data["northing"])

        d_eval = np.r_[np.arange(0, data["distance"].max(), 5), [data["distance"].max()]]

        geometry = shapely.geometry.LineString(np.transpose([
            easting_model(d_eval),
            northing_model(d_eval),
        ]))

        tracks.append(
            {
                "radar-key": radar_key,
                "geometry": geometry,
            } | {k: data.iloc[0][k] for k in ["antenna", "date_str"]}
        )


    tracks = pd.DataFrame.from_records(tracks)
    tracks = gpd.GeoDataFrame(tracks, crs=32633)

    insets = {
        "svalbard": [491000, 665000, 8585000, 8893000],
        "nordaustlandet": [630000, 660000, 8855000, 8890000],
        "heerland": [535000, 565000, 8625000, 8655000],
        "central_norden": [518000, 545500, 8650000, 8680000],
    }


    fig = plt.figure(figsize=(8, 5))
    axes = fig.subplots(2, 3)
    # aspect = 1.

    for i, key in enumerate(insets, start=0):

        col = i % axes.shape[1]
        row = int((i - col) / axes.shape[1])
        axis: plt.Axes = axes[row, col]

        extent = insets[key] or list(tracks.buffer(5000).total_bounds[[0, 2, 1, 3]])

        subset = tracks[
            (tracks.centroid.x > extent[0]) &
            (tracks.centroid.x < extent[1]) &
            (tracks.centroid.y > extent[2]) &
            (tracks.centroid.y < extent[3])
        ]

        if i == 0:
            for j, key2 in enumerate(insets):
                if j == 0:
                    continue
                extent2 = insets[key2]
                axis.add_patch(
                    plt.Rectangle(
                        (extent2[0], extent2[2]),
                        width=extent2[1] - extent2[0],
                        height=extent2[3] - extent2[2],
                    )
                )

        for _, track in subset.iterrows():
            axis.plot(*track.geometry.xy, color="black")


        # width_m = extent[1] - extent[0]
        axis.set_xlim(extent[0], extent[1])
        axis.set_ylim(extent[2], extent[3])
        axis.set_aspect("equal")

       
    plt.show()

    return
    for _, track in tracks.iterrows():
        plt.plot(*track.geometry.xy, color="black")

    plt.show()

    print(tracks)
        

def plot_model_temperate_cold_performance(show: bool = True):
    import svalbardradar.comparisons

    data = svalbardradar.comparisons.sample_models()
    glathida = svalbardradar.comparisons.sample_glathida()
    glathida = glathida[glathida["glathida_year"] > 2000]
    # data = svalbardradar.comparisons.sample_glathida(data.copy())

    models = [str(col).replace("_thickness", "") for col in data if "_thickness" in col] + ["glathida"]

    colors = {
        "cold": "white",
        "temperate": "red",
        "all": "grey",
    }
    ref_names = {
        "furst": "Fürst et al.\n(2018)",
        "farinotti": "Farinotti et al.\n(2019)",
        "millan": "Millan et al.\n(2022)",
        "vanpelt": "van Pelt & Frank\n(2025)",
        "glathida": "GlaThiDa 2000-"
    }
    case_names = {
        "temperate": "Temperate ice",
        "cold": "Cold ice",
        "all": "All data",
    }
    box_distance = 5
    plt.figure(figsize=(8, 5))
    for i, model in enumerate(models):
        if model != "glathida":
            temperate = data["temperate_frac"] > 0.1
            diff = data[f"{model}_thickness"] - data["thickness"]
        else:
            temperate = glathida["temperate_frac"] > 0.1
            diff =glathida["glathida_diff"]

        for j, (case, arr) in enumerate([("cold", diff[~temperate]), ("temperate", diff[temperate]), ("all", diff)]):
            arr = arr[np.abs(arr) < 300]
            plt.boxplot([arr], positions=[j - 1 + box_distance * i],  showfliers=False, manage_ticks=False, widths=0.8, patch_artist=True, boxprops={"facecolor": colors[case], "alpha": 0.5}, medianprops={"color": "black"}, label=case_names[case] if i == 0 else None)
            # violins = plt.violinplot([arr], positions=[j - 1 + box_distance * i], widths=1)
            # for violin in violins["bodies"]:
            #     violin.set_facecolor(colors[case])
            #     violin.set_edgecolor("black")
            # for key in violins:
            #     if key == "bodies":
            #         continue
            #     violins[key].set_edgecolor(colors[case] if colors[case] != "white" else "grey")
            #     violins[key].set_alpha(0.5)
    plt.xticks(np.arange(len(models)) * box_distance, [ref_names[model] for model in models])
    plt.ylabel("Thickness difference (m)")
    plt.legend()
    xlim = plt.gca().get_xlim()

    plt.hlines(0, *xlim, zorder=0, color="grey", linestyles="--")
    plt.xlim(xlim)
    plt.tight_layout()

    Path("figures/").mkdir(exist_ok=True)
    plt.savefig("figures/thickness_vs_cold_temperate.jpg", dpi=400)

    if show:
        plt.show()

        

    print(data.iloc[0])
    


def generate_all_figures(show: bool = True):
    plot_dronbreen_examples(show=show)
    plot_interp_profiles(show=show)
    plot_model_comparison(show=show)
    plot_glathida_comparison(show=show)


if __name__ == "__main__":
    generate_all_figures()
