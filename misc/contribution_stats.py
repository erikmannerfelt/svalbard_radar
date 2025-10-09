import numpy as np

from pathlib import Path

def main(target_avg_per_radargram: int = 8):

    active_user_dirs = list(Path("./submitted").iterdir())


    n_submissions_per_radargram = {}
    n_submissions_per_user = []

    n_active_users = 0
    for user_dir in active_user_dirs:
        if not user_dir.is_dir():
            continue
        n_active_users += 1

        n_submissions_per_user.append(0)

        for radargram_dir in user_dir.iterdir():
            if not radargram_dir.is_dir():
                continue

            n_submissions_per_user[-1] += 1

            if radargram_dir.stem not in n_submissions_per_radargram:
                n_submissions_per_radargram[radargram_dir.stem] = 1
            else:
                n_submissions_per_radargram[radargram_dir.stem] += 1

    avg_submissions_per_radar = np.mean(list(n_submissions_per_radargram.values()))

    trunc_avg_submissions_per_radar = np.mean(np.clip(list(n_submissions_per_radargram.values()), a_min=0, a_max=target_avg_per_radargram))
    truncated_progress = trunc_avg_submissions_per_radar / target_avg_per_radargram


    n_below_threshold = np.count_nonzero(np.array(list(n_submissions_per_radargram.values())) < target_avg_per_radargram)

    print(n_below_threshold)

    print(f"N active users: {n_active_users}")
    print(f"Avg submissions per user: {np.mean(n_submissions_per_user):.0f}")
    print(f"Avg submissions per radargram: {avg_submissions_per_radar:.1f}")
    print(f"Progress toward all having {target_avg_per_radargram} or more: {100 * truncated_progress:.1f}%")

if __name__ == "__main__":
    main()
