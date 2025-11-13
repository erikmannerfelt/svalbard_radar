function get_layer_classes() {
  let props = {
    bed_cold: {
      name: "Glacier bed (no temperate ice)",
      color: "#002EBD", // Blue
    },
    temperate: {
      name: "Temperate ice",
      color: "red",
    },
    bed_unspecified: {
      name: "Glacier bed",
      color: "#CE00FF", // Purple/pink
    },
    bed_missing: {
      name: "Glacier bed not visible",
      color: "#62F700", // Neon green
    },
  };

  for (key in props) {
    props[key]["key"] = key;
  }

  return props;
}

async function get_metadata() {
  let radar_key = document.querySelector('meta[name="radarkey"]').content;

  let meta = await fetch(`/radargram_meta/${radar_key}.json`).then((response) =>
    response.json()
  );
  meta["radar_key"] = radar_key;

  if (meta["xscale"] == undefined) {
    meta["xscale"] = 1;
  }

  return meta;
}

function get_current_kind() {
  let form = document.getElementById("interp-class-select");
  let selected_key = form.querySelector('input[name="key"]:checked');

  return selected_key.value;
}

function get_current_class() {
  const classes = get_layer_classes();
  return classes[get_current_kind()];
}
function get_current_color() {
  return get_current_class().color;
}

function get_draw_control_options() {
  let color = get_current_color();
  return {
    polyline: {
      allowIntersection: false,
      showLength: false,
      shapeOptions: {
        color: color,
      },
    },
    polygon: false,
    rectangle: false,
    circle: false, // Disable circle
    circlemarker: false,
    marker: false,
  };
}

function make_color_selector() {
  const selector = document.getElementById("interp-class-select");

  const classes = get_layer_classes();

  let initial = true;
  for (key in classes) {
    let item = document.createElement("input");

    var label = document.createElement("label");
    label.classList.add("color-option");

    selector.appendChild(item);
    item.type = "radio";
    item.name = "key";
    item.value = key;

    if (key == "bed_unspecified") {
      item.checked = true;
    }
    var patch = document.createElement("span");
    patch.classList.add("color-box");
    patch.style.backgroundColor = classes[key]["color"];

    const text = document.createTextNode(classes[key]["name"]);

    label.appendChild(item);
    label.appendChild(patch);
    label.appendChild(text);

    selector.appendChild(label);
  }
}

function validate_polyline(map, polyline, skip_alert = false) {
  // Reset all issue markers (if any). All need to be recreated.
  let issue_markers = (polyline.issue_markers = polyline.issue_markers || []);
  issue_markers.forEach(function (marker) {
    map.removeLayer(marker);
    marker.remove();
  });
  issue_markers.splice(0, issue_markers.length);

  let issues = [];

  var latlngs = polyline.getLatLngs();
  if (latlngs.length < 2) return issues; // Single point or empty polyline is valid
  // Check if the line is drawn left-right or right-left
  var increasing = latlngs[0].lng < latlngs[latlngs.length - 1].lng;
  // Loop through all vertices and see if the one before leads to an overhang
  for (var i = 1; i < latlngs.length; i++) {
    if (
      (increasing && latlngs[i].lng <= latlngs[i - 1].lng) ||
      (!increasing && latlngs[i].lng >= latlngs[i - 1].lng)
    ) {
      issues.push(`Line contains an overhang (vertex ${i})`);

      let marker = L.circleMarker([latlngs[i - 1].lat, latlngs[i - 1].lng], {
        color: "red",
      })
        .addTo(map)
        .bindPopup(function (_) {
          return "Invalid overhang.";
        });
      issue_markers.push(marker);
    }
  }
  if ((issues.length > 0) & !skip_alert) {
    alert(
      `${issues.length} issue(s) found. Please fix them!\n` + issues.join("\n")
    );
  }
  let dasharray = "none";
  if (issues.length > 0) {
    dasharray = "3 6";
  }

  // The timeout is a silly solution to a problem: Leaflet.Draw sets the dasharray when exiting an editing session
  // I haven't found out a way to override that, so instead I add a timeout that triggers after Leaflet.Draw finishes.
  setTimeout(function () {
    polyline.setStyle({ dashArray: dasharray });
  }, 100);

  return issues;
}

function change_layer_kind(layer, new_kind) {
  const classes = get_layer_classes();

  let class_props = classes[new_kind];

  layer.properties = layer.properties || {};
  layer.properties.kind = new_kind;
  layer.properties.color = class_props.color;
  layer.properties.name = class_props.name;

  layer.setStyle({ color: class_props.color });
}

function add_polyline_metadata(layer, kind, drawn_items) {
  change_layer_kind(layer, kind);

  let map = drawn_items._map;
  layer.properties.issues = validate_polyline(map, layer);

  layer.bindPopup(function (new_layer) {
    return polyline_popup(new_layer, drawn_items);
  });
}

function create_polyline(coords, drawn_items, kind) {
  console.log(kind);
  let class_props = get_layer_classes()[kind];
  let map = drawn_items._map;

  let new_layer = L.polyline(coords, { color: class_props.color });

  add_polyline_metadata(new_layer, kind, drawn_items);

  map.addLayer(new_layer);
  drawn_items.addLayer(new_layer);

  return new_layer;
}

function split_polyline(layer, x_coord, y_coord, drawn_items) {
  for (i in [0, 1]) {
    let coords = [];

    let done = false;
    layer["_latlngs"].forEach(function (pair) {
      if (
        ((i == 0) & (pair["lng"] > x_coord)) |
        ((i == 1) & (pair["lng"] < x_coord))
      ) {
        if (!done) {
          coords.push([y_coord, x_coord]);
        }
        done = true;
        return;
      }
      coords.push([pair["lat"], pair["lng"]]);
    });

    create_polyline(coords, drawn_items, layer.properties.kind);
  }

  layer._map.removeLayer(layer);
  layer.remove();
}

function polyline_popup(layer, drawn_items) {
  let popup_location = layer._popup._latlng;
  let popup_div = document.createElement("div");

  let class_name = document.createElement("p");
  class_name.innerHTML = `<b>Class: </b>${layer.properties.name}`;
  popup_div.appendChild(class_name);

  if (layer.properties.issues.length > 0) {
    let issues_text = document.createElement("p");
    issues_text.innerHTML =
      `<br><b>Issues</b><br>` + layer.properties.issues.join("<br>");
    popup_div.appendChild(issues_text);
  }

  let button_div = document.createElement("div");
  button_div.style.display = "flex";
  button_div.style.justifyContent = "space-between";
  popup_div.appendChild(button_div);
  let classes = get_layer_classes();

  let class_change_div = document.createElement("div");
  let dropdown = document.createElement("button");
  dropdown.innerText = "Change class";
  class_change_div.appendChild(dropdown);
  dropdown.classList.add("button", "change-class-dropdown-button");

  let dropdown_content = document.createElement("div");
  dropdown_content.className = "change-class-dropdown-content";
  class_change_div.appendChild(dropdown_content);

  dropdown.onclick = function () {
    dropdown_content.classList.toggle("show");
  };

  for (key in classes) {
    let item = document.createElement("button");

    item.key = key;
    item.classList.add("color-option");

    var patch = document.createElement("span");
    patch.classList.add("color-box");
    patch.style.backgroundColor = classes[key]["color"];

    const text = document.createTextNode(classes[key]["name"]);

    item.appendChild(patch);
    item.appendChild(text);

    item.onclick = function (event) {
      change_layer_kind(layer, event.target.key);
      class_name.innerHTML = `<b>Class: </b>${layer.properties.name}`;
    };

    dropdown_content.appendChild(item);
  }

  button_div.appendChild(class_change_div);

  let split_line_button = document.createElement("button");
  button_div.appendChild(split_line_button);
  split_line_button.innerText = "Split line here";
  split_line_button.classList.add("button");
  split_line_button.onclick = function () {
    if (!confirm("Split line?")) {
      return;
    }
    split_polyline(layer, popup_location.lng, popup_location.lat, drawn_items);
    dropdown_content.classList.remove("show");
  };

  // Close the dropdown if the user clicks outside of it
  window.onclick = function (e) {
    if (!e.target.matches(".change-class-dropdown-button")) {
      if (dropdown_content.classList.contains("show")) {
        dropdown_content.classList.remove("show");
      }
    }
  };

  return popup_div;
}

function setup_draw_features(map) {
  make_color_selector();

  // Create a layer group to manage drawn features.
  const drawnItems = new L.FeatureGroup();
  map.addLayer(drawnItems);

  // Create draw control
  const drawControl = new L.Control.Draw({
    edit: {
      featureGroup: drawnItems,
    },
    draw: get_draw_control_options(),
  });

  map.addControl(drawControl);

  function updateDrawControl() {
    drawControl.setDrawingOptions(get_draw_control_options());
  }

  // Add event listener for when new shapes are drawn
  map.on(L.Draw.Event.CREATED, function (event) {
    const layer = event.layer;

    let kind = get_current_kind();
    add_polyline_metadata(layer, kind, drawnItems);

    drawnItems.addLayer(layer);
  });

  map.on(L.Draw.Event.EDITED, function (event) {
    const layers = event.layers;

    layers.eachLayer(function (layer) {
      let props = layer.properties;

      props.issues = validate_polyline(map, layer);
    });
  });

  map.on(L.Draw.Event.DELETED, function (event) {
    const layers = event.layers;
    layers.eachLayer(function (layer) {
      // Remove all issue markers (if any)
      let issue_markers = layer.issue_markers || [];
      if (!issue_markers) {
        return;
      }
      issue_markers.forEach(function (marker) {
        map.removeLayer(marker);
        marker.remove();
      });
      issue_markers.splice(0, issue_markers.length);
    });
  });

  document
    .getElementById("interp-class-select")
    .addEventListener("change", function (_event) {
      updateDrawControl();
    });

  return drawnItems;
}

function make_feature_save_json(drawn_items, meta) {
  let date = new Date().toJSON();

  let drawn_items_geojson = { type: "FeatureCollection", features: [] };

  drawn_items.eachLayer(function (layer) {
    let geojson = layer.toGeoJSON();
    geojson.properties = layer.properties;
    drawn_items_geojson.features.push(geojson);
  });

  // Apply xscaling
  if (meta["xscale"] != 1) {
    drawn_items_geojson.features = drawn_items_geojson.features.map(function (
      feature
    ) {
      feature.geometry.coordinates = feature.geometry.coordinates.map(function (
        coords
      ) {
        return [coords[0] / meta["xscale"], coords[1]];
      });
      return feature;
    });
  }

  let output = {
    date_modified: date,
    height: meta["height"],
    width: meta["width"],
    // "user": meta.user || null,
    difficulty: meta.difficulty,
    comment: meta.comment || null,
    radar_key: meta["radar_key"],
    features: drawn_items_geojson,
  };

  return output;
}

function user_message(message, feedback = null) {
  let response_text = document.getElementById("response-text");

  console.log(message, feedback);
  let color = "#333";
  if (feedback != null) {
    if (feedback == "success") {
      color = "green";
    } else if (feedback == "error") {
      color = "red";
    }
    let response_div = document.getElementById("response-text-div");
    response_div.classList.add(`response-text-${feedback}`);
    setTimeout(function () {
      response_div.classList.remove(`response-text-${feedback}`);
    }, 1000);
  }
  response_text.style.color = color;
  response_text.textContent = message;
}

async function submit_digitized(data) {
  try {
    const response = await fetch("/submit-digitized", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(data),
    });

    if (response.status == 401) {
      user_message(
        "Not logged in! Please save the data, log in, and try again.",
        "error"
      );
      return;
    }

    const result = await response.json();
    console.log("Response:", result);
    user_message(result.message, "success");
  } catch (error) {
    console.error("Error:", error);
    user_message("An erorr occurred submitting!", "error");
  }
}

async function load_digitized_inner(data, meta, drawn_items) {
  const classes = get_layer_classes();
  try {
    for (key of ["radar_key", "width", "height"]) {
      if (data[key] != meta[key]) {
        user_message(
          `Error loading data: ${key} (${data[key]}) does not align with expected ${key} (${meta[key]})`,
          "error"
        );
        return;
      }
    }

    meta["comment"] = data["comment"];
    meta["difficulty"] = data["difficulty"];

    if (drawn_items.getLayers().length > 0) {
      drawn_items.clearLayers();
    }

    for (feature_geojson of data["features"]["features"]) {
      let layer;
      let kind = feature_geojson.properties.kind;

      // Added 2025-04-05. There was a bug where a loaded line didn't get the "kind" property, so if saved again, the kind property was lost.
      // If that's the case, the lookup below is by name instead of kind.
      if (kind == undefined) {
        for (kind_class in classes) {
          if (classes[kind_class].name == feature_geojson.properties.name) {
            kind = kind_class;
            break;
          }
        }
      }
      // let class_props = classes[kind];
      if (feature_geojson["geometry"]["type"] == "LineString") {
        let coords = [];

        feature_geojson["geometry"]["coordinates"].forEach(function (pair) {
          coords.push([pair[1], pair[0] * meta["xscale"]]);
        });

        layer = create_polyline(coords, drawn_items, kind);
        // layer = L.polyline(coords, {color: class_props.color});
        console.log(layer);
      } else {
        // alert("Loaded
        user_message(
          "Skipped loading of one feature as it was the wrong type",
          "error"
        );
        return;
        layer = L.geoJSON(feature_geojson, { style: class_props.color });

        console.log("Fallback load implementation as GeoJSON. Might be wrong!");
        console.log(feature_geojson);
      }

      drawn_items.addLayer(layer);
    }
    user_message(`Loaded ${drawn_items.getLayers().length} line(s)`);

    // Display formatted GeoJSON in the <pre> element
    // geojsonOutput.textContent = JSON.stringify(data, null, 2);
  } catch (error) {
    console.error("Error parsing JSON:", error);
    user_message("Error parsing data. Please check your file", "error");
  }
}

async function load_digitized(event, meta, drawn_items) {
  const file = event.target.files[0];

  if (!file) {
    return;
  }

  const reader = new FileReader();

  reader.onload = function (e) {
    try {
      const data = JSON.parse(e.target.result);
      load_digitized_inner(data, meta, drawn_items);
    } catch (error) {
      user_message(
        "Error parsing loaded JSON. Please check your file",
        "error"
      );
    }
  };
  reader.onerror = function () {
    console.error("File reading error:", reader.error);
    user_message("Error reading file. Please try again", "error");
  };
  reader.readAsText(file);
}

async function load_latest(meta, drawn_items) {
  try {
    let latest = await fetch(
      `/radargram_latest_submission/${meta.radar_key}.json`
    ).then((response) => response.json());
    // If it's emtpy, then there is no submission yet.
    if (Object.keys(latest).length == 0) {
      return;
    }
    console.log(latest);
    await load_digitized_inner(latest, meta, drawn_items);
    user_message(
      `Loaded the last submission (${drawn_items.getLayers().length} line(s))`
    );
  } catch (error) {
    console.log(error);
    return;
  }
}

function get_user_difficulty() {
  let radios = document.getElementsByName("digitize-difficulty-choice");

  for (radio of radios) {
    if (radio.checked) {
      return radio.value;
    }
  }

  return null;
}

function set_user_difficulty(difficulty) {
  let radios = document.getElementsByName("digitize-difficulty-choice");

  for (radio of radios) {
    radio.checked = radio.value == difficulty;
  }
}

async function setup_map() {
  let data_saved = true;

  const search_string = window.location.search.slice(1);
  const search_params = new URLSearchParams(search_string);

  const meta = await get_metadata();

  var map = L.map("map", {
    crs: L.CRS.Simple,
    maxZoom: 4,
    minZoom: -3,
  });
  // let imageUrl = 'static/images/ragna-mariebreen_20230305_lighter.jpg';
  var bounds = [
    [0, 0],
    [meta["height"], meta["width"] * meta["xscale"]],
  ]; // Assuming origin (0, 0) at top-left

  let tiles = {};
  for (kind of ["abslog", "classic"]) {
    let new_tiles = [];
    for (tile of meta["tiles"]) {
      new_tiles.push(
        L.imageOverlay(tile["filepaths"][kind], [
          [tile["miny"], tile["minx"] * meta["xscale"]],
          [tile["maxy"], tile["maxx"] * meta["xscale"]],
        ])
      );
    }
    // let new_tiles = meta["tiles"].forEach(function (tile) {
    //     return ;
    // });
    tiles[kind] = new_tiles;
  }

  function show_tiles(new_kind) {
    for (kind in tiles) {
      if (kind != new_kind) {
        tiles[kind].forEach(function (tile) {
          map.removeLayer(tile);
        });
      } else {
        tiles[kind].forEach(function (tile) {
          tile.addTo(map);
        });
      }
    }
  }
  let track_interval_colors = [
    "black",
    "green",
    "red",
    "purple",
    "orange",
    "blue",
  ];

  // Add interval indicators to the digitization window
  if (meta["interval_indicators"] != null) {
    if (meta["interval_indicators"].length > 1) {
      let rect_height = meta["height"] / 5;
      meta["interval_indicators"].forEach(function (pair, i) {
        L.rectangle(
          [
            [meta["height"], pair[0] * meta["xscale"]],
            [meta["height"] + rect_height, pair[1] * meta["xscale"]],
          ],
          {
            color: track_interval_colors[i % track_interval_colors.length],
            weight: 0,
            interactive: false,
          }
        ).addTo(map);
        let icon = L.divIcon({
          html: `<span class="interval-indicator">${i}</span>`,
          iconSize: "auto",
        });
        L.marker(
          [
            meta["height"] + rect_height / 2,
            (pair[0] * meta["xscale"] + pair[1] * meta["xscale"]) / 2,
          ],
          { icon: icon, interactive: false }
        ).addTo(map);
      });

      let icon = L.divIcon({
        html: "<b>Intervals:</b>",
        iconSize: "auto",
      });
      L.marker([meta["height"] + rect_height / 2, 0], { icon: icon })
        .bindPopup(function (layer) {
          return "Intervals are detected events where the radar may have been stopped and resumed at irregular times/places";
        })
        .addTo(map);
    }

    // Add x labels
    let time_interval = meta["max_time"] / meta["width"];
    meta["interval_indicators"].forEach(function (pair, i) {
      for (
        let time = 0;
        time <= time_interval * (pair[1] - pair[0]);
        time += 250
      ) {
        let icon = L.divIcon({
          html: `<span class="xlabel">${time}s</span>`,
          iconSize: "auto",
        });
        let marker = L.marker(
          [0, meta["xscale"] * (pair[0] + time / time_interval)],
          { icon: icon, interactive: false }
        ).addTo(map);
      }
    });
  }

  // Add a horizontal line below the radargram
  L.polyline(
    [
      [0, 0],
      [0, meta["width"] * meta["xscale"]],
    ],
    { color: "black", interactive: false }
  ).addTo(map);

  // Add y (depth) labels and decoration
  for (vals of [
    ["left", 0],
    ["right", meta["width"] * meta["xscale"]],
  ]) {
    let side = vals[0];
    let x = vals[1];

    // Add a vertical line along the radargram side.
    L.polyline(
      [
        [0, x],
        [meta["height"], x],
      ],
      { color: "black", interactive: false }
    ).addTo(map);

    // Add labels
    for (let depth = 0; depth <= meta["max_depth"]; depth += 50) {
      let y_px = depth * (meta["height"] / meta["max_depth"]);

      let icon = L.divIcon({
        html: `<span class="ylabel-${side}">${depth}m</span>`,
        iconSize: "auto",
      });
      L.marker([meta["height"] - y_px, x], {
        icon: icon,
        interactive: false,
      }).addTo(map);
    }
  }

  show_tiles("abslog");

  document.getElementById("display-abslog").onclick = function (_event) {
    show_tiles("abslog");
  };
  document.getElementById("display-classic").onclick = function (_event) {
    show_tiles("classic");
  };

  map.fitBounds(bounds);

  let drawn_items = setup_draw_features(map);

  await load_latest(meta, drawn_items);

  if (meta["difficulty"] == undefined) {
    meta["difficulty"] = get_user_difficulty();
  }

  if (meta["difficulty"] != null) {
    set_user_difficulty(meta["difficulty"]);
  }

  map.on(L.Draw.Event.CREATED, function (event) {
    data_saved = false;
  });
  map.on(L.Draw.Event.EDITED, function (event) {
    data_saved = false;
  });
  map.on(L.Draw.Event.DELETED, function (event) {
    data_saved = false;
  });

  let overview_map = L.map("overview-map", {
    maxZoom: 15,
    minZoom: 3,
  });

  meta["track"].forEach(function (track_json, _) {
    let i = track_json.properties.i;
    let lines = L.geoJSON(track_json, {
      color: track_interval_colors[i % track_interval_colors.length],
      opacity: 0.5,
    })
      .bindPopup(function (layer) {
        let props = layer.feature.properties;
        return `Interval nr ${props.i}<br>Num traces: ${props.n_traces}<br>Length: ${props.length} m`;
      })
      .addTo(overview_map);

    lines.getLayers().forEach(function (line) {
      L.polylineDecorator(line, {
        patterns: [
          {
            offset: "5%",
            repeat: 100, // No repeat for arrow
            opacity: 0.5,
            symbol: L.Symbol.arrowHead({
              pixelSize: 10, // Size of the arrow
              polygon: false,
              pathOptions: {
                stroke: true,
                color: track_interval_colors[i % track_interval_colors.length],
              }, // Arrow style
            }),
          },
        ],
      }).addTo(overview_map);
    });
  });

  L.tileLayer(
    "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
    {
      bounds: [
        [-90, -180],
        [90, 180],
      ],
      noWrap: true,
    }
  ).addTo(overview_map);

  let overview_bounds = [
    [meta["bounds"]["minlat"], meta["bounds"]["minlon"]],
    [meta["bounds"]["maxlat"], meta["bounds"]["maxlon"]],
  ];
  overview_map.fitBounds(overview_bounds);

  document.getElementById("save-button").onclick = function (event) {
    if (drawn_items.getLayers().length == 0) {
      document.getElementById("response-text").innerText =
        "Save failed: project is empty";
      return;
    }
    let output = make_feature_save_json(drawn_items, meta);

    var dataStr =
      "data:text/json;charset=utf-8," +
      encodeURIComponent(JSON.stringify(output, null, 2));

    let date_str = output.date_modified
      .replaceAll(":", "-")
      .replaceAll("-", "_");
    let filename = `digitized_${output.radar_key}-${date_str}.json`;

    var downloadAnchorNode = document.createElement("a");
    downloadAnchorNode.setAttribute("href", dataStr);
    downloadAnchorNode.setAttribute("download", filename);
    document.body.appendChild(downloadAnchorNode); // required for firefox
    downloadAnchorNode.click();
    downloadAnchorNode.remove();

    data_saved = true;
  };

  document
    .getElementById("load-button")
    .addEventListener("change", async function (event) {
      console.log("Load activated");
      await load_digitized(event, meta, drawn_items);
      data_saved = false;
    });

  let submit_button = document.getElementById("submit-button");
  submit_button.onclick = function (event) {
    if (meta["difficulty"] === null) {
      user_message("Please choose a difficulty before submitting", "error");
      return;
    }

    if (drawn_items.getLayers().length == 0) {
      user_message("Submit failed: project is empty", "error");
      return;
    }

    let n_lines_with_issues = 0;
    drawn_items.eachLayer(function (layer) {
      if (validate_polyline(map, layer, true).length > 0) {
        n_lines_with_issues += 1;
      }
    });

    if (n_lines_with_issues > 0) {
      user_message(
        `Submit failed: ${n_lines_with_issues} line(s) have unfixed issues. Please look for the red circles.`,
        "error"
      );
      return;
    }

    let confirmed = confirm(
      "Are you sure you want to submit your interpretation?"
    );
    if (!confirmed) {
      event.preventDefault();
      return;
    }

    let output = make_feature_save_json(drawn_items, meta);
    submit_digitized(output);

    data_saved = true;
  };

  document
    .getElementById("user-comment")
    .addEventListener("change", async function (event) {
      meta["comment"] = event.target.value;
    });

  document
    .getElementById("digitize-difficulty-form")
    .addEventListener("change", function (_event) {
      meta["difficulty"] = get_user_difficulty();
    });

  window.addEventListener("beforeunload", function (event) {
    console.log("unloading");

    if (!data_saved) {
      event.preventDefault();
      event.returnValue = "";
    }
  });
}

async function main() {
  await setup_map();
}

document.addEventListener("DOMContentLoaded", main);
