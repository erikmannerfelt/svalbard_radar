async function setup_map() {


  let logout_button = document.getElementById("logout-button");
  if (logout_button) {
    logout_button.onclick = force_logout;
  }
  // let login_button = document.getElementById("login-button");
  // if (login_button) {
  //   login_button.onclick = log_in;
  // }
}

async function main() {
  await setup_map()
}

document.addEventListener("DOMContentLoaded", main);
