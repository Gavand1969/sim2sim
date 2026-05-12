/**
 * Chart.js helpers for Sim2Sim.
 * All charts use the same dark-theme defaults derived from CSS variables.
 */

'use strict';

// Shared Chart.js defaults — applied once after Chart.js loads
function initChartDefaults() {
  Chart.defaults.color          = '#8b949e';
  Chart.defaults.borderColor    = '#30363d';
  Chart.defaults.font.family    = "'Inter', sans-serif";
  Chart.defaults.font.size      = 12;
  Chart.defaults.plugins.legend.display = false;
  Chart.defaults.plugins.tooltip.backgroundColor = '#1f2937';
  Chart.defaults.plugins.tooltip.borderColor      = '#30363d';
  Chart.defaults.plugins.tooltip.borderWidth      = 1;
  Chart.defaults.plugins.tooltip.padding          = 10;
  Chart.defaults.plugins.tooltip.titleColor       = '#e6edf3';
  Chart.defaults.plugins.tooltip.bodyColor        = '#8b949e';
}

/**
 * Destroy an existing chart on a canvas (prevents Chart.js double-register error).
 * @param {HTMLCanvasElement} canvas
 */
function destroyChart(canvas) {
  const existing = Chart.getChart(canvas);
  if (existing) existing.destroy();
}

/**
 * Render P(N=n) probability distribution bar chart.
 * @param {HTMLCanvasElement} canvas
 * @param {number[]} probs  - P(N=n) for n = 0..20
 */
function renderProbDist(canvas, probs) {
  destroyChart(canvas);
  const labels = probs.map((_, i) => i);
  new Chart(canvas, {
    type: 'bar',
    data: {
      labels,
      datasets: [{
        label: 'P(N=n)',
        data: probs,
        backgroundColor: probs.map(p =>
          p > 0.1 ? 'rgba(88,166,255,0.7)' : 'rgba(88,166,255,0.4)'
        ),
        borderColor: '#58a6ff',
        borderWidth: 1,
        borderRadius: 3,
      }],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      scales: {
        x: { title: { display: true, text: 'n (customers in system)' } },
        y: {
          title: { display: true, text: 'Probability' },
          min: 0, max: Math.min(1, Math.max(...probs) * 1.2),
        },
      },
      plugins: {
        tooltip: {
          callbacks: {
            label: ctx => `P(N=${ctx.label}) = ${ctx.raw.toFixed(4)}`,
          },
        },
      },
    },
  });
}

/**
 * Render EOQ total-cost curve with cost components.
 * @param {HTMLCanvasElement} canvas
 * @param {number[]} qVals
 * @param {number[]} tc
 * @param {number[]} holding
 * @param {number[]} ordering
 * @param {number}   eoq      - optimal Q to mark
 */
function renderCostCurve(canvas, qVals, tc, holding, ordering, eoq) {
  destroyChart(canvas);
  new Chart(canvas, {
    type: 'line',
    data: {
      labels: qVals.map(q => q.toFixed(0)),
      datasets: [
        {
          label: 'Total Cost',
          data: tc,
          borderColor: '#58a6ff',
          backgroundColor: 'rgba(88,166,255,0.08)',
          borderWidth: 2.5,
          pointRadius: 0,
          fill: true,
          tension: 0.3,
        },
        {
          label: 'Holding Cost',
          data: holding,
          borderColor: '#3fb950',
          borderWidth: 1.5,
          borderDash: [4, 4],
          pointRadius: 0,
          fill: false,
          tension: 0.3,
        },
        {
          label: 'Ordering Cost',
          data: ordering,
          borderColor: '#f0883e',
          borderWidth: 1.5,
          borderDash: [4, 4],
          pointRadius: 0,
          fill: false,
          tension: 0.3,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: {
          display: true,
          labels: { color: '#8b949e', boxWidth: 12 },
        },
        tooltip: {
          mode: 'index', intersect: false,
          callbacks: {
            label: ctx => `${ctx.dataset.label}: $${ctx.raw.toFixed(2)}`,
          },
        },
        annotation: {
          annotations: {
            eoqLine: {
              type: 'line',
              xMin: eoq.toFixed(0),
              xMax: eoq.toFixed(0),
              borderColor: 'rgba(88,166,255,0.5)',
              borderWidth: 1,
              borderDash: [6, 4],
              label: { content: `EOQ = ${eoq.toFixed(0)}`, display: true },
            },
          },
        },
      },
      scales: {
        x: {
          title: { display: true, text: 'Order Quantity (Q)' },
          ticks: { maxTicksLimit: 8 },
        },
        y: {
          title: { display: true, text: 'Annual Cost ($)' },
          ticks: {
            callback: v => '$' + v.toLocaleString(),
          },
        },
      },
    },
  });
}

/**
 * Render Newsvendor expected-profit curve.
 */
function renderProfitCurve(canvas, qVals, profits, qStar) {
  destroyChart(canvas);
  new Chart(canvas, {
    type: 'line',
    data: {
      labels: qVals.map(q => q.toFixed(0)),
      datasets: [{
        label: 'Expected Profit',
        data: profits,
        borderColor: '#3fb950',
        backgroundColor: 'rgba(63,185,80,0.08)',
        borderWidth: 2.5,
        pointRadius: 0,
        fill: true,
        tension: 0.3,
      }],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        tooltip: {
          callbacks: {
            label: ctx => `E[Profit] = $${ctx.raw.toFixed(2)}`,
          },
        },
      },
      scales: {
        x: {
          title: { display: true, text: 'Order Quantity (Q)' },
          ticks: { maxTicksLimit: 8 },
        },
        y: {
          title: { display: true, text: 'Expected Profit ($)' },
          ticks: { callback: v => '$' + v.toLocaleString() },
        },
      },
    },
  });
}

/**
 * Render Monte Carlo wait-time histogram with optional analytical overlay.
 */
function renderWaitHistogram(canvas, bins, counts, analyticalWq) {
  destroyChart(canvas);

  // Build bin labels from edges (bins has length counts.length + 1)
  const labels = counts.map((_, i) =>
    `${bins[i].toFixed(2)}–${bins[i + 1].toFixed(2)}`
  );
  const binWidth = bins[1] - bins[0];

  // Convert counts to density
  const total  = counts.reduce((a, b) => a + b, 0);
  const density = counts.map(c => c / (total * binWidth));

  new Chart(canvas, {
    type: 'bar',
    data: {
      labels,
      datasets: [{
        label: 'Density',
        data: density,
        backgroundColor: 'rgba(88,166,255,0.5)',
        borderColor: '#58a6ff',
        borderWidth: 1,
        borderRadius: 2,
      }],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        tooltip: {
          callbacks: {
            label: ctx => `Density: ${ctx.raw.toFixed(4)}`,
          },
        },
      },
      scales: {
        x: {
          title: { display: true, text: 'Wait Time in Queue (Wq)' },
          ticks: { maxTicksLimit: 8 },
        },
        y: {
          title: { display: true, text: 'Density' },
          beginAtZero: true,
        },
      },
    },
  });
}

/**
 * Simple cost curve without annotation plugin (for EPQ, backorder curves).
 * @param {HTMLCanvasElement} canvas
 * @param {number[]} qVals
 * @param {number[]} tc      - total cost
 * @param {number}   qStar   - label only, no annotation plugin needed
 * @param {string}   xLabel
 */
function renderSimpleCostCurve(canvas, qVals, tc, qStar, xLabel) {
  destroyChart(canvas);
  new Chart(canvas, {
    type: 'line',
    data: {
      labels: qVals.map(q => q.toFixed(0)),
      datasets: [{
        label: 'Total Cost',
        data: tc,
        borderColor: '#58a6ff',
        backgroundColor: 'rgba(88,166,255,0.08)',
        borderWidth: 2.5,
        pointRadius: 0,
        fill: true,
        tension: 0.3,
      }],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { display: false },
        tooltip: {
          callbacks: {
            label: ctx => `TC: $${ctx.raw.toFixed(2)}`,
            title: ctx => `Q = ${ctx[0].label}`,
          },
        },
      },
      scales: {
        x: {
          title: { display: true, text: xLabel || 'Order Quantity (Q)' },
          ticks: { maxTicksLimit: 8 },
        },
        y: {
          title: { display: true, text: 'Annual Cost ($)' },
          ticks: { callback: v => '$' + v.toLocaleString() },
        },
      },
    },
  });
}

/**
 * Grouped bar chart for scenario comparison.
 * @param {HTMLCanvasElement} canvas
 * @param {string[]} labels        - scenario names
 * @param {number[]} wqValues      - Wq per scenario
 * @param {number[]} utilizationValues - ρ per scenario
 */
function renderScenarioBar(canvas, labels, wqValues, utilizationValues) {
  destroyChart(canvas);
  new Chart(canvas, {
    type: 'bar',
    data: {
      labels,
      datasets: [
        {
          label: 'Avg Wait in Queue (Wq)',
          data: wqValues,
          backgroundColor: 'rgba(88,166,255,0.7)',
          borderColor: '#58a6ff',
          borderWidth: 1,
          borderRadius: 4,
          yAxisID: 'yWq',
        },
        {
          label: 'Utilization (ρ)',
          data: utilizationValues,
          backgroundColor: 'rgba(63,185,80,0.7)',
          borderColor: '#3fb950',
          borderWidth: 1,
          borderRadius: 4,
          yAxisID: 'yRho',
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: {
          display: true,
          labels: { color: '#8b949e', boxWidth: 12 },
        },
        tooltip: {
          mode: 'index', intersect: false,
          callbacks: {
            label: ctx => {
              if (ctx.dataset.yAxisID === 'yRho') {
                return `ρ = ${(ctx.raw * 100).toFixed(1)}%`;
              }
              return `Wq = ${ctx.raw.toFixed(4)}`;
            },
          },
        },
      },
      scales: {
        x: { ticks: { color: '#8b949e' } },
        yWq: {
          type: 'linear',
          position: 'left',
          title: { display: true, text: 'Wq (time units)', color: '#58a6ff' },
          ticks: { color: '#58a6ff' },
        },
        yRho: {
          type: 'linear',
          position: 'right',
          title: { display: true, text: 'Utilization ρ', color: '#3fb950' },
          ticks: {
            color: '#3fb950',
            callback: v => (v * 100).toFixed(0) + '%',
          },
          grid: { drawOnChartArea: false },
          min: 0, max: 1,
        },
      },
    },
  });
}

window.SimCharts = {
  initChartDefaults,
  renderProbDist,
  renderCostCurve,
  renderSimpleCostCurve,
  renderProfitCurve,
  renderWaitHistogram,
  renderScenarioBar,
};
