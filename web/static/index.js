async function set_progress(progress) {

  let progressElement = document.getElementById('progress-bar');
  let percentageElement = document.getElementById('progress-percentage');
  let progressRankElement = document.getElementById("progress-rank");
  let progressPercentage = (progress * 100).toFixed(0);
    
  progressElement.style.width = progressPercentage + '%';
  percentageElement.innerText = progressPercentage + '%';
  
  // Change color at specific intervals
  if (progressPercentage >= 80) {
      progressElement.classList.add("index-card-finished");
      // progressElement.style.backgroundColor = 'green';
  } else if (progressPercentage >= 20) {
      progressElement.classList.add("index-card-unfinished");
  } else {
      progressElement.classList.add("progress-bar-low");
  }

  let ranks = [
    [100, "Perfectionist radar god"],
    [98, "Radar god"],
    [90, "Senior radioglaciologist"],
    [75, "Professional radioglaciologist"],
    [50, "Halfway to perfection"],
    [30, "Radar connoisseur"],
    [15, "Very useful contributor!"],
    [7, "Useful contributor"],
    [1, "Great start!"],
    [0, ""],

  ];

  for (let rank of ranks) {
    if (progressPercentage >= rank[0]) {
      progressRankElement.innerText = `${rank[1]} (>${rank[0]}%)`;
      break;
    }

  };


};

async function setup_map() {


  let logout_button = document.getElementById("logout-button");
  if (logout_button) {
    logout_button.onclick = force_logout;
  }

  fetch("/recommended.json").then(response => response.json()).then(function (recommendations) {
    console.log(recommendations);
  })

  fetch("/all_radargrams.json").then(response => response.json()).then(function (all_radargrams) {
    let n_total_radargrams = Math.max(Object.keys(all_radargrams).length - 1, 1);

    fetch("/user_submissions.json").then(response => response.json()).then(function (submissions) {

      let logged_in = submissions != null;
      if (logged_in) {

        let n_total_submissions = 0;
        for (glacier_key in submissions["per_glacier"]) {
          let n_submissions = submissions.per_glacier[glacier_key];
          n_total_submissions = n_total_submissions + n_submissions;

          let item = document.getElementById(`li-${glacier_key}`);

          let parts = item.innerText.split("=")
          let n_total = parts[parts.length - 1];

          if (n_submissions < n_total) {
            item.className = "index-card-unfinished";
            item.innerText = item.innerText + `. Done ${n_submissions}.`;
          } else {
            item.className = "index-card-finished";
            item.innerText = item.innerText + `. Done all.`;
          }
        };

        set_progress(n_total_submissions / n_total_radargrams);
       
      };
      for (let card of document.getElementsByClassName("index-card")) {
        let radar_key = card.id.replace("card-", ""); 

        let meta = all_radargrams[radar_key];

        if ((meta == undefined) | (meta == null)) {
          continue;
        };

          let done_by_text = card.querySelector("#done-by");
          let n_submitted_by_user = 0;
          if (logged_in) {
            if (submissions["per_radar_key"][radar_key] != null) {
              n_submitted_by_user = submissions["per_radar_key"][radar_key];
            }
          }
          if (logged_in) {
            if (n_submitted_by_user > 0) {
              card.classList.add("index-card-finished");
            } else if (n_submitted_by_user == 0) {
              card.classList.add("index-card-unfinished");
            };
          } else {
              card.classList.add("index-card-anonymous");
          };
          if (meta["n_total_submissions"] > 1) {
            done_by_text.innerText = `Done by ${meta.n_total_submissions} people.`;
          } else if (meta["n_total_submissions"] == 1) {
            done_by_text.innerText = "Done by 1 person.";
          } else {
            done_by_text.innerText = "Not done by anyone.";
          };

          if (meta["n_total_submissions"] > 0) {
            let extra = logged_in ? "Not done by you" : "";
            if (n_submitted_by_user > 1) {
              extra = `Done by you (${n_submitted_by_user}x!)`;
            } else if (n_submitted_by_user == 1) {
              extra = "Done by you!";
            };
            done_by_text.innerText += " " + extra;
          }
      }});
  });


  // let login_button = document.getElementById("login-button");
  // if (login_button) {
  //   login_button.onclick = log_in;
  // }
}

async function main() {
  await setup_map()
}

document.addEventListener("DOMContentLoaded", main);
