import hashlib
from pathlib import Path
import requests
import shutil
import os

import numpy as np
import xarray as xr


def download_large_file(output_filepath: Path, url: str):
    temp_path = output_filepath.with_suffix(f".{output_filepath.suffix}.part")
    if temp_path.is_file():
        os.remove(temp_path)

    if output_filepath.is_file():
        return

    print(f"Downloading {url}")
    with requests.get(url, stream=True) as response:
        response.raise_for_status()

        temp_path.parent.mkdir(exist_ok=True, parents=True)

        with open(temp_path, "wb") as outfile:
            for chunk in response.iter_content(chunk_size=8192 * 4):
                outfile.write(chunk)

        shutil.move(temp_path, output_filepath)


def checksum(objects: list[object]) -> str:
    return hashlib.sha256("".join(map(str, objects)).encode()).hexdigest()


def siglog_strength(antenna: str) -> float:
    """Return the siglog strength that was used in the processing before siglog became a visualization step."""
    return 0.0 if "25 MHz" in antenna else 1.0


def siglog(data: np.ndarray, antenna: str) -> np.ndarray:
    """
    Apply ridal's siglog transform: sign(v) * max(log10(|v|) - k, 0).

    The radargrams are processed without siglog, so this is needed to reproduce the previous look.
    The strength (k) depends on the antenna; see `siglog_strength()`.
    """
    data = np.asarray(data)
    with np.errstate(divide="ignore"):
        return np.maximum(np.log10(np.abs(data)) - data.dtype.type(siglog_strength(antenna)), 0) * np.sign(data)


def siglog_radargram(dataset: xr.Dataset) -> xr.Dataset:
    """Apply `siglog()` to a radargram's data unless it was already processed with siglog."""
    if "siglog" in str(dataset.attrs.get("processing_steps", "")):
        return dataset

    dataset["data"] = dataset["data"].copy(data=siglog(dataset["data"].values, dataset.attrs["antenna"]))
    return dataset
