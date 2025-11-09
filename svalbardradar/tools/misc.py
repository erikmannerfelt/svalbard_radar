import hashlib
from pathlib import Path
import requests
import shutil
import os


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
