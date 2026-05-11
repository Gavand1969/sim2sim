/**
 * Sim2Real — Main application controller.
 *
 * Responsibilities:
 *  - Tab switching
 *  - Live utilisation preview
 *  - Form read → API call → render results
 *  - AI explanation trigger
 *  - Toast notifications
 *
 * No frameworks, no build step — runs directly in the browser.
 */

'use strict';

/* ── Initialise after all deferred scripts have loaded ────────────────────── */
document.addEventListener('DOMContentLoaded', () => {
  SimCharts.initChartDefaults();
  initTabs();
  initQueuingModelToggle();
  initUtilPreview();
  initButtons();
});

/* ══════════════════════════════════════════════════════════════════════════════
   TABS
══════════════════════════════════════════════════════════════════════════════ */

function initTabs() {
  const tabs   = document.querySelectorAll('.tab');
  const panels = document.querySelectorAll('.panel');

  tabs.forEach(tab => {
    tab.addEventListener('click', () => {
      const target = tab.dataset.tab;

      tabs.forEach(t => { t.classList.remove('active'); t.setAttribute('aria-selected', 'false'); });
      tab.classList.add('active');
      tab.setAttribute('aria-selected', 'true');

      panels.forEach(p => {
        if (p.id === `panel-${target}`) {
          p.classList.add('active');
          p.hidden = false;
        } else {
          p.classList.remove('active');
          p.hidden = true;
        }
      });
    });
  });
}

/* ══════════════════════════════════════════════════════════════════════════════
   QUEUING MODEL TOGGLE (show/hide server count & Cs² fields)
══════════════════════════════════════════════════════════════════════════════ */

function initQueuingModelToggle() {
  const sel     = document.getElementById('q-model');
  const cGroup  = document.getElementById('q-c-group');
  const csvGroup= document.getElementById('q-csv-group');

  function update() {
    const v = sel.value;
    cGroup.style.display   = (v === 'MMC') ? 'flex' : 'none';
    csvGroup.style.display = (v === 'MG1') ? 'flex' : 'none';
    cGroup.style.flexDirection  = 'column';
    csvGroup.style.flexDirection = 'column';
  }
  sel.addEventListener('change', update);
  update();
}

/* ══════════════════════════════════════════════════════════════════════════════
   LIVE UTILISATION PREVIEW
══════════════════════════════════════════════════════════════════════════════ */

function initUtilPreview() {
  ['q-lambda', 'q-mu', 'q-c', 'q-model'].forEach(id => {
    document.getElementById(id)?.addEventListener('input', updateUtilPreview);
  });
  updateUtilPreview();
}

function updateUtilPreview() {
  const lam = parseFloat(document.getElementById('q-lambda').value) || 0;
  const mu  = parseFloat(document.getElementById('q-mu').value)     || 1;
  const c   = parseInt(document.getElementById('q-c').value)        || 1;
  const el  = document.getElementById('q-util-preview');
  const val = document.getElementById('q-util-val');

  if (!lam || !mu) { val.textContent = '—'; return; }

  const rho = lam / (c * mu);
  val.textContent = rho.toFixed(4);

  el.classList.remove('warning', 'danger');
  if (rho >= 1.0)       el.classList.add('danger');
  else if (rho >= 0.85) el.classList.add('warning');
}

/* ══════════════════════════════════════════════════════════════════════════════
   BUTTON WIRING
══════════════════════════════════════════════════════════════════════════════ */

function initButtons() {
  document.getElementById('btn-queuing')?.addEventListener('click',    handleQueuing);
  document.getElementById('btn-eoq')?.addEventListener('click',        handleEOQ);
  document.getElementById('btn-newsvendor')?.addEventListener('click', handleNewsvendor);
  document.getElementById('btn-simulation')?.addEventListener('click', handleSimulation);
}

/* ══════════════════════════════════════════════════════════════════════════════
   QUEUING HANDLER
══════════════════════════════════════════════════════════════════════════════ */

async function handleQueuing() {
  const btn = document.getElementById('btn-queuing');
  const params = {
    model:          document.getElementById('q-model').value,
    arrival_rate:   parseFloat(document.getElementById('q-lambda').value),
    service_rate:   parseFloat(document.getElementById('q-mu').value),
    num_servers:    parseInt(document.getElementById('q-c').value)    || 1,
    service_cv_sq:  parseFloat(document.getElementById('q-csv').value) || 1,
  };

  setLoading(btn, true);
  try {
    const data = await SimAPI.analyseQueue(params);
    renderQueuingResults(data, params);
    triggerExplanation('Queuing (' + data.model + ')', params, summariseQueuing(data));
  } catch (e) {
    showToast(e.detail ?? e.message, 'error');
  } finally {
    setLoading(btn, false);
  }
}

function summariseQueuing(d) {
  return {
    model: d.model,
    utilization: d.utilization,
    avg_customers_in_system: d.L,
    avg_customers_in_queue: d.Lq,
    avg_time_in_system: d.W,
    avg_wait_time_in_queue: d.Wq,
    probability_server_idle: d.P0,
    probability_customer_waits: d.P_wait,
    little_law_error: d.little_law_check,
  };
}

function renderQueuingResults(d, params) {
  const container = document.getElementById('results-queuing');

  const rhoClass = d.utilization >= 0.9 ? 'danger' : d.utilization >= 0.75 ? 'warning' : 'good';

  container.innerHTML = `
    <div class="metric-grid">
      ${metric('ρ — Utilization',    d.utilization.toFixed(4), rhoClass,   'Server busy fraction')}
      ${metric('L — Avg in System',  d.L.toFixed(4),           '',         'Little\'s Law: L = λW')}
      ${metric('Lq — Avg in Queue',  d.Lq.toFixed(4),          '',         'Customers waiting')}
      ${metric('W — Avg Sojourn',    d.W.toFixed(4),           '',         'Time units in system')}
      ${metric('Wq — Avg Wait',      d.Wq.toFixed(4),          '',         'Time units in queue')}
      ${metric('P₀ — Server Idle',   d.P0.toFixed(4),          '',         'Fraction of time empty')}
      ${d.P_wait != null ? metric('P(wait) — Erlang C', d.P_wait.toFixed(4), '', 'Prob. a customer must wait') : ''}
    </div>

    <div style="display:flex; gap:8px; align-items:center; flex-wrap:wrap;">
      <span class="sanity-badge">✓ Little's Law error: ${d.little_law_check.toExponential(2)}</span>
      ${d.P_wait != null ? `<span class="ci-badge">Erlang-C verified</span>` : ''}
    </div>

    <div class="chart-card">
      <div class="chart-card-title">Queue-Length Distribution P(N=n)</div>
      <div class="chart-wrapper">
        <canvas id="chart-q-dist"></canvas>
      </div>
    </div>
  `;

  // Render chart after DOM is updated
  requestAnimationFrame(() => {
    SimCharts.renderProbDist(document.getElementById('chart-q-dist'), d.prob_dist);
  });
}

/* ══════════════════════════════════════════════════════════════════════════════
   EOQ HANDLER
══════════════════════════════════════════════════════════════════════════════ */

async function handleEOQ() {
  const btn = document.getElementById('btn-eoq');
  const params = {
    annual_demand: parseFloat(document.getElementById('eoq-demand').value),
    ordering_cost: parseFloat(document.getElementById('eoq-k').value),
    unit_cost:     parseFloat(document.getElementById('eoq-c').value),
    holding_rate:  parseFloat(document.getElementById('eoq-i').value),
  };

  setLoading(btn, true);
  try {
    const data = await SimAPI.analyseEOQ(params);
    renderEOQResults(data, params);
    triggerExplanation('EOQ (Economic Order Quantity)', params, {
      eoq: data.eoq,
      orders_per_year: data.orders_per_year,
      cycle_time_days: data.cycle_time_days,
      total_annual_cost: data.total_annual_cost,
    });
  } catch (e) {
    showToast(e.detail ?? e.message, 'error');
  } finally {
    setLoading(btn, false);
  }
}

function renderEOQResults(d, params) {
  const container = document.getElementById('results-eoq');
  container.innerHTML = `
    <div class="metric-grid">
      ${metric('EOQ — Optimal Q',      d.eoq.toFixed(2),              'good', 'Units per order')}
      ${metric('Orders / Year',        d.orders_per_year.toFixed(2),  '',     'Number of replenishments')}
      ${metric('Cycle Time',           d.cycle_time_days.toFixed(1),  '',     'Days between orders')}
      ${metric('Min Annual Cost',      '$' + d.total_annual_cost.toFixed(2), 'good', 'Holding + Ordering')}
    </div>

    <div class="chart-card">
      <div class="chart-card-title">Total Cost vs. Order Quantity</div>
      <div class="chart-wrapper">
        <canvas id="chart-eoq-cost"></canvas>
      </div>
    </div>
  `;

  requestAnimationFrame(() => {
    SimCharts.renderCostCurve(
      document.getElementById('chart-eoq-cost'),
      d.cost_curve_q, d.cost_curve_tc,
      d.cost_curve_holding, d.cost_curve_ordering,
      d.eoq
    );
  });
}

/* ══════════════════════════════════════════════════════════════════════════════
   NEWSVENDOR HANDLER
══════════════════════════════════════════════════════════════════════════════ */

async function handleNewsvendor() {
  const btn = document.getElementById('btn-newsvendor');
  const params = {
    selling_price: parseFloat(document.getElementById('nv-price').value),
    unit_cost:     parseFloat(document.getElementById('nv-cost').value),
    salvage_value: parseFloat(document.getElementById('nv-salvage').value),
    demand_mean:   parseFloat(document.getElementById('nv-mean').value),
    demand_std:    parseFloat(document.getElementById('nv-std').value),
    demand_dist:   document.getElementById('nv-dist').value,
  };

  setLoading(btn, true);
  try {
    const data = await SimAPI.analyseNewsvendor(params);
    renderNewsvendorResults(data, params);
    triggerExplanation('Newsvendor', params, {
      critical_ratio: data.critical_ratio,
      optimal_quantity: data.optimal_quantity,
      expected_profit: data.expected_profit,
      fill_rate: data.fill_rate,
      expected_stockout: data.expected_stockout,
      expected_leftover: data.expected_leftover,
    });
  } catch (e) {
    showToast(e.detail ?? e.message, 'error');
  } finally {
    setLoading(btn, false);
  }
}

function renderNewsvendorResults(d, params) {
  const container = document.getElementById('results-newsvendor');
  const crPct = (d.critical_ratio * 100).toFixed(1);
  const fillPct = (d.fill_rate * 100).toFixed(1);

  container.innerHTML = `
    <div class="metric-grid">
      ${metric('Critical Ratio',     crPct + '%',                        'good', 'Optimal service level')}
      ${metric('Optimal Q*',         d.optimal_quantity.toFixed(1),       'good', 'Units to order')}
      ${metric('Expected Profit',    '$' + d.expected_profit.toFixed(2),  'd.expected_profit > 0 ? "good" : "danger"', '')}
      ${metric('Fill Rate',          fillPct + '%',                        fillPct >= 90 ? 'good' : 'warning', 'Demand met from stock')}
      ${metric('Exp. Leftover',      d.expected_leftover.toFixed(1),      '',     'Units salvaged')}
      ${metric('Exp. Stockout',      d.expected_stockout.toFixed(1),      'warning', 'Unmet demand')}
    </div>

    <div class="chart-card">
      <div class="chart-card-title">Expected Profit vs. Order Quantity</div>
      <div class="chart-wrapper">
        <canvas id="chart-nv-profit"></canvas>
      </div>
    </div>
  `;

  requestAnimationFrame(() => {
    SimCharts.renderProfitCurve(
      document.getElementById('chart-nv-profit'),
      d.profit_curve_q, d.profit_curve_ep,
      d.optimal_quantity
    );
  });
}

/* ══════════════════════════════════════════════════════════════════════════════
   SIMULATION HANDLER
══════════════════════════════════════════════════════════════════════════════ */

async function handleSimulation() {
  const btn = document.getElementById('btn-simulation');
  const seedRaw = document.getElementById('sim-seed').value.trim();
  const params = {
    model:            document.getElementById('sim-model').value,
    arrival_rate:     parseFloat(document.getElementById('sim-lambda').value),
    service_rate:     parseFloat(document.getElementById('sim-mu').value),
    num_servers:      parseInt(document.getElementById('sim-c').value)    || 1,
    num_customers:    parseInt(document.getElementById('sim-n').value)    || 5000,
    num_replications: parseInt(document.getElementById('sim-reps').value) || 10,
    seed:             seedRaw !== '' ? parseInt(seedRaw) : null,
  };

  setLoading(btn, true);
  try {
    const data = await SimAPI.runSimulation(params);
    renderSimulationResults(data, params);
    triggerExplanation('Monte Carlo Simulation', params, {
      utilization: data.utilization_mean,
      avg_sojourn_time: data.W_mean,
      avg_wait_in_queue: data.Wq_mean,
      CI_95_W: `±${data.W_ci_hw.toFixed(4)}`,
      CI_95_Wq: `±${data.Wq_ci_hw.toFixed(4)}`,
      analytical_W: data.analytical_W,
      analytical_Wq: data.analytical_Wq,
    });
  } catch (e) {
    showToast(e.detail ?? e.message, 'error');
  } finally {
    setLoading(btn, false);
  }
}

function renderSimulationResults(d, params) {
  const container = document.getElementById('results-simulation');
  const rhoClass = d.utilization_mean >= 0.9 ? 'danger' : d.utilization_mean >= 0.75 ? 'warning' : 'good';

  const analyticalRow = (d.analytical_W != null) ? `
    <div style="display:flex; gap:8px; flex-wrap:wrap; align-items:center;">
      <span class="ci-badge">Analytical W = ${d.analytical_W.toFixed(4)}</span>
      <span class="ci-badge">Analytical Wq = ${d.analytical_Wq.toFixed(4)}</span>
    </div>
  ` : '';

  container.innerHTML = `
    <div class="metric-grid">
      ${metric('ρ — Utilization',    d.utilization_mean.toFixed(4),  rhoClass, 'Simulated server busy fraction')}
      ${metric('W — Avg Sojourn',    d.W_mean.toFixed(4),            '',       `95% CI ±${d.W_ci_hw.toFixed(4)}`)}
      ${metric('Wq — Avg Wait',      d.Wq_mean.toFixed(4),           '',       `95% CI ±${d.Wq_ci_hw.toFixed(4)}`)}
      ${metric('L — Avg in System',  d.L_mean.toFixed(4),            '',       'Via Little\'s Law')}
      ${metric('Lq — Avg in Queue',  d.Lq_mean.toFixed(4),           '',       'Via Little\'s Law')}
    </div>

    ${analyticalRow}

    <div class="chart-card">
      <div class="chart-card-title">Wait Time in Queue — Empirical Distribution</div>
      <div class="chart-wrapper">
        <canvas id="chart-sim-hist"></canvas>
      </div>
    </div>
  `;

  requestAnimationFrame(() => {
    SimCharts.renderWaitHistogram(
      document.getElementById('chart-sim-hist'),
      d.wait_histogram_bins,
      d.wait_histogram_counts,
      d.analytical_Wq
    );
  });
}

/* ══════════════════════════════════════════════════════════════════════════════
   AI EXPLANATION
══════════════════════════════════════════════════════════════════════════════ */

async function triggerExplanation(modelType, parameters, results) {
  const panel = document.getElementById('ai-panel');
  const body  = document.getElementById('ai-body');
  const badge = document.getElementById('ai-model-badge');

  panel.hidden = false;
  body.innerHTML = '<span class="spinner"></span> Generating insight…';
  badge.textContent = '';

  try {
    const resp = await SimAPI.getExplanation(modelType, parameters, results);
    body.textContent = resp.explanation;
    badge.textContent = resp.model_used;
  } catch (e) {
    if (e.status === 503) {
      body.textContent = 'AI insights are disabled — add your ANTHROPIC_API_KEY to the .env file to enable them.';
    } else {
      body.textContent = `AI error: ${e.detail ?? e.message}`;
    }
  }
}

/* ══════════════════════════════════════════════════════════════════════════════
   UTILITIES
══════════════════════════════════════════════════════════════════════════════ */

/** Build a metric card HTML string. */
function metric(label, value, cls, sub) {
  return `
    <div class="metric-card ${cls === 'good' || cls === 'warning' || cls === 'danger' ? 'highlight' : ''}">
      <div class="metric-label">${escHtml(label)}</div>
      <div class="metric-value ${cls ?? ''}">${escHtml(String(value))}</div>
      ${sub ? `<div class="metric-sub">${escHtml(sub)}</div>` : ''}
    </div>`;
}

/** HTML-escape a string — prevents XSS from server-returned strings. */
function escHtml(str) {
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

/** Toggle button loading state. */
function setLoading(btn, loading) {
  if (loading) {
    btn.disabled = true;
    btn.dataset.originalText = btn.textContent;
    btn.innerHTML = '<span class="spinner"></span>Computing…';
  } else {
    btn.disabled = false;
    btn.textContent = btn.dataset.originalText ?? 'Run Analysis';
  }
}

/** Show a toast notification. */
function showToast(message, type = '') {
  const toast = document.getElementById('toast');
  toast.textContent = message;
  toast.className   = `toast ${type} show`;
  setTimeout(() => { toast.classList.remove('show'); }, 5000);
}
