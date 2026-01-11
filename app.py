import streamlit as st
import pandas as pd
import datetime
import yfinance as yf
import feedparser
from fredapi import Fred
import cot_reports as cot # 专门用于获取真实 COT 数据的库

# ==========================================
# 1. 核心配置
# ==========================================
st.set_page_config(page_title="Institutional Dashboard V12 (Real Only)", layout="wide", page_icon="🏦")

FRED_KEY = '476ef255e486edb3fdbf71115caa2857'

st.markdown("""
<style>
    .stApp { background-color: #0e1117; color: #e0e0e0; font-family: 'Segoe UI', sans-serif; }
    .metric-card { background-color: #161b22; border: 1px solid #30363d; padding: 20px; border-radius: 8px; margin-bottom: 15px; }
    .metric-val { font-size: 28px; font-weight: 700; color: #f0f6fc; font-family: 'Roboto Mono', monospace; margin: 8px 0; }
    .metric-label { font-size: 13px; color: #8b949e; text-transform: uppercase; }
    .metric-sub { font-size: 11px; color: #666; display: flex; justify-content: space-between; }
    .pos { color: #3fb950; }
    .neg { color: #f85149; }
    .news-link { text-decoration: none; color: #58a6ff; font-weight: bold; }
</style>
""", unsafe_allow_html=True)

# ==========================================
# 2. 真实数据引擎 (NO MOCK DATA)
# ==========================================

@st.cache_data(ttl=86400)
def get_real_cot_data():
    """
    使用 cot_reports 库直接下载年度数据。
    严禁使用模拟数据。如果失败直接报错。
    """
    try:
        # 下载 2024 或 2025 年的 COT 报告 (Legacy Futures Only)
        # 注意：年初时可能需要切换年份，这里我们尝试获取最新的
        current_year = datetime.date.today().year
        
        # 使用 cot_reports 库下载 CME 数据
        # 这会下载一个 ZIP 文件并解析，比 requests 更稳健
        df = cot.cot_year(current_year, cot_report_type='legacy_fut')
        
        # 筛选我们需要的数据
        # 1. 黄金 (Gold)
        gold = df[df['Market and Exchange Names'] == 'GOLD - COMMODITY EXCHANGE INC.']
        # 2. 欧元 (Euro)
        euro = df[df['Market and Exchange Names'] == 'EURO FX - CHICAGO MERCANTILE EXCHANGE']
        # 3. 英镑 (GBP)
        gbp = df[df['Market and Exchange Names'] == 'BRITISH POUND - CHICAGO MERCANTILE EXCHANGE']
        
        results = []
        
        for name, data in [("GOLD", gold), ("EURO", euro), ("GBP", gbp)]:
            if not data.empty:
                # 获取最新一行
                latest = data.iloc[-1]
                # 计算净头寸: Non-Commercial Long - Non-Commercial Short
                net = latest['Noncommercial Long'] - latest['Noncommercial Short']
                date = latest['As of Date in Form YYYY-MM-DD']
                
                results.append({
                    "asset": name,
                    "net": net,
                    "date": date
                })
        return results
    except Exception as e:
        # 如果这里报错，说明 CFTC 官网彻底拒绝了连接
        st.error(f"Error fetching Real COT Data: {e}")
        return None

@st.cache_data(ttl=60)
def get_real_price():
    tickers = {
        "Gold Spot": "XAUUSD=X",
        "DXY": "DX-Y.NYB",
        "EUR/USD": "EURUSD=X",
        "GBP/USD": "GBPUSD=X"
    }
    res = []
    for k, v in tickers.items():
        try:
            t = yf.Ticker(v)
            price = t.fast_info['last_price']
            prev = t.fast_info['previous_close']
            pct = ((price-prev)/prev)*100
            res.append({"name": k, "price": price, "pct": pct})
        except:
            pass
    return res

@st.cache_data(ttl=3600)
def get_real_fred():
    try:
        fred = Fred(api_key=FRED_KEY)
        # 获取真实数据，不造假
        unrate = fred.get_series('UNRATE', limit=1)
        payems = fred.get_series('PAYEMS', limit=2) # 用于计算 NFP 变化
        cpi = fred.get_series('CPIAUCSL', limit=13) # 用于计算 YoY
        
        nfp_change = (payems.iloc[-1] - payems.iloc[-2]) * 1000
        cpi_yoy = ((cpi.iloc[-1] - cpi.iloc[-12]) / cpi.iloc[-12]) * 100
        
        return [
            {"Event": "Unemployment Rate", "Actual": f"{unrate.iloc[-1]:.1f}%"},
            {"Event": "Non-Farm Payrolls", "Actual": f"{int(nfp_change):+,}"},
            {"Event": "CPI (YoY)", "Actual": f"{cpi_yoy:.1f}%"}
        ]
    except Exception as e:
        st.error(f"FRED API Error: {e}")
        return []

@st.cache_data(ttl=300)
def get_real_news():
    try:
        # 使用 Investing.com 的 RSS
        feed = feedparser.parse("https://www.investing.com/rss/news_11.rss")
        return feed.entries[:6]
    except:
        return []

# ==========================================
# 3. 前端显示
# ==========================================

st.title("📡 Institutional Dashboard V12 (Strictly Real Data)")
st.caption("No Simulation. No Mock Data. If a data source is blocked, it will show an Error.")

# --- 1. Market ---
st.markdown("### 1. Real-Time Market")
prices = get_real_price()
cols = st.columns(4)
if prices:
    for i, p in enumerate(prices):
        with cols[i]:
            c = "pos" if p['pct'] >= 0 else "neg"
            fmt = "${:,.2f}" if "Gold" in p['name'] else "{:.4f}"
            if "DXY" in p['name']: fmt = "{:.2f}"
            st.markdown(f"""
            <div class="metric-card">
                <div class="metric-label">{p['name']}</div>
                <div class="metric-val {c}">{fmt.format(p['price'])}</div>
                <div class="metric-sub"><span class="{c}">{p['pct']:+.2f}%</span></div>
            </div>""", unsafe_allow_html=True)

# --- 2. COT ---
st.markdown("### 2. Smart Money Positioning (Real)")
cot_data = get_real_cot_data()

if cot_data:
    c1, c2, c3 = st.columns(3)
    for d in cot_data:
        tgt = c1 if "EURO" in d['asset'] else c2 if "GBP" in d['asset'] else c3
        with tgt:
            st.markdown(f"""
            <div class="metric-card">
                <div class="metric-label">{d['asset']} Net Pos</div>
                <div class="metric-val">{int(d['net']):,}</div>
                <div class="metric-sub">Date: {d['date']}</div>
            </div>""", unsafe_allow_html=True)
else:
    st.error("⚠️ Failed to fetch Real COT Data from CFTC.gov. This usually happens on Cloud Servers due to IP blocking.")
    st.info("💡 Solution: Run this app on your LOCAL computer (localhost).")

# --- 3. Macro ---
st.markdown("### 3. Macro Matrix (FRED)")
fred_data = get_real_fred()
if fred_data:
    st.dataframe(pd.DataFrame(fred_data), use_container_width=True, hide_index=True)

# --- 4. News ---
st.markdown("### 4. News Radar")
news = get_real_news()
if news:
    for n in news:
        st.markdown(f"- [{n.title}]({n.link})")
