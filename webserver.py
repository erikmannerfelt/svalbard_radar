import flask
import flask_httpauth
import flask_login
import werkzeug.security
import jsonschema
import json
from pathlib import Path

import format_radargrams
import functools

APP = flask.Flask(__name__)
APP.secret_key = "addonekeyhere"
AUTH_OLD = flask_httpauth.HTTPBasicAuth()
LOGIN_MANAGER = flask_login.LoginManager(APP)

USER_DATA_OLD = {
    "admin": "SuperSecretPwd",
    "elias": "alilat",
}

USER_DATA = {k: werkzeug.security.generate_password_hash(v) for k, v in USER_DATA_OLD.items()}

class User(flask_login.UserMixin):
    def __init__(self, username: str):
        self.id = username
        self.username = username

@LOGIN_MANAGER.user_loader
def load_user(username: str):
    if username in USER_DATA:
        return User(username=username)
    return None

@APP.route('/login', methods=['GET', 'POST'])
def login():
    if flask.request.method == 'POST':
        username = flask.request.form['username']
        password = flask.request.form['password']
    
        if username in USER_DATA and werkzeug.security.check_password_hash(USER_DATA[username], password):
            user_obj = User(username=username)
            flask_login.login_user(user_obj)
            return flask.redirect(flask.url_for('index'))
        else:
            flask.flash("Incorrect username or password.", "danger")
    
    return flask.render_template('login.html.jinja2')

@APP.route('/logout', methods=["GET", "POST"])
@flask_login.login_required
def logout():
    flask_login.logout_user()
    flask.flash("Logged out successfully.", "success")
    return flask.redirect(flask.url_for('login'))

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

    

@AUTH_OLD.verify_password
def verify(username: str, password: str) -> bool:
    if not (username and password):
        return False
    return USER_DATA_OLD.get(username) == password

def nice_name(glacier_key: str) -> str:
    if glacier_key == "dronbreen":
        return "Drønbreen"

    return " ".join(map(lambda part: part.capitalize(), glacier_key.replace("_", " ").split(" ")))

def get_all_radargrams():
    radargrams = format_radargrams.parse_all_radargrams(progress=False)
    user = get_username()
    for glacier_key in radargrams:
        for key in radargrams[glacier_key]:
            radargrams[glacier_key][key].update(
                {
                    "n_total_submissions": len(list(get_submitted_path().glob(f"*/{key}"))),
                    "n_submitted_by_user": len(list((get_submitted_path() / f"{user}/{key}").glob("*.json"))) if user is not None else 0,
                }
            )

        radargrams[glacier_key] = {k: v for k, v in sorted(radargrams[glacier_key].items(), key=lambda item: item[1]["n_total_submissions"])}
        radargrams[glacier_key]["_meta"] = {
            "n_total_submissions": sum(r["n_total_submissions"] for r in radargrams[glacier_key].values()),
            "nice_name": nice_name(glacier_key),
        }

    radargrams = {k: v for k, v in sorted(radargrams.items(), key=lambda item: item[1]["_meta"]["n_total_submissions"])}

    return radargrams


@APP.route("/all_radargrams.json")
def all_radargrams():
    radargrams = {}
    for value in get_all_radargrams().values():
        radargrams.update(value)
    return flask.jsonify(radargrams)

def get_username() -> str | None:

    user = flask_login.current_user

    if hasattr(user, "username"):
        return user.username

    return None

@APP.route("/")
def index():
    all_radargrams = get_all_radargrams()

    user = get_username()
    return flask.render_template("index.html.jinja2", all_keys=all_radargrams.keys(), all_radargrams=all_radargrams, user=user)


@APP.route("/digitize/<radar_key>")
def radargram(radar_key: str):
    all_radargrams = get_all_radargrams()
    meta = all_radargrams[radar_key.split("-")[0]][radar_key]
    user = get_username()

    return flask.render_template("digitize.html.jinja2", meta=meta, radar_key=radar_key, user=user)


@APP.route("/submit-digitized", methods=["POST"])
@flask_login.login_required
def submit_digitized():
    req = flask.request

    user = get_username()

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


@APP.route("/howto")
def howto():
    return flask.render_template("howto.html.jinja2")

# @APP.route('/login', methods=["GET", "POST"])
# @AUTH_OLD.login_required
# def force_login():
#     user = get_username()
#     return flask.jsonify({"message": f"Hello, {user}!"})



def main():

    print("Preprocessing...")
    format_radargrams.parse_all_radargrams(progress=True)

    # Set a maximum upload file size
    APP.config["MAX_CONTENT_LENGTH"] = 50 * 1024 * 1024  # 50 MB

    APP.run(host="0.0.0.0", debug=True)
    ...


if __name__ == "__main__":
    main()
