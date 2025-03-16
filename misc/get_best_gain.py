import xarray as xr
from pathlib import Path
import pandas as pd
import re
import matplotlib.pyplot as plt

def main():

    gains = []
    for radargram in Path("processed_radar").rglob("*.nc"):
        with xr.open_dataset(radargram) as data:

            if "auto_gain" not in data.attrs["processing-log"]:
                continue
            for line in data.attrs["processing-log"].splitlines():
                if line.startswith("gain"):
                    gains.append({"antenna_mhz": int(data.attrs["antenna"].split(" MHz")[0]), "gain": float(re.findall(r"gain of\s([-+]?\d*\.\d+|\d+)", line)[0])})

    gains = pd.DataFrame.from_records(gains)

    if gains.shape[0] == 0:
        raise ValueError("No available datasets with auto_gain")

    for antenna, per_ant in gains.groupby("antenna_mhz"):
        print(antenna)
        print(per_ant["gain"].describe())# / (0.168 / 2))
        print("\n\n")
if __name__ == "__main__":
    main()
