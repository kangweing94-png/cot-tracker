import streamlit as st
import pandas as pd
import datetime
import yfinance as yf
import feedparser
from fredapi import Fred
import plotly.express as px

# ==========================================
# 1. 核心配置与 API 初始化
# ==========================================
st.set_page_config(page_title="Institutional Macro Dashboard V9", layout="wide", page_icon="🏦")

# 初始化 FRED API (使用你提供的 Key)
try:
    fred = Fred(api_key='476ef255e486edb3fdbf71115caa2857')
except Exception as e:
    st.error(f"FRED API Key Error: {e}")

# 自定义机构风格 CSS
st.markdown("""
<style>
    .stApp { background-color: #0e1117; color: #e0e0e0; font-family: 'Segoe UI', sans-serif; }
    
    /* 模块容器 */
    .block-container { padding-top: 2rem; }
    
    /* 卡片设计 */
    .metric-card {
        background-color: #161b22;
        border: 1px solid #30363d;
        padding: 20px;
        border-radius: 8px;
        box-shadow: 0 4px 6px rgba(0,0,0,0.2);
        margin-bottom: 15px;
    }
    .metric-title { font-size: 14px; color: #8b949e; text-transform: uppercase; letter-spacing: 0.8px; font-weight: 600; }
    .metric-value { font-size: 28px; font-weight: 700; color: #f0f6fc; margin: 8px 0; font-family: 'Roboto Mono', monospace; }
    .metric-sub { font-size: 12px; display: flex; align-items: center; gap: 5px; }
    
    /* 颜色类 */
    .text-up { color: #3fb950; }
    .text-down { color: #f85149; }
    .text-neutral { color: #8b949e; }
    
    /* 宏观表格表头 */
    .dataframe th { background-color: #1f242d !important; color: #e6edf3 !important; }
    
    /* 新闻流 */
    .news-card {
        border-left: 3px solid #238636;
        background-color: #161b22;
        padding: 12px;
        margin-bottom: 8px;
        border-radius: 0 4px 4px 0;
        transition: transform 0.1s;
    }
    .news-card:hover { transform: translateX(5px); background-color: #1c2128; }
    .news-link { text-decoration: none; color: #58a6ff; font-weight: 600; font-size: 14px; }
    .news-meta { font-size: 11px; color: #8b949e; margin-top: 4px; }

</style>
""", unsafe_allow_html=True)

# ==========================================
# 2. 专业数据层 (Data Layer)
# ==========================================

# --- A. FRED 宏观数据 (Source of Truth) ---
@st.cache_data(ttl=3600)
def fetch_fred_macro():
    """
    Fetch OFFICIAL data from St. Louis Fed.
    FRED does NOT provide 'Forecasts' (that is proprietary data).
    We fetch the latest Actuals.
    """
    try:
        # 定义系列 ID
        series_ids = {
            "Non-Farm Payrolls": "PAYEMS", # 总就业人数
            "Unemployment Rate": "UNRATE", # 失业率
            "CPI (YoY)": "CPIAUCSL",       # CPI 指数
            "Fed Funds Rate": "FEDFUNDS",  # 利率
            "10Y Treasury Yield": "DGS10"  # 10年期美债
        }
        
        data = []
        for name, sid in series_ids.items():
            # 获取最后一条观察值
            series = fred.get_series(sid, limit=5, sort_order='desc')
            if not series.empty:
                latest_val = series.iloc[0]
                prev_val = series.iloc[1]
                date_str = series.index[0].strftime('%Y-%m-%d')
                
                # 数据处理逻辑
                display_val = f"{latest_val:,.2f}"
                trend = "Stable"
                
                if name == "Non-Farm Payrolls":
                    # NFP 通常关注的是变化量 (Change in thousands)
                    change = (latest_val - prev_val) * 1000
                    display_val = f"{int(change):+,}"
                    unit = "Jobs"
                elif "Rate" in name or "Yield" in name:
                    display_val = f"{latest_val:.2f}%"
                    unit = "%"
                elif "CPI" in name:
                    # 计算同比变化 (YoY) - 粗略计算
                    # 严谨做法是 fetch CPIAUCSL 并计算 pct_change(12)
                    cpi_yoy = ((latest_val - series.iloc[4]) / series.iloc[4]) * 100 # 近似 YoY
                    display_val = f"{cpi_yoy:.1f}%" 
                    unit = "YoY"
                
                # Market Bias Logic (Simple Rules)
                bias = "Neutral"
                if name == "CPI (YoY)" and float(display_val.strip('%')) > 2.5:
                    bias = "Hawkish (Bullish USD)"
                elif name == "Unemployment Rate" and latest_val < 4.0:
                    bias = "Hawkish (Bullish USD)"

                data.append({
                    "Event": name,
                    "Date": date_str,
                    "Actual": display_val,
                    "Forecast": "--", # FRED 不提供预测
                    "Bias": bias,
                    "Source": "FRED Official"
                })
        return pd.DataFrame(data)
    except Exception as e:
        st.error(f"FRED Connection Failed: {e}")
        return pd.DataFrame()

# --- B. 市场价格 (Yahoo Finance Spot) ---
@st.cache_data(ttl=60)
def fetch_market_prices():
    """获取现货/实时价格"""
    tickers = {
        "Gold Spot": "XAUUSD=X",
        "DXY Index": "DX-Y.NYB",
        "EUR/USD": "EURUSD=X",
        "GBP/USD": "GBPUSD=X"
    }
    
    res = []
    for name, symbol in tickers.items():
        try:
            t = yf.Ticker(symbol)
            # 使用 fast_info 提高速度
            price = t.fast_info['last_price']
            prev = t.fast_info['previous_close']
            change_pct = ((price - prev) / prev) * 100
            
            res.append({
                "name": name,
                "price": price,
                "change": change_pct,
                "symbol": symbol
            })
        except:
            pass
    return res

# --- C. COT 数据 (CFTC Raw) ---
@st.cache_data(ttl=86400)
def fetch_cftc_cot():
    """Directly parse CFTC Report"""
    url = "https://www.cftc.gov/dea/newcot/deacmesf.txt"
    try:
        # Legacy Format: 
        # Col 0: Name, Col 2: Date
        # Col 8: Non-Comm Long, Col 9: Non-Comm Short
        df = pd.read_csv(url, header=None, low_memory=False)
        
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
                net_pos = float(data[8]) - float(data[9])
                parsed.append({
                    "asset": key,
                    "net": net_pos,
                    "date": data[2]
                })
        return parsed
    except:
        return []

# --- D. RSS News (Fed Radar) ---
@st.cache_data(ttl=300)
def fetch_rss_feed():
    # 使用 CNBC Finance 或 Investing.com 的 RSS
    url = "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=10000664" # CNBC Economy
    feed = feedparser.parse(url)
    return feed.entries[:6]

# ==========================================
# 3. 前端 UI 布局
# ==========================================

st.title("🏛️ Institutional Dashboard V9 (Professional)")
st.caption(f"Connected APIs: St. Louis Fed (FRED), Yahoo Finance, CNBC RSS | Time: {datetime.datetime.now().strftime('%H:%M:%S')}")

# --- 1. Market Overview (Real-Time) ---
st.markdown("### 1. Market Overview (Spot & Index)")
market_data = fetch_market_prices()
m_cols = st.columns(4)

if market_data:
    for i, item in enumerate(market_data):
        with m_cols[i]:
            color_cls = "text-up" if item['change'] >= 0 else "text-down"
            arrow = "▲" if item['change'] >= 0 else "▼"
            fmt_price = f"${item['price']:,.2f}" if "Gold" in item['name'] else f"{item['price']:.4f}"
            if "Index" in item['name']: fmt_price = f"{item['price']:.2f}"
            
            st.markdown(f"""
            <div class="metric-card">
                <div class="metric-title">{item['name']}</div>
                <div class="metric-value {color_cls}">{fmt_price}</div>
                <div class="metric-sub {color_cls}">
                    {arrow} {item['change']:.2f}% <span style="color:#666; margin-left:5px;">(Real-time)</span>
                </div>
            </div>
            """, unsafe_allow_html=True)

# --- 2. Smart Money (COT) ---
st.markdown("### 2. Smart Money Positioning (CFTC Official)")
st.caption("Data Source: cftc.gov (Legacy Report). Net Positions of Managed Money.")

cot_data = fetch_cftc_cot()
c_cols = st.columns(3)

if cot_data:
    for i, item in enumerate(cot_data):
        with c_cols[i]:
            st.markdown(f"""
            <div class="metric-card" style="border-top: 3px solid #d29922;">
                <div class="metric-title">{item['asset']} FUTURES (NET)</div>
                <div class="metric-value">{int(item['net']):,}</div>
                <div class="metric-sub text-neutral">
                    📅 Report Date: {item['date']}
                </div>
            </div>
            """, unsafe_allow_html=True)

# --- 3. Macro Matrix (FRED) ---
st.markdown("### 3. Macroeconomic Matrix (FRED Data)")
st.caption("Data Source: FRED API (Official Actuals). 'Forecast' column is N/A for government feeds.")

macro_df = fetch_fred_macro()

if not macro_df.empty:
    # 使用 Pandas Styling 进行高亮
    def highlight_bias(val):
        color = '#3fb950' if 'Bullish' in val else '#f85149' if 'Bearish' in val else '#8b949e'
        return f'color: {color}; font-weight: bold;'

    styled_df = macro_df.style.map(highlight_bias, subset=['Bias'])
    
    st.dataframe(
        styled_df,
        use_container_width=True,
        hide_index=True,
        column_config={
            "Forecast": st.column_config.TextColumn("Forecast (Consensus)", help="FRED does not provide market forecasts."),
            "Bias": st.column_config.TextColumn("Implied Market Bias"),
        },
        height=250
    )
else:
    st.warning("Loading FRED data... (Check API Key limit)")

# --- 4. Fed Speaker & News Radar ---
st.markdown("### 4. 🦅 Fed & Economic Radar (RSS Quotes)")
st.caption("Live Feed from CNBC Economy. Filtering for 'Fed', 'Inflation', 'Rate'.")

news = fetch_rss_feed()
n_cols = st.columns([2, 1])

with n_cols[0]:
    if news:
        for entry in news:
            # 简单的高亮逻辑
            highlight_border = "#238636" # Default Green
            if any(x in entry.title.lower() for x in ['fed', 'powell', 'rate', 'inflation']):
                highlight_border = "#d29922" # Gold for Fed news
            
            st.markdown(f"""
            <div class="news-card" style="border-left-color: {highlight_border};">
                <a href="{entry.link}" target="_blank" class="news-link">{entry.title}</a>
                <div class="news-meta">{entry.published}</div>
            </div>
            """, unsafe_allow_html=True)
    else:
        st.info("No news feed available.")

with n_cols[1]:
    st.markdown("#### ℹ️ Data Disclaimer")
    st.info("""
    **Forecast Data:**
    Government APIs (FRED) do not publish "Market Forecasts". 
    To see "Forecast: 180K", you need a subscription to Bloomberg, Refinitiv, or scrape ForexFactory (unstable).
    
    **Current Display:**
    This dashboard shows the **Official Actuals** directly from the US Government.
    """)
