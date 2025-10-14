import pandas as pd
import xarray as xr
import numpy as np
from pathlib import Path


def main():
    dates = set()

    glaciers = {}

    data_list = []
    for glacier_dir in (Path(__file__).parent / "../processed_radar/").glob("*"):
        if not glacier_dir.is_dir():
            continue

        for date_dir in glacier_dir.glob("20*"):
            if not date_dir.is_dir():
                continue
            dates.add(date_dir.stem)

            for radargram_fp in date_dir.glob("*.nc"):
                entry = {}
                data_list.append(entry)

                with xr.open_dataset(radargram_fp) as dataset:

                    entry["antenna"] = dataset.attrs["antenna"].split("MHz")[0] + "MHz"
                
    data = pd.DataFrame.from_records(data_list)

    print(list(zip(map(list, np.unique(data["antenna"], return_counts=True)))))
    # antenna_counts = {k: v for k, v in np.unique(data["antenna"], return_counts=True)}
    # print((list(map(list, ))))

if __name__ == "__main__":
    main()
