"""Convert the legacy (website) interpretation JSONs to ridal's gprinterp format.

Adapted from ridal's `misc/convert_legacy_interpretations.py` (commit 675b011).
The changes compared to that script are:

* The twtt axis is read from each processed radargram instead of being hard-coded for one fixture radargram.
* `ConversionError` is a `ValueError` instead of a `SystemExit`, so it can't silently end an interactive session.
* The per-radargram CLI is replaced by `make_gprinterp_zip()`, which converts every interpreted radargram.
* Single-vertex features (4 in the dataset) are dropped and listed in `meta.dropped_single_vertex_features`.

Out-of-grid vertices are kept (not clipped), because dropping them at the vertex level would change the interpolated lines. They are counted and reported instead.
"""

import json
import zipfile
from pathlib import Path
from typing import Final

import numpy as np
import xarray as xr

from svalbardradar.tools import paths

#: Bumped when the emitted document shape changes, so a file says which converter made it.
CONVERTER_VERSION: Final[str] = "1"

#: Legacy `kind` -> `(new layer id, display name)`. `temperate_ice` (from the name fallback) is normalised as well.
KIND_TO_LAYER: Final[dict[str, tuple[str, str]]] = {
    "bed_unspecified": ("bed", "Glacier bed"),
    "bed_cold": ("bed_no_temperate", "Glacier bed (no temperate ice above)"),
    "temperate": ("temperate_ice", "Temperate ice (CTS)"),
    "temperate_ice": ("temperate_ice", "Temperate ice (CTS)"),
    "bed_missing": ("bed_not_visible", "Glacier bed not visible"),
}

#: Legacy `name` -> the same pairs, for early submissions where `kind` is absent.
NAME_TO_LAYER: Final[dict[str, tuple[str, str]]] = {
    "Glacier bed": ("bed", "Glacier bed"),
    "Cold glacier bed": ("bed_no_temperate", "Glacier bed (no temperate ice above)"),
    "Temperate ice": ("temperate_ice", "Temperate ice (CTS)"),
    "Glacier bed missing": ("bed_not_visible", "Glacier bed not visible"),
}


class ConversionError(ValueError):
    """Raised for anything that must fail the conversion loudly."""


def map_layer(properties: dict, path: Path, feature_index: int) -> tuple[str, str, bool]:
    """Resolve a feature's layer to `(id, display_name, used_name_fallback)`."""
    kind = properties.get("kind")
    if kind in KIND_TO_LAYER:
        layer_id, name = KIND_TO_LAYER[kind]
        return layer_id, name, False
    name = properties.get("name")
    if name in NAME_TO_LAYER:
        layer_id, display = NAME_TO_LAYER[name]
        return layer_id, display, True
    raise ConversionError(
        f"{path}: feature {feature_index} has unknown kind {kind!r} and name {name!r}; refusing to guess a layer"
    )


def convert_feature(
    feature: dict,
    path: Path,
    feature_index: int,
    user: str,
    n_samples: int,
    n_traces: int,
    out_of_grid: dict[tuple[str, str], int],
) -> tuple[dict, bool]:
    """Convert one legacy feature. Returns `(feature, used_fallback)`."""
    geometry = feature.get("geometry") or {}
    if geometry.get("type") != "LineString":
        raise ConversionError(
            f"{path}: feature {feature_index} is a {geometry.get('type')!r}, not a LineString; refusing to drop it silently"
        )
    coordinates = geometry.get("coordinates") or []
    if len(coordinates) < 2:
        raise ConversionError(
            f"{path}: feature {feature_index} has {len(coordinates)} vertices; a LineString needs at least 2"
        )

    properties = dict(feature.get("properties") or {})
    layer_id, display_name, used_fallback = map_layer(properties, path, feature_index)

    flipped = []
    for x, y in coordinates:
        sample = n_samples - 1 - y
        if not (0.0 <= x < n_traces) or not (0.0 <= sample < n_samples):
            out_of_grid[(user, layer_id)] = out_of_grid.get((user, layer_id), 0) + 1
        flipped.append([x, sample])

    converted = {
        "type": "Feature",
        "geometry": {"type": "LineString", "coordinates": flipped},
        "properties": {
            **properties,
            "id": f"{user.lower()}-{feature_index}",
            "label": layer_id,
            "name": display_name,
        },
    }
    return converted, used_fallback


def user_id(contributor: str) -> str:
    """
    Return ridal's user id for a legacy contributor nickname.

    Ridal's user ids only accept lowercase ASCII letters, digits, `-` and `_`. The nickname is kept in `meta.contributor`.

    Examples
    --------
    >>> user_id("AvalancheAmigo")
    'avalancheamigo'
    >>> user_id("Radar Force 2")
    'radar_force_2'
    """
    out = []
    for character in contributor.lower():
        if character.isascii() and (character.isalnum() or character in "-_"):
            out.append(character)
        else:
            out.append("_")
    cleaned = "".join(out).strip("_")
    if not cleaned:
        raise ValueError(f"no usable user id in contributor name {contributor!r}")
    return cleaned


def convert_submission(
    path: Path,
    radar_key: str,
    n_samples: int,
    n_traces: int,
    twtt_t0_ns: float,
    twtt_dt_ns: float,
    out_of_grid: dict[tuple[str, str], int],
    source_label: str | None = None,
) -> tuple[dict, int, int]:
    """Convert one submission. Returns `(document, n_features, n_fallbacks)`."""
    document = json.loads(path.read_text())
    if document.get("height") != n_samples:
        raise ConversionError(f"{path}: declares height {document.get('height')}, expected {n_samples}")
    if document.get("width") != n_traces:
        raise ConversionError(f"{path}: declares width {document.get('width')}, expected {n_traces}")
    if not isinstance(document.get("features"), dict):
        raise ConversionError(f"{path}: 'features' is not a FeatureCollection")

    user = path.parts[-3]
    converted_features = []
    dropped_single_vertex = []
    fallbacks = 0
    for index, feature in enumerate(document["features"]["features"]):
        # A few legacy features are single (probably accidental) clicks. They can't be represented as a LineString,
        # so they are dropped and listed in the metadata. Feature ids keep their original index.
        if len((feature.get("geometry") or {}).get("coordinates") or []) == 1:
            dropped_single_vertex.append(index)
            continue
        converted, used_fallback = convert_feature(feature, path, index, user, n_samples, n_traces, out_of_grid)
        converted_features.append(converted)
        fallbacks += int(used_fallback)

    out = {
        "key": radar_key.lower(),
        "schema": "gprinterp",
        "schema_version": "0.3",
        "date_modified": document.get("date_modified"),
        "source": {
            "id": radar_key.lower(),
            "n_traces": n_traces,
            "n_samples": n_samples,
        },
        "coordinates": {
            "space": "index2d",
            "convention": {
                "origin": "upper-left",
                "indexing": "zero-based",
                "pixel_reference": "center",
                "axis_directions": {"x": "right", "y": "down"},
            },
            "axes": {
                "x": {"primary": {"name": "trace", "unit": "index"}},
                "y": {
                    "primary": {"name": "sample", "unit": "index"},
                    "anchor": [
                        {
                            "name": "twtt",
                            "unit": "ns",
                            "type": "regular",
                            "t0": twtt_t0_ns,
                            "dt": twtt_dt_ns,
                        }
                    ],
                },
            },
        },
        "features": converted_features,
        "meta": {
            "legacy_source": source_label or str(path),
            "legacy_date_modified": document.get("date_modified"),
            "contributor": user,
            "difficulty": document.get("difficulty"),
            "comment": document.get("comment"),
            "converter_version": CONVERTER_VERSION,
        },
    }
    if dropped_single_vertex:
        out["meta"]["dropped_single_vertex_features"] = dropped_single_vertex
    return out, len(converted_features), fallbacks


def radargram_axes(radar_key: str) -> tuple[int, int, float, float]:
    """Return `(n_samples, n_traces, twtt_t0_ns, twtt_dt_ns)` of a processed radargram."""
    with xr.open_dataset(paths.processed_radar_path(radar_key)) as dataset:
        n_samples, n_traces = dataset["data"].shape
        twtt = dataset["twtt"].values.astype(float)
        twtt_unit = dataset["twtt"].attrs.get("units")

    if twtt_unit != "ns":
        raise ConversionError(f"{radar_key}: expected twtt in ns, got {twtt_unit!r}")

    t0 = float(twtt[0])
    dt = float(twtt[-1] - twtt[0]) / (twtt.size - 1)
    # The axis is regular to float32 precision
    if not np.allclose(np.diff(twtt), dt, rtol=1e-3):
        raise ConversionError(f"{radar_key}: the twtt axis is not regular")

    return n_samples, n_traces, t0, dt


def make_gprinterp_zip(out_path: Path, radar_keys: list[str] | None = None, verbose: bool = True) -> Path:
    """
    Convert the latest submission of each user and radargram into a zip of gprinterp JSONs.

    The zip is structured as `<radar_key>/<user_id>.gprinterp.json`.
    The latest submissions are the same as those used in the consensus (`paths.get_latest_submissions()`).
    """
    if radar_keys is None:
        radar_keys = sorted(paths.get_all_interpreted_radargrams())

    submissions_dir = paths._submissions_dir_path()
    totals = {"radargrams": 0, "submissions": 0, "features": 0, "fallbacks": 0, "out_of_grid": 0}

    with zipfile.ZipFile(out_path, mode="w", compression=zipfile.ZIP_DEFLATED) as zip_file:
        for radar_key in radar_keys:
            n_samples, n_traces, t0, dt = radargram_axes(radar_key)
            out_of_grid: dict[tuple[str, str], int] = {}
            written_ids: set[str] = set()

            for path in paths.get_latest_submissions(radar_key):
                document, n_features, fallbacks = convert_submission(
                    path,
                    radar_key,
                    n_samples,
                    n_traces,
                    t0,
                    dt,
                    out_of_grid,
                    source_label=str(path.relative_to(submissions_dir)),
                )
                contributor_id = user_id(path.parts[-3])
                if contributor_id in written_ids:
                    raise ConversionError(f"{radar_key}: two contributors map to the user id {contributor_id!r}")
                written_ids.add(contributor_id)

                zip_file.writestr(
                    f"{radar_key}/{contributor_id}.gprinterp.json", json.dumps(document, indent=2) + "\n"
                )
                totals["submissions"] += 1
                totals["features"] += n_features
                totals["fallbacks"] += fallbacks

            totals["radargrams"] += 1
            totals["out_of_grid"] += sum(out_of_grid.values())

    if verbose:
        print(
            f"Wrote {out_path}: {totals['radargrams']} radargrams, {totals['submissions']} submissions, "
            f"{totals['features']} features ({totals['fallbacks']} via the legacy name fallback), "
            f"{totals['out_of_grid']} out-of-grid vertices kept"
        )

    return out_path
