import streamlit as st
import pandas as pd
import numpy as np
import datetime
import plotly.express as px
import plotly.graph_objects as go
import time

# ==========================================
# 1. 页面配置与样式
# ==========================================
st.set_page_config(page_title="Smart Money Dashboard (Fixed)", layout="wide", page_icon="🏦")

# 模拟当前日期 (根据你的截图设定)
CURRENT_DATE = datetime.date(2025, 12, 8)

# 自定义 CSS 样式，还原你的黑金风格
st.markdown("""
<style>
    .stApp { background-color: #0e1117; }
    .metric-card {
        background-color: #1e1e1e;
        border: 1px solid #333;
        padding: 20px;
        border-radius: 10px;
        margin-bottom: 10px;
    }
    .metric-label { font-size: 14px; color: #aaa; }
    .metric-value { font-size: 28px; font-weight: bold; color: #fff; }
    .metric-delta { font-size: 14px; }
    .stAlert { background-color: #3d0c0c; border: 1px solid #ff4b4b; color: #ff4b4b; }
</style>
""", unsafe_allow_html=True)

# ==========================================
# 2. 核心修复逻辑：数据处理引擎
# ==========================================

class DataEngine:
    def __init__(self):
        # 模拟加载 CFTC CSV 数据
        # 在实际使用中，这里替换为 pd.read_csv('your_cftc_data.csv')
        self.df_cftc = self._generate_mock_cftc_data()

    def _generate_mock_cftc_data(self):
        """生成模拟数据，截止日期特意设为 2025-10-28 (模拟政府停摆)"""
        dates = pd.date_range(start="2024-01-01", end="2025-10-28", freq="W-TUE")
        data = []
        
        # 模拟三种资产的数据波动
        for d in dates:
            # Gold
            data.append({"Market_and_Exchange_Names": "GOLD - COMMODITY EXCHANGE INC.", "Report_Date_as_MM_DD_YYYY": d, "Net_Positions": 200000 + np.random.randint(-50000, 50000)})
            # Euro (注意：这里模拟官方名称叫 EURO FX)
            data.append({"Market_and_Exchange_Names": "EURO FX - CHICAGO MERCANTILE EXCHANGE", "Report_Date_as_MM_DD_YYYY": d, "Net_Positions": -15000 + np.random.randint(-20000, 20000)})
            # GBP (注意：这里模拟官方名称叫 BRITISH POUND STERLING)
            data.append({"Market_and_Exchange_Names": "BRITISH POUND STERLING - CHICAGO MERCANTILE EXCHANGE", "Report_Date_as_MM_DD_YYYY": d, "Net_Positions": 12000 + np.random.randint(-10000, 10000)})
            
        return pd.DataFrame(data)

    def get_cot_position(self, asset_keywords):
        """
        【修复点 1 & 2】
        1. 使用关键词模糊匹配 (contains)，不再精确匹配。
        2. 即使数据严重滞后，也返回最后一条数据，而不是 None。
        """
        # 1. 模糊匹配名称
        mask = self.df_cftc['Market_and_Exchange_Names'].str.contains('|'.join(asset_keywords), case=False, na=False)
        asset_df = self.df_cftc[mask].copy()
        
        if asset_df.empty:
            return None, None, "未找到资产"

        # 2. 确保按日期排序
        asset_df['Report_Date_as_MM_DD_YYYY'] = pd.to_datetime(asset_df['Report_Date_as_MM_DD_YYYY'])
        asset_df = asset_df.sort_values('Report_Date_as_MM_DD_YYYY')

        # 3. 获取最新一条数据 (哪怕它是 40 天前的)
        latest_record = asset_df.iloc[-1]
        latest_date = latest_record['Report_Date_as_MM_DD_YYYY'].date()
        latest_val = latest_record['Net_Positions']
        
        # 计算滞后天数
        lag_days = (CURRENT_DATE - latest_date).days
        
        status = "正常"
        if lag_days > 14:
            status = f"⚠️ 滞后 {lag_days} 天 (停摆中)"
        
        return latest_val, asset_df, status

    def get_fred_data_safe(self):
        """
        【修复点 3】FRED 数据模拟与兜底
        """
        try:
            # 模拟 API 请求延时
            time.sleep(0.5)
            # 生成模拟宏观数据
            dates = pd.date_range(start="2024-01-01", end="2025-11-01", freq="MS")
            values = [3.5 + np.random.normal(0, 0.1) for _ in range(len(dates))]
            return pd.DataFrame({"Date": dates, "Unemployment Rate": values})
        except Exception as e:
            return None

# 初始化引擎
engine = DataEngine()

# ==========================================
# 3. 前端 UI 渲染
# ==========================================

st.title("Smart Money & Macro Dashboard (v2.0 Fixed)")

# --- 顶部警报 ---
st.error(f"🚨 MARKET ALERT: 检测到数据严重滞后 (41天)。原因：美国政府停摆 (2025-10)。当前显示为 2025-10-28 的最后快照。")

st.markdown("### 🏛️ COT 持仓深度分析")

# 定义要展示的资产
assets_config = [
    {"name": "Euro (EUR)", "keywords": ["EURO FX", "EURO", "EC"], "color": "#FFD700"},
    {"name": "British Pound (GBP)", "keywords": ["BRITISH POUND", "STERLING", "GBP"], "color": "#00CED1"},
    {"name": "Gold (XAU)", "keywords": ["GOLD", "XAU"], "color": "#FFA500"},
]

cols = st.columns(3)

for idx, asset in enumerate(assets_config):
    with cols[idx]:
        # 调用修复后的获取函数
        net_pos, df_hist, status = engine.get_cot_position(asset["keywords"])
        
        if net_pos is not None:
            # UI 卡片渲染
            st.markdown(f"""
            <div class="metric-card">
                <div class="metric-label">{asset['name']} - Net Positions</div>
                <div class="metric-value">{int(net_pos):,}</div>
                <div class="metric-delta" style="color: {'#ff4b4b' if '滞后' in status else '#00ff00'};">
                    {status} | Date: {df_hist.iloc[-1]['Report_Date_as_MM_DD_YYYY'].date()}
                </div>
            </div>
            """, unsafe_allow_html=True)
            
            # 绘制迷你图表
            fig = px.area(df_hist, x='Report_Date_as_MM_DD_YYYY', y='Net_Positions', 
                          template="plotly_dark", height=150)
            fig.update_layout(margin=dict(l=0, r=0, t=0, b=0), 
                              xaxis_title=None, yaxis_title=None, 
                              showlegend=False)
            fig.update_traces(line_color=asset['color'], fillcolor=asset['color'].replace(")", ", 0.2)").replace("rgb", "rgba"))
            st.plotly_chart(fig, use_container_width=True, config={'displayModeBar': False})
        else:
            st.warning(f"{asset['name']} 数据加载失败")

st.markdown("---")

# --- 宏观部分 (修复了之前的空白) ---
st.markdown("### 🌍 宏观经济 (FRED 数据)")

fred_data = engine.get_fred_data_safe()

if fred_data is not None:
    # 显示宏观图表
    fig_macro = px.line(fred_data, x="Date", y="Unemployment Rate", title="US Unemployment Rate (Mock Data)",
                        template="plotly_dark", height=300)
    fig_macro.update_traces(line_color="#00ff00", line_width=3)
    st.plotly_chart(fig_macro, use_container_width=True)
else:
    st.error("FRED 数据源连接失败，请检查 API Key。")

# 底部状态栏
st.info(f"系统当前时间: {CURRENT_DATE} | 下次 FOMC: 2天后")
