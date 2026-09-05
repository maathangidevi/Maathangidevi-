TRACK_ID=PS03

# RetailIQ – Retail Sales & Inventory Copilot

RetailIQ is an AI-powered retail intelligence and copilot application built for small store managers. It bridges raw point-of-sale sales data and inventory levels with actionable analytics and conversational AI to prevent stock-outs, identify slow-moving inventory, detect sales anomalies, and optimize working capital.

---

## 🌟 Key Features

1. **Decision-Focused Dashboard ("Attention Today")**
   - Highlights top critical inventory risks (e.g. products with days of stock less than supplier lead time).
   - Shows live 30-day KPIs: total revenue, unit sales, gross margin %, low-stock count, overstock count, and active alerts.
   - Interactive 90-day daily sales revenue trend chart powered by Chart.js.

2. **Inventory Intelligence (Products Catalogue)**
   - Real-time instant search by SKU or product name.
   - Category filtering (Electronics, Clothing, FMCG, Personal Care, Stationery, Home).
   - Inventory status filtering (*Healthy*, *Low Stock*, *Critical*, *Overstock*).
   - Sortable columns: Stock level, 30d Units Sold, Avg Daily Velocity, Days of Stock Remaining.
   - Product Detail Modal: Click any product to view comprehensive stock status, supplier lead time, reorder point, active alerts, and recommended actions.

3. **Prioritised Alerts Engine**
   - **Critical**: Severe stock-out risks where stock will deplete before a supplier reorder can arrive.
   - **Warning**: Overstocked items locking up working capital, or sudden sales drop anomalies ($z < -1.8$).
   - **Info**: High sales spike anomalies ($z > 2.0$) and slow-moving SKUs.
   - Every alert includes exact data metrics, rationale, assumptions, and actionable recommendations.

4. **AI Copilot (Gemini API Integration)**
   - Plain language Q&A grounded strictly in deterministic analytics data.
   - Cites exact numeric figures and states operational assumptions.
   - Returns explicit "Insufficient data" responses when queries cannot be answered by store analytics context.
   - Robust fallback mode: operates deterministically if `GEMINI_API_KEY` is not configured.

---

## 🏗️ Architecture & Stack

```
RetailIQ/
├── app.py                      ← Single entry point (python app.py)
├── requirements.txt            ← Python 3.11 dependencies
├── README.md                   ← Project documentation (TRACK_ID=PS03)
├── .gitignore                  ← Git exclusions (.env, __pycache__, venv)
├── .env.example                ← Environment configuration template
│
├── backend/
│   ├── server.py               ← FastAPI server & REST API endpoints
│   ├── data/
│   │   ├── seed.py             ← Deterministic sample dataset (30 SKUs × 90d sales)
│   │   └── store.py            ← In-memory thread-safe data store
│   ├── analytics/
│   │   ├── inventory.py        ← Stockout risk, overstock, slow-mover calculations
│   │   ├── sales.py            ← Z-score anomaly detection, MoM %, aggregations
│   │   └── alerts.py           ← Prioritised alert generator
│   └── copilot/
│       ├── context.py          ← Structured context builder
│       └── gemini.py           ← Gemini API client with model failover & fallback
│
└── frontend/
    ├── index.html              ← Single Page Application (SPA) shell
    ├── css/style.css           ← Dark mode glassmorphism design system
    └── js/
        ├── api.js              ← REST API fetch utilities
        ├── dashboard.js        ← Dashboard KPI cards & Chart.js rendering
        ├── copilot.js          ← AI Copilot chat interface
        └── app.js              ← Router, product table, filters & modal
```

---

## ⚡ Quick Start & Installation

### Prerequisites
- Python 3.11+
- Virtual Environment (recommended)

### 1. Clone & Setup

```bash
cd RetailIQ
python -m venv venv
# On Windows:
venv\Scripts\activate
# On macOS/Linux:
source venv/bin/activate
```

### 2. Install Dependencies

```bash
pip install -r requirements.txt
```

### 3. Configure Environment (Optional for AI features)

Copy `.env.example` to `.env`:
```bash
cp .env.example .env
```

Add your Gemini API key in `.env`:
```env
GEMINI_API_KEY=your_actual_gemini_api_key_here
```
*(Note: If `GEMINI_API_KEY` is omitted or left empty, RetailIQ automatically runs in deterministic fallback mode without crashing).*

### 4. Launch Application

Run the single entry point command:
```bash
python app.py
```

Open your web browser and navigate to:
**`http://localhost:8000`**

---

## 🔌 API Endpoints

| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `GET` | `/` | Serves the single-page web app |
| `GET` | `/api/health` | Service status, total products & sales records |
| `GET` | `/api/dashboard` | Dashboard KPIs, top products, category breakdown & 90d sales series |
| `GET` | `/api/products` | Enriched product catalogue with stock status, days of stock & filters |
| `GET` | `/api/sales` | Daily sales series, period aggregations & anomaly detection |
| `GET` | `/api/alerts` | Prioritised alert list with data, assumptions & recommendations |
| `POST` | `/api/copilot` | AI Copilot Q&A (Accepts `{"question": "..."}`) |

---

## 📊 Sample Data Description

RetailIQ includes a deterministic, reproducible sample dataset (seed = 42) representing 90 days of store activity:
- **30 Products (SKUs)** across 6 core retail categories: Electronics, Clothing, FMCG, Personal Care, Stationery, Home.
- **2,700 Daily Sales Records**: 90 days of daily sales for every product with realistic demand variation and weekend seasonality.
- **Baked-in Operational Scenarios**:
  - `P001 Wireless Earbuds Pro`: Critical stockout risk (1.6 days of stock left vs 5 days supplier lead time).
  - `P010 Winter Hoodie`: Overstock scenario (420 units in stock, 133 days of inventory).
  - `P003 Mechanical Keyboard`: Sudden demand drop anomaly detected via Z-score analysis.

---

## 📹 Demo Video

[Link to Demo Video / Placeholder]
*(Insert link to RetailIQ walkthrough video here)*
