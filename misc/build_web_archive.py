from __future__ import annotations

import functools
import json
import os
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import jinja2

from svalbardradar import format_radargrams


ROOT = Path(__file__).resolve().parents[1]
WEB_DIR = ROOT / "web"
TEMPLATE_DIR = WEB_DIR / "templates"
STATIC_SRC = WEB_DIR / "static"
DOCS_DIR = ROOT / "docs"
SUBMITTED_DIR = ROOT / "submitted"
USERNAMES_FILE = ROOT / "usernames.txt"
BASE_TITLE = "The Svalbard radar interpretation experiment"


def nice_name(glacier_key: str) -> str:
    if glacier_key == "dronbreen":
        return "Drønbreen"
    if glacier_key == "vallakrabreen":
        return "Vallåkrabreen"
    if glacier_key == "moysalbreen":
        return "Møysalbreen"
    return " ".join(part.capitalize() for part in glacier_key.replace("_", " ").split())


def get_n_required_submissions(_: str) -> int:
    return 9


def load_usernames() -> list[str]:
    if not USERNAMES_FILE.exists():
        return []
    return [line.strip() for line in USERNAMES_FILE.read_text().splitlines() if line.strip()]


class Submissions:
    def __init__(self) -> None:
        self.all_users = load_usernames()
        self._cache: dict[str, dict[str, list[Path]]] = {}

    @staticmethod
    def _get_all_user_submissions_inner(user_dir: Path) -> dict[str, list[Path]]:
        if not user_dir.is_dir():
            return {}
        submissions: dict[str, list[Path]] = {}
        for key_dir in user_dir.glob("*"):
            if not key_dir.is_dir():
                continue
            submissions[key_dir.stem] = list(key_dir.glob("*.json"))
        return submissions

    def get_user_submissions(self, username: str, key: str) -> list[Path]:
        if username not in self.all_users:
            return []
        if username not in self._cache:
            self._cache[username] = self._get_all_user_submissions_inner(SUBMITTED_DIR / username)
        return self._cache[username].get(key, [])

    def get_n_users_submitted(self, key: str) -> int:
        return sum(1 for username in self.all_users if self.get_user_submissions(username=username, key=key))


SUBMISSIONS = Submissions()


parse_all_radargrams = functools.cache(format_radargrams.parse_all_radargrams)


def copy_static() -> None:
    dst = DOCS_DIR / "static"
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(
        STATIC_SRC,
        dst,
        ignore=shutil.ignore_patterns("*.map", "README.md", "CHANGELOG.md", "docs", "src", "package*.json", ".package-lock.json"),
    )


def rewrite_static_paths(meta: dict[str, object], prefix: str) -> dict[str, object]:
    out = json.loads(json.dumps(meta))
    out["thumbnail"] = prefix + str(out["thumbnail"]).lstrip("/")
    for tile in out.get("tiles", []):
        for key, value in list(tile.get("filepaths", {}).items()):
            tile["filepaths"][key] = prefix + str(value).lstrip("/")
    return out


def build_all_radargrams() -> dict[str, dict[str, object]]:
    radargrams = parse_all_radargrams()
    for glacier_key in radargrams:
        radargrams[glacier_key]["_meta"] = {"n_done_by_user": 0}
        for key in radargrams[glacier_key]:
            if key == "_meta":
                continue
            n_user_submissions = 0
            n_total_submissions = SUBMISSIONS.get_n_users_submitted(key=key)
            n_required_submissions = get_n_required_submissions(key)
            radargrams[glacier_key][key].update(
                {
                    "n_total_submissions": n_total_submissions,
                    "n_required_submission": n_required_submissions,
                    "is_finished": n_total_submissions >= n_required_submissions,
                    "n_submitted_by_user": n_user_submissions,
                }
            )
            if n_user_submissions > 0:
                radargrams[glacier_key]["_meta"]["n_done_by_user"] += 1

        radargrams[glacier_key] = {
            k: v
            for k, v in sorted(
                radargrams[glacier_key].items(),
                key=lambda item: item[1]["n_total_submissions"] if item[0] != "_meta" else -1,
            )
        }
        radargrams[glacier_key]["_meta"].update(
            {
                "n_total_submissions": sum(r["n_total_submissions"] for r in radargrams[glacier_key].values() if isinstance(r, dict) and "n_total_submissions" in r),
                "nice_name": nice_name(glacier_key),
                "is_finished": False,
                "n_required_submission": 9,
                "n_submitted_by_user": 0,
            }
        )

    radargrams = {
        k: v
        for k, v in sorted(
            radargrams.items(),
            key=lambda item: 9999 if item[0] == "dronbreen" else (item[1]["_meta"]["n_total_submissions"] / (len(item[1]) - 1)),
        )
    }
    return radargrams


def make_environment() -> jinja2.Environment:
    return jinja2.Environment(
        loader=jinja2.FileSystemLoader(str(TEMPLATE_DIR)),
        autoescape=jinja2.select_autoescape(["html", "jinja2"]),
        trim_blocks=True,
        lstrip_blocks=True,
    )


def render_templates(all_radargrams: dict[str, dict[str, object]]) -> None:
    env = make_environment()
    index_template = env.get_template("index.html.jinja2")
    howto_template = env.get_template("howto.html.jinja2")
    digitize_template = env.get_template("digitize.html.jinja2")

    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    (DOCS_DIR / "index.html").write_text(
        index_template.render(
            base_title=BASE_TITLE,
            all_radargrams={
                glacier_key: {
                    key: rewrite_static_paths(meta, "") if key != "_meta" else meta
                    for key, meta in glacier_radargrams.items()
                }
                for glacier_key, glacier_radargrams in all_radargrams.items()
            },
            site_root_prefix="",
            static_prefix="static/",
        )
    )
    (DOCS_DIR / "howto").mkdir(parents=True, exist_ok=True)
    (DOCS_DIR / "howto" / "index.html").write_text(
        howto_template.render(
            base_title=BASE_TITLE,
            site_root_prefix="../",
            static_prefix="../static/",
        )
    )

    for glacier_key, glacier_radargrams in all_radargrams.items():
        for radar_key, meta in glacier_radargrams.items():
            if radar_key == "_meta":
                continue
            page_meta = rewrite_static_paths(meta, "../../")
            page_dir = DOCS_DIR / "digitize" / radar_key
            page_dir.mkdir(parents=True, exist_ok=True)
            (page_dir / "index.html").write_text(
                digitize_template.render(
                    base_title=BASE_TITLE,
                    radar_key=radar_key,
                    meta=page_meta,
                    radar_meta_json=json.dumps(page_meta),
                    site_root_prefix="../../",
                    static_prefix="../../static/",
                )
            )


def main() -> None:
    if DOCS_DIR.exists():
        shutil.rmtree(DOCS_DIR)
    copy_static()
    (DOCS_DIR / ".nojekyll").write_text("")
    all_radargrams = build_all_radargrams()
    render_templates(all_radargrams)


if __name__ == "__main__":
    main()
