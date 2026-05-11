/**
 * Sim2Real API client — thin wrapper around fetch().
 *
 * Security notes:
 *  - All requests go to the same origin (/api/*) — no cross-origin calls.
 *  - No user-supplied strings are ever interpolated into URLs.
 *  - fetch() automatically includes the Origin header; the server's CORS
 *    policy is the authoritative gate.
 *  - Errors from the server are surfaced as structured ApiError objects so
 *    the UI can display them cleanly without leaking stack traces.
 */

'use strict';

class ApiError extends Error {
  constructor(status, detail) {
    super(detail);
    this.status = status;
    this.detail = detail;
  }
}

/**
 * Core fetch wrapper.
 * @param {string} path   - e.g. '/api/queuing'
 * @param {object} body   - JSON-serialisable payload
 * @returns {Promise<object>}
 */
async function post(path, body) {
  let response;
  try {
    response = await fetch(path, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      // JSON.stringify is safe: body never contains untrusted HTML
      body: JSON.stringify(body),
    });
  } catch (networkError) {
    throw new ApiError(0, 'Network error — is the server running?');
  }

  let data;
  try {
    data = await response.json();
  } catch {
    throw new ApiError(response.status, 'Server returned an invalid response.');
  }

  if (!response.ok) {
    // FastAPI surfaces validation errors as { detail: [...] } or { detail: "..." }
    const detail = Array.isArray(data.detail)
      ? data.detail.map(e => e.msg).join(' · ')
      : (data.detail ?? `HTTP ${response.status}`);
    throw new ApiError(response.status, detail);
  }

  return data;
}

/** Queuing analytical endpoint */
async function analyseQueue(params) {
  return post('/api/queuing', params);
}

/** EOQ endpoint */
async function analyseEOQ(params) {
  return post('/api/inventory/eoq', params);
}

/** Newsvendor endpoint */
async function analyseNewsvendor(params) {
  return post('/api/inventory/newsvendor', params);
}

/** Monte Carlo simulation endpoint */
async function runSimulation(params) {
  return post('/api/simulation', params);
}

/** AI explanation endpoint */
async function getExplanation(modelType, parameters, results) {
  return post('/api/explain', { model_type: modelType, parameters, results });
}

// Expose to app.js (no module bundler needed on Replit)
window.SimAPI = { analyseQueue, analyseEOQ, analyseNewsvendor, runSimulation, getExplanation, ApiError };
