import geopandas as gpd
import pandas as pd
import numpy as np

import zipfile
import io

def main():

    pts = gpd.read_feather("cache/comparisons/glathida/glathida_pts.feather")


    with zipfile.ZipFile("cache/comparisons/glathida/glathida.zip") as zip_file:

        # Get the largest "survey.csv"
        survey_finfo = max(filter(lambda f: "survey.csv" in f.filename, zip_file.filelist), key=lambda f: f.file_size)

        surveys = pd.read_csv(io.BytesIO(zip_file.read(survey_finfo))).set_index("id", drop=True)

    survey_lengths = pd.Series()
    survey_lengths.name = "length_km"

    for survey_id, survey_pts in pts.groupby("survey_id"):

        if survey_pts.shape[0] < 2:
            continue
        distance = 0.

        diffs = ((survey_pts.geometry.x.diff() ** 2 + survey_pts.geometry.y.diff() ** 2) ** 0.5).fillna(0).to_frame("diff")

        delim = np.nanmedian(diffs["diff"]) * 3
        diffs["part"] = (diffs["diff"] > delim).cumsum()

        diffs = diffs[diffs["diff"] < delim]

        survey_lengths[survey_id] = (diffs.groupby("part").sum().sum() / 1e3).item()

       
        # print("nan" in survey_pts["profile_id"].unique())
        #
    print(f"Total survey length: {survey_lengths.sum():.0f} km")

    surveys = survey_lengths.sort_values().to_frame().merge(surveys, left_index=True, right_index=True)

    surveys["from_date"] = pd.to_datetime(surveys["from_date"])

    total_modern_length = surveys.loc[surveys["from_date"].dt.year >= 2000, "length_km"].sum()
    total_modern_ground_length = surveys.loc[(surveys["from_date"].dt.year >= 1900) & (surveys["platform"] != "air"), "length_km"].sum()
    print(f"Total length >= 2000: {total_modern_length:.0f} km")
    print(f"Total no-air length >= 2000: {total_modern_ground_length:.0f} km")

    print(surveys.iloc[-6:][["from_date", "platform", "investigators", "length_km", "references"]])
    

if __name__ == "__main__":
    main()
