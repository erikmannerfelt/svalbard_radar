import flask

app = flask.Flask(__name__)


def get_all_radargrams():
    return {
        "test": {
            "width": 8400,
            "height": 4200,
            "img_path": "/static/images/ragna-mariebreen_20230305_lighter.jpg",
        },
    }

@app.route("/all_radargrams.json")
def all_radargrams():
    return flask.jsonify(get_all_radargrams())

@app.route("/")
def index():
    all_radargrams = get_all_radargrams()
    return flask.render_template("index.html.jinja2", all_keys=all_radargrams.keys(), all_radargrams=all_radargrams)


@app.route("/digitize/<radar_key>")
def radargram(radar_key: str):

    all_radargrams = get_all_radargrams()
    meta = all_radargrams[radar_key]

    return flask.render_template("digitize.html.jinja2", meta=meta, radar_key=radar_key)


def main():

    app.run(debug=True)
    ...


if __name__ == "__main__":
    main()
