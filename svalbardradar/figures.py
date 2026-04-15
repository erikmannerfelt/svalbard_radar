from pathlib import Path
import datetime
import functools

import geopandas as gpd
import matplotlib.patheffects
import matplotlib.ticker
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import scipy.interpolate
import scipy.optimize
import tqdm
import xarray as xr
import textalloc

from svalbardradar import interpretations
from svalbardradar.tools import paths, misc, stats
import svalbardradar.analysis

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

    dronbreen_outline = gpd.read_file("shapes/dronbreen_outline_20240828.geojson")

    data = svalbardradar.interpretations.merge_all_interpretations()
    data = data[data.intersects(dronbreen_outline.geometry[0])]

    interp_kwargs = {
        "res": 25.0,
        "outline": dronbreen_outline.geometry,
    }

    gridded = svalbardradar.interpretations.grid_interpretations("dronbreen", outline=dronbreen_outline.geometry[0])

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
            img = axis.imshow(gridded["thickness"], cmap="Blues", zorder=2, extent=extent, vmin=0)
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
            dataset = dataset.reset_coords(["easting", "northing", "distance"])
            dataset.coords["trace_n"] = "x", np.arange(dataset.x.shape[0])
            dataset = dataset.swap_dims(x="trace_n", y="depth").sel(trace_n=slice(info["start_trace"], None))

            diffs = dataset[["easting", "northing"]].diff("trace_n").fillna(0)

            dataset["distance"] = ((diffs["easting"] ** 2 + diffs["northing"] ** 2) ** 0.5).cumsum("trace_n")
            dataset["distance"] += np.linspace(0, 1e-3, dataset.data.shape[1])

            for standstill in info["standstills"]:
                dataset = dataset.drop_sel(trace_n=np.arange(*standstill))

            dataset = dataset.swap_dims(trace_n="distance").sel(
                distance=dataset["distance"].where(dataset["distance"] < 2050, drop=True).values
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
                        path_effects=[matplotlib.patheffects.withStroke(linewidth=2, foreground="white")],
                    )
                axis2.plot(dataset["easting"], dataset["northing"], color="black")

    plt.tight_layout()
    inset: plt.Axes = axes[0, 0].inset_axes((0.0, 0.6, 0.4, 0.4))
    inset.set_xticks([])
    inset.set_yticks([])
    inset.add_patch(outline_polygon())
    for _, line in data.groupby("radar_key"):
        line = line.sort_values("distance")
        inset.plot(line.geometry.x, line.geometry.y, linewidth=0.5, color="black", zorder=2)

    for i, axis in enumerate([inset, *axes.ravel()]):
        xvals = [0.41 if i == 1 else 0.01]

        if i in [3, 4]:
            xvals += [0.95]

        for j, xval in enumerate(xvals):
            axis.text(
                xval,
                0.99,
                "abcde"[i] + ("'" if j == 1 else ""),
                transform=axis.transAxes,
                fontsize=10,
                va="top",
                path_effects=[matplotlib.patheffects.withStroke(linewidth=2, foreground="white")],
            )

    Path("figures").mkdir(exist_ok=True)
    plt.savefig("figures/dronbreen_example.jpg", dpi=600)

    if show:
        plt.show()


def plot_user_spread(show: bool = True):
    import svalbardradar.interpretations
    from svalbardradar.tools import paths
    from matplotlib.backends.backend_pdf import PdfPages

    radar_keys = [
        "moysalbreen-20220222-DAT_0750_A1_6",
        "vallakrabreen-20210513-DAT_0014_A1_31",
        "ragna_mariebreen-20240412-DAT_0404_A1_1",
        "filantropbreen-20240406-DAT_0372_A1_1",
    ]

    all_data = svalbardradar.interpretations.merge_all_interpretations()

    all_data["glacier"] = all_data["radar_key"].str.split("-", expand=True).iloc[:, 0]
    all_data["part_idx"] = all_data["part_idx"].astype(int)
    all_data["bed_elevation"] = all_data["elevation"] - all_data["thickness"]

    all_data["temp_elevation"] = all_data["bed_elevation"] + all_data["thickness"] * all_data["temperate_frac"]

    out_path = Path("figures/all_interpretations.pdf")
    out_dir = Path("figures/all_interpretations_perprofile")
    out_dir.mkdir(exist_ok=True, parents=True)
    radar_keys = []
    with PdfPages(out_path) as pdf, tqdm.tqdm(total=all_data["radar_key"].unique().shape[0]) as progress_bar:
        for glacier, all_glacier_data in all_data.groupby("glacier"):
            for radar_key, data in all_glacier_data.groupby("radar_key"):
                radar_key = str(radar_key)
                _, date_str, filename = radar_key.split("-")

                data = data.copy()
                data["distance"] = (
                    (data[["easting", "northing"]].diff().fillna(0) ** 2).sum(axis="columns") ** 0.5
                ).cumsum() / 1e3

                fig = plt.figure(figsize=(8.3, 11.7))
                axes = fig.subplots(3, 1, sharex=True, sharey=True, height_ratios=[0.5, 0.25, 0.25])

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
                max_d = 0.0
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
                            f"Mean thickness uncertainty: {data['thickness_nmad'].mean():.2f} m",
                            f"Mean temperate ice fraction: {100 * data['temperate_frac'].mean():.2f}%",
                            f"Mean temperate ice fraction uncertainty: {100 * data['temperate_frac_std'].mean():.2f}%",
                        ]
                    ),
                    transform=axes[0].transAxes,
                )

                labeled = set()
                all_points = interpretations.read_interpretations(radar_key=radar_key, step_m=5.0).reset_index()
                for _, points in all_points.groupby(["user", "line_i"]):
                    kind = points["kind"].iloc[0].replace("temperate_ice", "temperate")
                    axes[1].plot(
                        points["x"],
                        points["depth"],
                        color=DIGITIZE_CLASS_PROPS[kind]["color"],
                        alpha=0.3,
                        label=DIGITIZE_CLASS_PROPS[kind]["name"] if kind not in labeled else None,
                    )
                    labeled.add(kind)

                diffs = (data["distance"].diff().fillna(0) > (25 / 1000)).cumsum()
                for _, data_split in data.groupby(diffs):
                    axes[2].fill_between(
                        data_split["x"],
                        data_split["thickness_lower"],
                        data_split["thickness_upper"],
                        color="#555",
                        alpha=0.5,
                        label="Thickness (+- 25%)",
                        zorder=2,
                    )
                    axes[2].plot(
                        data_split["x"],
                        data_split["thickness"],
                        color="#555",
                        path_effects=[matplotlib.patheffects.withStroke(linewidth=3, foreground="black")],
                        zorder=4,
                        label="Thickness (median)",
                    )
                    axes[2].fill_between(
                        data_split["x"],
                        data_split["thickness"] - data_split["temperate_lower"],
                        data_split["thickness"] - data_split["temperate_upper"],
                        color="red",
                        alpha=0.5,
                        label="Temperate ice (+- 25%)",
                        zorder=1,
                    )
                    axes[2].plot(
                        data_split["x"],
                        data_split["thickness"] - data_split["thickness"] * data_split["temperate_frac"],
                        color="red",
                        zorder=3,
                        label="Temperate ice (median)",
                    )

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
                map.set_xticklabels(
                    [str(int(xtick)) if i in [2, len(xticks) - 2] else "" for i, xtick in enumerate(xticks)]
                )

                map.set_xlabel("Easting (m)")

                axes[1].text(
                    0.5, 1.0, "Individual interpretations", ha="center", va="bottom", transform=axes[-2].transAxes
                )
                axes[1].legend()

                axes[2].text(0.5, 1.0, "Merged interpretations", ha="center", va="bottom", transform=axes[-1].transAxes)
                axes[2].set_ylabel("Depth (m)")
                axes[2].set_xlabel("Traces")

                # Because of split lines, legend entries may be repeated
                hand, labl = axes[2].get_legend_handles_labels()
                handout = []
                lablout = []
                for h, l in zip(hand, labl):
                    if l not in lablout:
                        lablout.append(l)
                        handout.append(h)
                axes[2].legend(handout, lablout)

                ylim = axes[2].get_ylim()
                axes[2].set_ylim(min(ylim[1], 350), -10)

                for axis in axes[1:]:
                    axis.grid(alpha=0.5, zorder=0)

                fig.text(0.02, 0.99, f"https://radar.mannerfelt.org/digitize/{radar_key}", va="top", fontsize=7)
                fig.text(0.03, 0.97, radar_key.replace("-", "-\n"), ha="left", va="top", fontsize=14)

                plt.subplots_adjust(left=0.1, bottom=0.05, right=0.95, top=0.99, hspace=0.05)

                fig.text(
                    0.99,
                    0.01,
                    f"Created {datetime.datetime.now().date().isoformat()}",
                    ha="right",
                    va="bottom",
                    fontsize=8,
                )

                plt.savefig(out_dir / f"interpretations_{radar_key}.pdf")
                fig.text(0.03, 0.01, str(len(radar_keys) + 1), ha="right", va="bottom", fontsize=8)

                pdf.savefig(fig)
                plt.close(fig)
                progress_bar.update()
                radar_keys.append(radar_key)


def plot_centerline_profiles(show: bool = True):
    import svalbardradar.interpretations
    import svalbardradar.analysis

    radar_keys = [
        ["mettebreen-20230305-DAT_0235_A1_8"],
        # "filantropbreen-20240406-DAT_0372_A1_1",
        ["moysalbreen-20220222-DAT_0749_A1_1"],
        # "rugaasfonna-20220218-DAT_0723_A1_1",
        # "lofthusbreen-20250326-DAT_0057_A1_1",
        ["finsterwalderbreen-20250407-DAT_0171_A1_1"],
        ["ragna_mariebreen-20240412-DAT_0404_A1_1"],
        ["winsnesbreen-20240503-DAT_0014_A1_1"],
        ["jinnbreen-20240206-DAT_0447_A1_1", "jinnbreen-20240206-DAT_0448_A1_1"],
        ["dronbreen-20230220-DAT_0009_A1_1"],
        # "dronbreen-20250327-DAT_0065_A1_1",
        ["kroppbreen-20230228-DAT_0042_A1_1"],
        ["slakbreen-20240310-DAT_0286_A1_1"],
        ["edvardbreen-20240411-DAT_0396_A1_1"],
    ]

    n_cols = 2
    n_rows = int(np.ceil(len(radar_keys) / n_cols))

    meta = {
        "mettebreen-20230305-DAT_0235_A1_8": {
            "stop_distance": 3.35,
        },
    }

    nice_names = {
        "dronbreen": "Drønbreen",
        "moysalbreen": "Møysalbreen",
        "ragna_mariebreen": "Ragna-Mariebreen",
    }

    fig = plt.figure(figsize=(6, 8))
    axes = fig.subplots(nrows=n_rows, ncols=n_cols)

    all_data = svalbardradar.interpretations.merge_all_interpretations()

    temperate_frac_minmax = [100, 0]

    for i, radar_key in enumerate(radar_keys):
        row = int(i / n_cols)
        col = i - row * n_cols
        axis: plt.Axes = axes[row, col]

        # data = gpd.read_feather(Path(f"cache/interpretations/per_radargram/{radar_key}.feather"))
        # data = svalbardradar.interpretations.merge_interpretations(radar_key)
        data = all_data[all_data["radar_key"].isin(radar_key)]

        radar_meta = meta.get(radar_key[0], {})

        data = data.sort_values(["radar_key", "distance"])

        glacier = radar_key[0].split("-")[0]

        if data.iloc[10]["elevation"] > data.iloc[-10]["elevation"]:
            data["distance"] = data["distance"].max() - data["distance"]
            data = data.iloc[::-1]

        data["distance"] = (
            (data[["easting", "northing"]].diff(axis="rows").fillna(0) ** 2).sum(axis="columns") ** 0.5
        ).cumsum() / 1e3

        if "start_distance" in radar_meta:
            data = data[data["distance"] > radar_meta["start_distance"]]
        if "stop_distance" in radar_meta:
            data = data[data["distance"] < radar_meta["stop_distance"]]

        data["bed_elevation"] = data["elevation"] - data["thickness"]

        data["temp_elevation"] = data["bed_elevation"] + data["temperate"]

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

        if row >= 1:
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

        inset = axis.inset_axes((-0.08, 0.4, 0.35, 0.35))
        inset.set_axis_off()

        temperate_frac = (data["temperate_frac"] * data["thickness"]).sum() / data["thickness"].sum()

        temperate_frac_minmax = min(temperate_frac_minmax[0], temperate_frac * 100), max(temperate_frac_minmax[1], temperate_frac * 100)
        inset.pie(
            [temperate_frac, 1- temperate_frac], 
            colors=["#f77", "lightblue"],
            labels=[f"{100 * temperate_frac:.0f}%", ""],
            textprops={"fontsize": 8},
            labeldistance=1.3,
            wedgeprops={"edgecolor": "#333"}
        )

    # This is not an analytical min/max for the entire dataset, but Finster is max and Winsnes is min, so it's okay.
    svalbardradar.analysis.record_information(
        {
            "temperate_fractions": {
                "min": round(temperate_frac_minmax[0]),
                "max": round(temperate_frac_minmax[1]),
            }
        }
    )

    plt.tight_layout()
    plt.savefig("figures/centerline_profiles.jpg", dpi=600)

    if show:
        plt.show()


def plot_model_comparison(show: bool = True, histogram: bool = False, correct_topo: bool = True):
    import svalbardradar.comparisons

    data = svalbardradar.comparisons.sample_models()

    # models = [str(col).replace("_thickness", "") for col in data if "_thickness" in col]
    models = ["furst", "millan", "vanpelt"]

    if not correct_topo:
        for col in ["thickness", *[f"{model}_thickness" for model in models]]:
            data[col] = data[f"{col}_uncorr"]

    ref_names = {
        "furst": "Fürst et al., (2018)",
        "farinotti": "Farinotti et al., (2019)",
        "millan": "Millan et al., (2022)",
        "vanpelt": "van Pelt & Frank (2025)",
        "frank": "Frank et al., (in review)",
    }

    n_rows = 1
    n_cols = 3
    fig = plt.figure(figsize=(8.3, 3.0))
    axes = fig.subplots(nrows=n_rows, ncols=n_cols, sharex=True, sharey=True)

    # Hack to make sure the array is always indexable as [row, col]
    if len(axes.shape) == 1:
        axes = axes[None, :]

    max_thickness = data[["thickness", *[f"{model}_thickness" for model in models]]].max().max()

    step_size = 7.5
    thickness_bins = np.arange(0, max_thickness - (max_thickness % step_size) + step_size * 2, step_size)

    r_minmax = [1, 0]
    bias_minmax = [1000, -1000]

    for i, model in enumerate(models):
        col = i % n_cols
        row = int((i - col) / n_cols)
        axis: plt.Axes = axes[row, col]

        axis.set_title(ref_names[model], fontsize=10)

        subset = data.dropna(subset=["thickness", f"{model}_thickness"], how="any")

        if histogram:
            hist2 = np.histogram2d(subset[f"{model}_thickness"], subset["thickness"], bins=thickness_bins)[0][::-1, :]
            hist2 = np.ma.masked_array(hist2, mask=hist2 == 0)
            axis.imshow(hist2, extent=(0.0, thickness_bins[-1], 0.0, thickness_bins[-1]))
        else:
            kde = scipy.stats.gaussian_kde(
                subset[["thickness", f"{model}_thickness"]].sample(n=5000, random_state=0).astype("float32").T
            )
            density = kde.evaluate(subset[["thickness", f"{model}_thickness"]].astype("float32").T)
            # Remove extremely sparsely located points (i.e. based on just one track)
            mask = density > np.percentile(density, 0.8)
            axis.scatter(
                subset["thickness"][mask],
                subset[f"{model}_thickness"][mask],
                c=density[mask],
                edgecolor="none",
                s=2,
            )
            plt.xlim(0, thickness_bins.max())
            plt.ylim(0, thickness_bins.max())

        xlim = axis.get_ylim()
        axis.plot([xlim[0], xlim[1]], [xlim[0], xlim[1]], color="black")

        diff = subset[f"{model}_thickness"] - subset["thickness"]

        nmad = stats.nmad(diff)
        bias = diff.median()
        pearson = subset["thickness"].corr(subset[f"{model}_thickness"])

        if correct_topo:
            bias_minmax = [min(bias_minmax[0], bias), max(bias_minmax[1], bias)] 
            r_minmax = [min(r_minmax[0], pearson), max(r_minmax[1], pearson)] 
            svalbardradar.analysis.record_information(
                {
                    "inversion": {
                        model: {
                            "nmad": nmad,
                            "r": svalbardradar.analysis.format_float(pearson, 2),
                        }
                    }
                }
            )
        axis.text(
            x=0.03,
            y=0.97,
            s="\n".join(
                [
                    f"Median: {bias:.1f} m",
                    f"NMAD: {nmad: .1f} m",
                    f"r = {pearson:.2f}",
                ]
            ),
            transform=axis.transAxes,
            fontsize=9,
            va="top",
            path_effects=[matplotlib.patheffects.withStroke(linewidth=4, foreground="white")],
        )

        axis.set_xlabel("Our thickness (m)")

        if col == 0:
            axis.set_ylabel("Modelled thickness (m)")

    if correct_topo:
        svalbardradar.analysis.record_information(
            {
                "inversion": {
                    "min_r": svalbardradar.analysis.format_float(r_minmax[0], 2),
                    "max_r": svalbardradar.analysis.format_float(r_minmax[1], 2),
                    "min_bias": bias_minmax[0],
                    "max_bias": bias_minmax[1],
                }
            }
        )
    plt.subplots_adjust(left=0.07, bottom=0.15, right=0.98, top=0.91, wspace=0.1)

    Path("figures/").mkdir(exist_ok=True)
    plt.savefig(f"figures/thickness_vs_models{'_uncorr' if not correct_topo else ''}.jpg", dpi=400)

    if show:
        plt.show()


def plot_glathida_comparison(show: bool = True, histogram: bool = False, correct_topo: bool = True):
    import scipy.spatial

    import svalbardradar.comparisons

    data = svalbardradar.comparisons.sample_glathida()

    if not correct_topo:
        for col in ["glathida_thickness", "thickness"]:
            data[col] = data[f"{col}_uncorr"]
        data["glathida_diff"] = data["glathida_thickness"] - data["thickness"]
        # data = data.rename(columns={"glathida_thickness_uncorr": "glathida_thickness"

    year_intervals = [1990, 2010, 2025]
    markers = ["x", "s", "o"]

    data["glathida_group"] = np.digitize(data["glathida_year"], year_intervals)
    max_thickness = data[["glathida_thickness", "thickness"]].max().max()

    step_size = 5
    thickness_bins = np.arange(0, max_thickness - (max_thickness % step_size) + step_size * 2, step_size)

    fig = plt.figure(figsize=(8.3, 3.2))
    axes = fig.subplots(ncols=3, sharex=True, sharey=True)
    for i, group in data.groupby("glathida_group"):
        axis: plt.Axes = axes[i]
        bias = group["glathida_diff"].median()
        if i == 0:
            title = f"before {year_intervals[0]}"
        elif i == (len(year_intervals) - 1):
            title = f"after {year_intervals[-2]}"
        else:
            title = f"{year_intervals[i - 1]}–{year_intervals[i]}"
        axis.set_title(title, fontsize=10)

        pearson = group["thickness"].corr(group["glathida_thickness"])

        axis.text(
            0.03,
            0.97,
            "\n".join(
                [
                    f"Median: {bias:.1f} m",
                    f"NMAD: {stats.nmad(group['glathida_diff']):.1f} m",
                    f"r: {pearson:.2f}",
                    f"n: {group.shape[0]}",
                ]
            ),
            transform=axis.transAxes,
            fontsize=9,
            ha="left",
            va="top",
            path_effects=[matplotlib.patheffects.withStroke(linewidth=4, foreground="white")],
        )

        def residuals(coefs, x, y):
            return coefs[0] * x + coefs[1] - y

        # Calculate a slope (should be =1 in the best case) and print the fit. Also calculate a <150 m slope separately.
        x = []
        y = []
        for _, vals in group.groupby(np.digitize(group["thickness"], bins=thickness_bins)):
            x.append(vals["thickness"].median())
            y.append(vals["glathida_thickness"].median())
        x, y = np.array(x), np.array(y)
        res_full = scipy.optimize.least_squares(residuals, x0=[0.0, 0.0], args=(x, y)).x
        res_150 = scipy.optimize.least_squares(residuals, x0=[0.0, 0.0], args=(x[x < 150], y[x < 150])).x

        if correct_topo:
            key = ["before", "middle", "after"][i]
            svalbardradar.analysis.record_information(
                {
                    "glathida": {
                        f"{key}_slope_full": svalbardradar.analysis.format_float(res_full[0], 2),
                        f"{key}_slope_thin": svalbardradar.analysis.format_float(res_150[0], 2),
                        f"{key}_bias": bias,
                    }
                }
            )

        # print(
        #     f"{label.replace('\n', ': ')}, Linear fit: old = {res_full[0]:.2f}*new + {res_full[1]:.2f}. Linear fit (<150 m): old = {res_150[0]:.2f}*new + {res_150[1]:.2f}"
        # )

        if histogram:
            hist2 = np.histogram2d(group["glathida_thickness"], group["thickness"], bins=thickness_bins)[0][::-1, :]
            hist2 = np.ma.masked_array(hist2, mask=hist2 == 0)
            axis.imshow(hist2, extent=(0.0, thickness_bins[-1], 0.0, thickness_bins[-1]))
        else:
            kde = scipy.stats.gaussian_kde(group[["thickness", "glathida_thickness"]].astype("float32").T)
            axis.scatter(
                group["thickness"],
                group["glathida_thickness"],
                s=5,
                alpha=1,
                c=kde.evaluate(group[["thickness", "glathida_thickness"]].astype("float32").T),
                edgecolor="none",
            )
            plt.xlim(0, thickness_bins.max())
            plt.ylim(0, thickness_bins.max())

        axis.plot([0, max_thickness], [0, max_thickness], color="black")

        if i == 0:
            axis.set_ylabel("GlaThiDa thickness (m)")

        axis.set_xlabel("Our thickness (m)")

    # plt.legend()
    plt.subplots_adjust(left=0.07, bottom=0.13, right=0.99, top=0.93, wspace=0.05)
    # plt.tight_layout()
    Path("figures/").mkdir(exist_ok=True)
    plt.savefig(f"figures/thickness_vs_glathida{'_uncorr' if not correct_topo else ''}.jpg", dpi=400)

    if show:
        plt.show()


def plot_model_temperate_cold_performance(show: bool = True):
    import svalbardradar.comparisons

    data = svalbardradar.comparisons.sample_models()
    data["glacier"] = data["radar_key"].str.split("-", expand=True).iloc[:, 0]

    glaciers = ["filantropbreen", "dronbreen", "bergmesterbreen"]

    models = [str(col).replace("_thickness", "") for col in data if "_thickness" in col and "uncorr" not in col]

    colors = {
        "cold": "lightblue",
        "temperate": "purple",
        "all": "grey",
    }
    case_names = {
        "temperate": "Temperate bed",
        "cold": "Cold bed",
        "all": "All data",
    }
    box_distance = 5
    fig = plt.figure(figsize=(8, 5))

    cold_temp_diffs = {}
    axes = []
    for k, glacier in enumerate([*glaciers, "all"]):
        if glacier == "all":
            df = data
            axis = plt.subplot2grid((3, len(glaciers)), (1, 0), rowspan=2, colspan=3)
        else:
            df = data[data["glacier"] == glacier]
            axis = plt.subplot2grid((3, len(glaciers)), (0, k), rowspan=1, colspan=1)

        axes.append(axis)
        for i, model in enumerate(models):
            diff = df[f"{model}_thickness"] - df["thickness"]

            cold = df["bed_type"] == "certain_cold"
            temperate = df["bed_type"] == "certain_temperate"

            if glacier == "all":
                cold_temp_diffs[model] = diff[cold].median() - diff[temperate].median()

            for j, (case, arr) in enumerate([("cold", diff[cold]), ("temperate", diff[temperate]), ("all", diff)]):
                arr = arr[np.abs(arr) < 300]
                axis.boxplot(
                    [arr],
                    positions=[j - 1 + box_distance * i],
                    showfliers=False,
                    manage_ticks=False,
                    widths=0.8,
                    patch_artist=True,
                    boxprops={"facecolor": colors[case], "alpha": 0.5},
                    medianprops={"color": "black"},
                    label=case_names[case] if i == 0 else None,
                )

            xtick_vals = np.arange(len(models)) * box_distance
            axis.set_xticks(
                xtick_vals, [svalbardradar.comparisons.ref_names(model, short=glacier != "all") for model in models]
            )

            axis.set_ylim(-200, 200)
            yticks = axis.get_yticks()
            if k in [0, 3]:
                axis.set_yticks(yticks)
            else:
                axis.set_yticks(yticks, labels=[""] * len(yticks))
            xlim = (-2, xtick_vals.max() + 2)
            # xlim = axis.get_xlim()
            axis.hlines(0, *xlim, zorder=0, color="grey", linestyles="--")
            axis.set_xlim(xlim)

            if k == 3:
                axis.set_ylabel("Thickness difference (m)")
                axis.legend(loc="lower center", ncols=3)
            elif k == 0:
                axis.set_ylabel("Thickness diff. (m)")

    cold_temp_diffs.update(
        {
            "mean": np.mean(list(cold_temp_diffs.values())),
            "min": np.min(list(cold_temp_diffs.values())),
            "max": np.max(list(cold_temp_diffs.values())),
        }
    )

    svalbardradar.analysis.record_information(
        {
            "inversion": {
                "coldvstemp": cold_temp_diffs,
            }
        }
    )
    plt.tight_layout()

    for i, axis in enumerate(axes):
        axis.text(
            0.03 if i < 3 else 0.01,
            0.97,
            "abcdef"[i],
            transform=axis.transAxes,
            va="top",
            path_effects=[matplotlib.patheffects.withStroke(linewidth=2, foreground="white")],
        )
        if i < (len(axes) - 1):
            axis.text(
                0.5,
                0.97,
                glaciers[i].capitalize().replace("akra", "åkra").replace("Dron", "Drøn"),
                transform=axis.transAxes,
                va="top",
                ha="center",
                fontsize=8,
            )

    Path("figures/").mkdir(exist_ok=True)
    plt.savefig("figures/thickness_vs_cold_temperate.jpg", dpi=400)

    if show:
        plt.show()


def plot_perglacier_temperate_cold_performance(show: bool = False):
    import svalbardradar.comparisons

    data = svalbardradar.comparisons.sample_models()
    data["glacier"] = data["radar_key"].str.split("-", expand=True).iloc[:, 0]

    glacier_pts = gpd.read_file("shapes/glacier_locations.geojson")
    glacier_names = glacier_pts.set_index("key")["name"].to_dict()

    models = [str(col).replace("_thickness", "") for col in data if "_thickness" in col and "uncorr" not in col]

    colors = {
        "cold": "lightblue",
        "temperate": "purple",
        "all": "grey",
    }
    case_names = {
        "temperate": "Temperate bed",
        "cold": "Cold bed",
        "all": "All data",
    }
    box_distance = 5

    fig = plt.figure(figsize=(8, 5))
    axes = fig.subplots(5, 5, sharex=True)

    for k, (glacier_key, df) in enumerate(data.groupby("glacier")):
        axis: plt.Axes = axes.ravel()[k]
        row = k // axes.shape[1]
        col = k % axes.shape[0]
        for i, model in enumerate(models):
            diff = df[f"{model}_thickness"] - df["thickness"]

            cold = df["bed_type"] == "certain_cold"
            temperate = df["bed_type"] == "certain_temperate"

            for j, (case, arr) in enumerate([("cold", diff[cold]), ("temperate", diff[temperate]), ("all", diff)]):
                arr = arr[np.abs(arr) < 300]
                axis.boxplot(
                    [arr],
                    positions=[j - 1 + box_distance * i],
                    showfliers=False,
                    manage_ticks=False,
                    widths=0.8,
                    patch_artist=True,
                    boxprops={"facecolor": colors[case], "alpha": 0.5},
                    medianprops={"color": "black"},
                    label=case_names[case] if i == 0 else None,
                )

            xtick_vals = np.arange(len(models)) * box_distance
            axis.set_xticks(xtick_vals, [svalbardradar.comparisons.ref_names(model, short=True) for model in models])

            axis.set_ylim(-200, 200)
            yticks = axis.get_yticks()

            if col == 0 and row in [0, 4]:
                axis.tick_params("y", pad=0.01, labelsize=8)
            else:
                axis.set_yticks(yticks, labels=[""] * len(yticks))

            xlim = (-2, xtick_vals.max() + 2)
            axis.hlines(0, *xlim, zorder=0, color="grey", linestyles="--")
            axis.set_xlim(xlim)

            fraction = np.count_nonzero(temperate) / np.count_nonzero(cold | temperate)
            axis.text(0.01, 0.01, f"T: {fraction * 100:.0f}%", va="bottom", transform=axis.transAxes, fontsize=8)
            axis.text(
                0.5,
                0.97,
                glacier_names[glacier_key],
                ha="center",
                va="top",
                transform=axis.transAxes,
                fontsize=8,
                path_effects=[matplotlib.patheffects.withStroke(linewidth=2, foreground="white")],
            )

            if col == 0 and row == 2:
                axis.set_ylabel("Thicknes difference (m)")
    plt.subplots_adjust(left=0.04, bottom=0.05, right=0.99, top=0.99, wspace=0.1, hspace=0.1)
    plt.savefig("figures/perglacier_thickness_vs_cold_temperate.jpg", dpi=500)
    if show:
        plt.show()
    else:
        plt.close()


def plot_elevation_vs_temp_diff(show: bool = False):
    import svalbardradar.comparisons

    data = svalbardradar.comparisons.sample_models()
    data["glacier"] = data["radar_key"].str.split("-", expand=True).iloc[:, 0]

    models = [
        str(col).replace("_thickness", "")
        for col in data
        if "_thickness" in col
        if "farinotti" not in col and "uncorr" not in col
    ]

    elevs = data.groupby("glacier")["elevation"].describe()
    data["elev_norm"] = (data["elevation"] - elevs["min"][data["glacier"].values].values) / (
        elevs["max"] - elevs["min"]
    )[data["glacier"].values].values

    bins = np.linspace(-0.01, 1.01, 11)
    bin_centers = bins[1:] - np.mean(np.diff(bins)) / 2
    data["elev_bin"] = bin_centers[np.digitize(data["elev_norm"], bins=bins) - 1]

    data = data[data["bed_type"].isin(["certain_cold", "certain_temperate"])]

    bin_axes = []
    line_axes = []
    fig = plt.figure(figsize=(8, 4))
    # axes = fig.subplots(3, len(models), sharex=True, sharey="row")
    for i, model in enumerate(models):
        axis = plt.subplot2grid((6, 2), (i * 2, 1), rowspan=2, fig=fig)
        line_axes.append(axis)

        plt.text(0.5, 0.97, svalbardradar.comparisons.ref_names(model), ha="center", va="top", transform=axis.transAxes)
        # axis.set_title(svalbardradar.comparisons.ref_names(model))

        data["diff"] = data[f"{model}_thickness"] - data["thickness"]

        for part, per_part in data.groupby("bed_type"):
            grouped = per_part.groupby("elev_bin")["diff"]
            df = grouped.median()

            color = "purple" if part == "certain_temperate" else "blue"

            axis.errorbar(
                df.index,
                df,
                yerr=grouped.std(),
                color=color,
                label=part.replace("certain_", "").capitalize() + " bed",
            )

            if i == 0:
                ax2 = plt.subplot2grid((6, 2), (0 if part == "certain_cold" else 3, 0), rowspan=3)
                bin_axes.append(ax2)

                ax2.bar(x=df.index, height=grouped.count(), width=np.mean(np.diff(bins)), color=color, alpha=0.5)

    bin_axes[0].set_ylabel("Cold bed count")
    bin_axes[1].set_ylabel("Temperate bed count")
    # for i in (2,):
    #     axes[i, 0].set_ylabel("Difference (m)")
    xticks = np.linspace(0.0, 1.0, 5)

    for i, axis in enumerate(bin_axes):
        axis.set_xticks(xticks)
        axis.ticklabel_format(style="sci", axis="y", scilimits=(0, 0), useMathText=True)
        if i != 1:
            axis.set_xticklabels([""] * len(xticks))

    for i, axis in enumerate(line_axes):
        axis.grid(alpha=0.5)

        axis.set_ylim(-130, 210)
        axis.set_xticks(xticks)
        if i == 1:
            axis.set_ylabel("Difference (m)")
        if i != 2:
            axis.set_xticklabels([""] * len(xticks))

    for i, axis in enumerate([*bin_axes, *line_axes]):
        plt.text(0.02, 0.97, "abcdefghi"[i], ha="left", va="top", transform=axis.transAxes)

    # axes[2, 0].legend(fontsize=8)
    for axis in [bin_axes[-1], line_axes[-1]]:
        axis.set_xlabel("Normalized elevation")
    plt.subplots_adjust(left=0.08, bottom=0.10, right=0.98, top=0.95, wspace=0.2, hspace=0.7)
    plt.savefig("figures/elevation_vs_temp_diff.jpg", dpi=500)

    if show:
        plt.show()
    else:
        plt.close()


def s20_hillshade() -> Path:
    dtm20_path = CACHE_PATH / "NP_S0_DTM20.zip"
    misc.download_large_file(
        dtm20_path, "https://public.data.npolar.no/kartdata/S0_Terrengmodell/Mosaikk/NP_S0_DTM20.zip"
    )
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
            ],
            check=True,
        )

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

    cache_filepath.parent.mkdir(exist_ok=True, parents=True)
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
            "x": 0.01,
            "y": 0.99,
            "va": "top",
            "ha": "left",
            "path_effects": [matplotlib.patheffects.withStroke(linewidth=2, foreground="white")],
            "fontsize": 10,
        },
        "scalebar_line": {
            "linewidth": 1,
            "color": "#333",
            "path_effects": [matplotlib.patheffects.withStroke(linewidth=1.5, foreground="white")],
        },
        "scalebar_label": {
            "fontsize": 8,
            "color": "#333",
            "path_effects": [matplotlib.patheffects.withStroke(linewidth=0.7, foreground="white")],
        },
        "glacier_label": {
            "textsize": 10,  # Fontsize
            "color": "black",
            "path_effects": [matplotlib.patheffects.withStroke(linewidth=1, foreground="white")],
        },
        "glacier_label_line": {
            "color": "white",
            "linewidth": 1,
            "path_effects": [matplotlib.patheffects.withStroke(linewidth=2, foreground="black")],
        },
        "radar_lines": {
            "color": "red",
            "linewidth": 1,
            "path_effects": [matplotlib.patheffects.withStroke(linewidth=1, foreground="black")],
        },
    }

    outlines = get_svalbard_outlines()
    glacier_outlines = get_svalbard_glaciers()
    glacier_outlines["used"] = glacier_outlines.geometry.intersects(
        shapely.geometry.MultiPoint(np.transpose([glaciers.geometry.x, glaciers.geometry.y]))
    )
    outlines_dissolved = glacier_outlines.dissolve()

    radar_track_pts = gpd.read_feather("cache/interpretations/interp_all.feather")
    radar_lines_list = []
    for (radar_key, part_idx), pts in radar_track_pts.groupby(["radar_key", "part_idx"]):
        if pts.shape[0] < 2:
            continue

        radar_lines_list.append(
            {
                "radar_key": radar_key,
                "part_idx": part_idx,
                "geometry": shapely.geometry.LineString(pts.sort_values("distance").geometry.values),
            }
        )
    radar_lines = gpd.GeoDataFrame(pd.DataFrame.from_records(radar_lines_list), crs=radar_track_pts.crs)

    def plot_background(axis: plt.Axes, xlim, ylim, overview_level):
        with rasterio.open(hillshade_path, overview_level=overview_level) as raster:
            window = rasterio.windows.from_bounds(xlim[0], ylim[0], xlim[1], ylim[1], transform=raster.transform)
            arr = np.clip(raster.read(1, masked=True, window=window, boundless=True).filled(181) / 181, min=0, max=1)
            transform = rasterio.windows.transform(window=window, transform=raster.transform)

            lighten_scale = 0.5
            arr = (arr * lighten_scale) + (1 - lighten_scale)

            land_mask = rasterio.features.rasterize(outlines.geometry, out_shape=arr.shape, transform=transform) == 1

            arr[~land_mask] = 1
            arr[land_mask] *= 0.8

            arr = np.repeat(arr[:, :, None], 3, axis=2)

            glacier_mask = (
                rasterio.features.rasterize(
                    glacier_outlines.query("~used").geometry, out_shape=arr.shape[:2], transform=transform
                )
                == 1
            )

            arr[glacier_mask, 0] *= 166 / 255
            arr[glacier_mask, 1] *= 225 / 255
            arr[glacier_mask, 2] *= 243 / 255

            chosen_glacier_mask = (
                rasterio.features.rasterize(
                    glacier_outlines.query("used").geometry, out_shape=arr.shape[:2], transform=transform
                )
                == 1
            )
            arr[chosen_glacier_mask, 1] *= 204 / 255
            arr[chosen_glacier_mask, 2] *= 153 / 255

            axis.imshow(arr, extent=[*xlim, *ylim])
            outlines_dissolved.plot(
                color="none", edgecolor="black", linewidth=0.05 if overview_level == 2 else 0.2, ax=axis
            )

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
        point = (
            lines.intersection(shapely.geometry.box(xlim[0], ylim[0], xlim[1], ylim[1]))
            .apply(lambda line: line.interpolate(0))
            .values[0]
        )
        overview_ax.annotate(f"{lat}°N", (point.x, point.y), **style["degree_label"])

    for lon in np.arange(5, 30, step=5):
        lines = gpd.GeoSeries(shapely.LineString([(lon, lat) for lat in np.linspace(50, 90)]), crs=4326).to_crs(32633)
        lines.plot(ax=overview_ax, **style["degree_line"])

        if lon in [15, 20]:
            point = (
                lines.intersection(shapely.geometry.box(xlim[0], ylim[0], xlim[1], ylim[1]))
                .apply(lambda line: line.interpolate(0))
                .values[0]
            )
            overview_ax.annotate(f"{lon}°E", (point.x, point.y + (ylim[1] - ylim[0]) * 1e-2), **style["degree_label"])

    overview_ax.set_xlim(xlim)
    overview_ax.set_ylim(ylim)
    overview_ax.set_xticks([])
    overview_ax.set_yticks([])
    overview_ax.text(s="a", transform=overview_ax.transAxes, **style["panel_label"])

    zooms = [
        {  # Southern Spitsbergen
            "letter": "b",
            "loc": (6, 0),
            "xlim": (491000, 547000),
            "ymid": 8.611e6,
            "colspan": 4,
            "rowspan": 3,
        },
        {  # Nordaustlandet
            "letter": "c",
            "loc": (9, 0),
            "xlim": (617000, 662000),
            "ymid": 8.872e6,
            "colspan": 4,
            "rowspan": 3,
        },
        {  # Central Spitsbergen
            "letter": "d",
            "loc": (0, 4),
            "xlim": (519000, 578000),
            "ymid": 8.671e6,
            "rowspan": 12,
            "colspan": 8,
        },
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

        glaciers_sub = glaciers.loc[
            ~glaciers.intersection(shapely.geometry.box(xlim[0], ylim[0], xlim[1], ylim[1])).is_empty
        ]

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
            bbox = texts[i].get_window_extent().transformed(axis.transData.inverted())
            # Extract and then plot the part of the line that's outside the bounding box.
            line_diff = line.difference(shapely.geometry.box(*bbox.extents))
            axis.plot(*line_diff.xy, zorder=1, **style["glacier_label_line"])

            # axis.axis("equal")
            axis.set_xticks([])
            axis.set_yticks([])

        overview_ax.add_patch(
            plt.Rectangle(
                (axis.get_xlim()[0], axis.get_ylim()[0]),
                width=np.diff(axis.get_xlim()).item(),
                height=np.diff(axis.get_ylim()).item(),
                **style["overview_box"],
            )
        )
        overview_ax.annotate(zoom["letter"], (xlim[0], ylim[1]), **style["overview_label"])
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

        axis.plot(
            [x_locs[0], x_locs[0], x_locs[1], x_locs[1]],
            [y_locs[0] - bar_height, y_locs[0], y_locs[1], y_locs[1] - bar_height],
            **style["scalebar_line"],
        )
        # axis.errorbar(x=x_locs, y=y_locs, yerr=np.repeat(np.array((bar_height, 0))[:, None], km + 1, axis=1), **style["scalebar_line"])
        for i in range(km + 1):
            axis.annotate(
                f"{i * 10} km",
                (x_locs[i], y_locs[i] - bar_height * 1.1),
                va="top",
                ha="center",
                **style["scalebar_label"],
            )

    panel_spacing = 0
    plt.subplots_adjust(
        left=0.01,
        right=0.99,
        bottom=0.01,
        top=0.99,
        wspace=panel_spacing,
        hspace=panel_spacing * (figsize[1] / figsize[0]),
    )
    plt.savefig("figures/location_overview.jpg", dpi=600)

    if show:
        plt.show()
    else:
        plt.close()


def plot_interpretation_merging(show: bool = False):
    all_merged = interpretations.merge_all_interpretations()

    colors = {
        "bed": "#555",
        "temperate": "red",
    }

    cases = [
        {
            "radar_key": "ragna_mariebreen-20240412-DAT_0404_A1_1",
            "xlim": [2000, 6500],
            "ylim": [230, -10],
            "vlim": [0.1, 4.0],
        },
        {
            "radar_key": "amenfonna-20240510-DAT_0044_A1_1",
            "xlim": [250, 750],
            "ylim": [120, 25],
            "vlim": [0.0, 3.0],
        },
        {
            "radar_key": "dronbreen-20200224-DAT_0003_A1_2",
            "xlim": [1100, 4400],
            "ylim": [170, 80],
            "vlim": [-0.05, 2.8],
        },
        # {
        #     "radar_key": "filantropbreen-20240406-DAT_0372_A1_1",
        #     "xlim": [1300, 2800],
        #     "ylim": [140, 30],
        #     "vlim": [0.00, 2.8],
        # },
        {
            "radar_key": "winsnesbreen-20240503-DAT_0013_A1_1",
            "xlim": [600, 1400],
            "ylim": [210, 128],
            "vlim": [0.5, 3.0],
        },
    ]

    fig = plt.figure(figsize=(8.3, 6.4))
    outer_grid = fig.add_gridspec(
        nrows=2, ncols=2, left=0.08, right=0.97, bottom=0.07, top=0.93, wspace=0.12, hspace=0.09
    )

    for i, case in enumerate(cases):
        inner_grid = outer_grid[i % 2, i // 2].subgridspec(3, 1, hspace=0.01)

        ax_bot = fig.add_subplot(inner_grid[2])
        ax_mid = fig.add_subplot(inner_grid[1], sharex=ax_bot)
        ax_top = fig.add_subplot(inner_grid[0], sharex=ax_bot)

        merged = all_merged.query(f"radar_key == '{case['radar_key']}'").sort_values("distance")

        all_points = interpretations.read_interpretations(radar_key=case["radar_key"], step_m=5.0).reset_index()

        with xr.open_dataset(paths.processed_radar_path(case["radar_key"])) as dataset:
            dataset.coords["trace_n"] = "x", np.arange(dataset.x.shape[0])
            dataset = dataset.swap_dims(x="trace_n", y="depth")  # .sel(

            # I'm avoiding a strange bug here where if I clip the data exactly to xlim, it cuts too much!
            # By trial and error, I found that adding an extra 300/1000 traces "solves" it.
            dataset = dataset.sel(
                trace_n=slice(max(case["xlim"][0] - 300, 0), case["xlim"][1] + 1000), depth=slice(*case["ylim"][::-1])
            )
            dataset["data"] = np.abs(dataset.data)

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
                vmin=case["vlim"][0],
                vmax=case["vlim"][1],
                interpolation="lanczos",
            )
        for _, points in all_points.groupby(["user", "line_i"]):
            ax_mid.plot(
                points["x"],
                points["depth"],
                color=DIGITIZE_CLASS_PROPS[points.iloc[0]["kind"].replace("temperate_ice", "temperate")]["color"],
                alpha=0.3,
            )

        ax_mid.text(
            0.01,
            0.03,
            f"n={all_points['user'].unique().shape[0]}",
            transform=ax_mid.transAxes,
        )
        # Lines where the x coordinate suddenly changes are probably due to missing data. They should
        # be plotted separately.
        diffs = (merged["x"].diff().fillna(0) > 50).cumsum()
        for k, (_, merged_split) in enumerate(merged.groupby(diffs)):
            ax_bot.fill_between(
                merged_split["x"],
                merged_split["thickness"] - merged_split["temperate_lower"],
                merged_split["thickness"] - merged_split["temperate_upper"],
                color=colors["temperate"],
                alpha=0.5,
                label="CTS (±25%)" if k == 0 else None,
            )
            ax_bot.plot(
                merged_split["x"],
                merged_split["thickness"] - merged_split["temperate"],
                color=colors["temperate"],
                label="CTS (median)" if k == 0 else None,
            )
            ax_bot.fill_between(
                merged_split["x"],
                merged_split["thickness_lower"],
                merged_split["thickness_upper"],
                color=colors["bed"],
                alpha=0.5,
                label="Bed (±25%)" if k == 0 else None,
            )
            ax_bot.plot(
                merged_split["x"],
                merged_split["thickness"],
                color=colors["bed"],
                label="Bed (median)" if k == 0 else None,
            )
        for j, axis in enumerate([ax_top, ax_mid, ax_bot]):
            axis.set_xlim(case["xlim"])
            axis.set_ylim(case["ylim"])

            if j < 2:
                axis.tick_params(labelbottom=False)

            plt.text(
                0.01,
                0.98,
                "abcghidefjkl"[i * 3 + j],
                ha="left",
                va="top",
                transform=axis.transAxes,
                path_effects=[matplotlib.patheffects.withStroke(linewidth=1, foreground="white")],
            )

        if i in [0, 1]:
            ax_mid.set_ylabel("Depth (m)")
        if i in [1, 3]:
            ax_bot.set_xlabel("Trace number")

        # Add legends for the middle and bottom panels
        if i == 3:
            legend_kwargs = {
                "fontsize": 8,
                "loc": "upper left",
                "framealpha": 0,
                "ncol": 2,
                "labelspacing": 0.25,
                "bbox_transform": fig.transFigure,
            }
            lines = []
            for key in sorted(
                DIGITIZE_CLASS_PROPS.keys(), key=lambda s: len(DIGITIZE_CLASS_PROPS[s]["name"]), reverse=True
            ):
                props = DIGITIZE_CLASS_PROPS[key]
                lines.append(plt.Line2D([], [], color=props["color"], label=props["name"]))
            legend = ax_mid.legend(handles=lines, **legend_kwargs, bbox_to_anchor=(0.105, 1.0))
            legend.set_zorder(-1)

            ax_bot.legend(**legend_kwargs, bbox_to_anchor=(0.66, 1.0))

            boxes = [
                {"label": "Users:", "left": 0.045, "width": 0.48},
                {"label": "Consensus:", "left": 0.55, "width": 0.42},
            ]
            for box in boxes:
                plt.text(box["left"] + 0.01, 0.966, box["label"], transform=fig.transFigure, va="center")

                fig.add_artist(
                    plt.Rectangle(
                        (box["left"], 0.941),
                        box["width"],
                        0.05,
                        facecolor="none",
                        edgecolor="#333",
                        transform=fig.transFigure,
                    )
                )

    plt.savefig("figures/interpretation_merging_examples.jpg", dpi=600)
    if show:
        plt.show()
    else:
        plt.close()


def plot_rgm_frequency_comparison(show: bool = False):
    radar_keys = {
        "ragna_mariebreen-20240317-DAT_0345_A1_2": {
            "xlim": [4426, 2110],
            "ylim": [170, 50],
            "vlim": [0.3, 2],
            "zoom_vlim": 2.0,
        },
        "ragna_mariebreen-20240412-DAT_0404_A1_1": {
            "xlim": [700, 2674],
            "ylim": [170, 50],
            "vlim": [-0.3, 4],
            "zoom_vlim": 4.5,
        },
    }

    fig = plt.figure(figsize=(8.3, 5), dpi=300)
    # width_steps = 9
    # track_width = int(width_steps / 4)
    # track_axis = plt.subplot2grid(
    #     (2, width_steps), (0, width_steps - track_width), colspan=track_width, rowspan=2, fig=fig
    # )

    axes = fig.subplots(2, 1)
    for i, (radar_key, case) in enumerate(radar_keys.items()):
        # axis = plt.subplot2grid((2, width_steps), (i, 0), colspan=width_steps - track_width, fig=fig)
        axis = axes.ravel()[i]
        with xr.open_dataset(paths.processed_radar_path(radar_key)) as dataset:
            dataset.coords["trace_n"] = "x", np.arange(dataset.x.shape[0])
            dataset = dataset.swap_dims(x="trace_n", y="depth")  # .sel(

            if flipped := case["xlim"][0] > case["xlim"][1]:
                case["xlim"] = case["xlim"][::-1]

            # I'm avoiding a strange bug here where if I clip the data exactly to xlim, it cuts too much!
            # By trial and error, I found that adding an extra 300/1000 traces "solves" it.
            dataset = dataset.sel(
                trace_n=slice(max(case["xlim"][0], 0), case["xlim"][1]), depth=slice(*case["ylim"][::-1])
            )
            dataset["data_abs"] = np.abs(dataset.data)

            # dataset["distance"] -= dataset["distance"].min()

            if flipped:
                # dataset["distance"] = dataset["distance"].max() - dataset["distance"]
                dataset["trace_n"] = dataset["trace_n"].max() - dataset["trace_n"]
                dataset = dataset.sortby("trace_n", ascending=True)
                # dataset = dataset.isel(trace_n=slice(dataset["trace_n"].shape[0], 0))
            dataset["trace_n"] = dataset["trace_n"] - dataset["trace_n"].min()

            extent = (
                0,
                dataset["trace_n"].max().item() - dataset["trace_n"].min().item(),
                dataset["depth"].max().item(),
                dataset["depth"].min().item(),
            )
            inset = axis.inset_axes([0.55, 0.65, 0.45, 0.35])
            inset.set_xticks([])
            inset.set_yticks([])

            subset_mid_trace = extent[1] // 2
            subset_width = int(subset_mid_trace / 3.5)
            subset_mid_depth = (extent[2] + extent[3]) / 2 - 8
            subset_height = (extent[2] - extent[3]) / 9
            subset_extent = (
                subset_mid_trace - subset_width // 2,
                subset_mid_trace + subset_width // 2,
                subset_mid_depth + subset_height / 2,
                subset_mid_depth - subset_height / 2,
            )
            subset = dataset.sel(trace_n=slice(*subset_extent[:2]), depth=slice(*subset_extent[2:][::-1]))

            inset.imshow(
                subset["data"],
                extent=extent,
                aspect="auto",
                vmin=-case["zoom_vlim"],
                vmax=case["zoom_vlim"],
                interpolation="lanczos",
                cmap="Greys_r",
            )

            axis.imshow(
                dataset["data_abs"],
                extent=extent,
                cmap="Greys_r",
                aspect="auto",
                vmin=case["vlim"][0],
                vmax=case["vlim"][1],
                interpolation="lanczos",
            )

            axis.add_patch(
                plt.Rectangle(
                    (subset_extent[0], subset_extent[3]),
                    subset_extent[1] - subset_extent[0],
                    subset_extent[2] - subset_extent[3],
                    facecolor="none",
                    edgecolor="red",
                )
            )

            if i == 1:
                axis.set_xlabel("Trace number")
            axis.set_ylabel("Depth (m)")
            axis.text(
                0.02,
                0.97,
                "ac"[i],
                va="top",
                path_effects=[matplotlib.patheffects.withStroke(linewidth=2, foreground="white")],
                transform=axis.transAxes,
            )
            inset.text(
                0.02,
                0.95,
                "bd"[i],
                va="top",
                path_effects=[matplotlib.patheffects.withStroke(linewidth=2, foreground="white")],
                transform=inset.transAxes,
            )

            # track_axis.plot(dataset["easting"], dataset["northing"], label="ac"[i])

    # track_axis.legend(loc="lower right")
    # track_axis.text(
    #     0.03,
    #     0.99,
    #     "e",
    #     va="top",
    #     path_effects=[matplotlib.patheffects.withStroke(linewidth=2, foreground="white")],
    #     transform=track_axis.transAxes,
    # )

    # # Reference point for offset
    # origin = [track_axis.get_xlim()[0], track_axis.get_ylim()[0]]

    # for i in range(len(origin)):
    #     origin[i] -= origin[i] % 100

    # # Custom formatter to show relative values
    # track_axis.xaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda val, _: f"{val - origin[0]:.0f}"))
    # track_axis.yaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda val, _: f"{val - origin[1]:.0f}"))

    # track_axis.yaxis.tick_right()
    # track_axis.yaxis.set_label_position("right")

    # track_axis.set_xlabel(f"Easting (+{origin[0]:.0f} m)")
    # track_axis.set_ylabel(f"Northing (+{origin[1]:.0f} m)")

    plt.subplots_adjust(left=0.08, bottom=0.09, right=0.99, top=0.98, wspace=0.06, hspace=0.15)
    plt.savefig("figures/rgm_frequency_comparison.jpg", dpi=500)

    if show:
        plt.show()
    else:
        plt.close()


def plot_cross_track_difference(show: bool = False):
    import itertools

    all_data = interpretations.merge_all_interpretations()
    tree = scipy.spatial.KDTree(np.transpose([all_data.geometry.x, all_data.geometry.y]))

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

        tree = scipy.spatial.KDTree(np.transpose([first.geometry.x, first.geometry.y]))

        distances, indices = tree.query(np.transpose([second.geometry.x, second.geometry.y]))

        distance_mask = distances < 10

        if np.count_nonzero(distance_mask) == 0:
            continue

        second = second[distance_mask]
        cols = ["antenna", "thickness", "temperate"]
        for col in cols:
            second[f"other_{col}"] = first[col].values[indices[distance_mask]]
        out_list.append(second[["temperate_frac", "bed_type", *cols, *[f"other_{col}" for col in cols]]])

    cmps = pd.concat(out_list)
    cmps["temperate_frac"] *= 100

    cmps["diff"] = cmps["thickness"] - cmps["other_thickness"]
    cmps["temperate_diff"] = cmps["temperate"] - cmps["other_temperate"]

    antenna_alias = {"25 MHz": "low", "100 MHz": "high"}
    per_antenna_stats = {}
    for antenna, a_cmps in cmps.groupby("antenna"):
        a_cmps = a_cmps[a_cmps["other_antenna"] == antenna]

        if a_cmps.shape[0] == 0:
            continue

        if antenna not in antenna_alias:
            continue

        nmad = stats.nmad(a_cmps["diff"])
        wavelength = 168 / int(antenna.split(" ")[0])
        per_antenna_stats[antenna_alias[antenna]] = {"nmad": nmad, "perwavelength": int(round(100 * nmad / wavelength))}

    svalbardradar.analysis.record_information(
        {
            "perantenna": {
                "crosstrack": per_antenna_stats,
            }
        }
    )

    # Filter the temperate differences to only look at transition zones
    # 0% could be a "cold bed" measurement, and 100% could be a clamped value. Only those in between are truly
    # representative of the uncertainty.
    cmps.loc[(cmps["temperate_frac"] < 10) | (cmps["temperate_frac"] > 90), "temperate_diff"] = np.nan

    temperate_bins = np.linspace(-0.01, 101, 11)
    bin_centers = temperate_bins[1:] - np.diff(temperate_bins) / 2
    cmps["temperate_bin"] = bin_centers[np.digitize(cmps["temperate_frac"], bins=temperate_bins) - 1]

    plt.figure(figsize=(8, 5))
    for i, (name, color, data) in enumerate(
        [
            ("All bed data", "gray", cmps),
            ("Temperate bed", "purple", cmps[cmps["bed_type"] == "certain_temperate"]),
            ("Cold bed", "blue", cmps[cmps["bed_type"] == "certain_cold"]),
            ("CTS", "red", cmps.drop(columns=["diff"]).rename(columns={"temperate_diff": "diff"})),
        ]
    ):
        axis = plt.subplot2grid((2, 2), (i % 2, i // 2))

        bin_edge = 10
        axis.hist(
            data["diff"], bins=np.linspace(-bin_edge, bin_edge, 100 if name != "CTS" else 50), color=color, alpha=0.5
        )
        if i % 2 == 0:
            axis.tick_params(labelbottom=False)
        else:
            axis.set_xlabel("Cross-track difference (m)")
        if i in [0, 1]:
            axis.set_ylabel("Frequency")

        plt.text(0.02, 0.97, "acbd"[i], transform=axis.transAxes, va="top", ha="left")
        plt.text(0.98, 0.97, name, transform=axis.transAxes, va="top", ha="right")
        nmad = stats.nmad(data["diff"])
        if name in ["All bed data", "CTS"]:
            key = {"All bed data": "all_bed", "CTS": "cts"}[name]
            svalbardradar.analysis.record_information(
                {
                    "crosstrack": {
                        f"{key}_nmad": nmad,
                    }
                }
            )
        plt.text(
            x=0.02,
            y=0.7,
            s="\n".join(
                [
                    f"Median: {data['diff'].median():.1f} m",
                    f"NMAD: {nmad:.1f} m",
                ]
            ),
            transform=axis.transAxes,
            va="center",
            path_effects=[matplotlib.patheffects.withStroke(linewidth=4, foreground="white")],
        )

    plt.subplots_adjust(left=0.07, bottom=0.1, right=0.986, top=0.99, wspace=0.136, hspace=0.207)
    plt.savefig("figures/cross_track_difference.jpg", dpi=600)

    if show:
        plt.show()
    else:
        plt.close()


def plot_heerland_dhdt(show: bool = False):
    import rasterio
    import rasterio.coords
    import rasterio.windows
    import svalbardradar.comparisons

    bounds = rasterio.coords.BoundingBox(546000, 8632000, 567000, 8657000)

    glaciers = gpd.read_file("shapes/glacier_locations.geojson")
    outlines = get_svalbard_glaciers()

    glaciers = gpd.sjoin(glaciers, outlines[["geometry"]], how="left", predicate="intersects")
    glaciers["geometry"] = outlines.loc[glaciers["index_right"].values, "geometry"].values
    glaciers["easting"] = glaciers["geometry"].centroid.x
    glaciers["northing"] = glaciers["geometry"].centroid.y

    with rasterio.open(svalbardradar.comparisons.get_hugonnet()) as raster:
        window = rasterio.windows.from_bounds(*bounds, transform=raster.transform)
        hugonnet = raster.read(1, window=window)

    with rasterio.open(svalbardradar.comparisons.get_geyman()) as raster:
        window = rasterio.windows.from_bounds(*bounds, transform=raster.transform)
        geyman = raster.read(1, window=window, masked=True).filled(0) / (2010 - 1936)

    fig = plt.figure(figsize=(8.3, 5.0))
    axes: list[plt.Axes] = fig.subplots(1, 2, sharex=True, sharey=True)
    extent = (bounds.left, bounds.right, bounds.bottom, bounds.top)

    for i, axis in enumerate(axes):
        if i == 0:
            params = {
                "arr": geyman,
                "title": "Geyman et al. (2022)",
            }
        else:
            params = {
                "arr": hugonnet,
                "title": "Hugonnet et al. (2021)",
            }
        axis.text(0.5, 1.02, params["title"], transform=axis.transAxes, ha="center", fontsize=12)
        img = axis.imshow(params["arr"], cmap="RdBu", vmin=-2, vmax=2, extent=extent)
        glaciers.plot(ax=axis, color="none", edgecolor="black")

        for _, glacier in glaciers.iterrows():
            axis.annotate(str(glacier["name"])[:1], (glacier["easting"], glacier["northing"]), ha="center", va="bottom", path_effects=[matplotlib.patheffects.withStroke(foreground="white", linewidth=2)])

        axis.set_xlabel("Easting (m)")
        if i == 0:
            axis.set_ylabel("Northing (m)")
        else:
            colorbar_ax = axis.inset_axes((0.05, 0.75, 0.15, 0.3))
            colorbar_ax.set_axis_off()
            cbar = plt.colorbar(img, ax=colorbar_ax, aspect=5, fraction=1.0)
            cbar.set_label("dH dt$^{-1}$")
    plt.xlim(extent[:2])
    plt.ylim(extent[2:])
    plt.subplots_adjust(left=0.09, bottom=0.09, right=0.99, top=0.95, wspace=0.05)
    plt.savefig("figures/heerland_dhdt.jpg", dpi=400)
    if show:
        plt.show()
    else:
        plt.close()


def generate_all_figures(show: bool = False):
    print("Generating Drønbreen example figure.")
    plot_dronbreen_examples(show=show)
    print("Generating centerline profiles figure.")
    plot_centerline_profiles(show=show)
    print("Generating inversion model comparison figure.")
    plot_model_comparison(show=show, correct_topo=True)
    plot_model_comparison(show=show, correct_topo=False)
    print("Generating glathida comparison figure.")
    plot_glathida_comparison(show=show, correct_topo=False)
    plot_glathida_comparison(show=show, correct_topo=True)
    print("Generating interpretation merging figure.")
    plot_interpretation_merging(show=show)
    print("Generating cross-track difference figure.")
    plot_cross_track_difference(show=show)
    print("Generating cold/temperate performance difference figure.")
    plot_model_temperate_cold_performance(show=show)
    print("Generating supplementary cold/temperate performance difference figure.")
    plot_perglacier_temperate_cold_performance(show=show)
    print("Generating supplementary cold/temperate elevation difference figure.")
    plot_elevation_vs_temp_diff(show=show)
    print("Generating Heer Land elevation change rate figure")
    plot_heerland_dhdt(show=show)
    print("Generating 25MHz vs 100MHz profile figure")
    plot_rgm_frequency_comparison(show=show)


if __name__ == "__main__":
    generate_all_figures()
