import geopandas as gpd
import pandas as pd
import matplotlib.pyplot as plt
import numpy as np

from pathlib import Path


def glacier_table():
    import svalbardradar.interpretations
    import svalbardradar.figures
    data = svalbardradar.interpretations.merge_all_interpretations()

    data["glacier"] = data["radar_key"].str.split("-", expand=True).iloc[:, 0]

    distances = data.groupby(["glacier", "radar_key"])["distance"].max().groupby("glacier").sum()

    outlines = svalbardradar.figures.get_svalbard_glaciers()
    glaciers = gpd.read_file("shapes/glacier_locations.geojson")

    glaciers = gpd.sjoin(glaciers, outlines, how="left", predicate="intersects")
    glaciers["geometry"] = outlines.loc[glaciers["index_right"].values, "geometry"].values
    
    glaciers["track_length"] = (distances.loc[glaciers["key"]].values / 1e3).round().astype(int) 
    glaciers["area"] = (glaciers["Shape_Area"] * 1e-6).round().astype(int)

    glaciers["zrange"] = glaciers["minZ"].round().astype(int).astype(str) + "–" + glaciers["maxZ"].round().astype(int).astype(str)

    cols = {
        "name": "Glacier",
        "area": "Area (km²)",
        "zrange": "Elevation range (m a.s.l.)",
        "track_length": "GPR track length (km)",
        "last_surge": "Last surge"
    }

    surging = {
        "etonbreen": "2023$^{[1]}$",
        "von_postbreen": "1920$^{[2]}$",
        "elfenbeinbreen": "1896$^{[2]}$",
        "jinnbreen": "ND",
        "moysalbreen": "1936",
        "lofthusbreen": "1896$^{[3]}$",
        "dronbreen": "1896$^{[3]}$",
        "scott_turnerbreen": "1914$^{[3]}$",
        "bergmesterbreen": "ND",
        "rugaasfonna": "ND",
        "svellnosbreen": "ND",
        "kroppbreen": "2007$^{[4]}$",
        "edvardbreen": "$\\sim$2025$^{[1]}$",
        "vallakrabreen": "2022$^{[1]}$",
        "mettebreen": "ND",
        "ragna_mariebreen": "ND",
        "filantropbreen": "20XX",
        "antoniabreen": "ND",
        "finsterwalderbreen": "ND"
    }
    print("TODO: Look up surge dates in Harcourt et al.")
    glaciers["last_surge"] = glaciers["key"].map(lambda k: surging.get(k, "-"))

    tex_table = r"\begin{tabular}{l" + "c" * (len(cols) - 1) + "}\n"
    tex_table += "&".join((r"\textbf{" + v + "}" for v in cols.values())) + "\\\\\n\\midrule\n"

    for _, glacier in glaciers.sort_values("Y_cent", ascending=False).iterrows():

        tex_table += "&".join((str(glacier[col]) for col in cols))
        tex_table += "\\\\\n"

    tex_table += r"\end{tabular}"

    out_path = Path("figures/glacier_table.tex")
    out_path.parent.mkdir(exist_ok=True, parents=True) 
    out_path.write_text(tex_table)
    print(tex_table)
    