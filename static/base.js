async function force_logout() {
    console.log("trying to log out");
  console.log(location);
  var p = window.location.protocol + '//'
  // current location must return 200 OK for this GET
  window.location = window.location.href.replace(p, p + 'logout:password@')
  return;
    fetch("/login", {
        method:"POST",
        headers: {
            'Authorization': 'Basic ' + btoa('invalid:credentials') // Deliberate bad credentials
        }
    })
    .then(() => {
        alert("This doesn't work right now!");
        location.reload();
    })
    .catch(() => {
        alert('An error occurred while logging out.');
    });
}

async function log_in() {
  await fetch("/login", {method: "POST"});
  location.reload();
}

