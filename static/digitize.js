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

	const all_meta = await fetch("/all_radargrams.json").then(response => response.json());

	let meta = all_meta[radar_key];
	meta["radar_key"] = radar_key;

	return meta;
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

    if (initial) {
      item.checked = true;
      initial = false;
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


  function get_current_class() {
    let form = document.getElementById('interp-class-select');
    let selected_key = form.querySelector('input[name="key"]:checked'); 
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
        shapeOptions: {
          color: color
        }
      },
      polygon: false,
      rectangle: false,
      circle: false, // Disable circle
      circlemarker: false,
      marker: false,
    }
  }
  // Set initial color and drawing control
  var initialColor = get_current_color();

  // Create draw control
  const drawControl = new L.Control.Draw({
    edit: {
      featureGroup: drawnItems
    },
    draw: get_draw_control_options(initialColor),
  });

  map.addControl(drawControl);

  function updateDrawControl(color) {
    drawControl.setDrawingOptions(get_draw_control_options(color));
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

  document.getElementById('interp-class-select').addEventListener('change', function(event) {
    updateDrawControl();
  })

  return drawnItems;
};

function make_feature_save_json(drawn_items, meta) {

  let date = new Date().toJSON();

  let output = {
    "date_modified": date,
    "height": meta["height"],
    "width": meta["width"],
    // "user": meta.user || null,
    "comment": meta.comment || null,
    "radar_key": meta["radar_key"],
    "features": drawn_items.toGeoJSON(),
  };

  return output;
}

function user_message(message) {
    document.getElementById('response-text').textContent = message;
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

      const result = await response.json();
      console.log('Response:', result);
      user_message(result.message);
  } catch (error) {
      console.error('Error:', error);
      user_message("An erorr occurred submitting!");
  }
}

async function load_digitized(event, meta, drawn_items) {

  const file = event.target.files[0];
  const classes = get_layer_classes();

  if (!file) {
    return;
  };

  const reader = new FileReader();

  reader.onload = function (e) {
    try {
      const data = JSON.parse(e.target.result);
      // Store the GeoJSON data in a JavaScript variable
      console.log('Parsed JSON:', data);

      for (key in ["key", "width", "height"]) {
        if (data[key] != meta[key]) {
          user_message(`Error loading data: data ${key} (${data[key]}) does not align with data ${key} (${meta[key]})`);
          return;
        };
      };

      meta["comment"] = data["comment"];

      if (drawn_items.getLayers().length > 0) {
        drawn_items.clearLayers();
      }

      L.geoJSON(data["features"], {
        style: function (feature) {return {color: classes[feature.properties.kind].color};},
        onEachFeature: function (feature, layer) {
            drawn_items.addLayer(layer);
        }
      });

      user_message(`Loaded ${drawn_items.getLayers().length} line(s)`);

      // Display formatted GeoJSON in the <pre> element
      // geojsonOutput.textContent = JSON.stringify(data, null, 2);
    } catch (error) {
      console.error('Error parsing JSON:', error);
      document.getElementById('response-text').textContent = 'Error parsing data. Please check your file.';
    };
  };
  reader.onerror = function() {
      console.error('File reading error:', reader.error);
      document.getElementById('response-text').textContent = 'Error reading file. Please try again.';
  };

  reader.readAsText(file);
  


}

async function setup_map() {
	const search_string = window.location.search.slice(1);
	const search_params = new URLSearchParams(search_string);

  const meta = await get_metadata();

  console.log(meta);
  var map = L.map('map', {
    crs: L.CRS.Simple,
    maxZoom: 4,
    minZoom: -3
  });
  // let imageUrl = 'static/images/ragna-mariebreen_20230305_lighter.jpg';
  var bounds = [[0, 0], [meta["height"], meta["width"]]]; // Assuming origin (0, 0) at top-left

  meta["tiles"].forEach(function (tile) {
    L.imageOverlay(tile["filepath"], [[tile["miny"], tile["minx"]],[tile["maxy"], tile["maxx"]]]).addTo(map);
  });
  // L.imageOverlay(meta["img_path"], bounds).addTo(map);

  map.fitBounds(bounds);

  let drawn_items = setup_draw_features(map);

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
  }

  document.getElementById("load-button").addEventListener("change", async function (event) {
    console.log("Load activated");
    await load_digitized(event, meta, drawn_items);
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

    if (drawn_items.getLayers().length == 0) {
      document.getElementById("response-text").innerText = "Submit failed: project is empty";
      return;
    };

    let output = make_feature_save_json(drawn_items, meta);
    submit_digitized(output);
  }

  document.getElementById("user-comment").addEventListener("change", async function (event) {
    meta["comment"] = event.target.value;
  });

}

async function main() {
  await setup_map()
}

document.addEventListener("DOMContentLoaded", main);
