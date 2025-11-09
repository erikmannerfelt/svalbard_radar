import concurrent.futures
import datetime
import functools
import hashlib
import json
import os
import socket
import string
import threading
from pathlib import Path
from typing import Callable

import dotenv
import flask
import flask_login
import jsonschema
import werkzeug.security
from gevent.pywsgi import WSGIServer

from svalbardradar import format_radargrams

APP = flask.Flask(__name__, static_folder="web/static/", template_folder="web/templates/")

dotenv.load_dotenv()

APP.config["MAX_CONTENT_LENGTH"] = 50 * 1024 * 1024  # 50 MB
LOGIN_MANAGER = flask_login.LoginManager(APP)


class Debug:
    def __init__(self, debug: bool):
        self.debug = debug

    def __bool__(self):
        return self.debug


DEBUG = Debug(False)


def read_privatekey():
    # The \n is an error on my side, but now it's all distributed so it's too late to fix!
    return os.environ["PRIVATEKEY"] + "\n"


APP.secret_key = read_privatekey()


def gen_password(username: str):
    length = 10

    password = ""
    checksum = hashlib.sha256((read_privatekey() + username).encode())
    letters = string.ascii_letters
    digits = string.digits

    all_chars = [*letters, *digits]

    for i in list(checksum.digest()):
        letter = all_chars[i % len(all_chars)]
        if len(password) >= length:
            continue
        password += letter

    return password


def gen_password_hash(username: str):
    return werkzeug.security.generate_password_hash(gen_password(username))


USER_DATA = {}


class User(flask_login.UserMixin):
    def __init__(self, username: str):
        self.id = username
        self.username = username


@LOGIN_MANAGER.user_loader
def load_user(username: str):
    if username in USER_DATA:
        return User(username=username)
    return None


@APP.route("/login", methods=["GET", "POST"])
def login():
    if flask.request.method == "POST":
        username = flask.request.form["username"]
        password = flask.request.form["password"]

        if username in USER_DATA and werkzeug.security.check_password_hash(USER_DATA[username], password):
            user_obj = User(username=username)
            flask_login.login_user(user_obj)
            return flask.redirect(flask.url_for("index"))
        else:
            flask.flash("Incorrect username or password.", "danger")

    return flask.render_template("login.html.jinja2")


@APP.route("/logout", methods=["GET", "POST"])
@flask_login.login_required
def logout():
    flask_login.logout_user()
    flask.flash("Logged out successfully.", "success")
    return flask.redirect(flask.url_for("login"))


def get_submitted_path() -> Path:
    return Path("submitted/")


def make_digitize_schema():
    geojson_schema = {
        "type": "object",
        "properties": {
            "type": {"type": "string"},
            "features": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "type": {"type": "string"},
                        "geometry": {"type": "object"},
                        "properties": {"type": "object"},
                    },
                    "required": ["type", "geometry"],
                },
            },
        },
        "required": ["type", "features"],
    }
    schema = {
        "date_modified": {"type": "string"},
        "radar_key": {"type": "string"},
        "height": {"type": "integer"},
        "width": {"type": "integer"},
        "comment": {"type": "string"},
        "features": geojson_schema,
        "user": {"type": "string"},
        "required": ["date_modified", "height", "width", "features", "user"],
    }
    return schema


def nice_name(glacier_key: str) -> str:
    if glacier_key == "dronbreen":
        return "Drønbreen"
    elif glacier_key == "vallakrabreen":
        return "Vallåkrabreen"
    elif glacier_key == "moysalbreen":
        return "Møysalbreen"

    return " ".join(map(lambda part: part.capitalize(), glacier_key.replace("_", " ").split(" ")))


class Submissions:
    all_users: list[str]
    user_submission_funcs: dict[str, Callable]

    @staticmethod
    def _get_all_user_submissions_inner(user_dir: Path) -> dict[str, Path]:
        if not user_dir.is_dir():
            return {}

        submissions = {}
        for key_dir in user_dir.glob("*"):
            if not key_dir.is_dir():
                continue

            submissions[key_dir.stem] = list(key_dir.glob("*.json"))

        return submissions

    def _refresh(self):
        """Reload the submissions database."""
        self.all_users = list(USER_DATA.keys())

        self.user_submission_funcs = {}
        for user in self.all_users:
            user_dir = self.get_user_dir(username=user)
            func = functools.partial(self._get_all_user_submissions_inner, user_dir=user_dir)
            func = functools.cache(func)
            func.cache_clear()
            self.user_submission_funcs[user] = func

    def __init__(self):
        self._refresh()

    def get_user_dirs(self) -> list[Path]:
        """Get directories of all users (existing or not)."""
        return [self.get_user_dir(username) for username in USER_DATA]

    def get_user_dir(self, username: str) -> Path:
        """Get directories of a specific user."""
        return get_submitted_path() / username

    def get_all_user_submissions(self, username: str) -> dict[str, list[Path]]:
        if username not in self.user_submission_funcs:
            return {}
        return self.user_submission_funcs[username]()

    def clear_user_cache(self, username: str) -> None:
        """Clear the cache of the submissions for a user."""
        self.user_submission_funcs[username].cache_clear() # pyright: ignore[reportFunctionMemberAccess]

    def get_user_submissions(self, username: str, key: str) -> list[Path]:
        """Get all submissions made by a user for the given key."""
        if username not in self.user_submission_funcs:
            return []
        return self.user_submission_funcs[username]().get(key, [])

    def get_latest_user_submission_path(self, username: str, key: str) -> Path | None:
        """Get the most recent user submission path for the given key."""
        submissions = self.get_user_submissions(username=username, key=key)

        if len(submissions) == 0:
            return

        return sorted(submissions, key=lambda fp: fp.stem.split("-")[-1])[-1]

    def read_latest_user_submission(self, username: str, key: str) -> dict[str, object] | None:
        latest_submission = self.get_latest_user_submission_path(username=username, key=key)

        if latest_submission is None:
            return None

        return json.loads(latest_submission.read_text())

    def get_n_users_submitted(self, key: str) -> int:
        """Get the count of users that have submitted under this key."""
        n = 0
        for username in self.all_users:
            if len(self.get_user_submissions(username=username, key=key)) > 0:
                n += 1
        return n


SUBMISSIONS = Submissions()


def get_username() -> str | None:
    user = flask_login.current_user

    if hasattr(user, "username"):
        return user.username

    return None


@flask_login.login_required
@APP.route("/user_submissions.json")
def get_n_user_submissions():
    username = get_username()
    if username is None:
        return flask.jsonify(None)

    all_submissions = SUBMISSIONS.get_all_user_submissions(username=username)
    out = {
        "per_radar_key": {},
        "per_glacier": {},
    }
    for radar_key in all_submissions:
        glacier_key = radar_key.split("-")[0]

        if glacier_key not in out["per_glacier"]:
            out["per_glacier"][glacier_key] = 0
        out["per_glacier"][glacier_key] += 1

        out["per_radar_key"][radar_key] = len(all_submissions[radar_key])

    return flask.jsonify(out)

    # for submissions in SUBMISSIONS.get_user_submissions(username=username


parse_all_radargrams = functools.cache(format_radargrams.parse_all_radargrams)


def get_n_required_submissions(radar_key: str) -> int:
    """Placeholder function in case we want to complicate the logic of how many submissions are required."""
    # match radar_key:
    #     case "ragna_mariebreen-20240412-DAT_0404_A1_1":
    #         return 100

    return 8


@functools.lru_cache(maxsize=10)
def get_all_radargrams(username: str):
    radargrams = parse_all_radargrams()
    for glacier_key in radargrams:
        radargrams[glacier_key]["_meta"] = {"n_done_by_user": 0}
        for key in radargrams[glacier_key]:
            n_user_submissions = len(SUBMISSIONS.get_user_submissions(username=username, key=key))
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
                key=lambda item: item[1]["n_total_submissions"],
            )
        }
        radargrams[glacier_key]["_meta"].update(
            {
                "n_total_submissions": sum(r["n_total_submissions"] for r in radargrams[glacier_key].values()),
                "nice_name": nice_name(glacier_key),
            }
        )

    radargrams = {
        k: v
        for k, v in sorted(
            radargrams.items(),
            # I'm setting Drønbreen to be the last one because it's so big.
            key=lambda item: 9999
            if item[0] == "dronbreen"
            else (item[1]["_meta"]["n_total_submissions"] / (len(item[1]) - 1)),
        )
    }

    return radargrams


@APP.route("/all_radargrams.json")
def all_radargrams():
    radargrams = {}
    for value in get_all_radargrams(get_username() or "").values():
        out = {}
        for key in value:
            out[key] = {}
            for key2 in value[key]:
                if key2 in ["tiles", "track"]:
                    continue
                out[key][key2] = value[key][key2]

        radargrams.update(out)
    return flask.jsonify(radargrams)


@APP.route("/radargram_meta/<radar_key>.json")
def radargram_meta(radar_key: str):
    try:
        return flask.jsonify(get_all_radargrams(get_username() or "")[radar_key.split("-")[0]][radar_key])
    except KeyError:
        return flask.jsonify({"error": "Key not valid"}), 400


@APP.route("/radargram_latest_submission/<radar_key>.json")
@flask_login.login_required
def radargram_latest_submission(radar_key: str):
    username = get_username()
    if username is None:
        return flask.jsonify({})
    latest = SUBMISSIONS.read_latest_user_submission(username=username, key=radar_key)

    if latest is None:
        return flask.jsonify({})
    return flask.jsonify(latest)


def _recommended() -> list[list[str]]:
    recommendations = [
        "ragna_mariebreen-20240412-DAT_0404_A1_1",
        "dronbreen-20250325-DAT_0007_A1_1",
        "ragna_mariebreen-20240405-DAT_0357_A1_1",
        "dronbreen-20250326-DAT_0004_A1_1",
        "dronbreen-20250325-DAT_0015_A1_7",
        "slakbreen-20240310-DAT_0289_A1_1",
        "elfenbeinbreen-20250326-DAT_0436_B1_1",
        "ragna_mariebreen-20240317-DAT_0332_A1_2",
    ]
    # Extract the glacier name such that it's glacier/radar_key
    recommendations = [[s.split("-")[0], s] for s in recommendations]
    return recommendations


@APP.route("/recommended.json")
def recommended():
    return flask.jsonify(_recommended())


@APP.route("/")
def index():
    all_radargrams = get_all_radargrams(get_username() or "")

    user = get_username()
    return flask.render_template(
        "index.html.jinja2",
        all_keys=all_radargrams.keys(),
        all_radargrams=all_radargrams,
        user=user,
        recommendations=_recommended(),
    )


@APP.route("/digitize/<radar_key>")
def radargram(radar_key: str):
    all_radargrams = get_all_radargrams(get_username() or "")
    meta = all_radargrams[radar_key.split("-")[0]][radar_key]
    user = get_username()

    return flask.render_template("digitize.html.jinja2", meta=meta, radar_key=radar_key, user=user)


@APP.route("/force-reload")
@flask_login.login_required
def force_clear_cache():
    user = get_username()

    if user != "admin":
        return "Unauthorized", 401

    get_all_radargrams.cache_clear()
    parse_all_radargrams.cache_clear()

    return "OK", 200


@APP.route("/submit-digitized", methods=["POST"])
@flask_login.login_required
def submit_digitized():
    req = flask.request

    user = get_username()

    if user is None:
        return flask.jsonify({"error": "Must be logged in"}), 401

    data = req.get_json()
    data["user"] = user
    try:
        jsonschema.validate(data, make_digitize_schema())

        filename = (
            get_submitted_path()
            / f"{user}/{data['radar_key']}/digitized-{data['radar_key']}-{data['date_modified'].replace(':', '-').replace('-', '_')}.json"
        )
        filename.parent.mkdir(exist_ok=True, parents=True)
        filename.write_text(json.dumps(data))

        # What this does is it first clears the user submission cache. I.e. it has to be recalculated when requested.
        SUBMISSIONS.clear_user_cache(username=user or "")
        # Then, the full index has to be recalculated (but all values except the one above are probably cached so it's fast)
        get_all_radargrams.cache_clear()

        return flask.jsonify({"message": "Data submitted successfully", "data": data}), 200

    except jsonschema.ValidationError as exception:
        return flask.jsonify({"error": f"JSON validation error: {exception.message}"}, 400)

    except Exception as exception:
        print(f"Exception when user submitted json: {str(exception)}")
        return flask.jsonify({"error": "Internal error occurred"}, 500)


@APP.route("/howto")
def howto():
    return flask.render_template("howto.html.jinja2")


@APP.after_request
def log_traffic(response: flask.Response):
    request = flask.request

    real_ip = request.headers.get("X-Real-IP", request.remote_addr)

    data = {
        "hostname": request.host,
        "ip_address": real_ip,
        "path": request.path,
        "user_agent": request.headers.get("user-agent", request.headers.get("User-Agent", None)),
        "method": request.method,
        "status": response.status_code,
        "user_id": get_username(),
        "created_at": datetime.datetime.now(datetime.UTC).isoformat(),
    }
    with threading.Lock():
        with open("traffic.log", "a+") as outfile:
            outfile.write(json.dumps(data) + "\n")

    return response


def main(debug: bool = False):
    usernames = Path("usernames.txt").read_text().splitlines()
    with concurrent.futures.ProcessPoolExecutor() as executor:
        pwds = list(executor.map(gen_password_hash, usernames))

    DEBUG.debug = debug
    USER_DATA.update(dict(zip(usernames, pwds, strict=True)))
    SUBMISSIONS._refresh()

    port = 5000
    if "yggdrasil" in socket.gethostname():
        port = 8081

    if debug:
        APP.run(debug=True)
    else:
        http_server = WSGIServer(("0.0.0.0", port), APP)
        http_server.serve_forever()


if __name__ == "__main__":
    main()
