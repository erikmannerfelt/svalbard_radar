import zipfile
import pandas as pd
import json
import matplotlib.pyplot as plt
import numpy as np

def main():

    with zipfile.ZipFile("traffic.zip") as zip_file:
        t_str = zip_file.read("traffic.log").decode()

    lines = []
    for line_str in t_str.splitlines():
        try:
            lines.append(json.loads(line_str))
        except:
            raise

    data = pd.DataFrame.from_records(lines)

    data.index = pd.to_datetime(data["created_at"])

    hourly_freq = data["ip_address"].groupby(data.index.hour).count()
    # Change timezone
    hourly_freq.index = (hourly_freq.index + 1) % 24

    plt.subplot(polar=True)

    xvals = (2 * np.pi - (hourly_freq.index / (24 / np.pi / 2)) + 0.5 * np.pi) % (2 * np.pi)
    plt.bar(xvals, hourly_freq)
    plt.gca().set_yticklabels([])

    plt.grid(alpha=0.3)
    plt.xticks(xvals, labels=hourly_freq.index)
    plt.show()
    return


    freq = data.resample("W")["ip_address"].count()
    plt.bar(freq.index, freq, width=freq.index.diff().mean())
    plt.yscale("log")
    plt.ylabel("N requests / week")
    plt.show()



if __name__ == "__main__":
    main()
