import streamlit as st
import pandas as pd
import numpy as np
import datetime
import plotly.express as px

# ==========================================
# 1. 页面配置与机构级样式
# ==========================================
st.set_page_config(page_title="Institutional Macro Dashboard V4", layout="wide", page_icon="🏦")

# 模拟当前日期
CURRENT_DATE = datetime.date(2025, 12, 8)

st.markdown("""
<style>
    .stApp { background-color: #0b0e11; color: #e0e0e0; }
    
    /* COT 卡片样式 */
    .metric-card {
        background-color: #161b22;
        border: 1px solid #30363d;
        padding: 20px;
        border-radius: 8px;
        margin-bottom: 15px;
    }
    .card-header { font-size: 14px; color: #8b949e; text-transform: uppercase; letter-spacing: 1px; }
    .card-value { font-size: 28px; font-weight: 700; color: #f0f6fc; font-family: 'Roboto Mono', monospace; }
    .card-delta { font-size: 14px; font-weight: 500; margin-top: 5px; }
    .delta-pos { color: #3fb950; }
    .delta-neg { color: #f85149; }
    
    /* Fed 讲话卡片 */
    .fed-card {
        background-color: #1c2128;
        border-left: 4px solid #333;
        padding: 15px;
        margin-bottom: 10px;
        border-radius: 4px;
    }
    .fed-hawk { border-left-color: #f85149; } /* 鹰派红色 */
    .fed-dove { border-left-color: #3fb950; } /* 鸽派绿色 */
    .fed-neutral { border-left-color: #d29922; } /* 中立黄色 */
    .fed-name { font-weight: bold; font-size: 16px; color: #fff; }
    .fed-role { font-size: 12px; color: #8b949e; margin-bottom: 8px; }
    .fed-quote { font-style: italic; color: #d0d7de; font-size: 14px; }
    .fed-date { font-size: 11px; color: #58a6ff; text-align: right; margin-top: 5px; }

</style>
""", unsafe_allow_html=True)

# ==========================================
# 2. 数据引擎
# ==========================================

class AdvancedDataEngine:
    def __init__(self):
        pass

    def get_cot_data(self):
        # 简单模拟 COT 数据用于展示
        return [
            {"name": "EUR/USD", "pos": -20094, "change": 9451, "date": "2025-10-28"},
            {"name": "GBP/USD", "pos": 12086, "change": 9275, "date": "2025-10-28"},
            {"name": "GOLD (XAU)", "pos": 195944, "change": -21189, "date": "2025-10-28"},
        ]

    def get_macro_data(self):
        # 使用 DataFrame 替代 HTML，解决乱码问题
        data = [
            {"Event": "Non-Farm Payrolls", "Date": "2025-12-05", "Actual": "150K", "Forecast": "180K", "Impact": "HIGH", "Bias": "Bearish USD"},
            {"Event": "CPI (YoY)", "Date": "2025-11-12", "Actual": "3.2%", "Forecast": "3.0%", "Impact": "HIGH", "Bias": "Bullish USD"},
            {"Event": "FOMC Rate Decision", "Date": "2025-11-06", "Actual": "5.25%", "Forecast": "5.25%", "Impact": "CRITICAL", "Bias": "Neutral"},
            {"Event": "Core PCE (MoM)", "Date": "2025-11-29", "Actual": "0.3%", "Forecast": "0.2%", "Impact": "HIGH", "Bias": "Bullish USD"},
            {"Event": "ISM Mfg PMI", "Date": "2025-12-01", "Actual": "48.5", "Forecast": "49.0", "Impact": "MED", "Bias": "Bearish USD"},
        ]
        return pd.DataFrame(data)

    def get_fed_speeches(self):
        # 模拟 Fed 官员言论
        return [
            {
                "Name": "Jerome Powell", "Role": "Fed Chair", "Stance": "Neutral/Hawk",
                "Quote": "We are not confident that we have achieved a sufficiently restrictive stance.",
                "Date": "2025-12-01", "Type": "fed-neutral"
            },
            {
                "Name": "Christopher Waller", "Role": "Governor", "Stance": "Hawk (鹰派)",
                "Quote": "Inflation data has been disappointing. There is no rush to cut rates.",
                "Date": "2025-12-04", "Type": "fed-hawk"
            },
            {
                "Name": "Austan Goolsbee", "Role": "Chicago Fed Pres", "Stance": "Dove (鸽派)",
                "Quote": "The labor market is cooling faster than expected. We must be careful not to overtighten.",
                "Date": "2025-12-06", "Type": "fed-dove"
            }
        ]

engine = AdvancedDataEngine()

# ==========================================
# 3. 前端 UI 渲染
# ==========================================

st.title("🏛️ Institutional Macro & COT Dashboard V4")
st.caption(f"Last Updated: {CURRENT_DATE} | Status: US Gov Shutdown Simulated")

# --- 1. COT Section (你满意的部分，保持不变) ---
st.markdown("### 1. Smart Money Positioning (COT)")
cot_data = engine.get_cot_data()
cols = st.columns(3)
for i, asset in enumerate(cot_data):
    color_class = "delta-pos" if asset['change'] > 0 else "delta-neg"
    arrow = "▲" if asset['change'] > 0 else "▼"
    with cols[i]:
        st.markdown(f"""
        <div class="metric-card">
            <div class="card-header">{asset['name']} Futures</div>
            <div class="card-value">{asset['pos']:,}</div>
            <div class="card-delta {color_class}">
                {arrow} {asset['change']:,} WoW
            </div>
            <div style="font-size:12px; color:#666; margin-top:5px;">Report Date: {asset['date']} (Lagging)</div>
        </div>
        """, unsafe_allow_html=True)

st.markdown("---")

# --- 2. Macro Data (修复乱码部分) ---
st.markdown("### 2. Macroeconomic Matrix (Fixed)")
st.markdown("关键经济数据日历。**High Impact** 事件以红色高亮显示。")

macro_df = engine.get_macro_data()

# 使用 Streamlit 原生 dataframe 渲染，彻底解决乱码
# 并使用 column_config 进行美化
st.dataframe(
    macro_df,
    use_container_width=True,
    hide_index=True,
    column_config={
        "Impact": st.column_config.TextColumn(
            "Impact Level",
            help="Market Volatility Potential",
            validate="^(HIGH|MED|LOW|CRITICAL)$",
        ),
        "Bias": st.column_config.TextColumn(
            "Market Bias",
            help="Directional Bias for USD",
        ),
    }
)

# --- 3. Market Impact & Fed Radar (全新升级) ---
st.markdown("---")
col_impact, col_fed = st.columns([1, 1])

# 左侧：Market Impact Analysis (具体化数据和日期)
with col_impact:
    st.markdown("### 🎯 Market Impact Analysis")
    st.info("Focus Event: Non-Farm Payrolls (NFP)")
    
    # 使用表格布局展示具体 Impact 数据
    st.markdown(f"""
    <div style="background-color:#161b22; padding:15px; border-radius:8px;">
        <table style="width:100%; color:#e0e0e0;">
            <tr>
                <td style="color:#8b949e;">Data Release Date:</td>
                <td style="text-align:right; font-weight:bold;">2025-12-05 (Last Friday)</td>
            </tr>
            <tr>
                <td style="color:#8b949e;">Actual Reading:</td>
                <td style="text-align:right; font-weight:bold; color:#f85149;">150K (Missed Exp)</td>
            </tr>
            <tr style="border-top:1px solid #333;">
                <td style="padding-top:10px;">📉 <strong>USD Impact</strong></td>
                <td style="text-align:right; padding-top:10px;"><strong>Bearish</strong> <br><span style="font-size:11px; color:#8b949e;">DXY dropped to 103.50</span></td>
            </tr>
            <tr>
                <td>📈 <strong>Gold Impact</strong></td>
                <td style="text-align:right;"><strong>Bullish</strong> <br><span style="font-size:11px; color:#8b949e;">XAU surged to 2050.00</span></td>
            </tr>
        </table>
    </div>
    """, unsafe_allow_html=True)
    
    st.markdown("#### Next Watchlist:")
    st.write("📅 **2025-12-10 (In 2 days):** FOMC Rate Decision")
    st.write("📅 **2025-12-12:** Retail Sales")

# 右侧：Fed Radar (多成员言论)
with col_fed:
    st.markdown("### 🦅 Fed Speaker Radar (FOMC)")
    st.markdown("追踪美联储核心成员的**鹰派 (Hawk)** vs **鸽派 (Dove)** 立场。")
    
    speeches = engine.get_fed_speeches()
    
    for speech in speeches:
        # 渲染漂亮的言论卡片
        st.markdown(f"""
        <div class="fed-card {speech['Type']}">
            <div class="fed-name">{speech['Name']} <span style="font-size:12px; font-weight:normal; color:#aaa;">| {speech['Role']}</span></div>
            <div class="fed-role" style="color:{'#f85149' if 'Hawk' in speech['Stance'] else '#3fb950' if 'Dove' in speech['Stance'] else '#d29922'};">
                {speech['Stance']}
            </div>
            <div class="fed-quote">“{speech['Quote']}”</div>
            <div class="fed-date">Speech Date: {speech['Date']}</div>
        </div>
        """, unsafe_allow_html=True)

# 底部免责
st.markdown("---")
st.caption("Disclaimer: Simulated Data for Dec 2025 Scenario. Trading involves significant risk.")
