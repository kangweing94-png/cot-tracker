import streamlit as st
import pandas as pd
import numpy as np
import datetime
import plotly.express as px
import time

# ==========================================
# 1. 页面配置与机构级样式
# ==========================================
st.set_page_config(page_title="Institutional Macro Dashboard V5", layout="wide", page_icon="🏦")

# 模拟当前日期
CURRENT_DATE = datetime.date(2025, 12, 8)

st.markdown("""
<style>
    .stApp { background-color: #0b0e11; color: #e0e0e0; }
    
    /* COT 卡片样式 */
    .metric-card {
        background-color: #161b22;
        border: 1px solid #30363d;
        padding: 15px;
        border-radius: 8px;
        margin-bottom: 5px; /* 减少底部边距，为图表留空间 */
    }
    .card-header { font-size: 13px; color: #8b949e; text-transform: uppercase; letter-spacing: 0.5px; }
    .card-value { font-size: 24px; font-weight: 700; color: #f0f6fc; font-family: 'Roboto Mono', monospace; margin: 5px 0; }
    .card-delta { font-size: 13px; font-weight: 500; }
    .delta-pos { color: #3fb950; }
    .delta-neg { color: #f85149; }
    .card-sub { font-size: 11px; color: #666; margin-top: 5px; }
    
    /* Fed 讲话卡片 */
    .fed-card { background-color: #1c2128; border-left: 4px solid #333; padding: 15px; margin-bottom: 10px; border-radius: 4px; }
    .fed-hawk { border-left-color: #f85149; }
    .fed-dove { border-left-color: #3fb950; }
    .fed-neutral { border-left-color: #d29922; }
    .fed-name { font-weight: bold; font-size: 15px; color: #fff; }
    .fed-role { font-size: 12px; color: #8b949e; margin-bottom: 8px; }
    .fed-quote { font-style: italic; color: #d0d7de; font-size: 13px; }

</style>
""", unsafe_allow_html=True)

# ==========================================
# 2. 数据引擎 (Data Engine V5)
# ==========================================

class DataEngineV5:
    def __init__(self):
        # 生成模拟历史数据用于图表
        self.dates = pd.date_range(start="2024-06-01", end="2025-10-28", freq="W-TUE")
        
    def _generate_history(self, base, volatility):
        # 生成带随机波动的历史序列
        np.random.seed(42) # 固定随机种子保证演示一致性
        changes = np.random.normal(0, volatility, len(self.dates))
        values = base + np.cumsum(changes)
        return pd.DataFrame({"Date": self.dates, "Net_Positions": values})

    def get_cot_data(self):
        # 模拟三种资产的历史数据
        eur_hist = self._generate_history(base=-10000, volatility=5000)
        gbp_hist = self._generate_history(base=5000, volatility=3000)
        xau_hist = self._generate_history(base=180000, volatility=8000)

        # 计算最新值和变化
        def get_stats(df):
            latest = df.iloc[-1]['Net_Positions']
            prev = df.iloc[-2]['Net_Positions']
            change = latest - prev
            return latest, change, df

        eur_pos, eur_chg, eur_df = get_stats(eur_hist)
        gbp_pos, gbp_chg, gbp_df = get_stats(gbp_hist)
        xau_pos, xau_chg, xau_df = get_stats(xau_hist)

        return [
            {"name": "EUR/USD", "pos": eur_pos, "change": eur_chg, "date": "2025-10-28", "history": eur_df, "color": "#FFD700"},
            {"name": "GBP/USD", "pos": gbp_pos, "change": gbp_chg, "date": "2025-10-28", "history": gbp_df, "color": "#00CED1"},
            {"name": "GOLD (XAU)", "pos": xau_pos, "change": xau_chg, "date": "2025-10-28", "history": xau_df, "color": "#FFA500"},
        ]

    def get_macro_data(self):
        # 增加 Link 列
        data = [
            {"Event": "Non-Farm Payrolls", "Date": "2025-12-05", "Actual": "150K", "Forecast": "180K", "Impact": "HIGH", "Bias": "Bearish USD", "Link": "https://www.bls.gov/news.release/empsit.nr0.htm"},
            {"Event": "CPI (YoY)", "Date": "2025-11-12", "Actual": "3.2%", "Forecast": "3.0%", "Impact": "HIGH", "Bias": "Bullish USD", "Link": "https://www.bls.gov/cpi/"},
            {"Event": "FOMC Rate Decision", "Date": "2025-11-06", "Actual": "5.25%", "Forecast": "5.25%", "Impact": "CRITICAL", "Bias": "Neutral", "Link": "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm"},
            {"Event": "Core PCE (MoM)", "Date": "2025-11-29", "Actual": "0.3%", "Forecast": "0.2%", "Impact": "HIGH", "Bias": "Bullish USD", "Link": "https://www.bea.gov/data/personal-consumption-expenditures-price-index"},
            {"Event": "ISM Mfg PMI", "Date": "2025-12-01", "Actual": "48.5", "Forecast": "49.0", "Impact": "MED", "Bias": "Bearish USD", "Link": "https://www.ismworld.org/"},
        ]
        return pd.DataFrame(data)

    def get_fed_speeches(self):
        # (保持不变)
        return [
            {"Name": "Jerome Powell", "Role": "Fed Chair", "Stance": "Neutral/Hawk", "Quote": "We need more evidence that inflation is sustainably down.", "Date": "2025-12-01", "Type": "fed-neutral"},
            {"Name": "Christopher Waller", "Role": "Governor", "Stance": "Hawk (鹰派)", "Quote": "The recent data suggests we should hold rates higher for longer.", "Date": "2025-12-04", "Type": "fed-hawk"},
            {"Name": "Austan Goolsbee", "Role": "Chicago Fed Pres", "Stance": "Dove (鸽派)", "Quote": "We are risking excessive job losses if we stay too tight.", "Date": "2025-12-06", "Type": "fed-dove"}
        ]

engine = DataEngineV5()

# ==========================================
# 3. 前端 UI 渲染
# ==========================================

st.title("🏛️ Institutional Macro & COT Dashboard V5")
st.caption(f"Last Updated: {CURRENT_DATE} | Status: US Gov Shutdown Simulated (Data lagging)")

# --- 1. COT Section (修复：图表回归) ---
st.markdown("### 1. Smart Money Positioning (COT & Trend)")
cot_data = engine.get_cot_data()
cols = st.columns(3)
for i, asset in enumerate(cot_data):
    color_class = "delta-pos" if asset['change'] > 0 else "delta-neg"
    arrow = "▲" if asset['change'] > 0 else "▼"
    with cols[i]:
        # 卡片 HTML
        st.markdown(f"""
        <div class="metric-card">
            <div class="card-header">{asset['name']} Futures</div>
            <div class="card-value">{int(asset['pos']):,}</div>
            <div class="card-delta {color_class}">
                {arrow} {int(asset['change']):,} WoW
            </div>
            <div class="card-sub">Report Date: {asset['date']} (⚠️Lagging)</div>
        </div>
        """, unsafe_allow_html=True)
        
        # 修复点：Plotly 迷你图回归
        fig = px.area(asset['history'], x='Date', y='Net_Positions', height=120)
        fig.update_layout(
            template="plotly_dark", 
            margin=dict(l=0, r=0, t=0, b=10), # 极简边距
            xaxis=dict(visible=False, showgrid=False), 
            yaxis=dict(visible=False, showgrid=False),
            paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
            showlegend=False
        )
        fig.update_traces(line_color=asset['color'], fillcolor=asset['color'].replace(")", ", 0.3)").replace("rgb", "rgba"), line_width=1.5)
        st.plotly_chart(fig, use_container_width=True, config={'displayModeBar': False, 'staticPlot': True})

st.markdown("---")

# --- 2. Macro Data (修复：可视化增强 + 链接回归) ---
st.markdown("### 2. Macroeconomic Matrix (Enhanced Viz)")
st.markdown("关键经济数据日历。使用 **Pandas Styling** 高亮重要信息。")

macro_df = engine.get_macro_data()

# 修复点：使用 Pandas Styler 进行条件着色
styler = macro_df.style.format({"Actual": "{}"}) \
    .map(lambda v: 'color: #ff7b72; font-weight: bold;' if v in ['HIGH', 'CRITICAL'] else '', subset=['Impact']) \
    .map(lambda v: 'color: #3fb950;' if 'Bullish' in v else 'color: #f85149;' if 'Bearish' in v else '', subset=['Bias'])

# 修复点：使用 column_config 渲染链接列
st.dataframe(
    styler,
    use_container_width=True,
    hide_index=True,
    column_config={
        "Link": st.column_config.LinkColumn(
            "Source Reference",
            help="Click to visit official data source",
            validate="^https://.*",
            display_text="Official Source 🔗"
        ),
        "Impact": st.column_config.TextColumn("Impact Level"),
        "Bias": st.column_config.TextColumn("Market Bias"),
    },
    height=300
)

# --- 3. Market Impact & Fed Radar (修复：数值合理化) ---
st.markdown("---")
col_impact, col_fed = st.columns([1.2, 1]) # 调整一下比例

# 左侧：Market Impact Analysis (修复数值)
with col_impact:
    st.markdown("### 🎯 Market Impact Analysis (NFP Focus)")
    
    # 修复点：更新了模拟数值，使其看起来更合理
    st.markdown(f"""
    <div style="background-color:#161b22; padding:20px; border-radius:8px; border:1px solid #30363d;">
        <div style="margin-bottom:15px; font-size:16px;">Focus Event: <strong>Non-Farm Payrolls (NFP)</strong></div>
        <table style="width:100%; color:#e0e0e0; font-size:14px;">
            <tr>
                <td style="color:#8b949e; padding-bottom:8px;">Data Release:</td>
                <td style="text-align:right; font-weight:bold;">2025-12-05 (Last Friday)</td>
            </tr>
            <tr style="border-bottom:1px solid #333;">
                <td style="color:#8b949e; padding-bottom:15px;">Outcome:</td>
                <td style="text-align:right; font-weight:bold; color:#f85149; padding-bottom:15px;">150K (Missed Exp of 180K)</td>
            </tr>
            <tr>
                <td style="padding-top:15px;">📉 <strong>USD Reaction</strong></td>
                <td style="text-align:right; padding-top:15px;"><strong>Bearish</strong> <br><span style="font-size:12px; color:#f85149;">DXY index dropped -0.6% to 103.50</span></td>
            </tr>
            <tr>
                <td style="padding-top:10px;">📈 <strong>Gold Reaction</strong></td>
                <td style="text-align:right; padding-top:10px;"><strong>Bullish</strong> <br><span style="font-size:12px; color:#3fb950;">XAU/USD rallied +$25 to $2050.00</span></td>
            </tr>
        </table>
    </div>
    <div style="margin-top:15px; font-size:13px; color:#888;">Note: Market reactions are simulated based on the 'Missed Expectation' scenario.</div>
    """, unsafe_allow_html=True)

# 右侧：Fed Radar (保持不变)
with col_fed:
    st.markdown("### 🦅 Fed Speaker Radar (FOMC)")
    speeches = engine.get_fed_speeches()
    for speech in speeches:
        st.markdown(f"""
        <div class="fed-card {speech['Type']}">
            <div class="fed-name">{speech['Name']} <span style="font-size:12px; font-weight:normal; color:#aaa;">| {speech['Role']}</span></div>
            <div class="fed-role" style="color:{'#f85149' if 'Hawk' in speech['Stance'] else '#3fb950' if 'Dove' in speech['Stance'] else '#d29922'};">
                {speech['Stance']}
            </div>
            <div class="fed-quote">“{speech['Quote']}”</div>
            <div class="fed-date" style="text-align:right; font-size:11px; margin-top:5px; color:#666;">{speech['Date']}</div>
        </div>
        """, unsafe_allow_html=True)

st.markdown("---")
st.caption("Disclaimer: Simulated Data for Dec 2025 Scenario. Trading involves significant risk.")
