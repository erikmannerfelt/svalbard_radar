from pathlib import Path

BASE_CACHE_PATH = Path(__file__).parents[2] / "cache/"

def _processed_radar_dir_path() -> Path:
    return Path(__file__).parents[2] / "processed_radar"

def _submissions_dir_path() -> Path:
    return Path(__file__).parents[2] / "submitted"
    

def processed_radar_path(radar_key: str) -> Path:
    glacier, date_str, file_stem = radar_key.split("-")

    return _processed_radar_dir_path() / f"{glacier}/{date_str}/{file_stem}.nc"


def get_all_interpreted_radargrams() -> list[str]:

    all_radargrams = set()
    for dir_path in _submissions_dir_path().glob("*/*"):
        if not dir_path.is_dir():
            continue
        radar_key = dir_path.stem

        if processed_radar_path(radar_key).is_file():
            all_radargrams.add(radar_key)

    return list(all_radargrams)

  

def get_latest_submissions(radar_key: str) -> list[Path]:

    interpretations = []
    for user_dir in _submissions_dir_path().glob("*"):
        if not user_dir.is_dir():
            continue
        radar_key_dir = user_dir / radar_key

        if not radar_key_dir.is_dir():
            continue

        interp = sorted(radar_key_dir.glob("*.json"))[-1]

        interpretations.append(interp)

    return interpretations
        



    
