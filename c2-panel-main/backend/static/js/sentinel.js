// Sentinel Admin — small client helpers.

// 1) Convert UTC timestamps with class .local-time to viewer's local time.
document.addEventListener("DOMContentLoaded", () => {
  document.querySelectorAll(".local-time").forEach((el) => {
    const utc = el.dataset.utc;
    if (!utc) return;
    try {
      const d = new Date(utc);
      el.textContent = d.toLocaleString();
    } catch (e) { /* keep server text */ }
  });
});

// 2) Ban an IP via /admin/ban-ip (used by Login History page).
window.banIP = function (ip) {
  const reason = window.prompt(`Ban IP ${ip} — reason?`, "Suspicious activity");
  if (!reason) return;
  const fd = new FormData();
  fd.append("ip_address", ip);
  fd.append("reason", reason);
  fetch("/admin/ban-ip", { method: "POST", body: fd })
    .then((r) => r.json())
    .then((d) => {
      if (d.success) location.reload();
      else alert(d.error || "Failed to ban IP");
    })
    .catch(() => alert("Network error"));
};
