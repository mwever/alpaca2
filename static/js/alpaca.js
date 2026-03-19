/* ── Alpaca client-side helpers ─────────────────────────────────── */

// Deadlines sidebar toggle — persists preference in localStorage
function alpacaToggleDeadlines() {
  const sidebar = document.getElementById("deadlines-sidebar");
  if (!sidebar) return;
  const collapsed = sidebar.classList.toggle("collapsed");
  localStorage.setItem("alpaca-deadlines-hidden", collapsed ? "1" : "0");
  const btn = document.getElementById("deadlines-toggle");
  if (btn) btn.classList.toggle("active", collapsed);
}

// Auto-dismiss flash messages after 4 s
document.addEventListener("DOMContentLoaded", () => {
  // Restore deadlines sidebar state
  if (localStorage.getItem("alpaca-deadlines-hidden") === "1") {
    const sidebar = document.getElementById("deadlines-sidebar");
    if (sidebar) sidebar.classList.add("collapsed");
    const btn = document.getElementById("deadlines-toggle");
    if (btn) btn.classList.add("active");
  }

  // Handle HX-Trigger flash events coming from HTMX responses
  document.body.addEventListener("showFlash", (evt) => {
    const { level = "info", message = "" } = evt.detail;
    showFlash(level, message);
  });

  // Show a toast for any HTMX request that returns a 4xx/5xx status
  document.body.addEventListener("htmx:responseError", (evt) => {
    const status = evt.detail.xhr.status;
    const messages = {
      400: "Invalid request. Please check your input.",
      403: "You don't have permission to perform this action.",
      404: "The requested resource was not found.",
      422: "The submitted data was invalid.",
      500: "An unexpected error occurred. Please try again.",
    };
    const message = messages[status] || `An error occurred (${status}). Please try again.`;
    showFlash("danger", message);
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
