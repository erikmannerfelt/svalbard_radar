import subprocess
from pathlib import Path
import tempfile
import datetime
from typing import Self, Callable

def get_paths():

    gpr_dir = Path("/home/erikmann/GPR/")

    return {
        "scott_turnerbreen": {
            "20240207": [gpr_dir / "2024/GPR_20240207_A-ScottTurnerbreen-100MHz/"],
        },
        "bergmesterbreen": {
            "20230222": [gpr_dir / "2023/GPR_230222_D-Bergmesterbreen-100MHz/"],
        }
    }

RSGPR_PATH = "/home/erikmann/Projects/UiO/rsgpr/target/release/rsgpr"

def run_rsgpr(input_filepath: Path | str, output_filepath: Path | str, merge: str | None = "30 min"):

    rsgpr_steps = [
        # "subset(0 3500)",
        "zero_corr_max_peak",
        "correct_antenna_separation",
        "normalize_horizontal_magnitudes(0.3)",
        "dewow(5)",
        # "kirchhoff_migration2d",
        "gain(0.043412704)",
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
        check=True,
        stdout=subprocess.PIPE,
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
            check=True,
            stdout=subprocess.PIPE,
        )
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
                with tempfile.TemporaryDirectory() as temp_dir:

                    # infos: list[GprInfo] = []
                    groups: list[list[GprInfo]] = [[]]
                    for filepath in sorted(file_dir.rglob("*.rad")):
                        gpr_info = GprInfo.from_rsgpr(filepath)

                        if (gpr_info.traces < 100) or (gpr_info.track_length < 100):
                            continue
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
                        group_name = Path(group[0].filepath).stem + f"_{len(group)}"

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

                        try:
                            out_path = Path(f"temp/{glacier}/{date_str}/{group_name}.nc")
                            out_path.parent.mkdir(exist_ok=True, parents=True)
                            run_rsgpr(
                                filepath,
                                out_path,
                            )
                        except subprocess.CalledProcessError as exception:
                            print(exception)

                        print(group_name)
                # i0 = -3
                # i1 = -2

                # print(infos[i0].start_time, infos[i0].stop_time)
                # print(infos[i1].start_time, infos[i1].stop_time)
                # print(infos[i0].time_between(infos[i1]))

                # run_rsgpr(filepath, f"{temp_dir}/")

                # print(list(Path(temp_dir).iterdir()))
            


        
