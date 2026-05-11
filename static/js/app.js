'use strict';

/* ── Boot ─────────────────────────────────────────────────────────────────── */
document.addEventListener('DOMContentLoaded', () => {
  SimCharts.initChartDefaults();
  initTabs();
  initQueuingModelToggle();
  initInventoryModelToggle();
  initOptimizationModelToggle();
  initUtilPreview();
  initButtons();
  initScenarioComparison();
  initLPBuilder();
  initCPMBuilder();
});

/* ══════════════════════════════════════════════════════════════════════════
   TABS
══════════════════════════════════════════════════════════════════════════ */
function initTabs() {
  document.querySelectorAll('.tab').forEach(tab => {
    tab.addEventListener('click', () => {
      const target = tab.dataset.tab;
      document.querySelectorAll('.tab').forEach(t => {
        t.classList.remove('active'); t.setAttribute('aria-selected','false');
      });
      document.querySelectorAll('.panel').forEach(p => {
        const isTarget = p.id === `panel-${target}`;
        p.classList.toggle('active', isTarget);
        p.hidden = !isTarget;
      });
      tab.classList.add('active'); tab.setAttribute('aria-selected','true');
    });
  });
}

/* ══════════════════════════════════════════════════════════════════════════
   QUEUING MODEL TOGGLE
══════════════════════════════════════════════════════════════════════════ */
function initQueuingModelToggle() {
  const sel = document.getElementById('q-model');
  if (!sel) return;

  function update() {
    const v = sel.value;
    const show = (id, condition) => {
      const el = document.getElementById(id);
      if (el) el.style.display = condition ? 'flex' : 'none';
      if (el) el.style.flexDirection = 'column';
    };
    show('q-c-group',     v === 'MMC' || v === 'MMCK');
    show('q-K-group',     v === 'MM1K' || v === 'MMCK');
    show('q-csv-group',   v === 'MG1' || v === 'GG1');
    show('q-cav-group',   v === 'GG1');
    show('q-batch-group', v === 'BULK');
  }
  sel.addEventListener('change', update);
  update();
}

/* ══════════════════════════════════════════════════════════════════════════
   INVENTORY MODEL TOGGLE
══════════════════════════════════════════════════════════════════════════ */
function initInventoryModelToggle() {
  const sel = document.getElementById('inv-model');
  if (!sel) return;

  const allGroups = ['inv-eoq-fields','inv-backorder-fields','inv-epq-fields',
                     'inv-newsvendor-fields','inv-reorder-fields'];

  function update() {
    const v = sel.value;
    allGroups.forEach(id => {
      const el = document.getElementById(id);
      if (el) el.style.display = 'none';
    });
    // Always show EOQ base fields for eoq, eoq-backorder, epq
    const showEOQ = ['eoq','eoq-backorder','epq'].includes(v);
    const el_eoq = document.getElementById('inv-eoq-fields');
    if (el_eoq) el_eoq.style.display = showEOQ ? 'block' : 'none';

    if (v === 'eoq-backorder') show('inv-backorder-fields');
    if (v === 'epq')           show('inv-epq-fields');
    if (v === 'newsvendor')    show('inv-newsvendor-fields');
    if (v === 'reorder-point' || v === 'base-stock') show('inv-reorder-fields');
  }

  function show(id) {
    const el = document.getElementById(id);
    if (el) el.style.display = 'block';
  }

  sel.addEventListener('change', update);
  update();
}

/* ══════════════════════════════════════════════════════════════════════════
   OPTIMIZATION MODEL TOGGLE
══════════════════════════════════════════════════════════════════════════ */
function initOptimizationModelToggle() {
  const sel = document.getElementById('opt-model');
  if (!sel) return;
  function update() {
    const v = sel.value;
    const lp  = document.getElementById('opt-lp-fields');
    const cpm = document.getElementById('opt-cpm-fields');
    if (lp)  lp.style.display  = v === 'lp'  ? 'block' : 'none';
    if (cpm) cpm.style.display = v === 'cpm' ? 'block' : 'none';
  }
  sel.addEventListener('change', update);
  update();
}

/* ══════════════════════════════════════════════════════════════════════════
   LIVE UTILIZATION PREVIEW
══════════════════════════════════════════════════════════════════════════ */
function initUtilPreview() {
  ['q-lambda','q-mu','q-c','q-model','q-batch'].forEach(id => {
    document.getElementById(id)?.addEventListener('input', updateUtilPreview);
  });
  updateUtilPreview();
}

function updateUtilPreview() {
  const lam   = parseFloat(document.getElementById('q-lambda')?.value) || 0;
  const mu    = parseFloat(document.getElementById('q-mu')?.value)     || 1;
  const c     = parseInt(document.getElementById('q-c')?.value)        || 1;
  const model = document.getElementById('q-model')?.value;
  const batch = parseInt(document.getElementById('q-batch')?.value)    || 1;
  const el    = document.getElementById('q-util-preview');
  const val   = document.getElementById('q-util-val');
  if (!el || !val) return;

  if (!lam || !mu) { val.textContent = '—'; return; }

  // Infinite server: utilization is always 0 (no saturation)
  if (model === 'MMINF') { val.textContent = 'N/A (∞ servers)'; el.className = 'utilization-preview'; return; }

  const lam_eff = model === 'BULK' ? lam * batch : lam;
  const rho = lam_eff / (c * mu);
  val.textContent = rho.toFixed(4);
  el.className = 'utilization-preview' + (rho >= 1.0 ? ' danger' : rho >= 0.85 ? ' warning' : '');
}

/* ══════════════════════════════════════════════════════════════════════════
   BUTTON WIRING
══════════════════════════════════════════════════════════════════════════ */
function initButtons() {
  document.getElementById('btn-queuing')?.addEventListener('click',     handleQueuing);
  document.getElementById('btn-inventory')?.addEventListener('click',   handleInventory);
  document.getElementById('btn-simulation')?.addEventListener('click',  handleSimulation);
  document.getElementById('btn-optimization')?.addEventListener('click',handleOptimization);
}

/* ══════════════════════════════════════════════════════════════════════════
   QUEUING HANDLER
══════════════════════════════════════════════════════════════════════════ */
async function handleQueuing() {
  const btn = document.getElementById('btn-queuing');
  const params = {
    model:          document.getElementById('q-model').value,
    arrival_rate:   parseFloat(document.getElementById('q-lambda').value),
    service_rate:   parseFloat(document.getElementById('q-mu').value),
    num_servers:    parseInt(document.getElementById('q-c').value)     || 1,
    service_cv_sq:  parseFloat(document.getElementById('q-csv').value)  || 1.0,
    arrival_cv_sq:  parseFloat(document.getElementById('q-cav').value)  || 1.0,
    capacity:       parseInt(document.getElementById('q-K').value)     || 10,
    batch_size:     parseInt(document.getElementById('q-batch').value) || 2,
  };

  setLoading(btn, true);
  try {
    const data = await SimAPI.analyseQueue(params);
    renderQueuingResults(data, params, 'results-queuing');
    triggerExplanation('Queuing (' + data.model + ')', params, summariseQueuing(data));
  } catch(e) { showToast(e.detail ?? e.message, 'error'); }
  finally    { setLoading(btn, false); }
}

function summariseQueuing(d) {
  return {
    model: d.model, utilization: d.utilization,
    L: d.L, Lq: d.Lq, W: d.W, Wq: d.Wq,
    P0: d.P0, P_wait: d.P_wait,
    blocking_prob: d.blocking_prob,
    effective_arrival_rate: d.effective_lam,
    little_law_error: d.little_law_check,
    notes: d.notes,
  };
}

function renderQueuingResults(d, params, containerId = 'results-queuing', label = null) {
  const container = document.getElementById(containerId);
  const rhoClass  = d.utilization >= 0.9 ? 'danger' : d.utilization >= 0.75 ? 'warning' : 'good';
  const title     = label ? `<h3 style="margin:0 0 0.75rem">${escHtml(label)}</h3>` : '';

  const blockingRow = d.blocking_prob != null ? `
    ${metric('P(block)',        d.blocking_prob.toFixed(4),  'warning', 'Prob. arriving customer is lost')}
    ${metric('λ_eff (throughput)', d.effective_lam.toFixed(4), '',      'Actual arrival rate after blocking')}
  ` : '';

  const notesRow = d.notes ? `<p class="field-hint" style="margin-top:.5rem">ℹ ${escHtml(d.notes)}</p>` : '';

  const formulaRow = getQueuingFormula(d.model);

  container.innerHTML = `
    ${title}
    <div class="metric-grid">
      ${metric('ρ — Utilization',   d.utilization.toFixed(4), rhoClass, 'Server busy fraction')}
      ${metric('L — Avg in System', d.L.toFixed(4),           '',       "Little's Law: L = λW")}
      ${metric('Lq — Avg in Queue', d.Lq.toFixed(4),          '',       'Customers waiting')}
      ${metric('W — Avg Sojourn',   d.W.toFixed(4),           '',       'Time in system')}
      ${metric('Wq — Avg Wait',     d.Wq.toFixed(4),          '',       'Time in queue')}
      ${metric('P₀ — Idle Prob',    d.P0.toFixed(4),          '',       'Fraction of time empty')}
      ${d.P_wait != null ? metric('P(wait) — Erlang-C', d.P_wait.toFixed(4), '', 'Prob. customer must wait') : ''}
      ${blockingRow}
    </div>
    <div style="display:flex;gap:8px;flex-wrap:wrap;align-items:center;">
      <span class="sanity-badge">✓ Little's Law error: ${d.little_law_check.toExponential(2)}</span>
    </div>
    ${notesRow}
    ${formulaRow}
    <div class="chart-card">
      <div class="chart-card-title">Queue-Length Distribution P(N = n)</div>
      <div class="chart-wrapper"><canvas id="chart-q-dist-${containerId}"></canvas></div>
    </div>
  `;

  // Re-render KaTeX after DOM update
  requestAnimationFrame(() => {
    renderKaTeX(container);
    SimCharts.renderProbDist(
      document.getElementById(`chart-q-dist-${containerId}`), d.prob_dist
    );
  });
}

function getQueuingFormula(model) {
  const formulas = {
    'M/M/1':      '$$W = \\frac{1}{\\mu - \\lambda}, \\quad W_q = \\frac{\\lambda}{\\mu(\\mu-\\lambda)}, \\quad L = \\lambda W$$',
    'M/D/1':      '$$L_q = \\frac{\\rho^2}{2(1-\\rho)} \\quad (\\text{half of M/M/1})$$',
    'M/G/1':      '$$L_q = \\frac{\\lambda^2 E[S^2]}{2(1-\\rho)} \\quad \\text{(Pollaczek-Khinchine)}$$',
    'M/M/∞':      '$$L = \\frac{\\lambda}{\\mu}, \\quad W_q = 0 \\quad \\text{(no queuing ever)}$$',
  };
  // Match prefix
  for (const [key, f] of Object.entries(formulas)) {
    if (model.startsWith(key)) {
      return `<div class="formula-box">${f}</div>`;
    }
  }
  if (model.includes('Kingman') || model.startsWith('G/G/1')) {
    return `<div class="formula-box">$$W_q \\approx \\frac{\\rho}{1-\\rho} \\cdot \\frac{C_a^2 + C_s^2}{2} \\cdot \\frac{1}{\\mu} \\quad \\text{(Kingman)}$$</div>`;
  }
  return '';
}

/* ══════════════════════════════════════════════════════════════════════════
   SCENARIO COMPARISON
══════════════════════════════════════════════════════════════════════════ */
let _scenarios = [];   // extra scenario overrides

function initScenarioComparison() {
  document.getElementById('btn-compare-toggle')?.addEventListener('click', () => {
    const panel = document.getElementById('compare-panel');
    if (!panel) return;
    const open = panel.style.display === 'none';
    panel.style.display = open ? 'block' : 'none';
    if (open && _scenarios.length === 0) addScenario();
  });

  document.getElementById('btn-add-scenario')?.addEventListener('click', addScenario);
  document.getElementById('btn-run-compare')?.addEventListener('click', handleCompare);
}

function addScenario() {
  if (_scenarios.length >= 7) { showToast('Maximum 7 additional scenarios', 'error'); return; }
  const idx = _scenarios.length;
  const id  = `scenario-${idx}`;
  _scenarios.push({});

  const row = document.createElement('div');
  row.className = 'scenario-row';
  row.id = id;
  row.innerHTML = `
    <span class="scenario-label">Scenario ${idx + 2}</span>
    <label class="field-label" style="margin-top:.5rem">λ</label>
    <input type="number" class="field-input sc-lambda" value="${document.getElementById('q-lambda').value}" min="0.01" step="0.1"/>
    <label class="field-label">μ</label>
    <input type="number" class="field-input sc-mu" value="${document.getElementById('q-mu').value}" min="0.01" step="0.1"/>
    <label class="field-label">c</label>
    <input type="number" class="field-input sc-c" value="${document.getElementById('q-c').value || 1}" min="1" step="1"/>
    <button class="btn-secondary" style="margin-top:.5rem" onclick="removeScenario(${idx})">Remove</button>
  `;
  document.getElementById('scenario-list')?.appendChild(row);
}

function removeScenario(idx) {
  _scenarios.splice(idx, 1);
  const el = document.getElementById(`scenario-${idx}`);
  el?.parentNode.removeChild(el);
  // Re-number remaining rows
  document.querySelectorAll('.scenario-row').forEach((row, i) => {
    row.id = `scenario-${i}`;
    const lbl = row.querySelector('.scenario-label');
    if (lbl) lbl.textContent = `Scenario ${i + 2}`;
    const btn = row.querySelector('button');
    if (btn) btn.setAttribute('onclick', `removeScenario(${i})`);
  });
  _scenarios = _scenarios.filter((_, i) => i !== idx);
}

async function handleCompare() {
  const btn = document.getElementById('btn-run-compare');
  const baseModel  = document.getElementById('q-model').value;
  const baseLambda = parseFloat(document.getElementById('q-lambda').value);
  const baseMu     = parseFloat(document.getElementById('q-mu').value);
  const baseC      = parseInt(document.getElementById('q-c').value) || 1;

  // Base scenario
  const scenarios = [{
    model: baseModel, arrival_rate: baseLambda, service_rate: baseMu,
    num_servers: baseC, service_cv_sq: parseFloat(document.getElementById('q-csv').value)||1,
    arrival_cv_sq: parseFloat(document.getElementById('q-cav').value)||1,
    capacity: parseInt(document.getElementById('q-K').value)||10,
    batch_size: parseInt(document.getElementById('q-batch').value)||2,
  }];
  const labels = ['Base'];

  // Additional scenarios from the compare panel
  document.querySelectorAll('.scenario-row').forEach((row, i) => {
    const lam = parseFloat(row.querySelector('.sc-lambda').value);
    const mu  = parseFloat(row.querySelector('.sc-mu').value);
    const c   = parseInt(row.querySelector('.sc-c').value) || 1;
    scenarios.push({ model: baseModel, arrival_rate: lam, service_rate: mu, num_servers: c,
                     service_cv_sq: 1, arrival_cv_sq: 1, capacity: 10, batch_size: 2 });
    labels.push(`S${i+2} (λ=${lam}, μ=${mu})`);
  });

  if (scenarios.length < 2) { showToast('Add at least one scenario to compare', 'error'); return; }

  setLoading(btn, true);
  try {
    const data = await SimAPI.compareScenarios({ scenarios, labels });
    renderComparisonResults(data);
  } catch(e) { showToast(e.detail ?? e.message, 'error'); }
  finally    { setLoading(btn, false); }
}

function renderComparisonResults(data) {
  const container = document.getElementById('results-queuing');
  const { results, labels } = data;

  // Comparison table
  const headers = ['Label','ρ','L','Lq','W','Wq','P₀'];
  const rows = results.map((r, i) => `
    <tr>
      <td>${escHtml(labels[i])}</td>
      <td class="${r.utilization>=0.9?'danger':r.utilization>=0.75?'warning':'good'}">${r.utilization.toFixed(3)}</td>
      <td>${r.L.toFixed(3)}</td>
      <td>${r.Lq.toFixed(3)}</td>
      <td>${r.W.toFixed(4)}</td>
      <td>${r.Wq.toFixed(4)}</td>
      <td>${r.P0.toFixed(3)}</td>
    </tr>`).join('');

  container.innerHTML = `
    <h3 style="margin:0 0 0.75rem">Scenario Comparison</h3>
    <div class="table-wrapper">
      <table class="compare-table">
        <thead><tr>${headers.map(h=>`<th>${h}</th>`).join('')}</tr></thead>
        <tbody>${rows}</tbody>
      </table>
    </div>
    <div class="chart-card">
      <div class="chart-card-title">Average Wait Time (Wq) by Scenario</div>
      <div class="chart-wrapper"><canvas id="chart-compare"></canvas></div>
    </div>
  `;

  requestAnimationFrame(() => {
    SimCharts.renderScenarioBar(
      document.getElementById('chart-compare'),
      labels,
      results.map(r => r.Wq),
      results.map(r => r.utilization)
    );
  });
}

/* ══════════════════════════════════════════════════════════════════════════
   INVENTORY HANDLER
══════════════════════════════════════════════════════════════════════════ */
async function handleInventory() {
  const btn   = document.getElementById('btn-inventory');
  const model = document.getElementById('inv-model').value;
  setLoading(btn, true);
  try {
    switch (model) {
      case 'eoq':          await handleEOQ();           break;
      case 'eoq-backorder': await handleEOQBackorder(); break;
      case 'epq':          await handleEPQ();           break;
      case 'newsvendor':   await handleNewsvendor();    break;
      case 'reorder-point': await handleReorderPoint(); break;
      case 'base-stock':   await handleBaseStock();     break;
      default: showToast('Unknown inventory model', 'error');
    }
  } catch(e) { showToast(e.detail ?? e.message, 'error'); }
  finally    { setLoading(btn, false); }
}

async function handleEOQ() {
  const params = {
    annual_demand: parseFloat(document.getElementById('eoq-demand').value),
    ordering_cost: parseFloat(document.getElementById('eoq-k').value),
    unit_cost:     parseFloat(document.getElementById('eoq-c').value),
    holding_rate:  parseFloat(document.getElementById('eoq-i').value),
  };
  const data = await SimAPI.analyseEOQ(params);
  renderEOQResults(data);
  triggerExplanation('EOQ', params, { eoq: data.eoq, orders_per_year: data.orders_per_year,
    cycle_time_days: data.cycle_time_days, total_annual_cost: data.total_annual_cost });
}

async function handleEOQBackorder() {
  const params = {
    annual_demand:  parseFloat(document.getElementById('eoq-demand').value),
    ordering_cost:  parseFloat(document.getElementById('eoq-k').value),
    unit_cost:      parseFloat(document.getElementById('eoq-c').value),
    holding_rate:   parseFloat(document.getElementById('eoq-i').value),
    backorder_cost: parseFloat(document.getElementById('eoq-pi').value),
  };
  const data = await SimAPI.post('/inventory/eoq-backorder', params);
  renderEOQBackorderResults(data);
  triggerExplanation('EOQ with Backorders', params, data);
}

async function handleEPQ() {
  const params = {
    annual_demand:   parseFloat(document.getElementById('eoq-demand').value),
    production_rate: parseFloat(document.getElementById('epq-P').value),
    setup_cost:      parseFloat(document.getElementById('eoq-k').value),
    unit_cost:       parseFloat(document.getElementById('eoq-c').value),
    holding_rate:    parseFloat(document.getElementById('eoq-i').value),
  };
  const data = await SimAPI.post('/inventory/epq', params);
  renderEPQResults(data);
  triggerExplanation('EPQ', params, data);
}

async function handleNewsvendor() {
  const params = {
    selling_price: parseFloat(document.getElementById('nv-price').value),
    unit_cost:     parseFloat(document.getElementById('nv-cost').value),
    salvage_value: parseFloat(document.getElementById('nv-salvage').value),
    demand_mean:   parseFloat(document.getElementById('nv-mean').value),
    demand_std:    parseFloat(document.getElementById('nv-std').value),
    demand_dist:   document.getElementById('nv-dist').value,
  };
  const data = await SimAPI.analyseNewsvendor(params);
  renderNewsvendorResults(data);
  triggerExplanation('Newsvendor', params, { critical_ratio: data.critical_ratio,
    optimal_quantity: data.optimal_quantity, expected_profit: data.expected_profit,
    fill_rate: data.fill_rate });
}

async function handleReorderPoint() {
  const params = {
    annual_demand:  parseFloat(document.getElementById('rp-demand').value),
    lead_time:      parseFloat(document.getElementById('rp-lead').value),
    demand_std_day: parseFloat(document.getElementById('rp-sigma').value),
    ordering_cost:  parseFloat(document.getElementById('rp-k').value),
    unit_cost:      parseFloat(document.getElementById('rp-c').value),
    holding_rate:   parseFloat(document.getElementById('rp-i').value),
    service_level:  parseFloat(document.getElementById('rp-sl').value),
  };
  const data = await SimAPI.post('/inventory/reorder-point', params);
  renderReorderPointResults(data);
  triggerExplanation('Reorder Point (Q,r) Policy', params, data);
}

async function handleBaseStock() {
  const params = {
    annual_demand:  parseFloat(document.getElementById('rp-demand').value),
    lead_time:      parseFloat(document.getElementById('rp-lead').value),
    demand_std_day: parseFloat(document.getElementById('rp-sigma').value),
    unit_cost:      parseFloat(document.getElementById('rp-c').value),
    holding_rate:   parseFloat(document.getElementById('rp-i').value),
    service_level:  parseFloat(document.getElementById('rp-sl').value),
  };
  const data = await SimAPI.post('/inventory/base-stock', params);
  renderBaseStockResults(data);
  triggerExplanation('Base Stock Policy', params, data);
}

/* ── Inventory result renderers ──────────────────────────────────────────── */
function renderEOQResults(d) {
  const container = document.getElementById('results-inventory');
  container.innerHTML = `
    <div class="metric-grid">
      ${metric('EOQ — Q*',         d.eoq.toFixed(2),             'good', 'Units per order')}
      ${metric('Orders / Year',    d.orders_per_year.toFixed(2), '',     'Replenishments')}
      ${metric('Cycle Time',       d.cycle_time_days.toFixed(1) + ' days','', '')}
      ${metric('Min Annual Cost',  '$'+d.total_annual_cost.toFixed(2), 'good', 'Holding + Ordering')}
    </div>
    <div class="formula-box">$$Q^* = \\sqrt{\\frac{2KD}{h}}, \\quad TC^* = \\sqrt{2KDh}$$</div>
    <div class="chart-card">
      <div class="chart-card-title">Total Cost vs. Order Quantity</div>
      <div class="chart-wrapper"><canvas id="chart-eoq-cost"></canvas></div>
    </div>
  `;
  requestAnimationFrame(() => {
    renderKaTeX(container);
    SimCharts.renderCostCurve(document.getElementById('chart-eoq-cost'),
      d.cost_curve_q, d.cost_curve_tc, d.cost_curve_holding, d.cost_curve_ordering, d.eoq);
  });
}

function renderEOQBackorderResults(d) {
  const container = document.getElementById('results-inventory');
  container.innerHTML = `
    <div class="metric-grid">
      ${metric('Optimal Q*',        d.eoq.toFixed(2),              'good', 'Order quantity')}
      ${metric('Max Inventory S*',  d.max_inventory.toFixed(2),    '',     'Peak on-hand stock')}
      ${metric('Max Backorder b*',  d.max_backorder.toFixed(2),    'warning', 'Peak backlog')}
      ${metric('Min Annual Cost',   '$'+d.total_annual_cost.toFixed(2),'good','')}
      ${metric('Savings vs EOQ',    '$'+d.savings_vs_eoq.toFixed(2),'good','Benefit of allowing backorders')}
    </div>
    <div class="formula-box">$$Q^* = \\sqrt{\\frac{2KD}{h}} \\cdot \\sqrt{\\frac{h+\\pi}{\\pi}}, \\quad S^* = Q^* \\cdot \\frac{\\pi}{h+\\pi}$$</div>
    <div class="chart-card">
      <div class="chart-card-title">Total Cost vs. Order Quantity</div>
      <div class="chart-wrapper"><canvas id="chart-eoq-cost"></canvas></div>
    </div>
  `;
  requestAnimationFrame(() => {
    renderKaTeX(container);
    SimCharts.renderSimpleCostCurve(document.getElementById('chart-eoq-cost'),
      d.cost_curve_q, d.cost_curve_tc, d.eoq, 'Order Quantity (Q)');
  });
}

function renderEPQResults(d) {
  const container = document.getElementById('results-inventory');
  container.innerHTML = `
    <div class="metric-grid">
      ${metric('EPQ — Q*',             d.epq.toFixed(2),              'good', 'Production run size')}
      ${metric('Max Inventory',        d.max_inventory.toFixed(2),    '',     'Peak on-hand stock')}
      ${metric('Production Run Time',  d.production_run_time.toFixed(1)+' days','','')}
      ${metric('Cycle Time',           d.cycle_time_days.toFixed(1)+' days','','')}
      ${metric('Uptime Fraction D/P',  (d.uptime_fraction*100).toFixed(1)+'%','','Fraction of time producing')}
      ${metric('Min Annual Cost',      '$'+d.total_annual_cost.toFixed(2),'good','')}
    </div>
    <div class="formula-box">$$Q^* = \\sqrt{\\frac{2KD}{h(1-D/P)}}, \\quad I_{\\max} = Q^*\\!\\left(1-\\frac{D}{P}\\right)$$</div>
    <div class="chart-card">
      <div class="chart-card-title">Total Cost vs. Production Run Size</div>
      <div class="chart-wrapper"><canvas id="chart-eoq-cost"></canvas></div>
    </div>
  `;
  requestAnimationFrame(() => {
    renderKaTeX(container);
    SimCharts.renderSimpleCostCurve(document.getElementById('chart-eoq-cost'),
      d.cost_curve_q, d.cost_curve_tc, d.epq, 'Production Run Size (Q)');
  });
}

function renderNewsvendorResults(d) {
  const container = document.getElementById('results-inventory');
  const fillPct = (d.fill_rate * 100).toFixed(1);
  container.innerHTML = `
    <div class="metric-grid">
      ${metric('Critical Ratio CR',  (d.critical_ratio*100).toFixed(1)+'%', 'good', 'Optimal service level')}
      ${metric('Optimal Q*',         d.optimal_quantity.toFixed(1),          'good', 'Units to order')}
      ${metric('Expected Profit',    '$'+d.expected_profit.toFixed(2),        d.expected_profit>0?'good':'danger','')}
      ${metric('Fill Rate',          fillPct+'%',                              parseFloat(fillPct)>=90?'good':'warning','Type-I service')}
      ${metric('Exp. Leftover',      d.expected_leftover.toFixed(1),          '','Units salvaged')}
      ${metric('Exp. Stockout',      d.expected_stockout.toFixed(1),          'warning','Unmet demand')}
    </div>
    <div class="formula-box">$$CR = \\frac{p - c}{p - s}, \\quad Q^* = F^{-1}(CR)$$</div>
    <div class="chart-card">
      <div class="chart-card-title">Expected Profit vs. Order Quantity</div>
      <div class="chart-wrapper"><canvas id="chart-nv-profit"></canvas></div>
    </div>
  `;
  requestAnimationFrame(() => {
    renderKaTeX(container);
    SimCharts.renderProfitCurve(document.getElementById('chart-nv-profit'),
      d.profit_curve_q, d.profit_curve_ep, d.optimal_quantity);
  });
}

function renderReorderPointResults(d) {
  const container = document.getElementById('results-inventory');
  container.innerHTML = `
    <div class="metric-grid">
      ${metric('Order Qty Q*',   d.order_quantity.toFixed(1),     'good', 'EOQ order size')}
      ${metric('Reorder Point r',d.reorder_point.toFixed(1),      'good', 'Order when stock hits r')}
      ${metric('Safety Stock',   d.safety_stock.toFixed(1),       '',     'Buffer against variability')}
      ${metric('z-score',        d.z_score.toFixed(3),            '',     'Std devs of safety stock')}
      ${metric('Service Level',  (d.service_level*100).toFixed(1)+'%','good','No-stockout probability')}
      ${metric('Total Annual Cost','$'+d.total_annual_cost.toFixed(2),'','')}
    </div>
    <div class="formula-box">$$r = D \\cdot L + z \\cdot \\sigma_L, \\quad SS = z \\cdot \\sigma_L, \\quad \\sigma_L = \\sigma_d \\sqrt{L}$$</div>
  `;
  requestAnimationFrame(() => renderKaTeX(container));
}

function renderBaseStockResults(d) {
  const container = document.getElementById('results-inventory');
  container.innerHTML = `
    <div class="metric-grid">
      ${metric('Base Stock S*',      d.base_stock_level.toFixed(1),    'good','Order-up-to level')}
      ${metric('Safety Stock',       d.safety_stock.toFixed(1),        '',    'Buffer against variability')}
      ${metric('Exp. On-Hand Inv.',  d.expected_inventory.toFixed(2),  '',    'Average units on shelf')}
      ${metric('Exp. Backorders',    d.expected_backorders.toFixed(2),  'warning','Average units short')}
      ${metric('Fill Rate',          (d.fill_rate*100).toFixed(1)+'%',  d.fill_rate>=0.95?'good':'warning','Type-II service level')}
      ${metric('Annual Hold Cost',   '$'+d.annual_hold_cost.toFixed(2),'','')}
    </div>
    <div class="formula-box">$$S^* = \\mu_L + z\\,\\sigma_L, \\quad E[B] = \\sigma_L \\, \\mathcal{L}(z), \\quad \\mathcal{L}(z) = \\phi(z) - z(1-\\Phi(z))$$</div>
  `;
  requestAnimationFrame(() => renderKaTeX(container));
}

/* ══════════════════════════════════════════════════════════════════════════
   SIMULATION HANDLER
══════════════════════════════════════════════════════════════════════════ */
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
      utilization: data.utilization_mean, W: data.W_mean, Wq: data.Wq_mean,
      W_CI: `±${data.W_ci_hw.toFixed(4)}`, Wq_CI: `±${data.Wq_ci_hw.toFixed(4)}`,
      analytical_W: data.analytical_W, analytical_Wq: data.analytical_Wq,
    });
  } catch(e) { showToast(e.detail ?? e.message, 'error'); }
  finally    { setLoading(btn, false); }
}

function renderSimulationResults(d) {
  const container = document.getElementById('results-simulation');
  const rhoClass = d.utilization_mean >= 0.9 ? 'danger' : d.utilization_mean >= 0.75 ? 'warning' : 'good';
  const analyticalRow = d.analytical_W != null ? `
    <div style="display:flex;gap:8px;flex-wrap:wrap;">
      <span class="ci-badge">Analytical W = ${d.analytical_W.toFixed(4)}</span>
      <span class="ci-badge">Analytical Wq = ${d.analytical_Wq.toFixed(4)}</span>
    </div>` : '';

  container.innerHTML = `
    <div class="metric-grid">
      ${metric('ρ — Utilization', d.utilization_mean.toFixed(4), rhoClass,     'Simulated busy fraction')}
      ${metric('W — Avg Sojourn', d.W_mean.toFixed(4),           '',           `95% CI ±${d.W_ci_hw.toFixed(4)}`)}
      ${metric('Wq — Avg Wait',   d.Wq_mean.toFixed(4),          '',           `95% CI ±${d.Wq_ci_hw.toFixed(4)}`)}
      ${metric('L — Avg in Sys',  d.L_mean.toFixed(4),           '',           "Little's Law")}
      ${metric('Lq — Avg in Q',   d.Lq_mean.toFixed(4),          '',           "Little's Law")}
    </div>
    ${analyticalRow}
    <div class="chart-card">
      <div class="chart-card-title">Wait Time Distribution — Empirical</div>
      <div class="chart-wrapper"><canvas id="chart-sim-hist"></canvas></div>
    </div>
  `;
  requestAnimationFrame(() => {
    SimCharts.renderWaitHistogram(document.getElementById('chart-sim-hist'),
      d.wait_histogram_bins, d.wait_histogram_counts, d.analytical_Wq);
  });
}

/* ══════════════════════════════════════════════════════════════════════════
   OPTIMIZATION HANDLER
══════════════════════════════════════════════════════════════════════════ */
async function handleOptimization() {
  const btn   = document.getElementById('btn-optimization');
  const model = document.getElementById('opt-model').value;
  setLoading(btn, true);
  try {
    if (model === 'lp')  await handleLP();
    if (model === 'cpm') await handleCPM();
  } catch(e) { showToast(e.detail ?? e.message, 'error'); }
  finally    { setLoading(btn, false); }
}

async function handleLP() {
  const nVars = parseInt(document.getElementById('lp-nvars').value) || 2;
  const objective = document.getElementById('lp-obj').value;

  const varInputs = document.querySelectorAll('#lp-obj-coeffs .coeff-input');
  const c_obj = Array.from(varInputs).slice(0, nVars).map(el => parseFloat(el.value) || 0);

  const varNameInputs = document.querySelectorAll('#lp-var-names .var-name-input');
  const variable_names = Array.from(varNameInputs).slice(0, nVars).map(el => el.value.trim() || `x${el.dataset.idx}`);

  const constraintRows = document.querySelectorAll('.lp-constraint-row');
  const A_ub = [], b_ub = [], constraint_names = [];
  constraintRows.forEach(row => {
    const coeffInputs = row.querySelectorAll('.con-coeff');
    const rhsInput    = row.querySelector('.con-rhs');
    const nameInput   = row.querySelector('.con-name');
    const A_row = Array.from(coeffInputs).slice(0, nVars).map(el => parseFloat(el.value)||0);
    A_ub.push(A_row);
    b_ub.push(parseFloat(rhsInput?.value) || 0);
    constraint_names.push(nameInput?.value.trim() || `C${constraint_names.length+1}`);
  });

  if (A_ub.length === 0) { showToast('Add at least one constraint', 'error'); return; }

  const params = { objective, c_obj, A_ub, b_ub, variable_names, constraint_names };
  const data = await SimAPI.post('/optimize/lp', params);
  renderLPResults(data, variable_names, constraint_names, c_obj, objective);
  triggerExplanation('Linear Programming', params, {
    status: data.status, optimal_value: data.optimal_value,
    variables: data.variables, shadow_prices: data.shadow_prices,
    binding_constraints: data.binding_constraints,
  });
}

async function handleCPM() {
  const taskRows = document.querySelectorAll('.cpm-task-row');
  const tasks = [];
  taskRows.forEach(row => {
    const name    = row.querySelector('.cpm-name')?.value.trim();
    const dur     = parseFloat(row.querySelector('.cpm-dur')?.value) || 0;
    const vari    = parseFloat(row.querySelector('.cpm-var')?.value) || 0;
    const preds   = (row.querySelector('.cpm-preds')?.value || '')
                       .split(',').map(s=>s.trim()).filter(Boolean);
    if (name) tasks.push({ name, duration: dur, variance: vari, predecessors: preds });
  });
  if (tasks.length === 0) { showToast('Add at least one task', 'error'); return; }

  const data = await SimAPI.post('/optimize/cpm', { tasks });
  renderCPMResults(data);
  triggerExplanation('CPM/PERT Project Scheduling', { tasks },
    { critical_path: data.critical_path, project_duration: data.project_duration,
      project_std: data.project_std });
}

/* ── LP / CPM result renderers ───────────────────────────────────────────── */
function renderLPResults(d, varNames, conNames, c_obj, objective) {
  const container = document.getElementById('results-optimization');
  if (d.status !== 'optimal') {
    container.innerHTML = `<div class="empty-state"><p>❌ ${escHtml(d.status)}</p></div>`;
    return;
  }

  const varRows = varNames.map(n =>
    `<tr><td>${escHtml(n)}</td><td>${d.variables[n]?.toFixed(4) ?? '—'}</td><td>${d.reduced_costs[n]?.toFixed(4) ?? '—'}</td></tr>`
  ).join('');

  const spRows = conNames.map(n => {
    const binding = d.binding_constraints.includes(n);
    return `<tr class="${binding?'binding':''}">
      <td>${escHtml(n)}</td>
      <td>${d.shadow_prices[n]?.toFixed(4) ?? '—'}</td>
      <td>${d.slacks[n]?.toFixed(4) ?? '—'}</td>
      <td>${binding ? '✓ Binding' : 'Slack'}</td>
    </tr>`;
  }).join('');

  container.innerHTML = `
    <div class="metric-grid">
      ${metric('Optimal Value', d.optimal_value?.toFixed(4) ?? '—', 'good',
               objective === 'maximize' ? 'Maximum objective' : 'Minimum objective')}
      ${metric('Status', d.status, 'good', '')}
      ${metric('Binding Constraints', d.binding_constraints.length + ' / ' + conNames.length, '', 'Tight at optimum')}
    </div>

    <h4 style="margin:1rem 0 .5rem">Decision Variables</h4>
    <div class="table-wrapper">
      <table class="compare-table">
        <thead><tr><th>Variable</th><th>Value</th><th>Reduced Cost</th></tr></thead>
        <tbody>${varRows}</tbody>
      </table>
    </div>

    <h4 style="margin:1rem 0 .5rem">Constraints — Shadow Prices</h4>
    <p class="field-hint">Shadow price = value of relaxing a binding constraint by 1 unit.</p>
    <div class="table-wrapper">
      <table class="compare-table">
        <thead><tr><th>Constraint</th><th>Shadow Price</th><th>Slack</th><th>Status</th></tr></thead>
        <tbody>${spRows}</tbody>
      </table>
    </div>
  `;
  requestAnimationFrame(() => renderKaTeX(container));
}

function renderCPMResults(d) {
  const container = document.getElementById('results-optimization');

  const taskRows = Object.entries(d.tasks).map(([name, t]) => `
    <tr class="${t.critical ? 'binding' : ''}">
      <td>${escHtml(name)}</td>
      <td>${t.duration}</td>
      <td>${t.ES}</td><td>${t.EF}</td>
      <td>${t.LS}</td><td>${t.LF}</td>
      <td>${t.float}</td>
      <td>${t.critical ? '⭐ Critical' : ''}</td>
    </tr>`).join('');

  const pert95 = d.project_std > 0
    ? ` (95% CI: ${(d.project_duration - 1.645*d.project_std).toFixed(2)} – ${(d.project_duration + 1.645*d.project_std).toFixed(2)})`
    : '';

  container.innerHTML = `
    <div class="metric-grid">
      ${metric('Project Duration', d.project_duration.toFixed(2)+' units', 'good', pert95)}
      ${metric('Critical Path', d.critical_path.join(' → '), 'good', 'Tasks with zero float')}
      ${d.project_std > 0 ? metric('PERT Std Dev', d.project_std.toFixed(3), 'warning', 'Uncertainty in completion') : ''}
    </div>

    <h4 style="margin:1rem 0 .5rem">Task Schedule</h4>
    <div class="table-wrapper">
      <table class="compare-table">
        <thead><tr><th>Task</th><th>Duration</th><th>ES</th><th>EF</th><th>LS</th><th>LF</th><th>Float</th><th>Flag</th></tr></thead>
        <tbody>${taskRows}</tbody>
      </table>
    </div>
  `;
}

/* ══════════════════════════════════════════════════════════════════════════
   LP BUILDER (dynamic form)
══════════════════════════════════════════════════════════════════════════ */
function initLPBuilder() {
  const nVarsSel = document.getElementById('lp-nvars');
  if (!nVarsSel) return;
  nVarsSel.addEventListener('change', buildLPForm);
  document.getElementById('btn-add-constraint')?.addEventListener('click', addLPConstraint);
  buildLPForm();
}

function buildLPForm() {
  const n = parseInt(document.getElementById('lp-nvars').value) || 2;
  const defaultCoeffs = [5, 4, 3, 2];
  const defaultVarNames = ['x1','x2','x3','x4'];

  // Variable names
  const varNamesDiv = document.getElementById('lp-var-names');
  if (varNamesDiv) {
    varNamesDiv.innerHTML = '<label class="field-label">Variable Names</label><div style="display:flex;gap:8px;flex-wrap:wrap;">' +
      Array.from({length:n}, (_,i) =>
        `<input class="field-input var-name-input" style="width:80px" data-idx="${i+1}" value="${defaultVarNames[i]||'x'+(i+1)}" placeholder="x${i+1}"/>`
      ).join('') + '</div>';
  }

  // Objective coefficients
  const objDiv = document.getElementById('lp-obj-coeffs');
  if (objDiv) {
    objDiv.innerHTML = '<div style="display:flex;gap:8px;flex-wrap:wrap;">' +
      Array.from({length:n}, (_,i) =>
        `<input class="field-input coeff-input" style="width:80px" value="${defaultCoeffs[i]||1}" type="number" step="any"/>`
      ).join('') + '</div>';
  }

  // Reset constraints with a default example
  const conDiv = document.getElementById('lp-constraints');
  if (conDiv) {
    conDiv.innerHTML = '';
    _lpConstraintCount = 0;
    // Default: 6x+4y<=24 and x+2y<=6
    const defaults = [
      { name:'Labor',    coeffs: [6,4,0,0], rhs: 24 },
      { name:'Material', coeffs: [1,2,0,0], rhs: 6  },
    ];
    defaults.forEach(d => addLPConstraint(null, d.name, d.coeffs.slice(0,n), d.rhs));
  }
}

let _lpConstraintCount = 0;

function addLPConstraint(e, name = '', defaultCoeffs = [], defaultRhs = 0) {
  const n   = parseInt(document.getElementById('lp-nvars').value) || 2;
  const div = document.createElement('div');
  div.className = 'lp-constraint-row';
  div.style.cssText = 'display:flex;flex-direction:column;gap:4px;margin-bottom:.75rem;padding:.5rem;background:var(--bg-card);border-radius:6px;border:1px solid var(--border)';

  div.innerHTML = `
    <div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap;">
      <input class="field-input con-name" style="width:100px" placeholder="Name" value="${escHtml(name)}"/>
      ${Array.from({length:n}, (_,i) =>
        `<input class="field-input con-coeff" style="width:70px" value="${defaultCoeffs[i]||0}" type="number" step="any"/>`
      ).join('')}
      <span style="padding:0 4px;color:var(--text-muted)">≤</span>
      <input class="field-input con-rhs" style="width:80px" value="${defaultRhs}" type="number" step="any"/>
      <button class="btn-secondary" style="padding:.25rem .5rem" onclick="this.closest('.lp-constraint-row').remove()">✕</button>
    </div>
  `;
  document.getElementById('lp-constraints')?.appendChild(div);
  _lpConstraintCount++;
}

/* ══════════════════════════════════════════════════════════════════════════
   CPM BUILDER (dynamic form)
══════════════════════════════════════════════════════════════════════════ */
function initCPMBuilder() {
  document.getElementById('btn-add-task')?.addEventListener('click', addCPMTask);
  // Default project
  [
    { name:'A', dur:3, v:0,    preds:''  },
    { name:'B', dur:4, v:0.11, preds:'A' },
    { name:'C', dur:2, v:0,    preds:'A' },
    { name:'D', dur:5, v:0.44, preds:'B,C'},
  ].forEach(t => addCPMTask(null, t.name, t.dur, t.v, t.preds));
}

function addCPMTask(e, name='', dur=1, variance=0, preds='') {
  const row = document.createElement('div');
  row.className = 'cpm-task-row';
  row.style.cssText = 'display:grid;grid-template-columns:1fr 1fr 1fr 2fr auto;gap:6px;margin-bottom:.5rem;align-items:center';
  row.innerHTML = `
    <input class="field-input cpm-name" placeholder="Task name" value="${escHtml(name)}"/>
    <input class="field-input cpm-dur"  type="number" placeholder="Duration" value="${dur}" min="0.01" step="any"/>
    <input class="field-input cpm-var"  type="number" placeholder="Variance" value="${variance}" min="0" step="any"/>
    <input class="field-input cpm-preds" placeholder="Predecessors (comma-sep)" value="${escHtml(preds)}"/>
    <button class="btn-secondary" style="padding:.25rem .5rem" onclick="this.closest('.cpm-task-row').remove()">✕</button>
  `;
  document.getElementById('cpm-tasks')?.appendChild(row);
}

/* ══════════════════════════════════════════════════════════════════════════
   AI EXPLANATION
══════════════════════════════════════════════════════════════════════════ */
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
  } catch(e) {
    if (e.status === 503)
      body.textContent = 'AI insights are disabled — add ANTHROPIC_API_KEY to .env to enable.';
    else
      body.textContent = `AI error: ${e.detail ?? e.message}`;
  }
}

/* ══════════════════════════════════════════════════════════════════════════
   KATEX RE-RENDER
══════════════════════════════════════════════════════════════════════════ */
function renderKaTeX(container) {
  if (typeof renderMathInElement === 'function') {
    renderMathInElement(container, {
      delimiters: [
        {left:'$$', right:'$$', display:true},
        {left:'$',  right:'$',  display:false},
      ],
      throwOnError: false,
    });
  }
}

/* ══════════════════════════════════════════════════════════════════════════
   UTILITIES
══════════════════════════════════════════════════════════════════════════ */
function metric(label, value, cls, sub) {
  const highlight = ['good','warning','danger'].includes(cls) ? 'highlight' : '';
  return `
    <div class="metric-card ${highlight}">
      <div class="metric-label">${escHtml(label)}</div>
      <div class="metric-value ${cls || ''}">${escHtml(String(value))}</div>
      ${sub ? `<div class="metric-sub">${escHtml(sub)}</div>` : ''}
    </div>`;
}

function escHtml(str) {
  return String(str)
    .replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')
    .replace(/"/g,'&quot;').replace(/'/g,'&#39;');
}

function setLoading(btn, loading) {
  if (!btn) return;
  if (loading) {
    btn.disabled = true;
    btn.dataset.originalText = btn.textContent;
    btn.innerHTML = '<span class="spinner"></span>Computing…';
  } else {
    btn.disabled = false;
    btn.textContent = btn.dataset.originalText || 'Run';
  }
}

function showToast(message, type = '') {
  const toast = document.getElementById('toast');
  if (!toast) return;
  toast.textContent = message;
  toast.className = `toast ${type} show`;
  setTimeout(() => toast.classList.remove('show'), 5000);
}
