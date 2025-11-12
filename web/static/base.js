async function force_logout() {
  fetch("/logout", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
  })
    .then((response) => {
      if (response.ok) {
        // Reload the page on successful logout
        window.location.reload();
      } else {
        console.error("Logout failed");
      }
    })
    .catch((error) => {
      console.error("Error:", error);
    });
}

async function log_in() {
  await fetch("/login", { method: "POST" });
  location.reload();
}
