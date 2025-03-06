function get_layer_classes() {
  let props = {
    "bed_cold": {
      "name": "Cold glacier bed",
      "color": "blue",
    },
    "temperate": {
      "name": "Temperate ice",
      "color": "red",
    },
    "bed_unspecified": {
      "name": "Glacier bed",
      "color": "purple",
    },
    "bed_missing": {
      "name": "Glacier bed not visible",
      "color": "green",
    },
  } 

  for (key in props) {
    props[key]["key"] = key;
  };

  return props;
}

async function get_metadata() {
  let radar_key = document.querySelector('meta[name="radarkey"]').content;

	let meta = await fetch(`/radargram_meta/${radar_key}.json`).then(response => response.json());
	meta["radar_key"] = radar_key;

	if (meta["xscale"] == undefined) {
	  meta["xscale"] = 1.;
	};

	return meta;
}

function get_current_class() {
  let form = document.getElementById('interp-class-select');
  let selected_key = form.querySelector('input[name="key"]:checked'); 
  const classes = get_layer_classes();
  return classes[selected_key.value];
};
function get_current_color() {
  return get_current_class().color;

};

function get_draw_control_options() {
  let color = get_current_color();
  return {
    polyline: {
      allowIntersection: false,
      showLength: false,
      shapeOptions: {
        color: color,
      }
    },
    polygon: false,
    rectangle: false,
    circle: false, // Disable circle
    circlemarker: false,
    marker: false,
  }
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
    };
    // item.defaultChecked = true;
    var patch = document.createElement("span");
    patch.classList.add("color-box");
    patch.style.backgroundColor = classes[key]["color"];

    const text = document.createTextNode(classes[key]["name"]);

    label.appendChild(item);
    label.appendChild(patch);
    label.appendChild(text);

    selector.appendChild(label);
  };
};

function setup_draw_features(map) {

  make_color_selector();
  const classes = get_layer_classes();
 
  // Create a layer group to manage drawn features.
  const drawnItems = new L.FeatureGroup();
  map.addLayer(drawnItems);

  // Set initial color and drawing control
  var initialColor = get_current_color();

  // Create draw control
  const drawControl = new L.Control.Draw({
    edit: {
      featureGroup: drawnItems
    },
    draw: get_draw_control_options(),
  });

  map.addControl(drawControl);

  function updateDrawControl(color) {
    drawControl.setDrawingOptions(get_draw_control_options());
  }

  // Add event listener for when new shapes are drawn
  map.on(L.Draw.Event.CREATED, function(event) {
    const layer = event.layer;

    let feature = layer.feature = layer.feature || {};
    feature.type = feature.type || "Feature"; // Intialize feature.type
    let props = feature.properties = feature.properties || {};
    
    let class_props = get_current_class();
    props.color = class_props.color;
    props.kind = class_props.key;

    drawnItems.addLayer(layer);
  });

  document.getElementById('interp-class-select').addEventListener('change', function(_event) {
    updateDrawControl();
  })

  return drawnItems;
};

function make_feature_save_json(drawn_items, meta) {

  let date = new Date().toJSON();

  let drawn_items_geojson = drawn_items.toGeoJSON();

  // Apply xscaling
  if (meta["xscale"] != 1.) {
    drawn_items_geojson.features = drawn_items_geojson.features.map(function (feature) {
      feature.geometry.coordinates = feature.geometry.coordinates.map(function (coords) {
        return [coords[0] / meta["xscale"], coords[1]];
      });
      return feature;
    });
  };

  let output = {
    "date_modified": date,
    "height": meta["height"],
    "width": meta["width"],
    // "user": meta.user || null,
    "difficulty": meta.difficulty,
    "comment": meta.comment || null,
    "radar_key": meta["radar_key"],
    "features": drawn_items_geojson,
  };

  return output;
}

function user_message(message, feedback = null) {

    let response_text = document.getElementById('response-text')

    console.log(message, feedback);
    let color = "#333";
    if (feedback != null) {

      if (feedback == "success") {
        color = "green";
      } else if (feedback == "error") {
        color = "red";
      };
      let response_div = document.getElementById('response-text-div');
      response_div.classList.add(`response-text-${feedback}`);
      setTimeout(function() {
            response_div.classList.remove(`response-text-${feedback}`);
        }, 1000);
    }
    response_text.style.color = color;
    response_text.textContent = message;
}

async function submit_digitized(data) {
  try {
      const response = await fetch("/submit-digitized", {
          method: 'POST',
          headers: {
              'Content-Type': 'application/json'
          },
          body: JSON.stringify(data)
      });

      if (response.status == 401) {
        user_message("Not logged in! Please save the data, log in, and try again.", "error");
        return;
      }

      const result = await response.json();
      console.log('Response:', result);
      user_message(result.message, "success");
  } catch (error) {
      console.error('Error:', error);
      user_message("An erorr occurred submitting!", "error");
  }
}

async function load_digitized_inner(data, meta, drawn_items) {
  const classes = get_layer_classes();
  try {
      for (key of ["radar_key", "width", "height"]) {
        if (data[key] != meta[key]) {
          user_message(`Error loading data: ${key} (${data[key]}) does not align with expected ${key} (${meta[key]})`, "error");
          return;
        };
      };

      meta["comment"] = data["comment"];
      meta["difficulty"] = data["difficulty"];

      if (drawn_items.getLayers().length > 0) {
        drawn_items.clearLayers();
      }

      for (feature_geojson of data["features"]["features"]) {
        let feature;
        if (feature_geojson["geometry"]["type"] == "LineString") {
          let coords = [];

          feature_geojson["geometry"]["coordinates"].forEach(function (pair) {
            coords.push([pair[1], pair[0] * meta["xscale"]]);
          });
          feature = L.polyline(coords, {color: classes[feature_geojson.properties.kind].color});
        } else {
          feature = L.geoJSON(feature_geojson, {style: classes[feature_geojson.properties.kind].color});

          console.log("Fallback load implementation as GeoJSON. Might be wrong!");
          console.log(feature_geojson);
        };

        drawn_items.addLayer(feature);
      };
      user_message(`Loaded ${drawn_items.getLayers().length} line(s)`);

      // Display formatted GeoJSON in the <pre> element
      // geojsonOutput.textContent = JSON.stringify(data, null, 2);
    } catch (error) {
      console.error('Error parsing JSON:', error);
      user_message("Error parsing data. Please check your file", "error");
    };
}

async function load_digitized(event, meta, drawn_items) {

  const file = event.target.files[0];

  if (!file) {
    return;
  };

  const reader = new FileReader();

  reader.onload = function (e) {
      try {
        const data = JSON.parse(e.target.result);
        load_digitized_inner(data, meta, drawn_items);
      } catch (error) {
        user_message("Error parsing loaded JSON. Please check your file", "error");
      }
  };
  reader.onerror = function() {
      console.error('File reading error:', reader.error);
      user_message("Error reading file. Please try again", "error");
  };
  reader.readAsText(file);
}

async function load_latest(meta, drawn_items) {

  try {
    let latest = await fetch(`/radargram_latest_submission/${meta.radar_key}.json`).then(response => response.json())
    // If it's emtpy, then there is no submission yet.
    if (Object.keys(latest).length == 0) {
      return;
    };
    console.log(latest);
    await load_digitized_inner(latest, meta, drawn_items)
    user_message(`Loaded the last submission (${drawn_items.getLayers().length} line(s))`);
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
    };
  };

  return null;
}

function set_user_difficulty(difficulty) {
  let radios = document.getElementsByName("digitize-difficulty-choice");

  for (radio of radios) {
    radio.checked = (radio.value == difficulty);
  };
}

async function setup_map() {

  let data_saved = true;

	const search_string = window.location.search.slice(1);
	const search_params = new URLSearchParams(search_string);

  const meta = await get_metadata();


  var map = L.map('map', {
    crs: L.CRS.Simple,
    maxZoom: 4,
    minZoom: -3
  });
  // let imageUrl = 'static/images/ragna-mariebreen_20230305_lighter.jpg';
  var bounds = [[0, 0], [meta["height"], meta["width"] * meta["xscale"]]]; // Assuming origin (0, 0) at top-left

  let tiles = {};
  for (kind of ["abslog", "classic"]) {

    let new_tiles = [];
    for (tile of meta["tiles"]) {
      new_tiles.push(L.imageOverlay(tile["filepaths"][kind], [[tile["miny"], tile["minx"] * meta["xscale"]],[tile["maxy"], tile["maxx"] * meta["xscale"]]]));

    };
    // let new_tiles = meta["tiles"].forEach(function (tile) {
    //     return ;
    // });
    tiles[kind] = new_tiles;
  };

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
      };
    };
  };
  let track_interval_colors = ["black", "green", "red", "purple", "orange", "blue"];

  if (meta["interval_indicators"] != null) {
    if (meta["interval_indicators"].length > 1) {
      let rect_height = meta["height"] / 5
      meta["interval_indicators"].forEach(function (pair, i) {

        L.rectangle(
          [[meta["height"], pair[0] * meta["xscale"]], [meta["height"] + rect_height, pair[1] * meta["xscale"]]],
          {
            color: track_interval_colors[i % track_interval_colors.length],
            weight: 0,
            interactive: false,
          }
        ).addTo(map);
        let icon = L.divIcon({
            html: `<span>${i}</span>`,
            iconSize: "auto",
        });
        L.marker([meta["height"] + rect_height / 2, (pair[0] * meta["xscale"] + pair[1] * meta["xscale"]) / 2], { icon: icon, interactive: false, }).addTo(map);
      });

      let icon = L.divIcon({
          html: '<b>Intervals:</b>',
          iconSize: "auto",
      });
      L.marker([meta["height"] + rect_height / 2, 0], { icon: icon}).bindPopup(function (layer) {
        return "Intervals are detected events where the radar may have been stopped and resumed at irregular times/places";
        
      }).addTo(map);
    };
  }


  show_tiles("abslog");

  document.getElementById("display-abslog").onclick = function (_event) {show_tiles("abslog")};
  document.getElementById("display-classic").onclick = function (_event) {show_tiles("classic")};

  // console.log(meta["tiles"]);
  // meta["tiles"].forEach(function (tile) {
  //   L.imageOverlay(tile["filepaths"]["abslog"], [[tile["miny"], tile["minx"]],[tile["maxy"], tile["maxx"]]]).addTo(map);
  // });
  // L.imageOverlay(meta["img_path"], bounds).addTo(map);

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

  meta["track"].forEach(function (track_json, i) {
    let lines = L.geoJSON(track_json, {color: track_interval_colors[i % track_interval_colors.length]}).bindPopup(function (layer) {
      let props = layer.feature.properties;
      return `Interval nr ${props.i}<br>Num traces: ${props.n_traces}<br>Length: ${props.length} m`;
      
    }).addTo(overview_map);

    lines.getLayers().forEach(function (line) {
      L.polylineDecorator(line, {
            patterns: [
                {
                    offset: '5%',          
                    repeat: 100,               // No repeat for arrow
                    symbol: L.Symbol.arrowHead({
                        pixelSize: 10,       // Size of the arrow
                        polygon: false,
                        pathOptions: { stroke: true, color: track_interval_colors[i % track_interval_colors.length] } // Arrow style
                    })
                }
            ]
        }).addTo(overview_map);
    });
  });
  
	L.tileLayer("https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}", {
		bounds:[[-90, -180], [90, 180]],
		noWrap: true,
	}).addTo(overview_map);

	let overview_bounds = [[meta["bounds"]["minlat"], meta["bounds"]["minlon"]], [meta["bounds"]["maxlat"], meta["bounds"]["maxlon"]]]
  overview_map.fitBounds(overview_bounds);

  document.getElementById("save-button").onclick = function(event) {
    if (drawn_items.getLayers().length == 0) {
      document.getElementById("response-text").innerText = "Save failed: project is empty";
      return;
    };
    let output = make_feature_save_json(drawn_items, meta);

    var dataStr = "data:text/json;charset=utf-8," + encodeURIComponent(JSON.stringify(output, null, 2));

    let date_str = output.date_modified.replaceAll(":", "-").replaceAll("-", "_");
    let filename = `digitized_${output.radar_key}-${date_str}.json`
    
    var downloadAnchorNode = document.createElement('a');
    downloadAnchorNode.setAttribute("href", dataStr);
    downloadAnchorNode.setAttribute("download", filename);
    document.body.appendChild(downloadAnchorNode); // required for firefox
    downloadAnchorNode.click();
    downloadAnchorNode.remove();

    data_saved = true;
  }

  document.getElementById("load-button").addEventListener("change", async function (event) {
    console.log("Load activated");
    await load_digitized(event, meta, drawn_items);
    data_saved = false;
  });

  /*
  let username_box = document.getElementById("user-name");
  username_box.addEventListener("change", function (event) {
    console.log("Noted change");

    let home_button = document.getElementById("home-button");
    home_button.href = `/?user=${event.target.value}`;

    search_params.set("user", event.target.value);
    meta["user"] = event.target.value;
  });

  if (username_box.nodeValue == null & search_params.has("user")) {
    username_box.value = search_params.get("user");
    meta["user"] = username_box.value;
  }
  */

  let submit_button = document.getElementById("submit-button");
  submit_button.onclick = function (event) {
    if (meta["difficulty"] === null) {
      user_message("Please choose a difficulty before submitting", "error");
      return;
    };

    if (drawn_items.getLayers().length == 0) {
      user_message("Submit failed: project is empty", "error");
      return;
    };

    let confirmed = confirm("Are you sure you want to submit your interpretation?");
    if (!confirmed) {
      event.preventDefault();
      return;
    };


    let output = make_feature_save_json(drawn_items, meta);
    submit_digitized(output);

    data_saved = true;
  }

  document.getElementById("user-comment").addEventListener("change", async function (event) {
    meta["comment"] = event.target.value;
  });

  document.getElementById("digitize-difficulty-form").addEventListener("change", function (_event) {
    meta["difficulty"] = get_user_difficulty();
  });


  window.addEventListener("beforeunload", function (event) {

    console.log("unloading");

    if (!data_saved) {
      event.preventDefault();
      event.returnValue = "";
    };
  });


}

async function main() {
  await setup_map()
}

document.addEventListener("DOMContentLoaded", main);
