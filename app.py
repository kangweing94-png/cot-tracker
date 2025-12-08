import streamlit as st
import pandas as pd
import numpy as np
import datetime
import plotly.express as px
import yfinance as yf

# ==========================================
# 1. 页面配置与机构级样式 (V6 Style Restored)
# ==========================================
st.set_page_config(page_title="Institutional Live Dashboard V7", layout="wide", page_icon="📡")

st.markdown("""
<style>
    .stApp { background-color: #0b0e11; color: #e0e0e0; }
    
    /* 卡片通用样式 */
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
    .delta-pos { color: #3fb950; } /* 绿色 */
    .delta-neg { color: #f85149; } /* 红色 */
    .card-sub { font-size: 11px; color: #666; margin-top: 5px; }
    
    /* Fed 雷达卡片 */
    .fed-card { background-color: #1c2128; border-left: 4px solid #333; padding: 15px; margin-bottom: 10px; border-radius: 4px; }
    .fed-hawk { border-left-color: #f85149; }
    .fed-dove { border-left-color: #3fb950; }
    .fed-neutral { border-left-color: #d29922; }
    .fed-name { font-weight: bold; font-size: 15px; color: #fff; }
    .fed-role { font-size: 12px; color: #8b949e; margin-bottom: 8px; }
    .fed-quote-en { font-style: italic; color: #d0d7de; font-size: 14px; margin-bottom: 4px; display: block;}
    .fed-quote-cn { color: #8b949e; font-size: 13px; display: block; }

</style>
""", unsafe_allow_html=True)

# ==========================================
# 2. 独立数据获取函数 (修复 UnhashableParamError)
# ==========================================

@st.cache_data(ttl=300) # 缓存5分钟
def fetch_yahoo_price(ticker):
    """获取 Yahoo 实时价格 + 历史走势"""
    try:
        # 获取3个月历史用于画图
        df = yf.download(ticker, period="3mo", interval="1d", progress=False)
        if df.empty: return None
        
        # 处理 MultiIndex
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
            
        latest = float(df['Close'].iloc[-1])
        prev = float(df['Close'].iloc[-2])
        change = latest - prev
        pct = (change / prev) * 100
        
        return {
            "latest": latest,
            "change": change,
            "pct": pct,
            "history": df.reset_index()
        }
    except Exception as e:
        return None

@st.cache_data(ttl=86400) # 缓存24小时
def fetch_cftc_latest():
    """从 CFTC 官网抓取最新一期报告"""
    url = "https://www.cftc.gov/dea/newcot/deacmesf.txt"
    try:
        df = pd.read_csv(url, header=None, low_memory=False)
        
        # 定义我们需要抓取的资产
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
                # 计算净多头 (Non-Comm Long - Short)
                net = float(data[8]) - float(data[9]) 
                date = data[2] # Report Date
                results[key] = {"net": net, "date": date}
        return results
    except:
        return None

# ==========================================
# 3. 数据引擎类 (Wrapper)
# ==========================================
class LiveDataEngine:
    def get_price(self, ticker):
        return fetch_yahoo_price(ticker)
    
    def get_cot(self):
        return fetch_cftc_latest()
        
    def get_macro_calendar(self):
        # 注意：由于没有免费API能抓取“下周”的预测值，这里为了展示表格样式
        # 我们使用一套"标准模板"数据，或者你可以手动更新下周的数据。
        # 这里展示的是样式 (Enhanced Viz)。
        data = [
            {"Event": "Non-Farm Payrolls (NFP)", "Date": "2024-12-06", "Actual": "227K", "Forecast": "200K", "Impact": "HIGH", "Bias": "Bullish USD", "Link": "https://www.bls.gov/"},
            {"Event": "CPI (YoY)", "Date": "2024-12-11", "Actual": "--", "Forecast": "2.6%", "Impact": "HIGH", "Bias": "Bullish USD", "Link": "https://www.bls.gov/cpi/"},
            {"Event": "FOMC Rate Decision", "Date": "2024-12-18", "Actual": "--", "Forecast": "4.50%", "Impact": "CRITICAL", "Bias": "Neutral", "Link": "https://www.federalreserve.gov/"},
            {"Event": "ISM Services PMI", "Date": "2024-12-04", "Actual": "52.1", "Forecast": "55.0", "Impact": "MED", "Bias": "Bearish USD", "Link": "https://www.ismworld.org/"},
        ]
        return pd.DataFrame(data)

    def get_fed_radar(self):
        # 这里放入真实的近期言论 (Real Quotes)
        return [
            {
                "Name": "Jerome Powell", "Role": "Fed Chair", "Stance": "Neutral", 
                "QuoteEn": "The economy is not sending any signals that we need to be in a hurry to lower rates.",
                "QuoteCn": "经济没有发出任何信号表明我们需要急于降息。",
                "Date": "2024-11-14", "Type": "fed-neutral"
            },
            {
                "Name": "Christopher Waller", "Role": "Governor", "Stance": "Hawk (鹰派)", 
                "QuoteEn": "I am inclined to support a rate cut in December, but data will decide.",
                "QuoteCn": "我倾向于支持12月降息，但最终取决于数据。",
                "Date": "2024-12-02", "Type": "fed-hawk"
            },
            {
                "Name": "Michelle Bowman", "Role": "Governor", "Stance": "Hawk (鹰派)", 
                "QuoteEn": "Progress on inflation looks to have stalled.",
                "QuoteCn": "通胀方面的进展似乎已经停滞。",
                "Date": "2024-11-20", "Type": "fed-hawk"
            }
        ]

engine = LiveDataEngine()

# ==========================================
# 4. 前端 UI 渲染
# ==========================================

st.title("📡 Institutional Real-Time Dashboard V7")
st.caption(f"Data Sources: Yahoo Finance (Live) & CFTC.gov (Weekly) | System Time: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}")

# --- 1. Real-Time Market Prices (保留你的要求) ---
st.markdown("### 1. Real-Time Market Prices (Yahoo Finance)")
tickers = [
    {"name": "Gold (XAU)", "symbol": "GC=F", "fmt": "${:,.2f}"},
    {"name": "Euro (EUR)", "symbol": "EURUSD=X", "fmt": "{:.4f}"},
    {"name": "GBP (GBP)", "symbol": "GBPUSD=X", "fmt": "{:.4f}"},
    {"name": "Dollar Index", "symbol": "DX-Y.NYB", "fmt": "{:.2f}"},
]
cols_price = st.columns(4)
for i, t in enumerate(tickers):
    data = engine.get_price(t['symbol'])
    with cols_price[i]:
        if data:
            color = "#3fb950" if data['change'] >= 0 else "#f85149"
            arrow = "▲" if data['change'] >= 0 else "▼"
            st.markdown(f"""
            <div class="metric-card">
                <div class="card-header">{t['name']}</div>
                <div class="card-value" style="color:{color}">{t['fmt'].format(data['latest'])}</div>
                <div class="card-delta" style="color:{color}">{arrow} {data['pct']:.2f}%</div>
            </div>
            """, unsafe_allow_html=True)
        else:
            st.warning("Loading...")

st.markdown("---")

# --- 2. Smart Money Positioning (COT & Trend) (恢复 V6 样式) ---
st.markdown("### 2. Smart Money Positioning (COT & Trend)")
st.markdown("结合 **CFTC 真实持仓数据** 与 **Yahoo 实时价格趋势**。")

cot_data = engine.get_cot() # 获取真实 CFTC 数据
# 定义卡片配置
cot_config = [
    {"name": "EUR Futures", "key": "EURO", "symbol": "EURUSD=X", "color": "#FFD700"},
    {"name": "GBP Futures", "key": "GBP", "symbol": "GBPUSD=X", "color": "#00CED1"},
    {"name": "Gold Futures", "key": "GOLD", "symbol": "GC=F", "color": "#FFA500"},
]

cols_cot = st.columns(3)
for i, conf in enumerate(cot_config):
    with cols_cot[i]:
        # 1. 获取 COT 数值
        net_pos = "N/A"
        date_str = "Checking CFTC..."
        if cot_data and conf['key'] in cot_data:
            net_pos = int(cot_data[conf['key']]['net'])
            date_str = cot_data[conf['key']]['date']
        
        # 2. 获取价格走势 (用于画迷你图)
        price_data = engine.get_price(conf['symbol'])
        
        # 3. 渲染卡片
        st.markdown(f"""
        <div class="metric-card">
            <div class="card-header">{conf['name']} (Managed Money)</div>
            <div class="card-value">{f"{net_pos:,}" if net_pos != "N/A" else "Loading..."}</div>
            <div class="card-sub">CFTC Report: {date_str}</div>
        </div>
        """, unsafe_allow_html=True)
        
        # 4. 渲染迷你图 (V6 特性回归)
        if price_data:
            fig = px.area(price_data['history'], x='Date', y='Close', height=120)
            fig.update_layout(
                template="plotly_dark", 
                margin=dict(l=0, r=0, t=0, b=0),
                xaxis=dict(visible=False), yaxis=dict(visible=False),
                showlegend=False,
                paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)'
            )
            fig.update_traces(line_color=conf['color'], fillcolor=conf['color'].replace(")", ", 0.2)").replace("rgb", "rgba"))
            st.plotly_chart(fig, use_container_width=True, config={'staticPlot': True})

st.markdown("---")

# --- 3. Macroeconomic Matrix (Enhanced Viz) (恢复 V6 表格样式) ---
st.markdown("### 3. Macroeconomic Matrix (Enhanced Viz)")
st.markdown("关键经济数据日历 (Live/Forecast)。**Pandas Styling** 高亮已恢复。")

macro_df = engine.get_macro_calendar()

# 样式映射
styler = macro_df.style.format({"Actual": "{}"}) \
    .map(lambda v: 'color: #ff7b72; font-weight: bold;' if v in ['HIGH', 'CRITICAL'] else '', subset=['Impact']) \
    .map(lambda v: 'color: #3fb950;' if 'Bullish' in v else 'color: #f85149;' if 'Bearish' in v else '', subset=['Bias'])

st.dataframe(
    styler,
    use_container_width=True,
    hide_index=True,
    column_config={
        "Link": st.column_config.LinkColumn(
            "Source", display_text="Official Data 🔗"
        ),
        "Impact": st.column_config.TextColumn("Impact"),
        "Bias": st.column_config.TextColumn("USD Bias"),
    },
    height=250
)

st.markdown("---")

# --- 4. Macro Market Proxies (Live Charts) (保留你的要求) ---
st.markdown("### 4. Macro Market Proxies (Live)")
macro_tickers = [
    {"name": "US 10Y Yield", "symbol": "^TNX"},
    {"name": "Crude Oil", "symbol": "CL=F"},
    {"name": "VIX Index", "symbol": "^VIX"},
]
m_cols = st.columns(3)
for i, t in enumerate(macro_tickers):
    data = engine.get_price(t['symbol'])
    with m_cols[i]:
        if data:
            st.markdown(f"**{t['name']}**: {data['latest']:.2f}")
            fig = px.line(data['history'], x='Date', y='Close', height=150)
            fig.update_layout(template="plotly_dark", margin=dict(l=0,r=0,t=0,b=0), xaxis=dict(visible=False), yaxis=dict(visible=False))
            st.plotly_chart(fig, use_container_width=True)

st.markdown("---")

# --- 5. Fed Speaker Radar (Visualized) (恢复双语/卡片样式) ---
st.markdown("### 5. 🦅 Fed Speaker Radar (FOMC)")
st.markdown("美联储核心成员最新立场追踪 (Current Real Quotes)。")

speeches = engine.get_fed_radar()
col_fed1, col_fed2 = st.columns(2)

for i, speech in enumerate(speeches):
    # 分栏显示
    target_col = col_fed1 if i % 2 == 0 else col_fed2
    with target_col:
        st.markdown(f"""
        <div class="fed-card {speech['Type']}">
            <div class="fed-name">{speech['Name']} <span style="font-size:12px; font-weight:normal; color:#aaa;">| {speech['Role']}</span></div>
            <div class="fed-role" style="color:{'#f85149' if 'Hawk' in speech['Type'] else '#3fb950' if 'Dove' in speech['Type'] else '#d29922'};">
                {speech['Stance']}
            </div>
            <span class="fed-quote-en">“{speech['QuoteEn']}”</span>
            <span class="fed-quote-cn">{speech['QuoteCn']}</span>
            <div style="text-align:right; font-size:11px; margin-top:5px; color:#666;">Date: {speech['Date']}</div>
        </div>
        """, unsafe_allow_html=True)

st.markdown("---")
st.info("💡 Note: Prices are Real-Time (Yahoo). COT data is Latest Available (CFTC). Calendar/Fed Radar are curated for visual demonstration.")
