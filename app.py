import streamlit as st
import pandas as pd
import numpy as np
import datetime
import yfinance as yf
import feedparser
from fredapi import Fred
import requests
import io

# ==========================================
# 1. 核心配置
# ==========================================
st.set_page_config(page_title="Institutional Dashboard V11", layout="wide", page_icon="🏦")

# API Keys & Config
FRED_KEY = '476ef255e486edb3fdbf71115caa2857'
headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
}

st.markdown("""
<style>
    .stApp { background-color: #0e1117; color: #e0e0e0; font-family: 'Segoe UI', sans-serif; }
    
    /* 卡片样式 */
    .metric-card {
        background-color: #161b22;
        border: 1px solid #30363d;
        padding: 20px;
        border-radius: 8px;
        margin-bottom: 15px;
    }
    .metric-label { font-size: 13px; color: #8b949e; text-transform: uppercase; letter-spacing: 1px; }
    .metric-val { font-size: 28px; font-weight: 700; color: #f0f6fc; font-family: 'Roboto Mono', monospace; margin: 8px 0; }
    .metric-sub { font-size: 11px; display: flex; justify-content: space-between; color: #666; }
    
    /* 颜色标识 */
    .status-real { color: #3fb950; font-weight: bold; }
    .status-sim { color: #d29922; font-weight: bold; }
    .pos { color: #3fb950; }
    .neg { color: #f85149; }

    /* Fed 新闻流 */
    .fed-card {
        border-left: 3px solid #238636;
        background-color: #1c2128;
        padding: 12px;
        margin-bottom: 8px;
        border-radius: 0 4px 4px 0;
    }
    .news-link { text-decoration: none; color: #58a6ff; font-weight: 600; font-size: 14px; }
    .news-meta { font-size: 11px; color: #8b949e; margin-top: 4px; }
</style>
""", unsafe_allow_html=True)

# ==========================================
# 2. 双保险数据引擎 (Hybrid Engine)
# ==========================================

class HybridDataEngine:
    def __init__(self):
        pass

    # --- 方案 A: 尝试抓取真实 CFTC 数据 ---
    def _fetch_real_cftc(self):
        url = "https://www.cftc.gov/dea/newcot/deacmesf.txt"
        try:
            # 设置 3 秒超时，避免卡住
            response = requests.get(url, headers=headers, timeout=3)
            if response.status_code != 200: return None
            
            csv_data = io.StringIO(response.text)
            df = pd.read_csv(csv_data, header=None, low_memory=False)
            
            targets = {
                "GOLD": "GOLD - COMMODITY EXCHANGE INC.",
                "EURO": "EURO FX - CHICAGO MERCANTILE EXCHANGE",
                "GBP": "BRITISH POUND - CHICAGO MERCANTILE EXCHANGE"
            }
            
            parsed = []
            for key, long_name in targets.items():
                row = df[df[0].str.contains(key, case=False, na=False)]
                if not row.empty:
                    data = row.iloc[0]
                    parsed.append({
                        "asset": key,
                        "net": float(data[8]) - float(data[9]),
                        "date": data[2],
                        "source_type": "REAL"
                    })
            return parsed
        except:
            return None

    # --- 方案 B: 生成模拟数据 (你提供的算法) ---
    def _generate_mock_cftc(self):
        # 模拟日期：今天
        sim_date = datetime.date.today().strftime("%Y-%m-%d")
        
        # 基于真实市场范围的随机波动
        return [
            {
                "asset": "GOLD",
                "net": 195000 + np.random.randint(-5000, 5000),
                "date": sim_date,
                "source_type": "SIMULATED"
            },
            {
                "asset": "EURO",
                "net": -22000 + np.random.randint(-2000, 2000),
                "date": sim_date,
                "source_type": "SIMULATED"
            },
            {
                "asset": "GBP",
                "net": 12000 + np.random.randint(-1000, 1000),
                "date": sim_date,
                "source_type": "SIMULATED"
            }
        ]

    # --- 主调用：智能切换 ---
    def get_cot_data(self):
        # 1. 优先尝试真实数据
        data = self._fetch_real_cftc()
        if data:
            return data
        
        # 2. 失败则启用模拟数据
        return self._generate_mock_cftc()

# 初始化引擎
hybrid_engine = HybridDataEngine()

# ==========================================
# 3. 其他数据函数 (Yahoo, FRED, RSS)
# ==========================================

@st.cache_data(ttl=60)
def fetch_live_prices():
    tickers = {
        "Gold Spot": "XAUUSD=X",
        "DXY Index": "DX-Y.NYB",
        "EUR/USD": "EURUSD=X",
        "GBP/USD": "GBPUSD=X"
    }
    res = []
    for name, sym in tickers.items():
        try:
            t = yf.Ticker(sym)
            curr = t.fast_info['last_price']
            prev = t.fast_info['previous_close']
            chg_pct = ((curr - prev)/prev)*100
            res.append({"name": name, "price": curr, "pct": chg_pct})
        except:
            pass
    return res

@st.cache_data(ttl=3600)
def fetch_fred_official():
    try:
        fred = Fred(api_key=FRED_KEY)
        indicators = [
            {"name": "Non-Farm Payrolls", "id": "PAYEMS", "change": True},
            {"name": "Unemployment Rate", "id": "UNRATE", "change": False},
            {"name": "CPI (YoY)", "id": "CPIAUCSL", "change": "yoy"},
            {"name": "Fed Funds Rate", "id": "FEDFUNDS", "change": False},
        ]
        rows = []
        for ind in indicators:
            series = fred.get_series(ind['id'], sort_order='desc', limit=13)
            if series.empty: continue
            
            val = series.iloc[0]
            date = series.index[0].strftime('%Y-%m-%d')
            disp = ""
            
            if ind['change'] == True:
                diff = (val - series.iloc[1]) * 1000
                disp = f"{int(diff):+,}"
            elif ind['change'] == "yoy":
                yoy = ((val - series.iloc[12])/series.iloc[12])*100
                disp = f"{yoy:.1f}%"
            else:
                disp = f"{val:.2f}%"
                
            rows.append({"Event": ind['name'], "Date": date, "Actual": disp, "Source": "FRED Official"})
        return pd.DataFrame(rows)
    except:
        return pd.DataFrame()

@st.cache_data(ttl=300)
def fetch_fed_rss():
    url = "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=10000664"
    try:
        feed = feedparser.parse(url)
        return feed.entries[:6]
    except:
        return []

# ==========================================
# 4. 前端 UI 渲染
# ==========================================

st.title("🏛️ Institutional Dashboard V11 (Hybrid)")
st.caption(f"System: Live Production | Time: {datetime.datetime.now().strftime('%H:%M:%S')}")

# --- 1. Real-Time Market ---
st.markdown("### 1. Real-Time Market Overview")
prices = fetch_live_prices()
m_cols = st.columns(4)
if prices:
    for i, p in enumerate(prices):
        with m_cols[i]:
            color = "pos" if p['pct']>=0 else "neg"
            fmt_p = f"${p['price']:,.2f}" if "Gold" in p['name'] else f"{p['price']:.4f}"
            if "Index" in p['name']: fmt_p = f"{p['price']:.2f}"
            
            st.markdown(f"""
            <div class="metric-card">
                <div class="metric-label">{p['name']}</div>
                <div class="metric-val {color}">{fmt_p}</div>
                <div class="metric-sub">
                    <span class="{color}">{p['pct']:+.2f}%</span>
                    <span>Live</span>
                </div>
            </div>
            """, unsafe_allow_html=True)

st.markdown("---")

# --- 2. Smart Money (Hybrid Engine) ---
st.markdown("### 2. Smart Money Positioning (COT)")
st.caption("Engine: Hybrid. Tries to fetch Real CFTC data first; auto-switches to Simulation if government server blocks connection.")

cot_data = hybrid_engine.get_cot_data()

if cot_data:
    c1, c2, c3 = st.columns(3)
    for item in cot_data:
        target = c1 if "EURO" in item['asset'] else c2 if "GBP" in item['asset'] else c3
        
        # 状态指示器
        if item['source_type'] == "REAL":
            status_html = '<span class="status-real">✅ Real Data (CFTC.gov)</span>'
        else:
            status_html = '<span class="status-sim">⚠️ Simulated (Mock)</span>'
            
        with target:
            st.markdown(f"""
            <div class="metric-card">
                <div class="metric-label">{item['asset']} Futures</div>
                <div class="metric-val">{int(item['net']):,}</div>
                <div class="metric-sub">
                    <span>Date: {item['date']}</span>
                    {status_html}
                </div>
            </div>
            """, unsafe_allow_html=True)

st.markdown("---")

# --- 3. Macro Matrix (FRED) ---
st.markdown("### 3. Macroeconomic Matrix (Official)")
macro_df = fetch_fred_official()

if not macro_df.empty:
    st.dataframe(
        macro_df,
        use_container_width=True,
        hide_index=True
    )
else:
    st.warning("FRED Data unavailable (Check API Key).")

st.markdown("---")

# --- 4. Fed Radar (RSS) ---
st.markdown("### 4. 🦅 Fed & Economic Radar (RSS)")
news = fetch_fed_rss()
n_cols = st.columns(2)

if news:
    # Split news into two columns
    mid = len(news)//2
    left_news = news[:mid]
    right_news = news[mid:]
    
    with n_cols[0]:
        for n in left_news:
            st.markdown(f'<div class="fed-card"><a href="{n.link}" target="_blank" class="news-link">{n.title}</a><div class="news-meta">{n.published}</div></div>', unsafe_allow_html=True)
    with n_cols[1]:
        for n in right_news:
            st.markdown(f'<div class="fed-card"><a href="{n.link}" target="_blank" class="news-link">{n.title}</a><div class="news-meta">{n.published}</div></div>', unsafe_allow_html=True)
else:
    st.info("No news feed currently available.")
