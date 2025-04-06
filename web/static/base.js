async function force_logout() {

    fetch('/logout', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        }
    })
    .then(response => {
        if (response.ok) {
            // Reload the page on successful logout
            window.location.reload();
        } else {
            console.error('Logout failed');
        }
    })
    .catch(error => {
        console.error('Error:', error);
    });

    // await fetch("/logout", {method: "POST"});
    // location.reload();

    /*
      return;
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
    */
}

async function log_in() {
  await fetch("/login", {method: "POST"});
  location.reload();
}

