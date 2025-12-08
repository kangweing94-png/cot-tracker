import streamlit as st
import pandas as pd
import numpy as np
import datetime
import plotly.express as px
import plotly.graph_objects as go
import yfinance as yf

# ==========================================
# 1. 页面配置
# ==========================================
st.set_page_config(page_title="Real-Time Institutional Dashboard", layout="wide", page_icon="📡")

st.markdown("""
<style>
    .stApp { background-color: #0b0e11; color: #e0e0e0; }
    .metric-card {
        background-color: #161b22;
        border: 1px solid #30363d;
        padding: 15px;
        border-radius: 8px;
        margin-bottom: 5px;
    }
    .card-header { font-size: 13px; color: #8b949e; text-transform: uppercase; letter-spacing: 0.5px; }
    .card-value { font-size: 26px; font-weight: 700; color: #f0f6fc; font-family: 'Roboto Mono', monospace; margin: 5px 0; }
    .card-delta { font-size: 13px; font-weight: 500; }
    .delta-pos { color: #3fb950; }
    .delta-neg { color: #f85149; }
    .sub-text { font-size: 11px; color: #666; margin-top: 5px; }
</style>
""", unsafe_allow_html=True)

# ==========================================
# 2. 真实数据引擎 (修复版：缓存函数移至类外)
# ==========================================

# --- 关键修改：将带有 @st.cache_data 的函数定义在 Class 外面 ---
# 这样 Streamlit 就不会尝试去 Hash 'self'，从而解决了 UnhashableParamError

@st.cache_data(ttl=300) # 缓存5分钟
def fetch_yahoo_data(ticker):
    """独立函数：获取 Yahoo Finance 数据"""
    try:
        # 下载最近3个月的数据
        df = yf.download(ticker, period="3mo", interval="1d", progress=False)
        if df.empty:
            return None
        
        # yfinance 新版本返回的数据结构可能包含多级索引，这里做一下处理
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)

        # 获取最新价和涨跌幅
        latest_price = float(df['Close'].iloc[-1])
        prev_price = float(df['Close'].iloc[-2])
        change = latest_price - prev_price
        pct_change = (change / prev_price) * 100
        
        return {
            "latest": latest_price,
            "change": change,
            "pct": pct_change,
            "history": df.reset_index()
        }
    except Exception as e:
        print(f"Error fetching {ticker}: {e}")
        return None

@st.cache_data(ttl=86400) # 缓存24小时
def fetch_cftc_data():
    """独立函数：获取 CFTC 数据"""
    cftc_url = "https://www.cftc.gov/dea/newcot/deacmesf.txt"
    try:
        df = pd.read_csv(cftc_url, header=None, low_memory=False)
        
        assets = {
            "GOLD": "GOLD - COMMODITY EXCHANGE INC.",
            "EURO": "EURO FX - CHICAGO MERCANTILE EXCHANGE",
            "GBP": "BRITISH POUND - CHICAGO MERCANTILE EXCHANGE"
        }
        
        results = []
        for short_name, cftc_name in assets.items():
            # 模糊匹配名称
            row = df[df[0].str.contains(short_name, case=False, na=False)]
            
            if not row.empty:
                data = row.iloc[0]
                date_str = data[2]
                
                # 在 Legacy 报告中: Col 8 = Non-Comm Long, Col 9 = Non-Comm Short
                long_pos = float(data[8])
                short_pos = float(data[9])
                net_pos = long_pos - short_pos
                
                results.append({
                    "name": short_name,
                    "net": net_pos,
                    "date": date_str,
                    "long": long_pos,
                    "short": short_pos
                })
        return results
    except Exception as e:
        return None

# --- DataEngine 类现在只负责调用上面的独立函数 ---
class RealDataEngine:
    def __init__(self):
        pass

    def get_market_price(self, ticker):
        return fetch_yahoo_data(ticker)

    def get_cftc_data(self):
        return fetch_cftc_data()

engine = RealDataEngine()

# ==========================================
# 3. 前端 UI 渲染
# ==========================================

st.title("📡 Real-World Live Market Dashboard")
st.caption(f"Connected to: Yahoo Finance & CFTC.gov | Time Zone: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}")

# --- 1. Real Market Prices (Yahoo Finance) ---
st.markdown("### 1. Real-Time Market Prices (Yahoo Finance)")
st.markdown("直接获取全球市场实时报价 (Live Quote)。")

tickers = [
    {"name": "Gold (XAU/USD)", "symbol": "GC=F", "format": "${:,.2f}"},
    {"name": "Euro (EUR/USD)", "symbol": "EURUSD=X", "format": "{:.4f}"},
    {"name": "GBP (GBP/USD)", "symbol": "GBPUSD=X", "format": "{:.4f}"},
    {"name": "Dollar Index (DXY)", "symbol": "DX-Y.NYB", "format": "{:.2f}"},
]

cols = st.columns(4)

for i, t in enumerate(tickers):
    data = engine.get_market_price(t['symbol'])
    with cols[i]:
        if data:
            color_class = "delta-pos" if data['change'] >= 0 else "delta-neg"
            arrow = "▲" if data['change'] >= 0 else "▼"
            
            st.markdown(f"""
            <div class="metric-card">
                <div class="card-header">{t['name']}</div>
                <div class="card-value" style="color: {'#3fb950' if data['change']>=0 else '#f85149'};">
                    {t['format'].format(data['latest'])}
                </div>
                <div class="card-delta {color_class}">
                    {arrow} {t['format'].format(data['change'])} ({data['pct']:.2f}%)
                </div>
            </div>
            """, unsafe_allow_html=True)
            
            # 绘制真实走势图
            fig = px.area(data['history'], x='Date', y='Close', height=100)
            fig.update_layout(
                template="plotly_dark", 
                margin=dict(l=0, r=0, t=0, b=0),
                xaxis=dict(visible=False), yaxis=dict(visible=False),
                showlegend=False
            )
            line_color = '#3fb950' if data['change'] >= 0 else '#f85149'
            fig.update_traces(line_color=line_color) 
            
            st.plotly_chart(fig, use_container_width=True, config={'staticPlot': True})
        else:
            st.warning(f"{t['name']} data unavailable")

st.markdown("---")

# --- 2. Real CFTC COT Data (Live Scrape) ---
st.markdown("### 2. CFTC COT Data (Real Scrape)")

cftc_data = engine.get_cftc_data()

if cftc_data:
    c_cols = st.columns(3)
    for i, item in enumerate(cftc_data):
        with c_cols[i]:
            st.markdown(f"""
            <div class="metric-card">
                <div class="card-header">{item['name']} Futures (Net Non-Comm)</div>
                <div class="card-value">{int(item['net']):,}</div>
                <div class="sub-text">
                    Longs: {int(item['long']):,} | Shorts: {int(item['short']):,} <br>
                    Report Date: {item['date']}
                </div>
            </div>
            """, unsafe_allow_html=True)
else:
    st.warning("⚠️ 无法连接到 CFTC 官网获取实时 COT 数据。请检查网络或 CFTC 是否正在维护。")

st.markdown("---")

# --- 3. Real Macro Proxies ---
st.markdown("### 3. Macro Market Proxies (Live)")

macro_tickers = [
    {"name": "US 10Y Yield (通胀预期)", "symbol": "^TNX"},
    {"name": "Crude Oil (能源)", "symbol": "CL=F"},
    {"name": "VIX (恐慌指数)", "symbol": "^VIX"},
]

m_cols = st.columns(3)
for i, t in enumerate(macro_tickers):
    data = engine.get_market_price(t['symbol'])
    with m_cols[i]:
        if data:
            st.markdown(f"**{t['name']}**: {data['latest']:.2f}")
            fig = px.line(data['history'], x='Date', y='Close', height=150)
            fig.update_layout(template="plotly_dark", margin=dict(l=0,r=0,t=0,b=0), xaxis_title=None, yaxis_title=None)
            st.plotly_chart(fig, use_container_width=True)

# --- 4. Fed News ---
st.markdown("---")
st.markdown("### 4. Fed Speeches & Calendar")
st.info("💡 Real-time Fed Analysis requires external news API.")
st.markdown("""
* [Federal Reserve Press Releases](https://www.federalreserve.gov/newsevents/pressreleases.htm) 🔗
* [CME FedWatch Tool](https://www.cmegroup.com/markets/interest-rates/cme-fedwatch-tool.html) 🔗
""")
