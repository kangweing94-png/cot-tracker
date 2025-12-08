import streamlit as st
import pandas as pd
import numpy as np
import datetime
import plotly.express as px
import plotly.graph_objects as go
import time

# ==========================================
# 1. 页面配置与机构级样式 (Institutional Style)
# ==========================================
st.set_page_config(page_title="Institutional Macro Dashboard", layout="wide", page_icon="🏦")

# 模拟当前日期: 2025年12月8日
CURRENT_DATE = datetime.date(2025, 12, 8)

st.markdown("""
<style>
    /* 全局深色背景 */
    .stApp { background-color: #0b0e11; color: #e0e0e0; }
    
    /* 卡片容器 */
    .metric-card {
        background-color: #161b22;
        border: 1px solid #30363d;
        padding: 20px;
        border-radius: 8px;
        margin-bottom: 15px;
        box-shadow: 0 4px 6px rgba(0,0,0,0.3);
    }
    
    /* 标题样式 */
    .card-header {
        font-size: 14px;
        color: #8b949e;
        margin-bottom: 5px;
        text-transform: uppercase;
        letter-spacing: 1px;
    }
    
    /* 数值样式 */
    .card-value {
        font-size: 28px;
        font-weight: 700;
        color: #f0f6fc;
        font-family: 'Roboto Mono', monospace;
    }
    
    /* 变化量样式 (Delta) */
    .card-delta {
        font-size: 14px;
        font-weight: 500;
        margin-top: 5px;
        display: flex;
        align-items: center;
    }
    .delta-pos { color: #3fb950; } /* 绿色涨 */
    .delta-neg { color: #f85149; } /* 红色跌 */
    .delta-neu { color: #8b949e; }
    
    /* 宏观表格样式 */
    .macro-table-header {
        font-weight: bold;
        color: #d2a106; /* 金色高亮 */
        border-bottom: 1px solid #333;
        padding-bottom: 5px;
        margin-bottom: 10px;
    }
    
    /* 来源链接小字 */
    .source-link {
        font-size: 11px;
        color: #58a6ff;
        text-decoration: none;
        margin-top: 10px;
        display: block;
    }
    
    /* 标签 Badges */
    .badge-high { background-color: #3d0c0c; color: #ff7b72; padding: 2px 6px; border-radius: 4px; font-size: 11px; border: 1px solid #ff7b72; }
    .badge-med { background-color: #382800; color: #d2a106; padding: 2px 6px; border-radius: 4px; font-size: 11px; border: 1px solid #d2a106; }
</style>
""", unsafe_allow_html=True)

# ==========================================
# 2. 高级数据引擎 (Advanced Data Engine)
# ==========================================

class AdvancedDataEngine:
    def __init__(self):
        # 模拟生成历史 CFTC 数据
        self.df_cftc = self._generate_mock_cftc_data()
        
    def _generate_mock_cftc_data(self):
        # 模拟到 2025-10-28 (停摆前)
        dates = pd.date_range(start="2024-01-01", end="2025-10-28", freq="W-TUE")
        data = []
        for d in dates:
            # 模拟随机游走数据
            data.append({
                "Market": "GOLD", "Date": d, 
                "Net_Positions": 200000 + np.random.randint(-50000, 50000),
                "Open_Interest": 500000 + np.random.randint(-10000, 10000)
            })
            data.append({
                "Market": "EURO FX", "Date": d, 
                "Net_Positions": -20000 + np.random.randint(-20000, 20000),
                "Open_Interest": 600000 + np.random.randint(-20000, 20000)
            })
            data.append({
                "Market": "BRITISH POUND", "Date": d, 
                "Net_Positions": 10000 + np.random.randint(-15000, 15000),
                "Open_Interest": 200000 + np.random.randint(-5000, 5000)
            })
        return pd.DataFrame(data)

    def get_cot_analysis(self, asset_keyword):
        """
        获取 COT 数据及 WoW (Week over Week) 变化
        """
        mask = self.df_cftc['Market'].str.contains(asset_keyword, case=False)
        df = self.df_cftc[mask].sort_values('Date')
        
        if len(df) < 2:
            return None
        
        latest = df.iloc[-1]
        prev = df.iloc[-2]
        
        # 计算变化量
        net_change = latest['Net_Positions'] - prev['Net_Positions']
        oi_change = latest['Open_Interest'] - prev['Open_Interest']
        
        return {
            "current_net": latest['Net_Positions'],
            "prev_net": prev['Net_Positions'],
            "net_change": net_change,
            "date": latest['Date'],
            "history": df,
            "status": "⚠️ 滞后 (停摆)" if (CURRENT_DATE - latest['Date'].date()).days > 14 else "✅ 实时"
        }

    def get_macro_calendar(self):
        """
        生成硬核宏观数据表 (含 Forecast vs Actual 和 Impact)
        """
        # 模拟最近一次发布的数据
        data = [
            {
                "Event": "Non-Farm Payrolls (NFP)",
                "Date": "2025-12-05",
                "Actual": "150K",
                "Forecast": "180K",
                "Impact": "HIGH",
                "USD_Effect": "Bearish 📉",
                "Gold_Effect": "Bullish 📈",
                "Source": "BLS",
                "Link": "https://www.bls.gov/news.release/empsit.nr0.htm"
            },
            {
                "Event": "CPI (YoY)",
                "Date": "2025-11-12",
                "Actual": "3.2%",
                "Forecast": "3.0%",
                "Impact": "HIGH",
                "USD_Effect": "Bullish 📈",
                "Gold_Effect": "Bearish 📉",
                "Source": "BLS",
                "Link": "https://www.bls.gov/cpi/"
            },
            {
                "Event": "FOMC Rate Decision",
                "Date": "2025-11-06",
                "Actual": "5.25%",
                "Forecast": "5.25%",
                "Impact": "CRITICAL",
                "USD_Effect": "Neutral ➖",
                "Gold_Effect": "Neutral ➖",
                "Source": "Federal Reserve",
                "Link": "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm"
            },
            {
                "Event": "Core PCE (MoM)",
                "Date": "2025-11-29",
                "Actual": "0.3%",
                "Forecast": "0.2%",
                "Impact": "HIGH",
                "USD_Effect": "Bullish 📈",
                "Gold_Effect": "Bearish 📉",
                "Source": "BEA",
                "Link": "https://www.bea.gov/data/personal-consumption-expenditures-price-index"
            },
            {
                "Event": "ISM Manufacturing PMI",
                "Date": "2025-12-01",
                "Actual": "48.5",
                "Forecast": "49.0",
                "Impact": "MED",
                "USD_Effect": "Bearish 📉",
                "Gold_Effect": "Bullish 📈",
                "Source": "ISM",
                "Link": "https://www.ismworld.org/"
            },
            {
                "Event": "Initial Jobless Claims",
                "Date": "2025-12-04",
                "Actual": "220K",
                "Forecast": "215K",
                "Impact": "MED",
                "USD_Effect": "Bearish 📉",
                "Gold_Effect": "Bullish 📈",
                "Source": "DOL",
                "Link": "https://www.dol.gov/ui/data.pdf"
            }
        ]
        return pd.DataFrame(data)

engine = AdvancedDataEngine()

# ==========================================
# 3. 前端 UI 渲染
# ==========================================

st.title("🏛️ Institutional Macro & COT Dashboard")
st.caption(f"Last Updated: {CURRENT_DATE} | Data Mode: Institutional | Status: US Gov Shutdown Simulated")

# --- 侧边栏：快速链接与设置 ---
with st.sidebar:
    st.header("⚙️ Settings & Sources")
    st.info("数据源快速导航 (Official Sources)")
    st.markdown("""
    - [CFTC COT Reports](https://www.cftc.gov/MarketReports/CommitmentsofTraders/index.htm)
    - [CME FedWatch Tool](https://www.cmegroup.com/markets/interest-rates/cme-fedwatch-tool.html)
    - [BLS (CPI/NFP)](https://www.bls.gov/)
    - [BEA (PCE Data)](https://www.bea.gov/)
    """)
    st.markdown("---")
    st.write("📊 **Display Config**")
    show_history = st.checkbox("Show Historical Charts", value=True)

# --- 第一部分：COT 深度分析 (带 WoW 对比) ---
st.markdown("### 1. Smart Money Positioning (COT Managed Money)")
st.markdown("该板块展示大型基金（Managed Money）的净持仓及周度变化 (WoW Change)。")

col1, col2, col3 = st.columns(3)

assets = [
    {"title": "EUR/USD Futures", "key": "EURO", "col": col1, "color": "#FFD700"},
    {"title": "GBP/USD Futures", "key": "BRITISH", "col": col2, "color": "#00CED1"},
    {"title": "Gold (XAU) Futures", "key": "GOLD", "col": col3, "color": "#FFA500"},
]

for asset in assets:
    data = engine.get_cot_analysis(asset["key"])
    with asset["col"]:
        if data:
            # 格式化变化量：+500 或 -200
            change_val = data['net_change']
            change_sign = "+" if change_val > 0 else ""
            change_class = "delta-pos" if change_val > 0 else "delta-neg"
            arrow = "▲" if change_val > 0 else "▼"
            
            # 渲染自定义 HTML 卡片
            st.markdown(f"""
            <div class="metric-card">
                <div class="card-header">{asset['title']}</div>
                <div class="card-value">{int(data['current_net']):,}</div>
                <div class="card-delta {change_class}">
                    {arrow} {change_sign}{int(change_val):,} WoW (周环比)
                </div>
                <div style="margin-top:8px; font-size:12px; color:#666;">
                    报告日期: {data['date'].date()} <br>
                    {data['status']}
                </div>
                <a href="https://www.cftc.gov/dea/futures/deacmesf.htm" target="_blank" class="source-link">🔗 Verify at CFTC.gov</a>
            </div>
            """, unsafe_allow_html=True)
            
            if show_history:
                # 迷你走势图
                fig = px.area(data['history'], x='Date', y='Net_Positions', height=100)
                fig.update_layout(
                    template="plotly_dark", 
                    margin=dict(l=0, r=0, t=0, b=0),
                    xaxis=dict(visible=False), 
                    yaxis=dict(visible=False),
                    paper_bgcolor='rgba(0,0,0,0)',
                    plot_bgcolor='rgba(0,0,0,0)'
                )
                fig.update_traces(line_color=asset['color'], fillcolor=asset['color'].replace(")", ", 0.2)").replace("rgb", "rgba"))
                st.plotly_chart(fig, use_container_width=True, config={'displayModeBar': False})

st.markdown("---")

# --- 第二部分：宏观全景矩阵 (Macro Matrix) ---
st.markdown("### 2. Macroeconomic Matrix & Impact Analysis")
st.markdown("包含美联储关注的核心通胀(PCE/CPI)、就业数据(NFP)及经济景气度(ISM)。")

macro_df = engine.get_macro_calendar()

# 使用 Streamlit 的列布局来模拟 Dashboard 布局
m_col1, m_col2 = st.columns([2, 1])

with m_col1:
    st.markdown("#### 📅 Key Economic Events (Recent)")
    
    # 我们不用原生的 dataframe，而是用 HTML 表格来获得更好的控制
    table_html = """
    <table style="width:100%; border-collapse: collapse; color: #e0e0e0; font-size: 14px;">
        <thead>
            <tr style="border-bottom: 2px solid #333; text-align: left;">
                <th style="padding: 10px;">Event</th>
                <th style="padding: 10px;">Date</th>
                <th style="padding: 10px;">Actual</th>
                <th style="padding: 10px;">Forecast</th>
                <th style="padding: 10px;">Impact Level</th>
                <th style="padding: 10px;">Source</th>
            </tr>
        </thead>
        <tbody>
    """
    
    for index, row in macro_df.iterrows():
        impact_badge = f'<span class="badge-high">HIGH</span>' if row['Impact'] in ['HIGH', 'CRITICAL'] else f'<span class="badge-med">{row["Impact"]}</span>'
        
        # 简单判断 Actual vs Forecast 的颜色
        val_color = "#e0e0e0"
        try:
            # 这里的逻辑比较简单，仅做演示，真实情况需根据数据类型判断利好利空
            if float(row['Actual'].strip('%K')) > float(row['Forecast'].strip('%K')):
                val_color = "#d2a106" # 超过预期显示金色
        except:
            pass

        table_html += f"""
        <tr style="border-bottom: 1px solid #222;">
            <td style="padding: 10px; font-weight:bold;">{row['Event']}</td>
            <td style="padding: 10px; color:#888;">{row['Date']}</td>
            <td style="padding: 10px; color:{val_color}; font-weight:bold;">{row['Actual']}</td>
            <td style="padding: 10px;">{row['Forecast']}</td>
            <td style="padding: 10px;">{impact_badge}</td>
            <td style="padding: 10px;"><a href="{row['Link']}" target="_blank" style="color:#58a6ff;">Link</a></td>
        </tr>
        """
    table_html += "</tbody></table>"
    st.markdown(table_html, unsafe_allow_html=True)

with m_col2:
    st.markdown("#### 🎯 Market Impact Analysis")
    # 这里展示最后一个事件对市场的影响
    latest_event = macro_df.iloc[0]
    
    st.info(f"Focus: {latest_event['Event']}")
    
    st.markdown(f"""
    **USD Impact:** {latest_event['USD_Effect']}
    
    **Gold Impact:** {latest_event['Gold_Effect']}
    
    ---
    **FOMC Watch:**
    目前市场押注下一次会议维持利率不变的概率为 **65%**。
    
    [查看 Fed Dot Plot (点阵图)](https://www.federalreserve.gov/monetarypolicy/fomcprojtabl20251215.htm)
    """)
    
    # 模拟一个 Gauge
    st.markdown("#### Powell Tone Meter (Simulated)")
    st.progress(0.7, text="Hawkish (鹰派) 🦅")

# --- 底部：技术支持与声明 ---
st.markdown("---")
st.caption("Disclaimer: This dashboard is for informational purposes only. Trading involves risk. Data is simulated for the 'Dec 2025' scenario.")
