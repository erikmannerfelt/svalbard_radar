import flask
import flask_httpauth
import jsonschema
import json
from pathlib import Path

import format_radargrams

APP = flask.Flask(__name__)
AUTH = flask_httpauth.HTTPBasicAuth()

USER_DATA = {
    "admin": "SuperSecretPwd"
}

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
                        "properties": {"type": "object"}
                    },
                    "required": ["type", "geometry"]
                }
            }
        },
        "required": ["type", "features"]
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

    

@AUTH.verify_password
def verify(username: str, password: str) -> bool:
    if not (username and password):
        return False
    return USER_DATA.get(username) == password

def get_all_radargrams():

    radargrams = format_radargrams.parse_all_radargrams()
    user = get_username()
    for key in radargrams:
        radargrams[key].update(
            {
                "n_total_submissions": len(list(get_submitted_path().glob(f"*/{key}"))),
                "n_submitted_by_user": len(list((get_submitted_path() / f"{user}/{key}").glob("*.json"))) if user is not None else 0,
            }
        )

    radargrams = {k: v for k, v in sorted(radargrams.items(), key=lambda item: item[1]["n_total_submissions"])}

    return radargrams


@APP.route("/all_radargrams.json")
def all_radargrams():
    return flask.jsonify(get_all_radargrams())

def get_username() -> str | None:
    req = flask.request

    auth = req.authorization

    if auth is None:
        return

    user = req.authorization.username

    if user not in USER_DATA:
        return

    return user

@APP.route("/")
def index():
    all_radargrams = get_all_radargrams()

    user = get_username()
    return flask.render_template("index.html.jinja2", all_keys=all_radargrams.keys(), all_radargrams=all_radargrams, user=user)


@APP.route("/digitize/<radar_key>")
def radargram(radar_key: str):
    all_radargrams = get_all_radargrams()
    meta = all_radargrams[radar_key]

    return flask.render_template("digitize.html.jinja2", meta=meta, radar_key=radar_key)


@APP.route("/submit-digitized", methods=["POST"])
@AUTH.login_required
def submit_digitized():
    req = flask.request

    user = req.authorization.username

    data = req.get_json()
    data["user"] = user

    try:
        jsonschema.validate(data, make_digitize_schema())

        filename = get_submitted_path() / f"{user}/{data['radar_key']}/digitized-{data['radar_key']}-{data['date_modified'].replace(':', '-').replace('-', '_')}.json"
        filename.parent.mkdir(exist_ok=True, parents=True)
        filename.write_text(json.dumps(data))

        return flask.jsonify({"message": "Data submitted successfully", "data": data}), 200

    except jsonschema.ValidationError as exception:
        return flask.jsonify({"error": f"JSON validation error: {exception.message}"}, 400)

    except Exception as exception:
        print(f"Exception when user submitted json: {str(exception)}")
        return flask.jsonify({"error": "Internal error occurred"}, 500)


@APP.route('/login', methods=["GET", "POST"])
@AUTH.login_required
def force_login():
    user = get_username()
    return flask.jsonify({"message": f"Hello, {user}!"})



def main():
    # Set a maximum upload file size
    APP.config["MAX_CONTENT_LENGTH"] = 50 * 1024 * 1024  # 50 MB

    APP.run(debug=True)
    ...


if __name__ == "__main__":
    main()
