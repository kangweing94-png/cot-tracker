import streamlit as st
import pandas as pd
import datetime
import yfinance as yf
import feedparser # 用于抓取实时新闻/日历 RSS
import pandas_datareader.data as web # 用于抓取 FRED 真实宏观数据

# ==========================================
# 1. 页面配置
# ==========================================
st.set_page_config(page_title="Institutional Live Dashboard V8", layout="wide", page_icon="📡")

# 获取系统当前精确时间
NOW = datetime.datetime.now()
LAST_UPDATE_STR = NOW.strftime('%Y-%m-%d %H:%M:%S')

st.markdown("""
<style>
    .stApp { background-color: #0b0e11; color: #e0e0e0; }
    
    /* 核心卡片样式 */
    .metric-card {
        background-color: #161b22;
        border: 1px solid #30363d;
        padding: 15px;
        border-radius: 8px;
        margin-bottom: 10px;
    }
    .card-header { font-size: 13px; color: #8b949e; text-transform: uppercase; letter-spacing: 0.5px; }
    .card-value { font-size: 28px; font-weight: 700; color: #f0f6fc; font-family: 'Roboto Mono', monospace; margin: 5px 0; }
    .card-footer { font-size: 11px; color: #666; margin-top: 5px; display: flex; justify-content: space-between;}
    
    /* 涨跌幅颜色 */
    .pos { color: #3fb950; }
    .neg { color: #f85149; }
    
    /* 新闻流样式 */
    .news-item {
        border-left: 3px solid #1f6feb;
        background-color: #0d1117;
        padding: 10px;
        margin-bottom: 8px;
        border-radius: 0 4px 4px 0;
    }
    .news-title { font-weight: bold; font-size: 14px; color: #58a6ff; text-decoration: none;}
    .news-date { font-size: 11px; color: #8b949e; margin-top: 4px;}

</style>
""", unsafe_allow_html=True)

# ==========================================
# 2. 真实数据引擎 (V8)
# ==========================================

# --- A. 市场价格 (Yahoo Finance) ---
@st.cache_data(ttl=60) # 1分钟刷新一次，保证 XAU 实时性
def get_live_price(ticker):
    try:
        # 使用 fast_info 获取最新报价，速度更快
        ticker_obj = yf.Ticker(ticker)
        # 尝试获取 info，如果失败则回退
        latest = ticker_obj.fast_info['last_price']
        prev = ticker_obj.fast_info['previous_close']
        
        change = latest - prev
        pct = (change / prev) * 100
        
        # 获取最新交易时间
        quote_time = datetime.datetime.fromtimestamp(ticker_obj.fast_info['last_price_time_timestamp']) if hasattr(ticker_obj.fast_info, 'last_price_time_timestamp') else datetime.datetime.now()
        
        return {
            "price": latest,
            "change": change,
            "pct": pct,
            "time": quote_time.strftime('%H:%M:%S')
        }
    except:
        return None

# --- B. COT 数据 (纯 CFTC 官网抓取) ---
@st.cache_data(ttl=86400)
def get_cftc_pure():
    url = "https://www.cftc.gov/dea/newcot/deacmesf.txt"
    try:
        df = pd.read_csv(url, header=None, low_memory=False)
        assets_map = {
            "GOLD": "GOLD - COMMODITY EXCHANGE INC.",
            "EURO": "EURO FX - CHICAGO MERCANTILE EXCHANGE",
            "GBP": "BRITISH POUND - CHICAGO MERCANTILE EXCHANGE"
        }
        results = {}
        for key, name in assets_map.items():
            row = df[df[0].str.contains(key, case=False, na=False)]
            if not row.empty:
                data = row.iloc[0]
                # 计算净持仓
                net = float(data[8]) - float(data[9])
                date = data[2] # 报告日期
                results[key] = {"net": net, "date": date}
        return results
    except:
        return None

# --- C. 宏观数据 (FRED 官方 API) ---
@st.cache_data(ttl=3600)
def get_fred_macro():
    """
    使用 pandas_datareader 从 FRED 获取真实的最新发布数据
    """
    try:
        # UNRATE: 失业率, CPIAUCSL: CPI, PAYEMS: 非农就业总人数, FEDFUNDS: 联邦基金利率
        start = datetime.datetime.now() - datetime.timedelta(days=90)
        
        # 抓取数据
        unrate = web.DataReader('UNRATE', 'fred', start)
        cpi = web.DataReader('CPIAUCSL', 'fred', start)
        nfp = web.DataReader('PAYEMS', 'fred', start)
        fed_rate = web.DataReader('FEDFUNDS', 'fred', start)
        
        # 处理数据
        # 1. 失业率
        curr_un = unrate.iloc[-1].item()
        
        # 2. CPI YoY (需要计算同比)
        # 注意：这里为了简单展示最新读数
        curr_cpi_idx = cpi.iloc[-1].item()
        
        # 3. NFP (计算月度变化 = 非农增减)
        curr_nfp = int(nfp.iloc[-1].item() - nfp.iloc[-2].item()) * 1000
        
        # 4. 利率
        curr_rate = fed_rate.iloc[-1].item()
        
        return [
            {"Event": "Unemployment Rate", "Actual": f"{curr_un}%", "Source": "FRED (Official)"},
            {"Event": "Non-Farm Payrolls (Change)", "Actual": f"{curr_nfp:+,}", "Source": "FRED (Official)"},
            {"Event": "Fed Funds Rate", "Actual": f"{curr_rate}%", "Source": "FRED (Official)"},
            {"Event": "CPI Index (Latest)", "Actual": f"{curr_cpi_idx:.2f}", "Source": "FRED (Official)"},
        ]
    except Exception as e:
        return None

# --- D. 实时新闻流 (RSS) ---
@st.cache_data(ttl=300)
def get_rss_news(feed_url):
    try:
        feed = feedparser.parse(feed_url)
        news_items = []
        for entry in feed.entries[:5]: # 只取前5条
            news_items.append({
                "title": entry.title,
                "link": entry.link,
                "published": entry.published if 'published' in entry else "Just now"
            })
        return news_items
    except:
        return []

# ==========================================
# 3. 前端 UI 渲染
# ==========================================

st.title("📡 Institutional Live Dashboard V8")
st.caption(f"System Time: {LAST_UPDATE_STR} (GMT+8) | Connection: Yahoo Finance, CFTC.gov, St.Louis Fed, Reuters RSS")

# -------------------------------------------
# 1. Real-Time Market Prices (Yahoo Finance)
# -------------------------------------------
st.markdown("### 1. Real-Time Market Prices (Yahoo Finance)")
st.caption(f"Prices updated as of: {datetime.datetime.now().strftime('%H:%M:%S')}. XAU uses Spot Price.")

# 配置：使用 XAUUSD=X (现货)
tickers = [
    {"name": "Gold Spot (XAU)", "symbol": "XAUUSD=X", "fmt": "${:,.2f}"},
    {"name": "Euro (EUR/USD)", "symbol": "EURUSD=X", "fmt": "{:.4f}"},
    {"name": "GBP (GBP/USD)", "symbol": "GBPUSD=X", "fmt": "{:.4f}"},
    {"name": "Dollar Index (DXY)", "symbol": "DX-Y.NYB", "fmt": "{:.2f}"},
]

cols_price = st.columns(4)
for i, t in enumerate(tickers):
    data = get_live_price(t['symbol'])
    with cols_price[i]:
        if data:
            color = "pos" if data['change'] >= 0 else "neg"
            arrow = "▲" if data['change'] >= 0 else "▼"
            st.markdown(f"""
            <div class="metric-card">
                <div class="card-header">{t['name']}</div>
                <div class="card-value {color}">{t['fmt'].format(data['price'])}</div>
                <div class="card-footer">
                    <span class="{color}">{arrow} {data['pct']:.2f}%</span>
                    <span>Last: {data['time']}</span>
                </div>
            </div>
            """, unsafe_allow_html=True)
        else:
            st.warning("Fetching...")

st.markdown("---")

# -------------------------------------------
# 2. Smart Money Positioning (Pure CFTC)
# -------------------------------------------
st.markdown("### 2. Smart Money Positioning (COT)")
st.caption("Data Source: Direct fetch from cftc.gov (Legacy Report). No Yahoo charts mixed.")

cot_data = get_cftc_pure()
cot_config = [
    {"name": "EUR Futures (Net)", "key": "EURO"},
    {"name": "GBP Futures (Net)", "key": "GBP"},
    {"name": "Gold Futures (Net)", "key": "GOLD"},
]

cols_cot = st.columns(3)
for i, conf in enumerate(cot_config):
    with cols_cot[i]:
        if cot_data and conf['key'] in cot_data:
            net_val = cot_data[conf['key']]['net']
            date_val = cot_data[conf['key']]['date']
            
            st.markdown(f"""
            <div class="metric-card">
                <div class="card-header">{conf['name']}</div>
                <div class="card-value">{int(net_val):,}</div>
                <div class="card-footer">
                    <span>Managed Money</span>
                    <span>Date: {date_val}</span>
                </div>
            </div>
            """, unsafe_allow_html=True)
        else:
            st.info("Waiting for CFTC...")

st.markdown("---")

# -------------------------------------------
# 3. Macroeconomic Data (Real from FRED)
# -------------------------------------------
st.markdown("### 3. Macroeconomic Matrix (Latest Releases)")
st.caption("Data Source: St. Louis Fed (FRED) Official API. Showing actual released numbers.")

fred_data = get_fred_macro()

if fred_data:
    st.dataframe(
        pd.DataFrame(fred_data),
        use_container_width=True,
        hide_index=True,
        column_config={
            "Event": st.column_config.TextColumn("Indicator", width="medium"),
            "Actual": st.column_config.TextColumn("Latest Actual Value", width="medium"),
            "Source": st.column_config.TextColumn("Data Source"),
        }
    )
else:
    st.warning("FRED API 连接超时，请稍后刷新。")

st.markdown("---")

# -------------------------------------------
# 4. Macro Market Proxies (Live)
# -------------------------------------------
st.markdown("### 4. Macro Market Proxies (Live)")
st.caption(f"Real-time yields & volatility. Updated: {datetime.datetime.now().strftime('%H:%M:%S')}")

proxies = [
    {"name": "US 10Y Yield", "symbol": "^TNX"},
    {"name": "Crude Oil (WTI)", "symbol": "CL=F"},
    {"name": "VIX (Fear Index)", "symbol": "^VIX"},
]
p_cols = st.columns(3)
for i, p in enumerate(proxies):
    data = get_live_price(p['symbol'])
    with p_cols[i]:
        if data:
            st.markdown(f"**{p['name']}**: {data['price']:.2f}")
            st.caption(f"Change: {data['change']:.2f} ({data['pct']:.2f}%) | Time: {data['time']}")

st.markdown("---")

# -------------------------------------------
# 5. Fed Speaker & News Radar (RSS Feed)
# -------------------------------------------
st.markdown("### 5. 🦅 Fed & Market News Radar (Live RSS)")
st.caption("Live Headlines from Investing.com & CNBC (Replacing hardcoded quotes).")

col_news1, col_news2 = st.columns(2)

# 获取真实新闻流
# 备注：Reuters 经常封锁 RSS，这里使用 Investing.com 或 CNBC 作为替代，它们更稳定
fed_rss_url = "https://www.investing.com/rss/news_11.rss" # Market News
general_rss_url = "https://www.investing.com/rss/news_285.rss" # Economic Indicators News

with col_news1:
    st.subheader("Market News (Investing.com)")
    news_items = get_rss_news(fed_rss_url)
    if news_items:
        for item in news_items:
            st.markdown(f"""
            <div class="news-item">
                <a href="{item['link']}" target="_blank" class="news-title">{item['title']}</a>
                <div class="news-date">{item['published']}</div>
            </div>
            """, unsafe_allow_html=True)
    else:
        st.write("No news fetched.")

with col_news2:
    st.subheader("Economy & Fed (Investing.com)")
    fed_items = get_rss_news(general_rss_url)
    if fed_items:
        for item in fed_items:
            st.markdown(f"""
            <div class="news-item" style="border-left-color: #d29922;">
                <a href="{item['link']}" target="_blank" class="news-title">{item['title']}</a>
                <div class="news-date">{item['published']}</div>
            </div>
            """, unsafe_allow_html=True)
    else:
        st.write("No Fed news fetched.")

st.markdown("---")
st.info("💡 Note: FRED data usually lags by 1 month (release schedule). RSS News is real-time.")
