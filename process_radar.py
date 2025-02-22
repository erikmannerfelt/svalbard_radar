import subprocess
from pathlib import Path
import tempfile
import datetime
from typing import Self, Callable

def get_paths(offline: bool = False):

    gpr_dir = Path("/home/erikmann/GPR/")
    gpr_dir2 = Path("/remotes/nornan/Erik/Data/GPR")

    missing = [
        "Scott 2019",
        "Ayer 2019",
        "Rieper 2019",
        "Vallakra 2021",
        "Mette 2024",
        "Dron 20190227",
        "Dron 2022",
        "Dron 2024",
        "Ragna 20240317",
    ]

    print("Missing", "\n".join(missing))

    filepaths = {
        "scott_turnerbreen": {
            "20240207": [gpr_dir / "2024/GPR_20240207_A-ScottTurnerbreen-100MHz/"],
        },
        "bergmesterbreen": {
            "20230222": [
                gpr_dir / "2023/GPR_230222_D-Bergmesterbreen-100MHz/",
                gpr_dir / "2023/GPR_230222_E-BergmesterbreenSlakbreen-100MHz/",
            ],
        },
        "kroppbreen": {
            "20230228": [gpr_dir / "2023/GPR_230228_A-Kroppbreen-100MHz/"],
            "20240407": [gpr_dir / "2024/GPR_20240407_B-Kroppbreen-100MHz"],
        },
        "rugaasfonna": {
            "20220218": [gpr_dir2/ "2022/Svalbard/GPR_220218_A-Kokbreen-100MHz"],
            "20220222": [gpr_dir2/ "2022/Svalbard/GPR_220222_A-Kokbreen-100MHz"],
        },
        "svellnosbreen": {
            "20220218": [gpr_dir2 / "2022/Svalbard/GPR_220218_B-Svellnosbreen-100MHz"],
        },
        "moysalbreen": {
            "20220222": [gpr_dir2 / "2022/Svalbard/GPR_220222_B-Moysalbreen-100MHz"],

        },
        "fimbulisen": {
            "20220430": [gpr_dir2 / "2022/Svalbard/GPR_220430_B-Fimbulisen-100MHz"]
        },
        "vallakrabreen": {
            "20220419": [gpr_dir2 / "2022/Svalbard/GPR_220419_C-Vallakrabreen-100MHz"],
            "20220505": [gpr_dir2 / "2022/Svalbard/GPR_220505_A-VallakrabreenSurgeFront-100MHz"],
        },
        "mettebreen": {
            "20230305": [gpr_dir2 / "2023/GPR_230305_A-Mettebreen-100MHz"],
        },
        "dronbreen": {
            "20190225": [
                gpr_dir2 / "2019/Svalbard/GPR_190225_A-Dronbreen-25MHz",
                gpr_dir2 / "2019/Svalbard/GPR_190225_B-Dronbreen-50MHz",
            ],
            # "20190227": [gpr_dir2 / "2019/Svalbard/GPR_190227_A-Dronbreen-50MHz"],
            "20200224": [gpr_dir2 / "2020/Svalbard/GPR_200224_A-Dronbreen-100MHz"],
            "20200225": [gpr_dir2 / "2020/Svalbard/GPR_200225_A-Dronbreen-100MHz"],
            "20200226": [
                gpr_dir2 / "2020/Svalbard/GPR_200226_A-Dronbreen-25MHz",
                gpr_dir2 / "2020/Svalbard/GPR_200226_B-Dronbreen-50MHz",
                gpr_dir2 / "2020/Svalbard/GPR_200226_C-Dronbreen-100MHz",
            ],
            "20230220": [gpr_dir / "2023/GPR_230220_B-Slakbreen-100MHz"],  # It's misnamed as slakbreen
            "20230221": [gpr_dir / "2023/GPR_230221_B-Slakbreen-100MHz"],  # It's misnamed as slakbreen
            "20240209": [gpr_dir / "2024/GPR_20240209_A-Dronbreen-100MHz"],
        },
        "slakbreen": {
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
            # "20240317": [gpr_dir / "2024/Input/Radar_16-17.3.24/MALAGS/GPR_20240317_A-RagnaMariebreen-100MHz"],  # This doesn't have proper GPS
            "20230305": [gpr_dir2 / "2023/GPR_230305_B-RagnaMariebreen-100MHz"],
            "20240405": [gpr_dir / "2024/GPR_20240405_A-RagnaMariebreen-100MHz"],
            "20240412": [gpr_dir / "input/GPR_20240412_C-RagnaMariebreen-25MHz"],
        },
        "edvardbreen": {
            "20230305": [gpr_dir2 / "2023/GPR_230305_C-Edvardbreen-100MHz"],
            "20240411": [gpr_dir / "input/GPR_20240411_A-Edvardbreen-25MHz"],
            "20240407": [gpr_dir / "2024/GPR_20240407_A-Edvardbreen-100MHz"],
        },
        "filantropbreen": {
            "20240406": [gpr_dir / "2024/GPR_20240406_A-Filantropbreen-100MHz"],
        },
        "etonbreen": {
            "20240503": [
                gpr_dir / "austfonna/GPR_20240503_B-EtonbreenProfile-25MHz",
                gpr_dir / "austfonna/GPR_20240503_C-EtonbreenWinsnesbreenCross-25MHz"
            ],
        },
        "winsnesbreen": {
            "20240503": [
                gpr_dir / "austfonna/GPR_20240503_D-WinsnesbreenFreehand-25MHz",
                gpr_dir / "austfonna/GPR_20240503_E-WinsnesbreenCenterline-25MHz",
            ],
        },
        "austfonna": {
            "20240507": [gpr_dir / "austfonna/GPR_20240507_A-AustfonnaWestMargin-25MHz"],
        },
        "amenfonna": {
            "20240510": [gpr_dir / "austfonna/GPR_20240510_A-Amenfonna-25MHz"],
        },
    }

    if offline:

        # Remove all entries containing key2. Not sure why it doesn't take all on the first try!
        for _ in range(3):
            for key in filepaths:
                for key2 in filepaths[key]:
                    dir_list = filepaths[key][key2]
                    for dir_entry in dir_list:
                        if str(gpr_dir2) in str(dir_entry):
                            dir_list.remove(dir_entry)
            
    return filepaths

RSGPR_PATH = "/home/erikmann/Projects/UiO/rsgpr/target/release/rsgpr"

def run_rsgpr(input_filepath: Path | str, output_filepath: Path | str, merge: str | None = "30 min"):

    rsgpr_steps = [
        # "subset(0 3500)",
        # "zero_corr_max_peak",
        "zero_corr",
        "correct_antenna_separation",
        "normalize_horizontal_magnitudes(0.3)",
        "dewow(5)",
        # "kirchhoff_migration2d",
        # "gain(0.043412704)",
    ]

    cmds = [
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
    ] + (["--merge", merge]) if merge is not None else []
    

    
    result = subprocess.run(
        cmds,
        # check=True,
        capture_output=True,
    )
    if result.returncode != 0:
        raise ValueError(f"rsgpr failed: {result.stderr}")

    log_filepath = Path(output_filepath).with_suffix(".log")

    log_filepath.write_text(f"stdout:\n{result.stdout.decode()}\n\n\nstderr:\n{result.stderr.decode()}")


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
            return datetime.timedelta(seconds=-(self.start_time - other.stop_time).total_seconds())
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
            elif (value := parse(line, "Sampling frequency:", float, "MHz")) is not None:
                new.frequency = value
            elif (value := parse(line, "Track length:", float, "m")) is not None:
                new.track_length = value
            elif (value := parse(line, "Antenna:", str,)) is not None:
                new.antenna = value
            elif (value := parse(line, "Filepath:", str,)) is not None:
                new.filepath = value.replace('"', "")
            elif (value := parse(line, "Start time:", datetime.datetime.fromisoformat)) is not None:
                new.start_time = value
            elif (value := parse(line, "Stop time:", datetime.datetime.fromisoformat)) is not None:
                new.stop_time = value

        # print(result.stdout.decode())
        return new
        



# def rsgpr_info(filepath: Path) -> GprInfo:

def run_all():
    all_paths = get_paths()


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
                    if gpr_info.is_compatible(groups[-1][-1]) and (groups[-1][-1].time_between(gpr_info) < datetime.timedelta(minutes=30)):
                        groups[-1].append(gpr_info)

                    else:
                        groups.append([gpr_info]) 


                for group in groups:

                    if len(group) == 0: # TODO: Find out why this can happen
                        continue
                    group_traces = sum(i.traces for i in group)
                    group_name = Path(group[0].filepath).stem + f"_{len(group)}"
                    if (group_traces < 300):
                        print(f"Skipped {glacier}/{date_str}/{group_name} (width={group_traces})")
                        continue

                    group_length = sum(i.track_length for i in group)
                    if (group_length < 100):
                        print(f"Skipped {glacier}/{date_str}/{group_name} (length={group_length:.1f}m)")
                        continue
                    with tempfile.TemporaryDirectory() as temp_dir:

                        if len(group) > 1:
                            input_dir = Path(temp_dir) / "input"
                            input_dir.mkdir(exist_ok=True)

                            for item in group:
                                filepath = Path(item.filepath)
                                for subfile in list(filepath.parent.glob(filepath.stem + ".*")):
                                    (input_dir / subfile.name).symlink_to(subfile)

                            filepath = "" + str(input_dir) + "/*.rad"

                            
                        else:
                            filepath = group[-1].filepath

                        out_path = Path(f"processed_radar/{glacier}/{date_str}/{group_name}.nc")
                        out_path.parent.mkdir(exist_ok=True, parents=True)

                        if out_path.is_file():
                            continue

                        print(f"Processing {out_path}")
                        try:
                            run_rsgpr(
                                filepath,
                                out_path,
                            )
                        except subprocess.CalledProcessError as exception:
                            raise
                            print(exception)


if __name__ == "__main__":
    run_all()
