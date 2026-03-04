/* ── Alpaca client-side helpers ─────────────────────────────────── */

// Auto-dismiss flash messages after 4 s
document.addEventListener("DOMContentLoaded", () => {
  // Handle HX-Trigger flash events coming from HTMX responses
  document.body.addEventListener("showFlash", (evt) => {
    const { level = "info", message = "" } = evt.detail;
    showFlash(level, message);
  });
});

function showFlash(level, message) {
  const container = document.getElementById("flash-container");
  if (!container) return;
  const id = "flash-" + Date.now();
  const html = `
    <div id="${id}" class="alert alert-${level} alert-dismissible fade show shadow-sm" role="alert">
      ${message}
      <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
    </div>`;
  container.insertAdjacentHTML("beforeend", html);
  setTimeout(() => {
    const el = document.getElementById(id);
    if (el) el.classList.remove("show");
  }, 4000);
}

// Close modal after a successful HTMX form submission
document.body.addEventListener("closeModal", () => {
  const modal = bootstrap.Modal.getInstance(document.getElementById("alpacaModal"));
  if (modal) modal.hide();
});

// Open the shared modal and load content via HTMX
function openModal(title, url) {
  document.getElementById("alpacaModalLabel").textContent = title;
  htmx.ajax("GET", url, { target: "#alpacaModalBody", swap: "innerHTML" });
  const modal = new bootstrap.Modal(document.getElementById("alpacaModal"));
  modal.show();
}
