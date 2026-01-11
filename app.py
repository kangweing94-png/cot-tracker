import streamlit as st
import pandas as pd
import datetime
import yfinance as yf
import feedparser
from fredapi import Fred
import requests
import zipfile
import io

# ==========================================
# 1. 核心配置 (XAUUSD 专属)
# ==========================================
st.set_page_config(page_title="XAUUSD Institutional Dashboard", layout="wide", page_icon="🏆")

FRED_KEY = '476ef255e486edb3fdbf71115caa2857'

# 自定义 CSS：黑金风格
st.markdown("""
<style>
    .stApp { background-color: #000000; color: #e0e0e0; font-family: 'Segoe UI', sans-serif; }
    
    /* 顶部标题 */
    h1 { color: #d4af37 !important; text-align: center; border-bottom: 2px solid #333; padding-bottom: 20px; }
    
    /* 卡片容器 */
    .metric-card {
        background-color: #111;
        border: 1px solid #333;
        padding: 20px;
        border-radius: 4px;
        margin-bottom: 15px;
        border-left: 3px solid #d4af37; /* 金色左边框 */
    }
    .metric-val { font-size: 32px; font-weight: 700; color: #fff; font-family: 'Roboto Mono', monospace; }
    .metric-label { font-size: 12px; color: #888; text-transform: uppercase; letter-spacing: 1px; }
    .metric-sub { font-size: 12px; color: #555; margin-top: 5px; }
    
    /* 涨跌颜色 */
    .pos { color: #00ff00; }
    .neg { color: #ff3333; }
    
    /* 表格样式 */
    .stDataFrame { border: 1px solid #222; }
</style>
""", unsafe_allow_html=True)

# ==========================================
# 2. 黄金专属数据引擎
# ==========================================

# --- A. 黄金现货价格 (Live Spot) ---
@st.cache_data(ttl=15) # 每15秒刷新一次价格
def get_gold_live():
    """获取 XAUUSD=X 实时报价"""
    try:
        # XAUUSD=X 是 Yahoo Finance 的黄金现货代码
        ticker = yf.Ticker("XAUUSD=X")
        # 使用 fast_info 获取极速报价
        price = ticker.fast_info['last_price']
        prev = ticker.fast_info['previous_close']
        change = price - prev
        pct = (change / prev) * 100
        
        return {
            "price": price,
            "change": change,
            "pct": pct,
            "time": datetime.datetime.now().strftime('%H:%M:%S')
        }
    except:
        return None

# --- B. CFTC 机构持仓 (ZIP 穿透版) ---
@st.cache_data(ttl=86400) # 24小时刷新一次 (CFTC每周五更新，不需要频繁刷)
def get_cftc_gold_zip():
    """
    通过下载 ZIP 文件来获取数据。
    这种方法比抓取 TXT 网页更难被防火墙拦截。
    """
    # 2025年 CME 交易所的 ZIP 文件地址 (如果2025还没出，会自动回退逻辑)
    # 通常格式: https://www.cftc.gov/files/dea/history/deacmesf{year}.zip
    current_year = datetime.datetime.now().year
    url = f"https://www.cftc.gov/files/dea/history/deacmesf{current_year}.zip"
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
    }
    
    try:
        # 1. 请求下载 ZIP
        r = requests.get(url, headers=headers, timeout=10)
        
        # 如果当年文件不存在(年初常见)，尝试去年的
        if r.status_code == 404:
            url = f"https://www.cftc.gov/files/dea/history/deacmesf{current_year-1}.zip"
            r = requests.get(url, headers=headers, timeout=10)
            
        if r.status_code != 200:
            return None, f"HTTP Error {r.status_code}"

        # 2. 在内存中解压
        z = zipfile.ZipFile(io.BytesIO(r.content))
        file_name = z.namelist()[0] # 获取包内文件名
        
        # 3. 读取 CSV
        with z.open(file_name) as f:
            df = pd.read_csv(f, low_memory=False)
            
        # 4. 筛选黄金 (GOLD)
        # CFTC 官方名称: "GOLD - COMMODITY EXCHANGE INC."
        gold_data = df[df['Market_and_Exchange_Names'] == 'GOLD - COMMODITY EXCHANGE INC.']
        
        if gold_data.empty:
            return None, "Gold data not found in file"
            
        # 5. 取最新一周的数据
        # 按日期排序
        gold_data['Report_Date_as_MM_DD_YYYY'] = pd.to_datetime(gold_data['Report_Date_as_MM_DD_YYYY'])
        gold_data = gold_data.sort_values('Report_Date_as_MM_DD_YYYY')
        latest = gold_data.iloc[-1]
        
        # 6. 计算 Managed Money Net Position (基金净头寸)
        # 在 ZIP 文件中，列名通常是 "Pct_of_OI_M_Money_Long" 等，或者 "M_Money_Positions_Long_ALL"
        # 我们使用最标准的 Non-Commercial (大投机商) 数据，这通常被视为 Smart Money
        # 列名: "NonComm_Positions_Long_All", "NonComm_Positions_Short_All"
        
        longs = latest['NonComm_Positions_Long_All']
        shorts = latest['NonComm_Positions_Short_All']
        net = longs - shorts
        date = latest['Report_Date_as_MM_DD_YYYY'].strftime('%Y-%m-%d')
        
        return {
            "net": net,
            "longs": longs,
            "shorts": shorts,
            "date": date
        }, "Success"
        
    except Exception as e:
        return None, str(e)

# --- C. 宏观真实数据 (FRED) ---
@st.cache_data(ttl=3600)
def get_fred_data():
    try:
        fred = Fred(api_key=FRED_KEY)
        
        # 获取最新 NFP (PAYEMS) 和 上个月对比
        nfp = fred.get_series('PAYEMS', sort_order='desc', limit=2)
        nfp_change = (nfp.iloc[0] - nfp.iloc[1]) * 1000
        nfp_date = nfp.index[0].strftime('%Y-%m-%d')
        
        # 获取 CPI YoY
        cpi = fred.get_series('CPIAUCSL', sort_order='desc', limit=13)
        cpi_yoy = ((cpi.iloc[0] - cpi.iloc[12]) / cpi.iloc[12]) * 100
        cpi_date = cpi.index[0].strftime('%Y-%m-%d')
        
        # 获取 10年期美债 (影响黄金最大因素)
        yield10 = fred.get_series('DGS10', sort_order='desc', limit=1)
        yield_val = yield10.iloc[0]
        
        return [
            {"Indicator": "Non-Farm Payrolls", "Value": f"{int(nfp_change):+,}", "Date": nfp_date},
            {"Indicator": "CPI (YoY)", "Value": f"{cpi_yoy:.1f}%", "Date": cpi_date},
            {"Indicator": "10Y Treasury Yield", "Value": f"{yield_val:.2f}%", "Date": yield10.index[0].strftime('%Y-%m-%d')}
        ]
    except:
        return []

# --- D. 黄金新闻源 (Investing.com Gold) ---
@st.cache_data(ttl=300)
def get_gold_news():
    # Investing.com Gold Specific RSS
    url = "https://www.investing.com/rss/news_286.rss" # 286 是 Commodities 或者是 Gold
    # 备用: https://www.investing.com/rss/news_285.rss (Commodities)
    try:
        feed = feedparser.parse(url)
        return feed.entries[:5]
    except:
        return []

# ==========================================
# 3. 前端 UI 渲染
# ==========================================

st.title("🏆 XAUUSD Institutional Center")
st.caption(f"System Time: {datetime.datetime.now().strftime('%H:%M:%S')} | Focused on GOLD Only")

# --- 1. 实时报价 (Spot Price) ---
gold = get_gold_live()
if gold:
    c_price = "pos" if gold['pct'] >= 0 else "neg"
    arrow = "▲" if gold['pct'] >= 0 else "▼"
    
    st.markdown(f"""
    <div style="text-align:center; margin-bottom: 20px;">
        <div style="font-size: 16px; color: #888;">XAU/USD SPOT PRICE</div>
        <div style="font-size: 60px; font-weight: bold; color: #fff;">${gold['price']:,.2f}</div>
        <div style="font-size: 24px;" class="{c_price}">{arrow} ${gold['change']:.2f} ({gold['pct']:.2f}%)</div>
    </div>
    """, unsafe_allow_html=True)
else:
    st.warning("Fetching Live Gold Price...")

st.markdown("---")

# --- 2. 机构持仓 (CFTC ZIP) ---
st.header("1. Institutional Positioning (CFTC)")
st.caption("Fetching via ZIP Download (More robust against blocks). Updates Weekly.")

cftc_data, msg = get_cftc_gold_zip()

if cftc_data:
    c1, c2, c3 = st.columns(3)
    
    with c1:
        st.markdown(f"""
        <div class="metric-card">
            <div class="metric-label">Smart Money Net Position</div>
            <div class="metric-val" style="color:#d4af37">{int(cftc_data['net']):,}</div>
            <div class="metric-sub">Date: {cftc_data['date']}</div>
        </div>
        """, unsafe_allow_html=True)
        
    with c2:
        st.markdown(f"""
        <div class="metric-card">
            <div class="metric-label">Long Contracts</div>
            <div class="metric-val pos">{int(cftc_data['longs']):,}</div>
            <div class="metric-sub">Bullish Bets</div>
        </div>
        """, unsafe_allow_html=True)
        
    with c3:
        st.markdown(f"""
        <div class="metric-card">
            <div class="metric-label">Short Contracts</div>
            <div class="metric-val neg">{int(cftc_data['shorts']):,}</div>
            <div class="metric-sub">Bearish Bets</div>
        </div>
        """, unsafe_allow_html=True)

else:
    st.error(f"CFTC Data Unavailable: {msg}")
    st.info("💡 Note: CFTC data is weekly. If you are on a cloud server, try running locally.")

# --- 3. 宏观驱动 (FRED) ---
st.header("2. Macro Drivers (FRED Official)")
macro = get_fred_data()

if macro:
    m1, m2, m3 = st.columns(3)
    for i, item in enumerate(macro):
        col = [m1, m2, m3][i]
        with col:
            st.markdown(f"""
            <div class="metric-card" style="border-left-color: #555;">
                <div class="metric-label">{item['Indicator']}</div>
                <div class="metric-val">{item['Value']}</div>
                <div class="metric-sub">Released: {item['Date']}</div>
            </div>
            """, unsafe_allow_html=True)

# --- 4. 黄金新闻 (RSS) ---
st.header("3. Gold Market Intelligence")
news = get_gold_news()

if news:
    for n in news:
        st.markdown(f"""
        <div style="background:#111; padding:10px; margin-bottom:5px; border-left:2px solid #d4af37;">
            <a href="{n.link}" target="_blank" style="color:#fff; text-decoration:none; font-size:16px; font-weight:bold;">{n.title}</a>
            <div style="color:#666; font-size:12px; margin-top:5px;">{n.published}</div>
        </div>
        """, unsafe_allow_html=True)
else:
    st.info("No gold news available at the moment.")
