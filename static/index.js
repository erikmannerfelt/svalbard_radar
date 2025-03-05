async function setup_map() {


  let logout_button = document.getElementById("logout-button");
  if (logout_button) {
    logout_button.onclick = force_logout;
  }

  fetch("/recommended.json").then(response => response.json()).then(function (recommendations) {
    console.log(recommendations);
  })

  fetch("/all_radargrams.json").then(response => response.json()).then(function (all_radargrams) {

    fetch("/user_submissions.json").then(response => response.json()).then(function (submissions) {

      let logged_in = submissions != null;
      console.log("logged_in", logged_in);

      if (logged_in) {
        for (glacier_key in submissions["per_glacier"]) {
          let n_submissions = submissions.per_glacier[glacier_key];


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
            let extra = "Not done by you";
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
