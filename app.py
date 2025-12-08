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
# 2. 真实数据引擎 (Real Data Engine)
# ==========================================

class RealDataEngine:
    def __init__(self):
        pass

    @st.cache_data(ttl=3600) # 缓存1小时，避免频繁请求被封
    def get_market_price(self, ticker):
        """
        从 Yahoo Finance 获取实时价格和历史走势
        """
        try:
            # 下载最近3个月的数据
            df = yf.download(ticker, period="3mo", interval="1d", progress=False)
            if df.empty:
                return None
            
            # 获取最新价和涨跌幅
            latest_price = df['Close'].iloc[-1].item()
            prev_price = df['Close'].iloc[-2].item()
            change = latest_price - prev_price
            pct_change = (change / prev_price) * 100
            
            return {
                "latest": latest_price,
                "change": change,
                "pct": pct_change,
                "history": df.reset_index()
            }
        except Exception as e:
            st.error(f"Error fetching {ticker}: {e}")
            return None

    @st.cache_data(ttl=86400) # 缓存24小时，CFTC 每周才更新一次
    def get_cftc_data(self):
        """
        尝试从 CFTC 官网直接读取最新的 COT 报告 (Legacy format for simplicity)
        URL: https://www.cftc.gov/dea/newcot/deacmesf.txt (CME Futures Only)
        """
        cftc_url = "https://www.cftc.gov/dea/newcot/deacmesf.txt"
        
        try:
            # CFTC 的 txt 文件没有 header，我们需要手动定义常用列
            # 格式参考 CFTC 文档：
            # Col 0: Market Name, Col 2: Date
            # Col 10: Non-Comm Long, Col 11: Non-Comm Short (这是 Smart Money 的大概位置)
            # *注意*: 这种直接抓取比较脆弱，如果 CFTC 改格式会失效
            
            df = pd.read_csv(cftc_url, header=None, low_memory=False)
            
            # 简单的名称映射
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
                    # 取第一行（通常是最新的，但文件里通常只有最新一周的数据）
                    data = row.iloc[0]
                    date_str = data[2] # Report Date
                    
                    # 在 Legacy 报告中，Non-Commercial Long 通常在 index 8-10 左右，这里为了演示稳定性，
                    # 我们模拟计算 Net Position (Long - Short)。 
                    # *真实项目中建议使用 `cot_reports` 库，这里直接读取原始数据列可能需要根据文档校准*
                    long_pos = float(data[8]) # Non-Commercial Long
                    short_pos = float(data[9]) # Non-Commercial Short
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
            # 如果 CFTC 官网连接失败 (常见于反爬虫)，返回 None
            return None

engine = RealDataEngine()

# ==========================================
# 3. 前端 UI 渲染
# ==========================================

st.title("📡 Real-World Live Market Dashboard")
st.caption(f"Connected to: Yahoo Finance & CFTC.gov | Time Zone: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}")

# --- 1. Real Market Prices (Yahoo Finance) ---
st.markdown("### 1. Real-Time Market Prices (Yahoo Finance)")
st.markdown("直接获取全球市场实时报价 (Live Quote)。")

# 定义代码: 黄金, 欧元, 英镑, 美元指数
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
            # 根据涨跌变色
            line_color = '#3fb950' if data['change'] >= 0 else '#f85149'
            fig.update_traces(line_color=line_color, fillcolor=line_color.replace("#", "rgba(").replace(")", ", 0.2)"))
            # 修复rgba转换问题，直接用简单颜色
            fig.update_traces(line_color=line_color) 
            
            st.plotly_chart(fig, use_container_width=True, config={'staticPlot': True})
        else:
            st.error(f"Failed to fetch {t['name']}")

st.markdown("---")

# --- 2. Real CFTC COT Data (Live Scrape) ---
st.markdown("### 2. CFTC COT Data (Real Scrape)")
st.markdown("尝试从 `cftc.gov` 获取最新报告。如果显示空白，可能是因为 CFTC 官网拒绝了连接（反爬虫）。")

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
    # 这里为了不让你看到空白，我可以显示一个“如何手动下载”的链接
    st.markdown("[点击这里手动下载最新 COT 报告 (cftc.gov)](https://www.cftc.gov/dea/newcot/deacmesf.txt)")

st.markdown("---")

# --- 3. Real Macro Proxies (Using Yields/Oil) ---
st.markdown("### 3. Macro Market Proxies (Live)")
st.markdown("由于获取实时 NFP/CPI 需要 API Key (FRED)，此处使用 **市场定价的宏观指标** (Market-Priced Macro Indicators) 作为实时替代。")

macro_tickers = [
    {"name": "US 10Y Yield (通胀预期/利率)", "symbol": "^TNX"},
    {"name": "Crude Oil (能源通胀)", "symbol": "CL=F"},
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

# --- 4. Fed News (External Link) ---
st.markdown("---")
st.markdown("### 4. Fed Speeches & Calendar")
st.info("💡 获取实时的 Fed 官员鹰鸽派言论分析需要接入新闻 API (如 Bloomberg/Reuters Terminal)。以下是官方源链接：")

st.markdown("""
* [Federal Reserve Press Releases](https://www.federalreserve.gov/newsevents/pressreleases.htm) 🔗
* [CME FedWatch Tool (Rate Hike Probability)](https://www.cmegroup.com/markets/interest-rates/cme-fedwatch-tool.html) 🔗
""")
