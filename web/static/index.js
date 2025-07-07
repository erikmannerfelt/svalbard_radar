async function set_progress(n_radargrams_done, n_total_radargrams) {

  let progress = n_radargrams_done / n_total_radargrams;

  n_radargrams_done = Math.round(progress * n_total_radargrams);

  let progressElement = document.getElementById('progress-bar');
  let percentageElement = document.getElementById('progress-percentage');
  let progressRankElement = document.getElementById("progress-rank");
  let current_rank_element = document.getElementById("progress-status");
  let progressPercentage = (progress * 100).toFixed(0);

  let missions = [
    [8, "Contributor"],
    [10, "Enthusiast"],
    [10, "Wave"],
    [10, "Apprentice"],
    [10, "Investigator"],
    [10, "Professional"],
    [10, "Technician"],
    [10, "Specialist"],
    [10, "Elite"],
    [10, "Expert"],
    [10, "Guru"],
    [10, "Whisperer"],
    [200, "God"],
  ];

  let rank_name = "Beginner";
  let mission_i = 0;
  let mission_name;
  let mission_points;
  let current_zero = 0;
  let current_goal = 0;
  for ([mission_points, mission_name] of missions) {
    mission_i += 1;

    current_zero = current_goal;
    // current_goal = Math.min(current_zero + mission_points, n_total_radargrams);
    mission_points = Math.min(current_zero + mission_points, n_total_radargrams) - current_zero; 
    current_goal = current_zero + mission_points;

    if (current_goal > n_radargrams_done) {
      break;
    };
    rank_name = mission_name;
  };

  let mission_score = n_radargrams_done - current_zero;

  let mission_percentage = 100 * mission_score / mission_points;

  progressElement.style.width = mission_percentage + '%';

  let text = "";
  if (mission_score < mission_points) {
    text += `Mission ${mission_i}: become a Radar ${mission_name}`;
  } else {
    text += `You are a Radar ${mission_name}`;
  };

  text += ` (${mission_score} / ${mission_points})\n\nIn total: ${n_radargrams_done}/${n_total_radargrams} (${progressPercentage}%)`

  current_rank_element.innerText = `Status: Radar ${rank_name}`;
  progressRankElement.innerText = text;

  percentageElement.innerText = `(${mission_score} / ${mission_points})`;

  // Change color at specific intervals
  if (mission_percentage >= 70) {
      progressElement.classList.add("index-card-finished");
      console.log(progressElement);
      // progressElement.style.backgroundColor = 'green';
  } else if (mission_percentage >= 20) {
      progressElement.classList.add("index-card-unfinished");
  } else {
      progressElement.classList.add("progress-bar-low");
  }
  // for (let rank of ranks) {
  //   if (progressPercentage >= rank[0]) {
  //     progressRankElement.innerText = `${rank[1]} (>${rank[0]}%)`;
  //     break;
  //   }

  // };


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

        set_progress(n_total_submissions, n_total_radargrams);
       
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
