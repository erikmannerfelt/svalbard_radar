import geopandas as gpd
import pandas as pd
import numpy as np

from pathlib import Path

def main():

    #
    investigators = [
        "Erik Schytt {Mannerfelt} 0000-0002-9146-557X (1,2)",
        "Ursula {Enzenhofer} 0009-0005-4802-1243 (2,3)",
        "Satu {Innanen} 0009-0002-2899-1021 (1)",
        "Jogscha M. {Aberhalden} 0009-0008-9767-2722 (4)",
        "Karlijn {Ploeg} 0000-0002-8866-9555 (5)",
        "Johannes {Brunner} 0009-0004-3792-3121 (1)",
        "Mette Kusk {Gillespie} 0000-0003-2201-9901 (4,6)",
        "Gabrielle E. {Kleber} 0000-0002-5062-970X (7)",
        "Jonathan {Kolar} 0009-0004-2109-9115 (8)",
        "Geir {Moholdt} 0000-0002-8883-1620 (9)",
        "Solveig {Solem} 0009-0007-4566-0167 (10)",
        "Andrew {Hodson} 0000-0002-1255-7987 (2)"
    ]
    agencies = [
        "1. Department of Geosciences, University of Oslo, Oslo, Norway",
        "2. Arctic Geology, The University Centre in Svalbard, Longyearbyen, Norway",
        "3. Department of Geography and Social Anthropology, NTNU, Trondheim, Norway",
        "4. Department of Civil Engineering and Environmental Sciences, Western Norway University of Applied Sciences, Sogndal, Norway.",
        "5. Department of Earth Science, University of Bergen and Bjerknes Centre for Climate Research, Bergen, Norway",
        "6. VIA University College, Nørre Nissum, Denmark",
        "7. Department of Geoscience, UiT the Arctic University of Norway, Tromsø, Norway",
        "8. Institute of Earth Sciences (ISTE), University of Lausanne, Lausanne, Switzerland",
        "9. Glaciology and Geology Section, Norwegian Polar Institute, Fram Centre, Tromsø, Norway",
        "10. Department of Hydrology, Norwegian Water Resources and Energy Directorate (NVE), Oslo, Norway",
    ]

    freq_ids = {"25 MHz": 0, "50 MHz": 1, "100 MHz": 2}

    cts_survey = pd.DataFrame.from_records(
        [
            {
                "id": i,
                # "source_id": 0,  # TODO: What is this?
                "location_origin": "submitted",
                "elevation_origin": "submitted",
                "method_notes": " ".join(
                    [
                        "From surface-coupled ground-penetrating radar.",
                        f"Data collected with a center frequency of {freq}.",
                        "Interpretations crowd-sourced from >= 10 contributors.",
                        "Elevations are from co-registered ArcticDEM mosaics.",
                        "Uncertainties are normalized median absolute deviations (NMAD).",
                        "Location uncertainty is roughly +- 10 m."
                    ]
                ),
                # "curator": investigators[0],
                "investigators": "|".join(investigators),
                "agencies": "|".join(agencies),
                "funding": ""
            } for freq, i in freq_ids.items()
        ]
    )

    all_data = gpd.read_feather(Path(__file__).absolute().parents[1] / "cache/interpretations/interp_all.feather").to_crs(4326)

    all_data["date_str"] = all_data["radar_key"].str.split("-", expand=True).iloc[:, 1]
    print((all_data["date_str"] == "nan").describe())

    # Convert to isoformat with exactly one decimal
    all_data["time"] = all_data["time"].dt.round(freq="100ms").dt.strftime("%Y-%m-%dT%H:%M:%S.%f").str.slice(0, 21) + all_data["time"].dt.strftime("%:z")

    all_data["survey_id"] = all_data["antenna"].apply(lambda s: freq_ids[s])
    all_data["id"] = all_data.index
    # all_data["profile_id"] = all_data["radar_key"].astype("category").cat.codes
    all_data["date_min"] = all_data["date_str"].str.slice(0, 4) + "-" + all_data["date_str"].str.slice(4, 6) + "-" + all_data["date_str"].str.slice(6, 8)
    all_data["date_max"] = all_data["date_min"]
    # all_data["location_uncertainty"] = 10
    all_data["depth"] = np.where(all_data["temperate"] == 0, np.inf, all_data["thickness"] - all_data["temperate"])
    all_data["depth_uncertainty"] = np.where(all_data["temperate"] == 0, np.inf, all_data["temperate_nmad"])
    all_data = all_data.rename(columns={"thickness": "bed_depth", "thickness_nmad": "bed_depth_uncertainty", "time": "datetime", "radar_key": "profile_id"})
    all_data["longitude"] = all_data["geometry"].x.round(6)
    all_data["latitude"] = all_data["geometry"].y.round(6)


    for key in ["depth", "depth_uncertainty", "bed_depth", "bed_depth_uncertainty", "elevation"]:
        all_data[key] = all_data[key].round(2)

    all_data.sort_values(["survey_id", "profile_id", "id"], inplace=True)

    cts_point = all_data[["survey_id", "id", "profile_id", "date_min", "date_max", "latitude", "longitude", "depth", "depth_uncertainty", "elevation", "bed_depth", "bed_depth_uncertainty", "datetime"]]

    # sub = pd.concat([cts_point[np.isfinite(cts_point["depth"])].sample(n=50, random_state=1),cts_point[~np.isfinite(cts_point["depth"])].sample(n=10, random_state=1)])
    sub = cts_point


    out_dir = Path(__file__).absolute().parents[1] / "glenglat_pub"

    out_dir.mkdir(exist_ok=True, parents=True)
    sub.to_csv(out_dir / "cts_point.csv", index=False)
    cts_survey.to_csv(out_dir / "cts_survey.csv", index=False)
    # print(cts_survey.iloc[0])
    # print(cts_point[np.isfinite(cts_point["depth"])].iloc[1000])
    

    
    
    
if __name__ == "__main__":
    main()
