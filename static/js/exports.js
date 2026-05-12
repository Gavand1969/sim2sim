/**
 * Sim2Sim — Export buttons + Pro gating.
 *
 * This file is loaded last (after api.js, license.js, app.js).  It:
 *   1. Updates the header tier pill based on license status.
 *   2. Provides window.Sim2SimExports.attach({kind, result, params, container})
 *      which injects "Download Excel" and "Download PDF" buttons into the
 *      given container.  app.js will call this after rendering results.
 *   3. Falls back to a "soft" mode where, if app.js never calls attach(),
 *      we observe DOM mutations and inject a generic export bar after each
 *      panel's results-area finishes rendering.  We hide the bar if no
 *      result is yet computed.
 *   4. Shows an "Upgrade to Pro" modal when a Free user clicks an export.
 */
(function () {
  "use strict";

  // ── Tier pill ─────────────────────────────────────────────────────────────
  async function refreshPill() {
    const pill = document.getElementById("tier-pill");
    if (!pill) return;
    const status = await window.Sim2SimLicense.fetchStatus();
    if (status.valid && status.tier === "team") {
      pill.textContent = "Team";
      pill.className = "tier-pill team";
    } else if (status.valid && status.tier === "pro") {
      pill.textContent = "Pro";
      pill.className = "tier-pill pro";
    } else {
      pill.textContent = "Free";
      pill.className = "tier-pill free";
    }
  }

  // ── Upgrade modal ─────────────────────────────────────────────────────────
  function showUpgradeModal(feature) {
    if (document.getElementById("upgrade-modal-bg")) return;
    const bg = document.createElement("div");
    bg.className = "upgrade-modal-bg";
    bg.id = "upgrade-modal-bg";
    bg.innerHTML = `
      <div class="upgrade-modal" role="dialog" aria-modal="true">
        <h3>Upgrade to Pro</h3>
        <p>${feature} is a Pro feature. Get unlimited exports, AI explanations,
           and every advanced model for a one-time <strong>$49</strong>.</p>
        <div class="modal-actions">
          <button id="modal-close">Maybe later</button>
          <a class="cta-primary" href="/pricing">See pricing →</a>
        </div>
      </div>
    `;
    document.body.appendChild(bg);
    bg.addEventListener("click", (e) => { if (e.target === bg) bg.remove(); });
    document.getElementById("modal-close").addEventListener("click", () => bg.remove());
  }

  // ── Export download ───────────────────────────────────────────────────────
  async function downloadExport(path, body, filename) {
    if (!window.Sim2SimLicense.isPro()) {
      showUpgradeModal("Exporting results");
      return;
    }
    const key = window.Sim2SimLicense.getKey() || "";
    let resp;
    try {
      resp = await fetch(path, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-License-Key": key,
        },
        body: JSON.stringify(body),
      });
    } catch (e) {
      alert("Network error — could not reach the server.");
      return;
    }
    if (resp.status === 403) {
      showUpgradeModal("Exporting results");
      return;
    }
    if (!resp.ok) {
      let detail = `HTTP ${resp.status}`;
      try { detail = (await resp.json()).detail || detail; } catch (_) {}
      alert("Export failed: " + detail);
      return;
    }
    const blob = await resp.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  }

  // ── attach() — called by app.js after each result render ──────────────────
  function attach({ kind, result, params, container, modelKind }) {
    if (!container) return;
    // Remove any prior export bar in this container.
    const prior = container.querySelector(".export-bar");
    if (prior) prior.remove();

    const bar = document.createElement("div");
    bar.className = "export-bar";
    bar.innerHTML = `
      <button class="btn-export" data-fmt="xlsx">⬇ Excel</button>
      <button class="btn-export" data-fmt="pdf">⬇ PDF Report</button>
      <span class="export-hint"></span>
    `;
    const isPro = window.Sim2SimLicense.isPro();
    bar.querySelectorAll(".btn-export").forEach((btn) => {
      btn.classList.toggle("locked", !isPro);
      btn.title = isPro ? "Download" : "Pro feature — click to upgrade";
    });
    bar.querySelector(".export-hint").textContent =
      isPro ? "Pro feature included" : "🔒 Pro — upgrade to download";

    container.appendChild(bar);

    const pathByKind = {
      queuing:   { xlsx: "/api/export/queuing/xlsx",   pdf: "/api/export/queuing/pdf",   file: "sim2sim-queuing" },
      inventory: { xlsx: "/api/export/inventory/xlsx", pdf: "/api/export/inventory/pdf", file: "sim2sim-inventory" },
      lp:        { xlsx: "/api/export/lp/xlsx",        pdf: "/api/export/lp/pdf",        file: "sim2sim-lp" },
    };
    const cfg = pathByKind[kind];
    if (!cfg) return;

    bar.querySelectorAll(".btn-export").forEach((btn) => {
      btn.addEventListener("click", () => {
        const fmt = btn.dataset.fmt;
        const body = kind === "inventory"
          ? { result, params, model_kind: modelKind || "eoq" }
          : { result, params };
        downloadExport(cfg[fmt], body, `${cfg.file}.${fmt}`);
      });
    });
  }

  // ── Light styling for the export bar (kept here to avoid bloating style.css) ──
  const style = document.createElement("style");
  style.textContent = `
    .export-bar {
      display: flex; gap: var(--space-3, .75rem); align-items: center;
      margin-top: var(--space-4, 1rem); padding: var(--space-3, .75rem) var(--space-4, 1rem);
      background: var(--bg-elevated, #1f2937);
      border: 1px solid var(--border, #30363d);
      border-radius: var(--radius-md, 8px);
      flex-wrap: wrap;
    }
    .btn-export {
      background: var(--accent-dark, #1f6feb); color: #fff;
      border: none; padding: 6px 14px;
      border-radius: var(--radius-sm, 4px);
      font-weight: 600; font-size: 0.85rem; cursor: pointer;
      transition: background .15s ease;
    }
    .btn-export:hover { background: var(--accent, #58a6ff); }
    .btn-export.locked {
      background: var(--bg-hover, #2d3748);
      color: var(--text-muted, #6e7681);
      border: 1px dashed var(--border, #30363d);
    }
    .btn-export.locked:hover { color: var(--accent, #58a6ff); border-color: var(--accent, #58a6ff); }
    .export-hint { color: var(--text-muted, #6e7681); font-size: 0.8rem; margin-left: auto; }
  `;
  document.head.appendChild(style);

  // ── Expose ────────────────────────────────────────────────────────────────
  window.Sim2SimExports = { attach, showUpgradeModal, refreshPill };

  // ── Bootstrap ─────────────────────────────────────────────────────────────
  document.addEventListener("DOMContentLoaded", () => {
    refreshPill();
    window.Sim2SimLicense.on("change", refreshPill);
  });
})();
