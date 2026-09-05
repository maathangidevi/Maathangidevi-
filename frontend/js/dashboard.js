/**
 * dashboard.js – Dashboard view rendering and chart management.
 *
 * All values come from /api/dashboard — nothing is hardcoded.
 * Sections:
 *   1. Formatters
 *   2. Attention Today  ← new, decision-focused top panel
 *   3. KPI Cards
 *   4. Revenue Chart    ← date range derived from API series
 *   5. Category Chart
 *   6. Top Products
 *   7. Inventory Health
 *   8. Quick Copilot widget
 *   9. Main loader
 */

// ─── Chart instances ──────────────────────────────────────────────────────────
let revenueChart = null;
let categoryChart = null;

// ─── Formatters ───────────────────────────────────────────────────────────────
function fmtINR(val) {
  if (val >= 1_00_00_000) return `\u20b9${(val / 1_00_00_000).toFixed(1)}Cr`;
  if (val >= 1_00_000)    return `\u20b9${(val / 1_00_000).toFixed(1)}L`;
  if (val >= 1_000)       return `\u20b9${(val / 1_000).toFixed(1)}K`;
  return `\u20b9${Number(val).toFixed(0)}`;
}

function fmtNum(n) {
  return Number(n).toLocaleString('en-IN');
}

function deltaClass(pct) {
  if (pct == null) return '';
  return pct >= 0 ? 'positive' : 'negative';
}

function deltaArrow(pct) {
  if (pct == null) return 'vs prev 30d';
  const arrow = pct >= 0 ? '\u25b2' : '\u25bc';
  return `${arrow} ${Math.abs(pct)}% vs prev 30d`;
}

function setText(id, val) {
  const el = document.getElementById(id);
  if (el) el.textContent = val;
}

function setDelta(id, pct) {
  const el = document.getElementById(id);
  if (!el) return;
  el.textContent = deltaArrow(pct);
  el.className = 'kpi-delta ' + deltaClass(pct);
}

// ─── 1. ATTENTION TODAY ───────────────────────────────────────────────────────
/**
 * Renders the "Attention Today" panel at the top of the dashboard.
 * Uses alerts from /api/dashboard — data.critical_alerts (already sorted by
 * severity: critical first). Each card shows:
 *   - severity badge
 *   - product name + key metric pulled from alert.data
 *   - why it matters (alert.description, truncated)
 *   - recommended action (alert.recommendation, truncated)
 */
function renderAttentionToday(alerts, alertsSummary) {
  const container = document.getElementById('attention-cards');
  const countEl   = document.getElementById('attention-count');
  if (!container) return;

  // Determine the count badge text
  const crit = alertsSummary.critical;
  const warn = alertsSummary.warning;
  const countText = crit > 0
    ? `${crit} critical · ${warn} warnings`
    : warn > 0 ? `${warn} warnings` : 'No critical issues';
  if (countEl) {
    countEl.textContent = countText;
    countEl.className = 'attention-count' + (crit > 0 ? ' attention-count--critical' : warn > 0 ? ' attention-count--warning' : ' attention-count--ok');
  }

  if (!alerts || alerts.length === 0) {
    container.innerHTML = `
      <div class="attention-empty">
        <span style="font-size:1.5rem">✅</span>
        <span>No critical issues right now. Store looks healthy.</span>
      </div>`;
    return;
  }

  // Build metric badge from alert.data (pick the most informative field)
  function buildMetricBadge(alert) {
    const d = alert.data || {};
    if (alert.type === 'stockout_risk') {
      return `<span class="attn-metric critical">${d.days_of_stock != null ? d.days_of_stock.toFixed(1) + ' days left' : ''}</span>
              <span class="attn-metric-sub">${d.current_stock != null ? fmtNum(d.current_stock) + ' units' : ''}</span>`;
    }
    if (alert.type === 'overstock') {
      return `<span class="attn-metric warning">${d.days_of_stock != null ? Math.round(d.days_of_stock) + ' days of stock' : ''}</span>
              <span class="attn-metric-sub">${d.capital_locked_inr != null ? fmtINR(d.capital_locked_inr) + ' locked' : ''}</span>`;
    }
    if (alert.type === 'sales_spike') {
      return `<span class="attn-metric info">z = ${d.z_score != null ? d.z_score.toFixed(1) : ''}&sigma; spike</span>
              <span class="attn-metric-sub">${d.units_sold != null ? fmtNum(d.units_sold) + ' units' : ''} on ${d.date || ''}</span>`;
    }
    if (alert.type === 'sales_drop') {
      return `<span class="attn-metric warning">z = ${d.z_score != null ? d.z_score.toFixed(1) : ''}&sigma; drop</span>
              <span class="attn-metric-sub">${d.units_sold != null ? fmtNum(d.units_sold) + ' units' : ''} on ${d.date || ''}</span>`;
    }
    if (alert.type === 'slow_mover') {
      return `<span class="attn-metric info">${d.avg_daily_units_30d != null ? d.avg_daily_units_30d + ' units/day' : ''}</span>
              <span class="attn-metric-sub">${d.current_stock != null ? fmtNum(d.current_stock) + ' in stock' : ''}</span>`;
    }
    return '';
  }

  // Truncate text helper
  function trunc(str, max) {
    if (!str) return '';
    return str.length > max ? str.slice(0, max) + '\u2026' : str;
  }

  container.innerHTML = alerts.slice(0, 6).map(a => {
    const sev = a.severity;
    const metric = buildMetricBadge(a);
    return `
      <div class="attn-card ${sev}" role="listitem">
        <div class="attn-card-top">
          <span class="attn-sev-pill ${sev}">${sev.toUpperCase()}</span>
          <div class="attn-product">${a.product_name || a.title}</div>
          <div class="attn-metric-row">${metric}</div>
        </div>
        <div class="attn-why">${trunc(a.description, 120)}</div>
        <div class="attn-action">
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
            <polyline points="9 18 15 12 9 6"/>
          </svg>
          ${trunc(a.recommendation, 110)}
        </div>
      </div>`;
  }).join('');
}

// ─── 2. KPI Cards ─────────────────────────────────────────────────────────────
function renderKPIs(data) {
  const k        = data.kpis;
  const inv      = data.inventory_health;
  const alertSum = data.alerts_summary;

  // Revenue
  setText('kpi-revenue-val', fmtINR(k.revenue_30d));
  setDelta('kpi-revenue-delta', k.mom_revenue_change_pct);

  // Units
  setText('kpi-units-val', fmtNum(k.units_30d));
  setDelta('kpi-units-delta', k.mom_units_change_pct);

  // Gross margin
  setText('kpi-margin-val', fmtINR(k.gross_margin_30d));
  const margEl = document.getElementById('kpi-margin-pct');
  if (margEl) {
    margEl.textContent = `${k.gross_margin_pct_30d}% margin`;
    margEl.className = 'kpi-delta';
  }

  // Alerts summary
  setText('kpi-alerts-val', alertSum.total);
  const alertDelta = document.getElementById('kpi-alerts-detail');
  if (alertDelta) {
    alertDelta.textContent = `${alertSum.critical} critical · ${alertSum.warning} warnings`;
    alertDelta.className = 'kpi-delta' + (alertSum.critical > 0 ? ' negative' : '');
  }

  // Low stock
  setText('kpi-lowstock-val', inv.low_stock_count);
  const lsSub = document.getElementById('kpi-lowstock-sub');
  if (lsSub) {
    const critCount = inv.low_stock_products.filter(p => p.stock_status === 'critical').length;
    lsSub.textContent = `${critCount} critical · ${inv.low_stock_count - critCount} low`;
    lsSub.className = 'kpi-delta' + (critCount > 0 ? ' negative' : '');
  }

  // Overstock
  setText('kpi-overstock-val', inv.overstock_count);
  const osSub = document.getElementById('kpi-overstock-sub');
  if (osSub) {
    osSub.textContent = `${inv.slow_mover_count} slow movers`;
    osSub.className = 'kpi-delta';
  }
}

// ─── 3. Revenue Chart ─────────────────────────────────────────────────────────
function renderRevenueChart(series) {
  const ctx = document.getElementById('revenue-chart');
  if (!ctx || !series || series.length === 0) return;

  if (revenueChart) revenueChart.destroy();

  // Derive actual date range from API data (no hardcoding)
  const firstDate = series[0].date;
  const lastDate  = series[series.length - 1].date;
  const fmtDate   = iso => {
    const d = new Date(iso);
    return d.toLocaleDateString('en-IN', { day: 'numeric', month: 'short', year: '2-digit' });
  };
  setText('chart-date-range', `${fmtDate(firstDate)} \u2013 ${fmtDate(lastDate)} · ${series.length} days`);

  const labels   = series.map(d => {
    const dt = new Date(d.date);
    return dt.toLocaleDateString('en-IN', { day: 'numeric', month: 'short' });
  });
  const revenues = series.map(d => d.revenue);

  const chartCtx = ctx.getContext('2d');
  const gradient = chartCtx.createLinearGradient(0, 0, 0, 220);
  gradient.addColorStop(0, 'rgba(99,102,241,0.35)');
  gradient.addColorStop(1, 'rgba(99,102,241,0.01)');

  revenueChart = new Chart(ctx, {
    type: 'line',
    data: {
      labels,
      datasets: [{
        label: 'Revenue',
        data: revenues,
        borderColor: '#6366f1',
        backgroundColor: gradient,
        borderWidth: 2,
        fill: true,
        tension: 0.4,
        pointRadius: 0,
        pointHoverRadius: 5,
        pointHoverBackgroundColor: '#818cf8',
        pointHoverBorderColor: '#fff',
        pointHoverBorderWidth: 2,
      }],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: { mode: 'index', intersect: false },
      plugins: {
        legend: { display: false },
        tooltip: {
          backgroundColor: '#141426',
          borderColor: 'rgba(255,255,255,0.1)',
          borderWidth: 1,
          titleColor: '#94a3b8',
          bodyColor: '#f1f5f9',
          padding: 12,
          callbacks: {
            label: ctx => ` \u20b9${Number(ctx.raw).toLocaleString('en-IN')}`,
          },
        },
      },
      scales: {
        x: {
          grid: { color: 'rgba(255,255,255,0.04)' },
          ticks: {
            color: '#475569', font: { size: 10 },
            maxTicksLimit: 12, maxRotation: 0,
          },
        },
        y: {
          grid: { color: 'rgba(255,255,255,0.04)' },
          ticks: {
            color: '#475569', font: { size: 10 },
            callback: v => fmtINR(v),
          },
          border: { dash: [4, 4] },
        },
      },
    },
  });
}

// ─── 4. Category Chart ────────────────────────────────────────────────────────
const CAT_COLORS = ['#6366f1','#8b5cf6','#06b6d4','#10b981','#f59e0b','#f43f5e','#ec4899'];

function renderCategoryChart(catData) {
  const ctx = document.getElementById('category-chart');
  if (!ctx) return;
  if (categoryChart) categoryChart.destroy();

  const labels   = catData.map(c => c.category);
  const revenues = catData.map(c => c.revenue);
  const colors   = labels.map((_, i) => CAT_COLORS[i % CAT_COLORS.length]);

  categoryChart = new Chart(ctx, {
    type: 'doughnut',
    data: {
      labels,
      datasets: [{
        data: revenues,
        backgroundColor: colors.map(c => c + 'cc'),
        borderColor: colors,
        borderWidth: 2,
        hoverOffset: 8,
      }],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      cutout: '65%',
      plugins: {
        legend: {
          position: 'right',
          labels: { color: '#94a3b8', font: { size: 11 }, padding: 10, boxWidth: 12, boxHeight: 12 },
        },
        tooltip: {
          backgroundColor: '#141426',
          borderColor: 'rgba(255,255,255,0.1)',
          borderWidth: 1,
          titleColor: '#94a3b8',
          bodyColor: '#f1f5f9',
          callbacks: { label: ctx => ` ${ctx.label}: ${fmtINR(ctx.raw)}` },
        },
      },
    },
  });
}

// ─── 5. Top Products ──────────────────────────────────────────────────────────
function renderTopProducts(products) {
  const el = document.getElementById('top-products-list');
  if (!el || !products.length) return;

  const maxRev = Math.max(...products.map(p => p.revenue));
  el.innerHTML = products.map((p, i) => `
    <div class="top-product-row">
      <div class="top-product-rank">#${i + 1}</div>
      <div style="flex:1;min-width:0">
        <div class="top-product-name">${p.name}</div>
        <div class="top-product-bar" style="width:${(p.revenue / maxRev * 100).toFixed(1)}%"></div>
      </div>
      <div class="top-product-rev">${fmtINR(p.revenue)}</div>
    </div>
  `).join('');
}

// ─── 6. Inventory Health ──────────────────────────────────────────────────────
function renderInventoryHealth(inv) {
  const el = document.getElementById('inv-health-grid');
  if (!el) return;

  el.innerHTML = `
    <div class="inv-cell inv-cell--good">
      <div class="inv-cell-value">${inv.healthy_count}</div>
      <div class="inv-cell-label">Healthy</div>
    </div>
    <div class="inv-cell inv-cell--bad">
      <div class="inv-cell-value">${inv.low_stock_count}</div>
      <div class="inv-cell-label">Low Stock</div>
    </div>
    <div class="inv-cell inv-cell--info">
      <div class="inv-cell-value">${inv.overstock_count}</div>
      <div class="inv-cell-label">Overstocked</div>
    </div>
    <div class="inv-cell inv-cell--warn">
      <div class="inv-cell-value">${inv.slow_mover_count}</div>
      <div class="inv-cell-label">Slow Movers</div>
    </div>
  `;
}

// ─── 7. Quick Copilot widget (dashboard) ─────────────────────────────────────
function initQuickCopilot() {
  // Prompt buttons — navigate to copilot view and pre-send the question
  document.querySelectorAll('.qc-prompt-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      const q = btn.dataset.q;
      // Navigate to copilot tab
      if (typeof showView === 'function') showView('copilot');
      // Send via copilot.js after a tick (so DOM is visible)
      setTimeout(() => { if (typeof sendCopilotMessage === 'function') sendCopilotMessage(q); }, 80);
    });
  });

  // Inline input + send button
  const qcInput = document.getElementById('qc-input');
  const qcSend  = document.getElementById('qc-send');

  function doSend() {
    const q = qcInput ? qcInput.value.trim() : '';
    if (!q) return;
    if (typeof showView === 'function') showView('copilot');
    setTimeout(() => { if (typeof sendCopilotMessage === 'function') sendCopilotMessage(q); }, 80);
    if (qcInput) qcInput.value = '';
  }

  if (qcSend) qcSend.addEventListener('click', doSend);
  if (qcInput) {
    qcInput.addEventListener('keydown', e => {
      if (e.key === 'Enter') { e.preventDefault(); doSend(); }
    });
  }
}

// ─── 8. Main loader ───────────────────────────────────────────────────────────
async function loadDashboard() {
  try {
    const data = await API.getDashboard();

    // All renders use API data — no hardcoded values
    renderAttentionToday(data.critical_alerts, data.alerts_summary);
    renderKPIs(data);
    renderRevenueChart(data.daily_series_90d);
    renderTopProducts(data.top_products_30d);
    renderCategoryChart(data.category_breakdown_30d);
    renderInventoryHealth(data.inventory_health);
    initQuickCopilot();

    // Store badge
    const badge = document.getElementById('store-badge');
    if (badge && data.store) {
      badge.textContent = `${data.store.name} \u00b7 ${data.store.location}`;
    }
  } catch (err) {
    console.error('Dashboard load error:', err);
    const errEl = document.getElementById('kpi-revenue-val');
    if (errEl) errEl.textContent = 'Error loading data';
    const attnEl = document.getElementById('attention-cards');
    if (attnEl) attnEl.innerHTML = `<div class="attention-empty">Failed to load: ${err.message}</div>`;
  }
}
