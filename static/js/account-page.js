// Account page activation flow. Moved out of inline <script> to comply with
// CSP script-src 'self'.
document.addEventListener("DOMContentLoaded", async () => {
  const tierEl  = document.getElementById("status-tier");
  const emailEl = document.getElementById("status-email");
  const countEl = document.getElementById("status-count");
  const block   = document.getElementById("status-block");
  const form    = document.getElementById("activate-form");
  const input   = document.getElementById("key-input");
  const msgEl   = document.getElementById("activate-msg");
  const clearBtn = document.getElementById("clear-license");

  async function refresh() {
    const status = await window.Sim2SimLicense.fetchStatus();
    if (status.valid) {
      tierEl.textContent = status.tier.toUpperCase();
      emailEl.textContent = status.email || "—";
      countEl.textContent = status.activation_count ?? "—";
      block.className = "status-block status-active";
    } else {
      tierEl.textContent = "Free (no license)";
      emailEl.textContent = "—";
      countEl.textContent = "—";
      block.className = "status-block status-empty";
    }
  }

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const key = input.value.trim();
    if (!key) return;
    msgEl.textContent = "Activating…";
    msgEl.className = "activate-msg";
    const result = await window.Sim2SimLicense.activate(key);
    if (result.valid) {
      msgEl.textContent = `Activated. Welcome to ${result.tier.toUpperCase()}.`;
      msgEl.className = "activate-msg success";
      input.value = "";
      await refresh();
    } else {
      msgEl.textContent = result.message || "Invalid license key.";
      msgEl.className = "activate-msg error";
    }
  });

  clearBtn.addEventListener("click", async () => {
    window.Sim2SimLicense.clear();
    await refresh();
    msgEl.textContent = "License removed from this browser.";
    msgEl.className = "activate-msg";
  });

  await refresh();
});
