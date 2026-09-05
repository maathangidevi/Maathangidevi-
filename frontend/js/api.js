/**
 * api.js – Fetch helpers for the RetailIQ backend.
 * All API calls go through these wrappers.
 */

const API_BASE = '';   // same origin

const API = {
  async get(path) {
    const res = await fetch(API_BASE + path);
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }));
      throw new Error(err.detail || `HTTP ${res.status}`);
    }
    return res.json();
  },

  async post(path, body) {
    const res = await fetch(API_BASE + path, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }));
      throw new Error(err.detail || `HTTP ${res.status}`);
    }
    return res.json();
  },

  getDashboard:   () => API.get('/api/dashboard'),
  getProducts:    (params = {}) => {
    const qs = new URLSearchParams(params).toString();
    return API.get('/api/products' + (qs ? '?' + qs : ''));
  },
  getSales:       (params = {}) => {
    const qs = new URLSearchParams(params).toString();
    return API.get('/api/sales' + (qs ? '?' + qs : ''));
  },
  getAlerts:      (severity) => API.get('/api/alerts' + (severity ? `?severity=${severity}` : '')),
  askCopilot:     (question) => API.post('/api/copilot', { question }),
  getHealth:      () => API.get('/api/health'),
};
