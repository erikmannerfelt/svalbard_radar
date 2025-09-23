import io
import json
import warnings
from pathlib import Path
import datetime
import functools

import geopandas as gpd
import matplotlib.patheffects
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import scipy.interpolate
import tqdm
import xarray as xr
import textalloc

from svalbardradar import interpretations
import svalbardradar.tools.statistics as statistics
from svalbardradar.tools import paths, statistics, misc

CACHE_PATH = paths.BASE_CACHE_PATH / "figures"
DIGITIZE_CLASS_PROPS = {
    "bed_cold": {
      "name": "Glacier bed (no temperate ice)",
      "color": "#002EBD",
    },
    "temperate": {
      "name": "Temperate ice",
      "color": "red",
    },
    "bed_unspecified": {
      "name": "Glacier bed",
      "color": "#CE00FF",
    },
    "bed_missing": {
      "name": "Glacier bed not visible",
      "color": "#62F700",
    },
  }
def plot_dronbreen_examples(show: bool = True):
    import svalbardradar.interpretations
    import svalbardradar.tools.rasters

    # data = gpd.read_feather(Path("cache/interpretations/interp_all.feather"))

    dronbreen_outline = gpd.read_file("shapes/dronbreen_outline_20240828.geojson")

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
            "radar_key": "dronbreen-20240209-DAT_0463_A1_3",
            "start_trace": 3540,
            # "stop_trace": 6420,
            "standstills": [(3983, 4038)],
            # "max_depth": 175,
        },
        {
            "radar_key": "dronbreen-20220328-DAT_0226_A1_1",
            "start_trace": 1100,
            # "stop_trace": 4100,
            "standstills": [],
        },
    ]

    for i, info in enumerate(examples):
        # info["stop_distance"] = 2600
        glacier, date_str, file_stem = info["radar_key"].split("-")
        axis: plt.Axes = axes[1, i]

        with xr.open_dataset(paths.processed_radar_path(info["radar_key"])) as dataset:
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
                vmin=0.4,
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
    for _, line in data.groupby("radar_key"):
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


def plot_user_spread(show: bool = True):
    import svalbardradar.interpretations
    from svalbardradar.tools import paths, rasters
    from matplotlib.backends.backend_pdf import PdfPages
    radar_keys = [
        "moysalbreen-20220222-DAT_0750_A1_6",
        "vallakrabreen-20210513-DAT_0014_A1_31",
        "ragna_mariebreen-20240412-DAT_0404_A1_1",
        "filantropbreen-20240406-DAT_0372_A1_1",
    ]

    all_data =svalbardradar.interpretations.merge_all_interpretations()

    all_data["glacier"] = all_data["radar_key"].str.split("-", expand=True).iloc[:, 0]
    all_data["part_idx"] = all_data["part_idx"].astype(int)
    all_data["bed_elevation"] = all_data["elevation"] - all_data["thickness"]

    all_data["temp_elevation"] = (
        all_data["bed_elevation"] + all_data["thickness"] * all_data["temperate_frac"]
    )

    out_path = Path("figures/all_interpretations.pdf")
    out_path.parent.mkdir(exist_ok=True)
    radar_keys = []
    with PdfPages(out_path) as pdf, tqdm.tqdm(total=all_data["radar_key"].unique().shape[0]) as progress_bar:
        for glacier, all_glacier_data in all_data.groupby("glacier"):
            for radar_key, data in all_glacier_data.groupby("radar_key"):

                # if "dronbreen-20200224-DAT_0003_A1_2" not in radar_key:
                #     continue
                # if len(radar_keys) > 9:
                #     break
                _, date_str, filename = radar_key.split("-")

                data = data.copy()
                data["distance"] = (
                    (data[["easting", "northing"]].diff(axis="rows").fillna(0) ** 2).sum(
                        axis="columns"
                    )
                    ** 0.5
                ).cumsum() / 1e3

                fig = plt.figure(figsize=(8.3, 11.7))
                axes = fig.subplots(3, 1, sharex=True, sharey=True, height_ratios=[0.5, 0.25, 0.25])

                with xr.open_dataset(f"processed_radar/{glacier}/{date_str}/{filename}.nc") as dataset:
                    depth_model = scipy.interpolate.interp1d(
                        np.arange(dataset["data"].shape[0])[::-1],
                        dataset["depth"].values,
                        bounds_error=False,
                    )
            
                interp_paths = paths.get_latest_submissions(radar_key)

                map: plt.Axes = axes[0].inset_axes([0.5, 0.05, 0.5, 0.95])
                for _, per_radargram in all_glacier_data.groupby("radar_key"):
                    for _, part in per_radargram.groupby("part_idx"):
                        if part.iloc[0]["radar_key"] == radar_key:
                            style = {"color": "red", "zorder": 2}
                        else:
                            style = {"color": "grey", "zorder": 1}
                        map.plot(part.geometry.x, part.geometry.y, **style)


                topo_ax: plt.Axes = axes[0].inset_axes([-0.02, 0.35, 0.4, 0.4]) 
                max_d = 0.
                for _, part in data.groupby("part_idx"):

                    distances = part["distance"] - part["distance"].min() + max_d

                    topo_ax.fill_between(
                        distances,
                        data["bed_elevation"].min() - 50,
                        part["bed_elevation"],
                        color="gray",
                    )

                    mask = (~part[["temperate_elevation", "elevation"]].isna()).all(axis=1)
                    topo_ax.fill_between(
                        distances[mask],
                        part.loc[mask, "temperate_elevation"],
                        part.loc[mask, "elevation"],
                        color="lightblue",
                        alpha=0.5,
                    )
                    topo_ax.fill_between(
                        distances[mask],
                        part.loc[mask, "bed_elevation"],
                        part.loc[mask, "temperate_elevation"],
                        color="red",
                        alpha=0.5,
                    )
                    topo_ax.plot(distances, part["bed_elevation"], color="black")
                    topo_ax.plot(distances, part["elevation"], color="blue")

                    max_d = distances.max()

                axes[0].text(
                    -0.1,
                    0.03,
                    "\n".join(
                         [
                             f"Date: {date_str}",
                             f"Glacier: {glacier}", 
                             f"n contributors: {len(interp_paths)}", 
                             f"Length: {max_d:.2f} km",
                             f"Mean thickness: {data['thickness'].mean():.2f} m",
                             f"Mean thickness uncertainty: {data['thickness_std'].mean():.2f} m",
                             f"Mean temperate ice fraction: {100 *data['temperate_frac'].mean():.2f}%",
                             f"Mean temperate ice fraction uncertainty: {100 * data['temperate_frac_std'].mean():.2f}%",
                         ]
                    ),
                    transform=axes[0].transAxes
                )

                labeled = set()
                all_points = interpretations.read_interpretations(radar_key=radar_key, step_m=5.).reset_index()
                for _, points in all_points.groupby(["user", "line_i"]):
                    kind = points["kind"].iloc[0].replace("temperate_ice", "temperate")
                    axes[1].plot(points["x"], points["depth"], color=DIGITIZE_CLASS_PROPS[kind]["color"], alpha=0.3, label=DIGITIZE_CLASS_PROPS[kind]["name"] if kind not in labeled else None)
                    labeled.add(kind)

                axes[2].fill_between(
                    data["x"],
                    data["thickness_lower"],
                    data["thickness_upper"],
                    color="blue",
                    alpha=0.5,
                    label="Thickness (+- 25%)", zorder=2
                )
                axes[2].plot(data["x"], data["thickness"], color="blue", path_effects=[
                        matplotlib.patheffects.withStroke(
                            linewidth=3, foreground="black"
                        )
                ], zorder=4, label="Thickness (median)")
                axes[2].fill_between(
                    data["x"],
                    data["thickness"] - data["temperate_lower"],
                    data["thickness"] - data["temperate_upper"],
                    color="red",
                    alpha=0.5,
                    label="Temperate ice (+- 25%)",
                    zorder=1,
                )
                # plt.fill_between(out0.index, out["bed_elevation"] + out0["temperate_lower"], out["bed_elevation"] + out0["temperate_upper"], color="red", alpha=0.3)
                # plt.fill_between(out0.index, out["elevation"] - out0["thickness_lower"], out["elevation"] - out0["thickness_upper"], color="blue", alpha=0.3)
                axes[2].plot(data["x"], data["thickness"] - data["thickness"] * data["temperate_frac"], color="red", zorder=3, label="Temperate ice (median)")

                for spine in axes[0].spines.values():
                    spine.set_visible(False)
                axes[0].tick_params(left=False, bottom=False, labelleft=False, labelbottom=False)

                topo_ax.set_xlim(0, max_d)
                topo_ax.set_ylim(data["bed_elevation"].min(), topo_ax.get_ylim()[1])
                topo_ax.set_ylabel("Elevation (m a.s.l.)")
                topo_ax.set_xlabel("Distance (km)")

                map.set_aspect("equal")
                map.set_ylabel("Northing (m)")
                xticks = map.get_xticks()
                map.set_xticks(xticks)
                map.set_xticklabels([str(int(xtick)) if i in [2, len(xticks) - 2] else "" for i, xtick in enumerate(xticks)])
                
                map.set_xlabel("Easting (m)")

                axes[1].text(0.5, 1., "Individual interpretations", ha="center", va="bottom", transform=axes[-2].transAxes)
                axes[1].legend()

                axes[2].text(0.5, 1., "Merged interpretations", ha="center", va="bottom", transform=axes[-1].transAxes)
                axes[2].set_ylabel("Depth (m)")
                axes[2].set_xlabel("Traces")
                axes[2].legend()

                ylim = axes[2].get_ylim()
                axes[2].set_ylim(min(ylim[1], 350), -10)

                for axis in axes[1:]:
                    axis.grid(alpha=0.5, zorder=0)

                fig.text(0.02, 0.99, f"https://radar.mannerfelt.org/digitize/{radar_key}", va="top", fontsize=7)
                fig.text(0.03, 0.97, radar_key.replace("-", "-\n"), ha="left", va="top", fontsize=14)

                plt.subplots_adjust(left=0.1, bottom=0.05, right=0.95, top=0.99, hspace=0.05)

                fig.text(0.99, 0.01, f"Created {datetime.datetime.now().date().isoformat()}", ha="right", va="bottom", fontsize=8)
                fig.text(0.03, 0.01, str(len(radar_keys) + 1), ha="right", va="bottom", fontsize=8)

                pdf.savefig(fig)
                # plt.savefig("temp.jpg", dpi=300)
                plt.close(fig)
                progress_bar.update()
                radar_keys.append(radar_key)
                # raise NotImplementedError()

def plot_centerline_profiles(show: bool = True):
    import svalbardradar.interpretations

    better_but_need_gps = [
        "dronbreen-20230220-DAT_0009_A1_1",
    ]

    radar_keys = [
        "mettebreen-20230305-DAT_0235_A1_8",
        # "filantropbreen-20240406-DAT_0372_A1_1",
        "moysalbreen-20220222-DAT_0749_A1_1",
        # "rugaasfonna-20220218-DAT_0723_A1_1",
        "lofthusbreen-20250326-DAT_0057_A1_1",
        "ragna_mariebreen-20240412-DAT_0404_A1_1",
        "jinnbreen-20240206-DAT_0448_A1_1",
        "finsterwalderbreen-20250407-DAT_0171_A1_1",
        "dronbreen-20230220-DAT_0009_A1_1",
        # "dronbreen-20250327-DAT_0065_A1_1",
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


def plot_model_comparison(show: bool = True, histogram: bool = False):
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


        axis.set_title(ref_names[model])

        if histogram:
            hist2 = np.histogram2d(
                data[f"{model}_thickness"], data["thickness"], bins=thickness_bins
            )[0][::-1, :]
            hist2 = np.ma.masked_array(hist2, mask=hist2 == 0)
            axis.imshow(hist2, extent=(0.0, thickness_bins[-1], 0.0, thickness_bins[-1]))
        else:
            axis.scatter(data["thickness"], data[f"{model}_thickness"], color="black", edgecolor="none", s=2, alpha=0.025)
            plt.xlim(0, thickness_bins.max())
            plt.ylim(0, thickness_bins.max())

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
            alpha=0.3,
            color="black",
            edgecolor="none",
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


def s20_hillshade() -> Path:
    dtm20_path = CACHE_PATH / "NP_S0_DTM20.zip"
    misc.download_large_file(dtm20_path, "https://public.data.npolar.no/kartdata/S0_Terrengmodell/Mosaikk/NP_S0_DTM20.zip")
    hillshade_path = dtm20_path.with_name("NP_S0_DTM20_hillshade.tif")

    if not hillshade_path.is_file():
        import subprocess

        subprocess.run(
            [
                "gdaldem",
                "hillshade",
                f"/vsizip/{dtm20_path}/NP_S0_DTM20/S0_DTM20.tif",
                str(hillshade_path),
                "-multidirectional",
                "-co",
                "compress=DEFLATE",
                "-co",
                "zlevel=12",
                "-co",
                "tiled=YES",
                "-co",
                "predictor=2",
                "-co",
                "GDAL_NUM_THREADS=ALL_CPUS",
            ], check=True)

        subprocess.run(
            [
                "gdaladdo",
                "-r",
                "lanczos",
                "--config",
                "GDAL_NUM_THREADS=ALL_CPUS",
                "--config",
                "COMPRESS_OVERVIEW",
                "DEFLATE",
                str(hillshade_path),
            ],
            check=True,

        )

    return hillshade_path

def get_npi_data(layer: str):
    import rasterio
    if "CryoClim" in layer:
        url = "https://next.api.npolar.no/dataset/89f430f8-862f-11e2-8036-005056ad0004/attachment/4494bb0d-8b90-480b-aed1-47f7955ce81b/_blob"
        uri = "/vsizip/{" + f"/vsicurl/{url}" + "}" + f"/{layer}.shp"

    else:
        url = "https://public.data.npolar.no/kartdata/NP_S100_SHP.zip"
        uri = f"/vsizip/vsicurl/{url}/NP_S100_SHP/{layer}.shp"

    cache_filepath = CACHE_PATH / (layer + ".gpkg")

    if cache_filepath.is_file():
        return gpd.read_file(cache_filepath, layer="outlines")

    outlines = gpd.read_file(uri)
    # Remove Bjørnøya
    outlines = outlines[outlines["geometry"].centroid.y > 8.4e6]

    # The coordinate systems are essentially interchangeable
    # Converting did not work as one value seems invalid
    outlines.crs = rasterio.CRS.from_epsg(32633)

    outlines.to_file(cache_filepath, driver="GPKG", layer="outlines")
    return outlines

def get_svalbard_outlines() -> gpd.GeoDataFrame:
    return get_npi_data("S100_Land_f")

def get_svalbard_glaciers() -> gpd.GeoDataFrame:
    return get_npi_data("CryoClim_GAO_SJ_2001-2010")

def overview_map(show: bool = True):
    import rasterio
    import rasterio.features
    import shapely.geometry

    glaciers = gpd.read_file("shapes/glacier_locations.geojson")


    hillshade_path = s20_hillshade()

    figsize = (8, 7)
    fig = plt.figure(figsize=figsize)

    # NOTE TO FUTURE SELF: If the shape isn't equal (e.g. (12, 9)), the aspect calculation gets messed up.
    # Either it always needs to stay equal, or the aspect calculation needs to be fixed.
    new_ax = functools.partial(plt.subplot2grid, shape=(12,) * 2, fig=fig)

    overview_kwargs = {"rowspan": 6, "colspan": 4}
    overview_ax = new_ax(loc=(0, 0), **overview_kwargs)

    style = {
        "degree_label": {
            "fontsize": 8,
            "color": "#333",
        },
        "degree_line": {
            "linewidth": 0.5,
            "color": "gray",
            "alpha": 0.5,
        },
        "overview_box": {
            "alpha": 0.3,
            "color": "red",
        },
        "overview_label": {
            "color": "darkred",
            "ha": "left",
            "va": "top",
        },
        "panel_label": {
            "x": 0.01, "y": 0.99, "va": "top", "ha": "left", "path_effects": [matplotlib.patheffects.withStroke(linewidth=2, foreground="white")], "fontsize":10
        },
        "scalebar_line": {
            "linewidth": 1,
            "color": "#333",
            "path_effects": [matplotlib.patheffects.withStroke(linewidth=1.5, foreground="white")]
        },
        "scalebar_label": {
            "fontsize": 8,
            "color": "#333",
            "path_effects": [matplotlib.patheffects.withStroke(linewidth=0.7, foreground="white")]
        },
        "glacier_label": {
            "textsize": 10,  # Fontsize
            "color": "black",
            "path_effects": [matplotlib.patheffects.withStroke(linewidth=1, foreground="white")]
        },
        "glacier_label_line": {
            "color": "white",
            "linewidth": 1,
            "path_effects": [matplotlib.patheffects.withStroke(linewidth=2, foreground="black")]
        },
        "radar_lines": {
            "color": "red",
            "linewidth": 1,
            "path_effects": [matplotlib.patheffects.withStroke(linewidth=1, foreground="black")]
        },
    }

    outlines = get_svalbard_outlines()
    glacier_outlines = get_svalbard_glaciers()
    glacier_outlines["used"] = glacier_outlines.geometry.intersects(
        shapely.geometry.MultiPoint(
            np.transpose([glaciers.geometry.x, glaciers.geometry.y])
        )
    )
    outlines_dissolved = glacier_outlines.dissolve()

    radar_track_pts = gpd.read_feather("cache/interpretations/interp_all.feather")
    radar_lines_list = []
    for (radar_key, part_idx), pts in radar_track_pts.groupby(["radar_key", "part_idx"]):
        if pts.shape[0] < 2:
            continue

        radar_lines_list.append({
            "radar_key": radar_key,
            "part_idx": part_idx,
            "geometry": shapely.geometry.LineString(pts.sort_values("distance").geometry.values),
        })
    radar_lines = gpd.GeoDataFrame(pd.DataFrame.from_records(radar_lines_list), crs=radar_track_pts.crs)

    def plot_background(axis: plt.Axes, xlim, ylim, overview_level):
        with rasterio.open(hillshade_path, overview_level=overview_level) as raster:
            window = rasterio.windows.from_bounds(xlim[0], ylim[0], xlim[1], ylim[1], transform=raster.transform)
            arr = np.clip(raster.read(1, masked=True, window=window, boundless=True).filled(181) / 181, min=0, max=1)
            transform = rasterio.windows.transform(window=window,transform=raster.transform)

            lighten_scale = 0.5
            arr = (arr * lighten_scale) + (1 - lighten_scale) 

            land_mask = rasterio.features.rasterize(outlines.geometry, out_shape=arr.shape, transform=transform) == 1

            arr[~land_mask] = 1
            arr[land_mask] *= 0.8

            arr = np.repeat(arr[:, :, None], 3, axis=2)

            glacier_mask = rasterio.features.rasterize(glacier_outlines.query("~used").geometry, out_shape=arr.shape[:2], transform=transform) == 1

            arr[glacier_mask, 0] *= 173 / 255
            arr[glacier_mask, 1] *= 235 / 255

            chosen_glacier_mask = rasterio.features.rasterize(glacier_outlines.query("used").geometry, out_shape=arr.shape[:2], transform=transform) == 1
            arr[chosen_glacier_mask, 1] *= 204 / 255
            arr[chosen_glacier_mask, 2] *= 153 / 255

            axis.imshow(arr, extent=[*xlim, *ylim])
            outlines_dissolved.plot(color="none", edgecolor="black", linewidth=0.05 if overview_level == 2 else 0.2, ax=axis)
        

    xlim = 3.83e5, 7.5e5
    ymid = 8.71e6

    aspect = figsize[1] / figsize[0] * overview_kwargs.get("rowspan", 1) / overview_kwargs.get("colspan", 1)
    xrange = np.diff(xlim).item()
    yrange = xrange * aspect
    ylim = (ymid - yrange / 2, ymid + yrange / 2)

    plot_background(overview_ax, xlim=xlim, ylim=ylim, overview_level=2)

    for lat in np.arange(77, 81):
        lines = gpd.GeoSeries(shapely.LineString([(lon, lat) for lon in np.linspace(5, 50)]), crs=4326).to_crs(32633)
        lines.plot(ax=overview_ax, **style["degree_line"])
        point = lines.intersection(shapely.geometry.box(xlim[0], ylim[0], xlim[1], ylim[1])).apply(lambda line: line.interpolate(0)).values[0]
        overview_ax.annotate(f"{lat}°N", (point.x, point.y), **style["degree_label"]) 

    for lon in np.arange(5, 30, step=5):
        lines = gpd.GeoSeries(shapely.LineString([(lon, lat) for lat in np.linspace(50, 90)]), crs=4326).to_crs(32633)
        lines.plot(ax=overview_ax, **style["degree_line"])

        if lon in [15, 20]:
            point = lines.intersection(shapely.geometry.box(xlim[0], ylim[0], xlim[1], ylim[1])).apply(lambda line: line.interpolate(0)).values[0]
            overview_ax.annotate(f"{lon}°E", (point.x, point.y + (ylim[1] - ylim[0]) * 1e-2), **style["degree_label"]) 

    overview_ax.set_xlim(xlim)
    overview_ax.set_ylim(ylim)
    overview_ax.set_xticks([])
    overview_ax.set_yticks([])
    overview_ax.text(s="a", transform=overview_ax.transAxes, **style["panel_label"])

    zooms = [
        { # Southern Spitsbergen
            "letter": "b",
            "loc": (6, 0),
            "xlim": (491000, 547000),
            "ymid": 8.611e6,
            "colspan": 4,
            "rowspan": 3,
        },
        { # Nordaustlandet
            "letter": "c",
            "loc": (9, 0),
            "xlim": (617000, 662000),
            "ymid": 8.872e6,
            "colspan": 4,
            "rowspan": 3,
        },
        { # Central Spitsbergen
            "letter": "d",
            "loc": (0, 4),
            "xlim": (519000, 578000),
            "ymid": 8.671e6,
            "rowspan": 12,
            "colspan": 8,
        }
    ]

    for zoom in zooms:
        axis: plt.Axes = new_ax(loc=zoom["loc"], rowspan=zoom.get("rowspan", 1), colspan=zoom.get("colspan", 1))

        aspect = (figsize[1] / figsize[0]) * (zoom.get("rowspan", 1) / zoom.get("colspan", 1))

        xlim = zoom["xlim"]
        xrange = np.diff(xlim).item()
        yrange = xrange * aspect
        ylim = zoom["ymid"] - yrange / 2, zoom["ymid"] + yrange / 2

        axis.set_xlim(xlim)
        axis.set_ylim(ylim)

        plot_background(axis=axis, xlim=xlim, ylim=ylim, overview_level=None)

        radar_lines.plot(ax=axis, **style["radar_lines"])
    
        glaciers_sub = glaciers.loc[~glaciers.intersection(shapely.geometry.box(xlim[0], ylim[0], xlim[1], ylim[1])).is_empty]

        # Annotate the locations of the glaciers with their labels. This is nontrivial as the labels would
        # overlap without this package that makes sure they don't. The lines are stupid though so I'm making them myself.
        new_positions, _, texts, *_ = textalloc.allocate(
            axis,
            glaciers_sub.geometry.x.values,
            glaciers_sub.geometry.y.values,
            glaciers_sub["name"].apply(lambda s: s if len(s) < 15 else s.replace(" ", "\n")).values,
            x_scatter=glaciers_sub.geometry.x.values,
            y_scatter=glaciers_sub.geometry.y.values,
            draw_lines=False,
            min_distance=0.0,
            margin=0.0,
            ha="center",
            va="center",
            zorder=3,
            **style["glacier_label"],
        )

        # Draw lines from each label to the location's exact position
        for i, point in enumerate(new_positions):
            # This is the uncut line from label to the exact location
            line = shapely.geometry.LineString(
                [[point[0], point[1]], [glaciers_sub.geometry.x.values[i], glaciers_sub.geometry.y.values[i]]]
            )

            # We don't want the line within the bounding box of the label itself.
            bbox = (
                texts[i].get_window_extent().transformed(axis.transData.inverted())
            )
            # Extract and then plot the part of the line that's outside the bounding box.
            line_diff = line.difference(shapely.geometry.box(*bbox.extents))
            axis.plot(*line_diff.xy, zorder=1, **style["glacier_label_line"])

            # axis.axis("equal")
            axis.set_xticks([])
            axis.set_yticks([])

        overview_ax.add_patch(
            plt.Rectangle((axis.get_xlim()[0], axis.get_ylim()[0]), width=np.diff(axis.get_xlim()).item(), height=np.diff(axis.get_ylim()).item(), **style["overview_box"])
        )
        overview_ax.annotate(
            zoom["letter"],
            (xlim[0], ylim[1]),
            **style["overview_label"]
        )
        axis.text(s=zoom["letter"], transform=axis.transAxes, **style["panel_label"])


        # Make a scalebar
        upper_left_in = fig.dpi_scale_trans.inverted().transform(axis.transAxes.transform([0, 1]))
        upper_left_in[0] += 0.2  # Shift this many inches right of the upper left corner
        upper_left_in[1] -= 0.1  # Shift this many inches down of the upper left corner
        upper_left_data = axis.transData.inverted().transform(fig.dpi_scale_trans.transform(upper_left_in))
        km = 1

        x_locs = upper_left_data[0] + np.arange(km + 1) * 1e4
        y_locs = np.repeat(upper_left_data[1], km + 1)
        bar_height = 1e3

        axis.plot([x_locs[0], x_locs[0], x_locs[1], x_locs[1]], [y_locs[0] - bar_height, y_locs[0], y_locs[1], y_locs[1] - bar_height], **style["scalebar_line"])
        # axis.errorbar(x=x_locs, y=y_locs, yerr=np.repeat(np.array((bar_height, 0))[:, None], km + 1, axis=1), **style["scalebar_line"])
        for i in range(km + 1):
            axis.annotate(f"{i * 10} km", (x_locs[i], y_locs[i] - bar_height * 1.1), va="top", ha="center", **style["scalebar_label"])
        


    panel_spacing = 0
    plt.subplots_adjust(left=0.01, right=0.99, bottom=0.01, top=0.99, wspace=panel_spacing, hspace=panel_spacing * (figsize[1] / figsize[0]))
    plt.savefig("figures/location_overview.jpg", dpi=600)

    if show:
        plt.show()
    else:
        plt.close()


def plot_interpretation_merging(show: bool = False):

    all_merged = interpretations.merge_all_interpretations()

    cases = [
        {
            "radar_key": "ragna_mariebreen-20240412-DAT_0404_A1_1",
            "xlim": [2000, 6500],
            "ylim": [230, -10],
        },
        {
            "radar_key": "bergmesterbreen-20230222-DAT_0033_A1_3",
            "xlim": [3000, 5500],
            "ylim": [150, -10],
        },
        {
            "radar_key": "dronbreen-20200224-DAT_0003_A1_2",
            "xlim": [1100, 4400],
            "ylim": [170, 80],
        },
        {
            "radar_key": "filantropbreen-20240406-DAT_0372_A1_1",
            "xlim": [1300, 2800],
            "ylim": [140, 30],
        }
    ]

    fig = plt.figure(figsize=(8, 6.5))
    outer_grid = fig.add_gridspec(
        nrows=2, ncols=2,
        left=0.08, right=0.98, bottom=0.07, top=0.99,
        wspace=0.12, hspace=0.09
    )


    for i, case in enumerate(cases):
        inner_grid = outer_grid[i % 2, i // 2].subgridspec(3, 1, hspace=0.01)
        
        ax_bot = fig.add_subplot(inner_grid[2])
        ax_mid = fig.add_subplot(inner_grid[1], sharex=ax_bot)
        ax_top = fig.add_subplot(inner_grid[0], sharex=ax_bot)

        merged = all_merged.query(f"radar_key == '{case['radar_key']}'").sort_values("distance")

        all_points = interpretations.read_interpretations(radar_key=case["radar_key"], step_m=5.).reset_index()

        line_list = []
        with xr.open_dataset(paths.processed_radar_path(case["radar_key"])) as dataset:
            dataset.coords["trace_n"] = "x", np.arange(dataset.x.shape[0])
            dataset = dataset.swap_dims(x="trace_n", y="depth")#.sel(
            # I'm avoiding a strange bug here where if I clip the data exactly to xlim, it cuts too much!
            # By trial and error, I found that adding an extra 300/1000 traces "solves" it.
            dataset = dataset.sel(trace_n=slice(max(case["xlim"][0] - 300, 0), case["xlim"][1] + 1000), depth=slice(*case["ylim"][::-1]))
            dataset["data"] = np.abs(dataset.data)

            lower, upper = np.percentile(dataset.data, [2, 98])
            dataset.data.values = (dataset.data.values - lower) / (upper - lower)

            ax_top.imshow(
                dataset.data,
                # extent=[*case["xlim"], *case["ylim"]],
                extent=(
                    dataset["trace_n"].min().item(),
                    dataset["trace_n"].max().item(),
                    dataset["depth"].max(),
                    dataset["depth"].min(),
                ),
                cmap="Greys_r",
                aspect="auto",
                vmin=-0.1,
                vmax=1.7,
                interpolation="lanczos",
            )
        for _, points in all_points.groupby(["user", "line_i"]):
            ax_mid.plot(points["x"], points["depth"], color=DIGITIZE_CLASS_PROPS[points.iloc[0]["kind"].replace("temperate_ice", "temperate")]["color"], alpha=0.3)

        ax_bot.fill_between(
            merged["x"],
            merged["thickness"] - merged["temperate_lower"],
            merged["thickness"] - merged["temperate_upper"],
            color="red",
            alpha=0.5,
        )
        ax_bot.plot(
            merged["x"],
            merged["thickness"] - merged["temperate"],
            color="red",
        )
        ax_bot.fill_between(
            merged["x"],
            merged["thickness_lower"],
            merged["thickness_upper"],
            color="blue",
            alpha=0.5,
        )
        ax_bot.plot(
            merged["x"],
            merged["thickness"],
            color="blue",
        )
        for j, axis in enumerate([ax_top, ax_mid, ax_bot]):
            axis.set_xlim(case["xlim"])
            axis.set_ylim(case["ylim"])

            if j < 2:
                axis.tick_params(labelbottom=False)

            plt.text(0.01, 0.98, "abcdefghijklm"[i * 3 + j], ha="left", va="top", transform=axis.transAxes, path_effects=[
                            matplotlib.patheffects.withStroke(
                                linewidth=1, foreground="white"
                            )
                        ])

        if i in [0, 1]:
            ax_mid.set_ylabel("Depth (m)")
        if i in [1, 3]:
            ax_bot.set_xlabel("Trace number")
            
    plt.savefig("figures/interpretation_merging_examples.jpg", dpi=600)
    if show:
        plt.show()
    else:
        plt.close()

    

def plot_cross_track_difference(show: bool = False):
    import itertools

    all_data = interpretations.merge_all_interpretations()
    tree = scipy.spatial.KDTree(
        np.transpose([all_data.geometry.x, all_data.geometry.y])
    )

    distances, indices = tree.query(all_data[["easting", "northing"]])

    radar_keys = pd.Series(all_data["radar_key"].unique(), name="radar_key").to_frame()
    radar_keys[["glacier", "date_str"]] = radar_keys["radar_key"].str.split("-", expand=True).iloc[:, :2]
    radar_keys["year"] = radar_keys["date_str"].str.slice(0, 4)

    pairs = []
    for glacier, glacier_keys in radar_keys.groupby("glacier"):

        for year, in_year in glacier_keys.groupby("year"):
            
            pairs += list(itertools.combinations_with_replacement(in_year["radar_key"].values, 2))


    out_list = []
    for first_key, second_key in pairs:
        if first_key == second_key:
            continue

        first = all_data[all_data["radar_key"] == first_key]
        second = all_data[all_data["radar_key"] == second_key]

        tree = scipy.spatial.KDTree(
            np.transpose([first.geometry.x, first.geometry.y])
        )

        distances, indices = tree.query(np.transpose([second.geometry.x, second.geometry.y]))

        distance_mask = distances < 10

        if np.count_nonzero(distance_mask) == 0:
            continue

        second = second[distance_mask]
        second["other_thickness"] = first["thickness"].values[indices[distance_mask]]
        second["other_temperate"] = first["temperate"].values[indices[distance_mask]]

        out_list.append(second[["thickness", "other_thickness", "temperate_frac", "temperate", "other_temperate"]])

    cmps = pd.concat(out_list)
    cmps["temperate_frac"] *= 100

    cmps["diff"] = cmps["thickness"] - cmps["other_thickness"]
    cmps["temperate_diff"] = cmps["temperate"] - cmps["other_temperate"]

    temperate_bins = np.linspace(-0.01, 101, 11)
    bin_centers = (temperate_bins[1:] - np.diff(temperate_bins) / 2)
    cmps["temperate_bin"] = bin_centers[np.digitize(cmps["temperate_frac"], bins=temperate_bins) - 1]

    variances = []

    plt.figure(figsize=(8, 5))
    var_axis = plt.subplot2grid((3, 2),(1, 1), rowspan=2)
    for i in range(100):

        # binned = cmps.groupby("temperate_bin")["diff"].quantile([0.25, 0.5, 0.75])
        variance = cmps.sample(frac=0.2, random_state=i).groupby("temperate_bin")["diff"].apply(lambda s: 1.426 * np.median(np.abs(s - np.median(s))))
        variances.append(variance)

        var_axis.plot(variance, alpha=0.05, color="black")

    variance = pd.concat(variances)
    var_axis.plot(variance.groupby(variance.index).median(), color="black")

    for i, (name, color, data) in enumerate([("All bed data","gray",  cmps), ("Temperate bed", "purple", cmps[cmps["temperate_frac"] > 10]), ("Cold bed", "blue", cmps[cmps["temperate_frac"] <= 10]), ("Temperate ice", "red", cmps.drop(columns=["diff"]).rename(columns={"temperate_diff": "diff"}))]):
        axis = plt.subplot2grid((3, 2), (i % 3, i // 3))

        data = data[data["diff"] != 0.]

        axis.hist(data["diff"], bins=np.linspace(-10, 10, 100), color=color, alpha=0.5)
        if i < 2:
            axis.tick_params(labelbottom=False)
        if i == 1:
            axis.set_ylabel("Frequency")

        if i == 2:
            axis.set_xlabel("Cross-track difference (m)")

        plt.text(0.02, 0.97, "abcd"[i], transform=axis.transAxes, va="top", ha="left")
        plt.text(0.98, 0.97, name, transform=axis.transAxes, va="top", ha="right")
        plt.text(
            x=0.02,
            y=0.5,
            s="\n".join(
                [
                    f"Median: {data["diff"].median():.1f} m",
                    f"NMAD: {1.426 * np.median(np.abs(data["diff"] - np.median(data["diff"]))): .1f} m",
                ]
            ),
            transform=axis.transAxes,
            va="center",
            path_effects=[
                matplotlib.patheffects.withStroke(
                    linewidth=4, foreground="white"
                )
            ],
        )
        
    plt.text(0.02, 0.99, "e", transform=var_axis.transAxes, va="top", ha="left")
    var_axis.set_xlabel("Temperate ice fraction (%)")
    var_axis.set_ylabel("NMAD (m)")

    plt.subplots_adjust(left=0.07, bottom=0.1, right=0.986, top=0.99, wspace=0.136, hspace=0.207)
    plt.savefig("figures/cross_track_difference.jpg", dpi=600)

    if show:
        plt.show()
    else:
        plt.close()


    

def generate_all_figures(show: bool = True):
    plot_dronbreen_examples(show=show)
    plot_centerline_profiles(show=show)
    plot_model_comparison(show=show)
    plot_glathida_comparison(show=show)
    plot_interpretation_merging(show=show)
    plot_cross_track_difference(show=show)


if __name__ == "__main__":
    generate_all_figures()
