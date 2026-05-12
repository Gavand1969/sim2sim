/**
 * Sim2Sim license client.
 *
 * Stores the license key in localStorage under `sim2sim_license_key`.
 * Exposes window.Sim2SimLicense with:
 *   - getKey()           → string|null
 *   - setKey(key)        → void
 *   - clear()            → void
 *   - fetchStatus()      → Promise<{valid, tier, email, activation_count}>
 *   - activate(key)      → Promise<{valid, tier, email, message?}>
 *   - isPro()            → boolean (sync, last-known)
 *   - isTeam()           → boolean (sync, last-known)
 *   - on(event, cb)      → subscribe to "change" events
 *
 * Also exposes window.STRIPE_PRO_URL / STRIPE_TEAM_URL when set via
 * window.SIM2SIM_CONFIG (set in HTML before this script loads), so the
 * pricing CTAs can be configured by the user without touching this file.
 */
(function () {
  const STORAGE_KEY = "sim2sim_license_key";
  const STATUS_CACHE_KEY = "sim2sim_license_status";

  // Allow the host page (or a future config script) to inject Stripe URLs.
  // SIM2SIM_CONFIG can also be populated by Replit env vars via the index
  // template, but for now we read from localStorage as a dev convenience.
  if (window.SIM2SIM_CONFIG) {
    if (window.SIM2SIM_CONFIG.stripeProUrl)  window.STRIPE_PRO_URL  = window.SIM2SIM_CONFIG.stripeProUrl;
    if (window.SIM2SIM_CONFIG.stripeTeamUrl) window.STRIPE_TEAM_URL = window.SIM2SIM_CONFIG.stripeTeamUrl;
  }

  const listeners = [];
  function emit() {
    listeners.forEach((cb) => {
      try { cb(getCachedStatus()); } catch (_) {}
    });
  }

  function getKey() {
    try { return localStorage.getItem(STORAGE_KEY); } catch (_) { return null; }
  }
  function setKey(key) {
    try { localStorage.setItem(STORAGE_KEY, key); } catch (_) {}
  }
  function clear() {
    try {
      localStorage.removeItem(STORAGE_KEY);
      localStorage.removeItem(STATUS_CACHE_KEY);
    } catch (_) {}
    emit();
  }

  function getCachedStatus() {
    try {
      const raw = localStorage.getItem(STATUS_CACHE_KEY);
      return raw ? JSON.parse(raw) : { valid: false };
    } catch (_) { return { valid: false }; }
  }
  function setCachedStatus(s) {
    try { localStorage.setItem(STATUS_CACHE_KEY, JSON.stringify(s)); } catch (_) {}
    emit();
  }

  async function fetchStatus() {
    const key = getKey();
    if (!key) {
      const s = { valid: false };
      setCachedStatus(s);
      return s;
    }
    try {
      const resp = await fetch("/api/billing/status", {
        headers: { "X-License-Key": key },
      });
      const data = await resp.json();
      setCachedStatus(data);
      return data;
    } catch (e) {
      console.warn("license status fetch failed", e);
      return getCachedStatus();
    }
  }

  async function activate(key) {
    try {
      const resp = await fetch("/api/billing/activate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ key }),
      });
      const data = await resp.json();
      if (data.valid) {
        setKey(key);
        setCachedStatus(data);
      }
      return data;
    } catch (e) {
      return { valid: false, message: "Network error — try again." };
    }
  }

  function isPro()  { const s = getCachedStatus(); return !!(s.valid && (s.tier === "pro" || s.tier === "team")); }
  function isTeam() { const s = getCachedStatus(); return !!(s.valid && s.tier === "team"); }

  function on(_evt, cb) { listeners.push(cb); }

  window.Sim2SimLicense = {
    getKey, setKey, clear,
    fetchStatus, activate,
    isPro, isTeam,
    on,
    getCachedStatus,
  };

  // Refresh status on load so every page sees fresh state.
  fetchStatus().catch(() => {});
})();
