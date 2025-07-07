import datetime
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Callable, Self

import dotenv

dotenv.load_dotenv()


def get_paths(offline: bool = False):
    gpr_dir = Path(os.environ["GPR_DIR"])

    missing = [
        "Mette 2024",
        "Ragna 20240317",
    ]

    print("Missing", "\n".join(missing))

    filepaths = {
        "antoniabreen": {
            "20250406": [gpr_dir / "2025/GPR_20250406_B-Antoniabreen-25MHz"],
        },
        "finsterwalderbreen": {
            "20250407": [gpr_dir / "2025/GPR_20250407_A-Finsterwalderbreen-25MHz"]
        },
        "scott_turnerbreen": {
            "20240207": [gpr_dir / "2024/GPR_20240207_A-ScottTurnerbreen-100MHz/"],
        },
        "bergmesterbreen": {
            "20230222": [
                gpr_dir / "2023/GPR_230222_D-Bergmesterbreen-100MHz/",
                gpr_dir / "2023/GPR_230222_E-BergmesterbreenDronbreen-100MHz/",
            ],
        },
        "kroppbreen": {
            "20230228": [gpr_dir / "2023/GPR_230228_A-Kroppbreen-100MHz"],
            "20240407": [gpr_dir / "2024/GPR_20240407_B-Kroppbreen-100MHz"],
        },
        "rugaasfonna": {
            "20220218": [gpr_dir / "2022/Svalbard/GPR_220218_A-Kokbreen-100MHz"],
            "20220222": [gpr_dir / "2022/Svalbard/GPR_220222_A-Kokbreen-100MHz"],
        },
        "svellnosbreen": {
            "20220218": [gpr_dir / "2022/Svalbard/GPR_220218_B-Svellnosbreen-100MHz"],
        },
        "moysalbreen": {
            "20220222": [gpr_dir / "2022/Svalbard/GPR_220222_B-Moysalbreen-100MHz"],
        },
        "fimbulisen": {
            "20220430": [gpr_dir / "2022/Svalbard/GPR_220430_B-Fimbulisen-100MHz"]
        },
        "vallakrabreen": {
            "20210513": [gpr_dir / "2021/Svalbard/GPR_210513_A-Vallakrabreen-100MHz"],
            "20220419": [gpr_dir / "2022/Svalbard/GPR_220419_C-Vallakrabreen-100MHz"],
            "20220505": [
                gpr_dir / "2022/Svalbard/GPR_220505_A-VallakrabreenSurgeFront-100MHz"
            ],
        },
        "mettebreen": {
            "20230305": [gpr_dir / "2023/GPR_230305_A-Mettebreen-100MHz"],
        },
        "dronbreen": {
            "20190225": [
                gpr_dir / "2019/Svalbard/GPR_190225_A-Dronbreen-25MHz",
                gpr_dir / "2019/Svalbard/GPR_190225_B-Dronbreen-50MHz",
            ],
            # "20190227": [gpr_dir2 / "2019/Svalbard/GPR_190227_A-Dronbreen-50MHz"],
            "20200224": [gpr_dir / "2020/Svalbard/GPR_200224_A-Dronbreen-100MHz"],
            "20200225": [gpr_dir / "2020/Svalbard/GPR_200225_A-Dronbreen-100MHz"],
            "20200226": [
                gpr_dir / "2020/Svalbard/GPR_200226_A-Dronbreen-25MHz",
                gpr_dir / "2020/Svalbard/GPR_200226_B-Dronbreen-50MHz",
                gpr_dir / "2020/Svalbard/GPR_200226_C-Dronbreen-100MHz",
            ],
            "20220328": [
                gpr_dir / "2022/Svalbard/GPR_220328_A-Dronbreen-100MHz",
            ],
            "20220329": [
                gpr_dir / "2022/Svalbard/GPR_220329_A-Dronbreen-100MHz",
            ],
            "20230220": [
                gpr_dir / "2023/GPR_230220_B-Dronbreen-100MHz"
            ],  
            "20230221": [
                gpr_dir / "2023/GPR_230221_B-Dronbreen-100MHz"
            ],  
            "20240209": [gpr_dir / "2024/GPR_20240209_A-Dronbreen-100MHz"],
            "20250325": [gpr_dir / "2025/GPR_20250325_A-Dronbreen-100MHz"],
            "20250326": [
                gpr_dir / "2025/GPR_20250326_A-Dronbreen-100MHz",
                gpr_dir / "2025/GPR_20250326_B-Dronbreen-25MHz",
            ],
            "20250327": [
                gpr_dir / "2025/GPR_20250327_A-Dronbreen-25MHz",
            ],
        },
        "lofthusbreen": {
            "20250326": [gpr_dir / "2025/GPR_20250326_C-Lofthusbreen-25MHz"],
        },
        "slakbreen": {
            "20220330": [gpr_dir / "2022/Svalbard/GPR_220330_A-Slakbreen-100MHz"],
            "20230320": [gpr_dir / "2023/GPR_230320_A-Slakbreen-100MHz"],
            "20240310": [gpr_dir / "2024/GPR_20240310_A-Slakbreen-25MHz"],
        },
        "jinnbreen": {
            "20240206": [
                gpr_dir / "2024/GPR_20240206_A-Jinnbreen-100MHz",
                gpr_dir / "2024/GPR_20240206_C-Jinnbreen-25MHz",
            ],
        },
        "ragna_mariebreen": {
            "20240317": [gpr_dir / "2024/GPR_20240317_B-RagnaMariebreen-100MHz"],
            "20230305": [gpr_dir / "2023/GPR_230305_B-RagnaMariebreen-100MHz"],
            "20240405": [gpr_dir / "2024/GPR_20240405_A-RagnaMariebreen-100MHz"],
            "20240412": [gpr_dir / "2024/GPR_20240412_C-RagnaMariebreen-25MHz"],
        },
        "edvardbreen": {
            "20230305": [gpr_dir / "2023/GPR_230305_C-Edvardbreen-100MHz"],
            "20240411": [gpr_dir / "2024/GPR_20240411_A-Edvardbreen-25MHz"],
            "20240407": [gpr_dir / "2024/GPR_20240407_A-Edvardbreen-100MHz"],
        },
        "filantropbreen": {
            "20240406": [gpr_dir / "2024/GPR_20240406_A-Filantropbreen-100MHz"],
        },
        "etonbreen": {
            "20240503": [
                gpr_dir / "2024/GPR_20240503_B-EtonbreenProfile-25MHz",
                gpr_dir / "2024/GPR_20240503_C-EtonbreenWinsnesbreenCross-25MHz",
            ],
            "20250506": [
                gpr_dir / "2025/GPR_20250506_A-Etonbreen-100MHz/DAT_0027_B1",
                gpr_dir / "2025/GPR_20250506_A-Etonbreen-100MHz/DAT_0028_B1",
            ],
        },
        "winsnesbreen": {
            "20240503": [
                gpr_dir / "2024/GPR_20240503_D-WinsnesbreenFreehand-25MHz",
                gpr_dir / "2024/GPR_20240503_E-WinsnesbreenCenterline-25MHz",
            ],
        },
        "austfonna": {
            "20240507": [
                gpr_dir / "2024/GPR_20240507_A-AustfonnaWestMargin-25MHz"
            ],
        },
        "amenfonna": {
            "20240510": [gpr_dir / "2024/GPR_20240510_A-Amenfonna-25MHz"],
        },
        "elfenbeinbreen": {
            "20250326": [
                gpr_dir / "2025/GPR_20250326_D-Elfenbeinbreen-100MHz/DAT_0435_B1",
                gpr_dir / "2025/GPR_20250326_D-Elfenbeinbreen-100MHz/DAT_0436_B1",

            ],

        },
    }

    n_total = 0
    missing = []
    for key in filepaths:
        for key2 in filepaths[key]:
            for dir_entry in filepaths[key][key2]:
                n_total += 1
                if not dir_entry.is_dir():
                    missing.append(dir_entry)

    if len(missing) < 10:
        for dir_entry in missing:
            print(f"{dir_entry} not found")
    else:
        print(f"{len(missing)}/{n_total} GPR directories not found")

    if offline:
        # Remove all entries containing key2. Not sure why it doesn't take all on the first try!
        for _ in range(3):
            for key in filepaths:
                for key2 in filepaths[key]:
                    dir_list = filepaths[key][key2]
                    for dir_entry in dir_list:
                        if str(gpr_dir) in str(dir_entry):
                            dir_list.remove(dir_entry)

    return filepaths


def get_dem_path(radar_key: str) -> Path:

    dem_dir = Path("./dems/").absolute()

    year = int(radar_key.split("-")[1][:4])

    match radar_key.split("-")[0]:
        case "austfonna" | "etonbreen" | "amenfonna" | "winsnesbreen":
            return dem_dir / "austfonna_dem_2024.tif"
        case "moysalbreen" | "rugaasfonna" | "bergmesterbreen" | "svellnosbreen":
            return dem_dir / "dron_moysal_kok_dem_2022.tif"
        case "edvardbreen" | "mettebreen" | "ragna_mariebreen" | "kroppbreen":
            return dem_dir / "edvard_mette_ragna_kropp_dem_2024.tif"
        case "elfenbeinbreen":
            return dem_dir / "elfenbeinbreen_dem_2022.tif"
        case "filantropbreen":
            return dem_dir / "filantropbreen_dem_2023.tif"
        case "fimbulisen":
            return dem_dir / "fimbulisen_dem_2022.tif"
        case "jinnbreen":
            return dem_dir / "jinnbreen_dem_2022.tif"
        case "finsterwalderbreen" | "antoniabreen":
            return dem_dir / "finsterwalderbreen_antoniabreen_dem_2023.tif"
        case "rabotbreen":
            return dem_dir / "rabotbreen_dem_2024.tif"
        case "scott_turnerbreen":
            return dem_dir / "scott_turnerbreen_dem_2021.tif"
        case "von_postbreen":
            return dem_dir / "von_postbreen_dem_2024.tif"
        case "dronbreen" | "lofthusbreen":
            match year:
                case 2023 | 2024:
                    return dem_dir / "dronbreen_dem_2024.tif"
                case _:
                    return dem_dir / "dron_moysal_kok_dem_2022.tif"
        case "slakbreen":
            match year:
                case 2022:
                    return dem_dir / "slakbreen_dem_2022.tif"
                case _:
                    return dem_dir / "slakbreen_dem_2023.tif"
        case "vallakrabreen":
            match year:
                case 2021:
                    return dem_dir / "vallakra_dem_2021.tif"
                case _:
                    return dem_dir / "vallakra_dem_2022.tif"

    raise ValueError(f"No DEM match for radar key {radar_key}")

def extract_glacier_raw_data(glacier: str = "dronbreen"):
    import shutil

    filepaths = get_paths()[glacier]

    for date_str, date_fps in filepaths.items():
        for filepath in date_fps:
            for rad_fp in filepath.rglob("*.rad"):
                out_dir = Path(f"{glacier}/{date_str}/{rad_fp.stem}")
                out_dir.mkdir(exist_ok=True, parents=True)

                for fp2 in rad_fp.parent.glob(f"*{rad_fp.stem}*"):
                    out_fp = out_dir / fp2.name
                    if out_fp.is_file():
                        continue
                    shutil.copyfile(fp2, out_fp)
                print(rad_fp)


RSGPR_PATH = "/home/erikmann/Projects/UiO/rsgpr/target/release/rsgpr"


def run_rsgpr(
    input_filepath: Path | str,
    output_filepath: Path | str,
    dem_path: Path | None = None,
    merge: str | None = "30 min",
    antenna: str | None = None,
):
    siglog_strength = 1
    if antenna is not None and "25 MHz" in antenna:
        siglog_strength = 0

    # Unit: dB / ns of TWT. Found using auto_gain. The value below is for 25 MHz
    gain_strength = 0.002340
    if antenna is not None and "100 MHz" in antenna:
        gain_strength = 0.003556

    rsgpr_steps = [
        "remove_empty_traces",
        "zero_corr",
        "correct_antenna_separation",
        f"bandpass",
        "dewow(15)",  # Some long-range undulations are not captured by bandpass. Unsure why.
        f"gain({gain_strength})",
        f"siglog({siglog_strength})",
    ]

    # This radargram is very long and the bed is not visible. This cuts the invisible parts. 
    if "GPR_20250326_D-Elfenbeinbreen-100MHz/DAT_0436_B1" in str(input_filepath):
        rsgpr_steps.insert(0, "subset(18500 -1)")

    cmds = (
        [
            RSGPR_PATH,
            "-v",
            "0.168",
            "--steps",
            ",".join(rsgpr_steps),
            "--filepath",
            str(input_filepath),
            "--output",
            str(output_filepath),
            "-r",
        ]
        + ((["--merge", merge])
        if merge is not None
        else [])
        + ((["--dem", str(dem_path)])
        if dem_path is not None
        else [])
    )

    result = subprocess.run(
        cmds,
        # check=True,
        capture_output=True,
    )
    if result.returncode != 0:
        raise ValueError(f"rsgpr failed: {result.stderr}")

    log_filepath = Path(output_filepath).with_suffix(".log")

    log_filepath.write_text(
        f"stdout:\n{result.stdout.decode()}\n\n\nstderr:\n{result.stderr.decode()}"
    )


class GprInfo:
    filepath: str
    samples: int
    traces: int
    frequency: float
    antenna: str
    start_time: datetime.datetime
    stop_time: datetime.datetime
    track_length: float

    def is_compatible(self, other: Self) -> bool:
        return all(
            [
                self.samples == other.samples,
                self.frequency == other.frequency,
                self.antenna == other.antenna,
            ]
        )

    def time_between(self, other: Self) -> datetime.timedelta:
        if self.start_time > other.stop_time:
            return self.start_time - other.stop_time

        if self.stop_time < other.start_time:
            return datetime.timedelta(
                seconds=-(self.start_time - other.stop_time).total_seconds()
            )
            # return self.stop_time - other.start_time

        if self.start_time == self.start_time:
            return datetime.timedelta(seconds=0)

        raise NotImplementedError()
        diff0 = self.start_time - other.stop_time
        diff1 = self.stop_time - other.start_time

        return min(abs(diff0), abs(diff1))

    @classmethod
    def from_rsgpr(cls, filepath: Path):
        result = subprocess.run(
            [
                RSGPR_PATH,
                "--info",
                "--filepath",
                str(filepath),
            ],
            capture_output=True,
        )
        if result.returncode != 0:
            raise ValueError(f"rsgpr failed: {result.stderr.decode()}")
        new = cls()

        def parse(line: str, key: str, constructor: Callable, unit: str | None = None):
            if key not in line:
                return

            value = line.replace(key, "").strip()
            if unit is not None:
                value = value.split(unit)[0].strip()

            return constructor(value)

        for line in result.stdout.decode().splitlines():
            if (value := parse(line, "Samples (height):", int)) is not None:
                new.samples = value
            elif (value := parse(line, "Traces (width):", int)) is not None:
                new.traces = value
            elif (
                value := parse(line, "Sampling frequency:", float, "MHz")
            ) is not None:
                new.frequency = value
            elif (value := parse(line, "Track length:", float, "m")) is not None:
                new.track_length = value
            elif (
                value := parse(
                    line,
                    "Antenna:",
                    str,
                )
            ) is not None:
                new.antenna = value
            elif (
                value := parse(
                    line,
                    "Filepath:",
                    str,
                )
            ) is not None:
                new.filepath = value.replace('"', "")
            elif (
                value := parse(line, "Start time:", datetime.datetime.fromisoformat)
            ) is not None:
                new.start_time = value
            elif (
                value := parse(line, "Stop time:", datetime.datetime.fromisoformat)
            ) is not None:
                new.stop_time = value

        # print(result.stdout.decode())
        return new


# def rsgpr_info(filepath: Path) -> GprInfo:


def run_all(offline: bool = False, force_redo: bool = False):
    all_paths = get_paths(offline=offline)

    bad_list = [
        "scott_turnerbreen-20240207-DAT_0452_A1_1",
        "fimbulisen-20220430-DAT_0083_B1_1",
        "fimbulisen-20220430-DAT_0082_B1_1",
        "etonbreen-20240503-DAT_0010_A1_1",
        "vallakrabreen-20210513-DAT_0011_A1_1",
        "vallakrabreen-20220505-DAT_0101_A1_1",
        "ragna_mariebreen-20240317-DAT_0349_A1_1",
        "ragna_mariebreen-20240317-DAT_0343_A1_1",
        "ragna_mariebreen-20240317-DAT_0328_A1_2",
        "ragna_mariebreen-20240317-DAT_0328_A1_2",
        "ragna_mariebreen-20240317-DAT_0316_A1_2",
        "ragna_mariebreen-20240317-DAT_0318_A1_6",
        "ragna_mariebreen-20230305-DAT_0050_A1_15",
        "dronbreen-20200226-DAT_0086_A1_H_1",
        "dronbreen-20190225-DAT_0011_A1_4",
        "moysalbreen-20220222-DAT_0760_A1_1",
        "dronbreen-20250326-DAT_0011_A1_2",
        "dronbreen-20250326-DAT_0008_A1_1",
        "dronbreen-20250326-DAT_0009_A1_1",
        "slakbreen-20220330-DAT_0252_A1_1",
        "antoniabreen-20250406-DAT_0167_A1_1",
        "finsterwalderbreen-20250407-DAT_0170_A1_1",
    ]

    for glacier, per_date in all_paths.items():
        for date_str, paths in per_date.items():
            for file_dir in paths:
                if not file_dir.is_dir():
                    raise ValueError(f"Could not find {file_dir}")

                # infos: list[GprInfo] = []
                groups: list[list[GprInfo]] = [[]]
                for filepath in sorted(file_dir.rglob("*.rad")):
                    try:
                        gpr_info = GprInfo.from_rsgpr(filepath)
                    except ValueError as exception:
                        if "Could not parse location data" in str(exception):
                            print(f"Skipped {filepath} (invalid location)")
                            continue
                        raise
                    # infos.append(gpr_info)

                    if len(groups) == 1 and len(groups[-1]) == 0:
                        groups[-1].append(gpr_info)
                        continue

                    # print(infos[-2].time_between(gpr_info))
                    if gpr_info.is_compatible(groups[-1][-1]) and (
                        groups[-1][-1].time_between(gpr_info)
                        < datetime.timedelta(minutes=30)
                    ):
                        groups[-1].append(gpr_info)

                    else:
                        groups.append([gpr_info])

                for group in groups:
                    if len(group) == 0:  # TODO: Find out why this can happen
                        continue
                    group_traces = sum(i.traces for i in group)
                    group_name = Path(group[0].filepath).stem + f"_{len(group)}"
                    radar_key = f"{glacier}-{date_str}-{group_name}"

                    dem_path = get_dem_path(radar_key=radar_key)

                    if not dem_path.is_file():
                        raise ValueError(f"DEM cannot be found: {dem_path}")

                    if group_traces < 300:
                        print(
                            f"Skipped {glacier}/{date_str}/{group_name} (width={group_traces})"
                        )
                        continue

                    group_length = sum(i.track_length for i in group)
                    if group_length < 100:
                        print(
                            f"Skipped {glacier}/{date_str}/{group_name} (length={group_length:.1f}m)"
                        )
                        continue
                    with tempfile.TemporaryDirectory() as temp_dir:
                        if len(group) > 1:
                            input_dir = Path(temp_dir) / "input"
                            input_dir.mkdir(exist_ok=True)

                            for item in group:
                                filepath = Path(item.filepath)
                                for subfile in list(
                                    filepath.parent.glob(filepath.stem + ".*")
                                ):
                                    (input_dir / subfile.name).symlink_to(subfile)

                            filepath = "" + str(input_dir) + "/*.rad"

                        else:
                            filepath = group[-1].filepath

                        out_path = Path(
                            f"processed_radar/{glacier}/{date_str}/{group_name}.nc"
                        )
                        out_path.parent.mkdir(exist_ok=True, parents=True)

                        if radar_key in bad_list:
                            if out_path.is_file():
                                print(
                                    f"{out_path} on bad list but it exists. Removing..."
                                )
                                os.remove(out_path)
                            else:
                                print(
                                    f"Skipped radar key: {radar_key} as it was on the bad list"
                                )
                            continue

                        if out_path.is_file():
                            if not force_redo:
                                continue
                            print(f"Reprocessing {out_path}")
                        else:
                            print(f"Processing {out_path}")
                        try:
                            run_rsgpr(
                                filepath,
                                out_path,
                                dem_path=dem_path,
                                antenna=group[0].antenna,
                            )
                        except subprocess.CalledProcessError as exception:
                            raise
                            print(exception)


if __name__ == "__main__":
    run_all()
