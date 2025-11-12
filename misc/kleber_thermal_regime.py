import pandas as pd
import numpy as np

import svalbardradar.interpretations


def main():
    all_data = svalbardradar.interpretations.merge_all_interpretations()

    lines = {
        "filantropbreen": ["filantropbreen-20240406-DAT_0372_A1_1"],
        "finsterwalderbreen": ["finsterwalderbreen-20250407-DAT_0171_A1_1"],
        "ragna_mariebreen": ["ragna_mariebreen-20240412-DAT_0404_A1_1"],
        "moysalbreen": ["moysalbreen-20220222-DAT_0749_A1_1"],
        "scott_turnerbreen": ["scott_turnerbreen-20240207-DAT_0453_A1_2"],
        "mettebreen": ["mettebreen-20230305-DAT_0229_A1_1"],
        "vallakrabreen": ["vallakrabreen-20210513-DAT_0012_A1_1", "vallakrabreen-20210513-DAT_0014_A1_31"],
    }

    out_list = []

    for glacier, radar_keys in lines.items():
        data = all_data[all_data["radar-key"].isin(radar_keys)].copy()

        if "vallakrabreen-20210513-DAT_0014_A1_31" in radar_keys:
            data.drop(
                data.index[(data["radar-key"] == "vallakrabreen-20210513-DAT_0014_A1_31") & (data["distance"] < 1500)],
                inplace=True,
            )

        if data.shape[0] == 0:
            print(f"Data for {glacier} is empty")
            continue

        temperate_ice_fraction = (data["temperate_frac"] * data["thickness"]).sum() / data["thickness"].sum()

        temperate_bed_fraction = np.count_nonzero(data["temperate_frac"] > 0.05) / data.shape[0]

        out_list.append(
            {
                "glacier": glacier,
                "radar_keys": "/".join(radar_keys),
                "temperate_ice_fraction": temperate_ice_fraction,
                "temperate_bed_fraction": temperate_bed_fraction,
            }
        )

    out = pd.DataFrame.from_records(out_list)

    out.to_csv("temp/glacier_thermal_regime_fractions.csv")

    print(out.drop(columns=["radar_keys"]))


if __name__ == "__main__":
    main()
