/**
 * app.js – RetailIQ SPA bootstrap, routing, and shared state.
 */

// ─── View routing ─────────────────────────────────────────────────────────────
const VIEWS = ['dashboard', 'products', 'alerts', 'copilot'];

function showView(viewId) {
  VIEWS.forEach(v => {
    const section = document.getElementById(`view-${v}`);
    const navItem = document.getElementById(`nav-${v}`);
    if (section) section.classList.toggle('hidden', v !== viewId);
    if (navItem) navItem.classList.toggle('active', v === viewId);
  });

  // Update title
  const titles = {
    dashboard: ['Dashboard', 'Real-time retail intelligence'],
    products:  ['Products', 'Inventory & catalogue'],
    alerts:    ['Alerts', 'Issues needing your attention'],
    copilot:   ['AI Copilot', 'Ask anything about your store'],
  };
  const [title, sub] = titles[viewId] || ['RetailIQ', ''];
  setText('page-title', title);
  setText('page-subtitle', sub);

  // Lazy-load view data
  if (viewId === 'products') loadProducts();
  if (viewId === 'alerts')   loadAlerts();
}

function setText(id, val) {
  const el = document.getElementById(id);
  if (el) el.textContent = val;
}

// ─── Products View ────────────────────────────────────────────────────────────
let allProducts = [];
let filteredProducts = [];
let currentStatusFilter = '';
let currentSortField = null;
let currentSortAsc = true;

async function loadProducts() {
  try {
    const data = await API.getProducts();
    allProducts = data.products;

    // Populate category filter dropdown
    const catSelect = document.getElementById('filter-category');
    if (catSelect) {
      const cats = [...new Set(allProducts.map(p => p.category))].sort();
      catSelect.innerHTML = '<option value="">All Categories</option>' +
        cats.map(c => `<option value="${c}">${c}</option>`).join('');
    }

    // Attach status pill event listeners
    document.querySelectorAll('.pf-pill[data-status]').forEach(btn => {
      btn.addEventListener('click', () => {
        document.querySelectorAll('.pf-pill[data-status]').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        currentStatusFilter = btn.dataset.status || '';
        applyProductFilters();
      });
    });

    // Attach sort header event listeners
    document.querySelectorAll('.th-sortable[data-sort]').forEach(th => {
      th.addEventListener('click', () => {
        const field = th.dataset.sort;
        if (currentSortField === field) {
          currentSortAsc = !currentSortAsc;
        } else {
          currentSortField = field;
          currentSortAsc = false; // default descending for metrics
        }
        applyProductFilters();
      });
    });

    applyProductFilters();
  } catch (err) {
    const tbody = document.getElementById('products-tbody');
    if (tbody) tbody.innerHTML = `<tr><td colspan="9" class="loading-cell">Error loading products: ${err.message}</td></tr>`;
  }
}

function applyProductFilters() {
  const catFilter = document.getElementById('filter-category')?.value || '';
  const search = (document.getElementById('filter-search')?.value || '').toLowerCase().trim();

  filteredProducts = allProducts.filter(p => {
    if (catFilter && p.category !== catFilter) return false;
    if (search && !p.name.toLowerCase().includes(search) && !p.id.toLowerCase().includes(search)) return false;
    if (currentStatusFilter === 'critical' && p.stock_status !== 'critical') return false;
    if (currentStatusFilter === 'low' && !p.is_low_stock) return false;
    if (currentStatusFilter === 'overstock' && !p.is_overstock) return false;
    if (currentStatusFilter === 'slow_mover' && !p.is_slow_mover) return false;
    if (currentStatusFilter === 'normal' && p.stock_status !== 'normal') return false;
    return true;
  });

  // Apply sorting if active
  if (currentSortField) {
    filteredProducts.sort((a, b) => {
      let valA = 0, valB = 0;
      if (currentSortField === 'stock') { valA = a.current_stock; valB = b.current_stock; }
      else if (currentSortField === 'units') { valA = a.units_sold_30d || 0; valB = b.units_sold_30d || 0; }
      else if (currentSortField === 'avgdaily') { valA = a.avg_daily_units_30d || 0; valB = b.avg_daily_units_30d || 0; }
      else if (currentSortField === 'dos') { valA = a.days_of_stock; valB = b.days_of_stock; }

      return currentSortAsc ? valA - valB : valB - valA;
    });
  }

  // Update counts display
  const countsEl = document.getElementById('pf-counts');
  if (countsEl) {
    countsEl.textContent = `Showing ${filteredProducts.length} of ${allProducts.length} products`;
  }

  renderProductsTable(filteredProducts);
}

function getStatusLabel(p) {
  if (p.stock_status === 'critical') return ['critical', 'Critical'];
  if (p.stock_status === 'low')      return ['low', 'Low Stock'];
  if (p.is_overstock)                return ['overstock', 'Overstock'];
  if (p.is_slow_mover)               return ['slow', 'Slow Mover'];
  return ['normal', 'Healthy'];
}

function renderProductsTable(products) {
  const tbody = document.getElementById('products-tbody');
  if (!tbody) return;

  if (products.length === 0) {
    tbody.innerHTML = `<tr><td colspan="9" class="loading-cell">No products match the current filters.</td></tr>`;
    return;
  }

  tbody.innerHTML = products.map(p => {
    const [cls, label] = getStatusLabel(p);
    const dos = p.days_of_stock >= 999 ? '∞' : p.days_of_stock.toFixed(1);
    const units30d = p.units_sold_30d != null ? p.units_sold_30d.toLocaleString('en-IN') : '0';
    return `
      <tr class="product-row" data-id="${p.id}" style="cursor:pointer">
        <td>
          <div class="product-name-cell">${p.name}</div>
          <div class="product-id">${p.id}</div>
        </td>
        <td>${p.category}</td>
        <td><strong>${Number(p.current_stock).toLocaleString('en-IN')}</strong></td>
        <td>${units30d}</td>
        <td>${p.avg_daily_units_30d} / day</td>
        <td><strong>${dos}</strong> days</td>
        <td>${p.reorder_point}</td>
        <td><span class="status-pill ${cls}">${label}</span></td>
        <td class="th-detail">
          <button class="btn-detail" onclick="openProductModal('${p.id}'); event.stopPropagation();">
            View
          </button>
        </td>
      </tr>
    `;
  }).join('');

  // Row click opens modal
  tbody.querySelectorAll('.product-row').forEach(row => {
    row.addEventListener('click', () => openProductModal(row.dataset.id));
  });
}

// Product Detail Modal
async function openProductModal(productId) {
  const product = allProducts.find(p => p.id === productId);
  if (!product) return;

  const modal = document.getElementById('product-modal');
  const body = document.getElementById('product-modal-body');
  if (!modal || !body) return;

  const [cls, label] = getStatusLabel(product);
  const dos = product.days_of_stock >= 999 ? '∞' : product.days_of_stock.toFixed(1);
  const units30d = product.units_sold_30d != null ? product.units_sold_30d.toLocaleString('en-IN') : '0';
  const rev30d = product.revenue_30d ? fmtINR(product.revenue_30d) : '₹0';

  // Find relevant alerts for this product
  let alertMatches = [];
  try {
    if (allAlerts.length === 0) {
      const data = await API.getAlerts();
      allAlerts = data.alerts;
    }
    alertMatches = allAlerts.filter(a =>
      a.product_id === product.id || (a.product_name && a.product_name.toLowerCase() === product.name.toLowerCase())
    );
  } catch (e) {}

  let alertHtml = '';
  if (alertMatches.length > 0) {
    alertHtml = alertMatches.map(a => `
      <div class="pm-alert-box ${a.severity}">
        <div style="font-weight:700;font-size:0.82rem;margin-bottom:4px;color:var(--text-primary)">
          ${a.severity.toUpperCase()}: ${a.title}
        </div>
        <div style="font-size:0.78rem;color:var(--text-secondary);margin-bottom:8px">${a.description}</div>
        <div class="pm-rec-box">💡 <strong>Action:</strong> ${a.recommendation}</div>
      </div>
    `).join('');
  } else {
    alertHtml = `
      <div class="pm-rec-box" style="border-left-color:var(--emerald)">
        ✅ <strong>Healthy Inventory:</strong> Stock level (${product.current_stock} units) is above the reorder point of ${product.reorder_point} units. No immediate action required.
      </div>
    `;
  }

  body.innerHTML = `
    <div class="pm-header">
      <div>
        <div class="pm-title">${product.name}</div>
        <div class="pm-sku">SKU: ${product.id} · Category: ${product.category}</div>
      </div>
      <div style="display:flex;align-items:center;gap:12px">
        <span class="status-pill ${cls}">${label}</span>
        <button class="pm-close" onclick="closeProductModal()">&times;</button>
      </div>
    </div>

    <div class="pm-grid">
      <div class="pm-stat-box">
        <div class="pm-stat-lbl">Current Stock</div>
        <div class="pm-stat-val">${product.current_stock.toLocaleString('en-IN')}</div>
      </div>
      <div class="pm-stat-box">
        <div class="pm-stat-lbl">Days Left</div>
        <div class="pm-stat-val">${dos}</div>
      </div>
      <div class="pm-stat-box">
        <div class="pm-stat-lbl">Reorder Point</div>
        <div class="pm-stat-val">${product.reorder_point}</div>
      </div>
      <div class="pm-stat-box">
        <div class="pm-stat-lbl">30d Units Sold</div>
        <div class="pm-stat-val">${units30d}</div>
      </div>
      <div class="pm-stat-box">
        <div class="pm-stat-lbl">Avg Daily Sales</div>
        <div class="pm-stat-val">${product.avg_daily_units_30d}/day</div>
      </div>
      <div class="pm-stat-box">
        <div class="pm-stat-lbl">Lead Time</div>
        <div class="pm-stat-val">${product.supplier_lead_days || 5} days</div>
      </div>
    </div>

    <div class="pm-section">
      <div class="pm-sec-title">Intelligence & Recommended Actions</div>
      ${alertHtml}
    </div>
  `;

  modal.classList.add('open');
}

function closeProductModal() {
  const modal = document.getElementById('product-modal');
  if (modal) modal.classList.remove('open');
}

// Close modal when clicking outside panel
document.addEventListener('click', (e) => {
  const modal = document.getElementById('product-modal');
  if (modal && e.target === modal) {
    closeProductModal();
  }
});


// ─── Alerts View ──────────────────────────────────────────────────────────────
let allAlerts = [];
let currentSeverity = 'all';

async function loadAlerts() {
  try {
    const data = await API.getAlerts();
    allAlerts = data.alerts;

    // Update nav badge
    const badge = document.getElementById('alert-badge');
    if (badge) badge.textContent = data.summary.critical;

    renderAlertsList(allAlerts);
  } catch (err) {
    const list = document.getElementById('alerts-list');
    if (list) list.innerHTML = `<div class="loading-cell">Error: ${err.message}</div>`;
  }
}

function renderAlertsList(alerts) {
  const list = document.getElementById('alerts-list');
  if (!list) return;

  if (alerts.length === 0) {
    list.innerHTML = `<div style="text-align:center;padding:40px;color:var(--text-muted)">✓ No alerts in this category.</div>`;
    return;
  }

  list.innerHTML = alerts.map(a => {
    const dataChips = a.data
      ? Object.entries(a.data).slice(0, 6).map(([k, v]) =>
          `<span class="data-chip">${k}: ${typeof v === 'number' ? (Number.isInteger(v) ? v : v.toFixed(2)) : v}</span>`
        ).join('')
      : '';

    const assumptions = a.assumptions
      ? `<div class="alert-assumptions">Assumptions: ${a.assumptions.join(' · ')}</div>`
      : '';

    return `
      <div class="alert-card ${a.severity}">
        <div class="alert-card-header">
          <div class="alert-sev-dot"></div>
          <div class="alert-card-title">${a.title}</div>
          <span class="alert-badge-sev ${a.severity}">${a.severity}</span>
        </div>
        <div class="alert-card-body">${a.description}</div>
        ${dataChips ? `<div class="alert-data-chips">${dataChips}</div>` : ''}
        <div class="alert-rec-box">💡 ${a.recommendation}</div>
        ${assumptions}
      </div>
    `;
  }).join('');
}

function filterAlertsBySev(sev) {
  currentSeverity = sev;
  document.querySelectorAll('.filter-pill').forEach(b => {
    b.classList.toggle('active', b.dataset.sev === sev);
  });
  const shown = sev === 'all' ? allAlerts : allAlerts.filter(a => a.severity === sev);
  renderAlertsList(shown);
}

// ─── Date display ─────────────────────────────────────────────────────────────
function updateDateChip() {
  const el = document.getElementById('date-chip');
  if (!el) return;
  const now = new Date();
  el.textContent = now.toLocaleDateString('en-IN', {
    weekday: 'short', day: 'numeric', month: 'short', year: 'numeric',
  });
}

// ─── Refresh ──────────────────────────────────────────────────────────────────
async function refreshCurrentView() {
  const activeNav = document.querySelector('.nav-item.active');
  const viewId = activeNav?.dataset.view || 'dashboard';

  const btn = document.getElementById('btn-refresh');
  if (btn) btn.classList.add('spinning');

  try {
    if (viewId === 'dashboard') await loadDashboard();
    if (viewId === 'products')  await loadProducts();
    if (viewId === 'alerts')    await loadAlerts();
  } finally {
    if (btn) btn.classList.remove('spinning');
  }
}

// ─── Bootstrap ───────────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  updateDateChip();
  initCopilot();

  // Nav click routing
  document.querySelectorAll('.nav-item[data-view]').forEach(item => {
    item.addEventListener('click', (e) => {
      e.preventDefault();
      showView(item.dataset.view);
    });
  });

  // Card link routing
  document.querySelectorAll('.card-link[data-view]').forEach(link => {
    link.addEventListener('click', (e) => {
      e.preventDefault();
      showView(link.dataset.view);
    });
  });

  // Refresh button
  const refreshBtn = document.getElementById('btn-refresh');
  if (refreshBtn) refreshBtn.addEventListener('click', refreshCurrentView);

  // Product filters
  ['filter-status', 'filter-category', 'filter-search'].forEach(id => {
    const el = document.getElementById(id);
    if (el) {
      el.addEventListener(id === 'filter-search' ? 'input' : 'change', applyProductFilters);
    }
  });

  // Alert severity pills
  document.querySelectorAll('.filter-pill[data-sev]').forEach(btn => {
    btn.addEventListener('click', () => filterAlertsBySev(btn.dataset.sev));
  });

  // Initial load
  showView('dashboard');
  loadDashboard();

  // Also prefetch alert count for badge
  API.getAlerts().then(data => {
    const badge = document.getElementById('alert-badge');
    if (badge) badge.textContent = data.summary.critical;
  }).catch(() => {});
});
