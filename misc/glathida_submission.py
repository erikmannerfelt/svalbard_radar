import geopandas as gpd
import pandas as pd

import glenglat_submission
import svalbardradar.process_radar

from pathlib import Path

def main():

    investigators = glenglat_submission.get_investigators()
    agencies = glenglat_submission.get_agencies()
    freq_ids = glenglat_submission.get_freq_ids()


    all_data = gpd.read_feather(Path(__file__).absolute().parents[1] / "cache/interpretations/interp_all.feather").to_crs(4326)
    all_data["point_id"] = all_data.index
    all_data["latitude"] = all_data.geometry.y.round(6)
    all_data["longitude"] = all_data.geometry.x.round(6)
    all_data["survey_id"] = all_data["antenna"].apply(lambda s: freq_ids[s])

    all_data["elevation_date"] = all_data["radar_key"].apply(lambda key: svalbardradar.process_radar.get_dem_path(key).stem.split("_")[-1])

    all_data["time"] = all_data["time"].astype(str).str.slice(0, 10)

    for key in ["thickness", "thickness_nmad", "elevation"]:
        all_data[key] = all_data[key].astype(int)

    all_data = all_data.rename(columns={"radar_key": "profile_id", "time": "date", "thickness_nmad": "thickness_uncertainty"})

    surveys = []


    for frequency, freq_id in freq_ids.items():
        data = all_data[all_data["antenna"] == frequency].sort_values("date_str").copy()

        dates = data["date_str"].unique()
        date_min = f"{dates[0][:4]}-{dates[0][4:6]}-{dates[0][6:]}"
        if len(dates) > 1:
            date_max = f"{dates[1][:4]}-{dates[1][4:6]}-{dates[1][6:]}"
        else:
            date_max = date_min

        surveys.append(
            {
                "id": freq_id,
                "from_date": date_min,
                "to_date": date_max,
                "platform": "ground",
                "method": "radar",
                "method_details": " ".join(
                    [
                        f"Malå ProEx GPR system with a {frequency} unshielded antenna."
                        "Constant wave velocity in ice of 0.168 m per ns."
                        "Interpretations crowd-sourced from >= 10 contributors.",
                        "Elevations are from co-registered ArcticDEM mosaics.",
                        "Uncertainties are normalized median absolute deviations (NMAD).",
                        "Location uncertainty is roughly +- 10 m."
                    ],
                ),
                "investigators": "|".join(investigators),
                "agencies": "|".join(agencies),
            }
        )

    out_dir = Path("glathida_pub")
    out_dir.mkdir(exist_ok=True, parents=True)

    pd.DataFrame.from_records(surveys).to_csv(out_dir / "survey.csv", index=False)

    all_data = all_data.sample(n=50,random_state=1) 

    all_data[["survey_id", "profile_id", "point_id", "date", "elevation_date", "latitude", "longitude", "elevation", "thickness", "thickness_uncertainty"]].to_csv(out_dir / "point.csv", index=False)



if __name__ == "__main__":
    main()
