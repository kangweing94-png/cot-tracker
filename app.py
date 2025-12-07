import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import cot_reports as cot
import datetime

# --- 页面设置 ---
st.set_page_config(page_title="COT Pro Dashboard", page_icon="📊", layout="wide") # 改为宽屏模式

st.title("COT 机构持仓透视 (Pro Visuals)")
st.markdown("""
<style>
/* 简单的 CSS 让指标卡片更好看 */
div[data-testid="metric-container"] {
    background-color: #262730;
    padding: 15px;
    border-radius: 10px;
    border: 1px solid #444;
}
</style>
""", unsafe_allow_html=True)

# --- 核心数据逻辑 ---
@st.cache_data(ttl=3600*6)
def get_cftc_data():
    current_year = datetime.datetime.now().year
    try:
        df = cot.cot_year(current_year, cot_report_type='legacy_fut')
    except:
        df = cot.cot_year(current_year - 1, cot_report_type='legacy_fut')
    return df

def find_column(columns, keywords):
    for col in columns:
        col_lower = str(col).lower()
        if all(k in col_lower for k in keywords):
            return col
    return None

def process_data(df, name_keywords):
    # 1. 找名字
    name_col = find_column(df.columns, ['contract', 'name']) or \
               find_column(df.columns, ['market', 'exchange'])
    if not name_col: return pd.DataFrame()

    # 2. 筛选
    mask = df[name_col].apply(lambda x: any(k in str(x).upper() for k in name_keywords))
    data = df[mask].copy()
    if data.empty: return pd.DataFrame()

    # 3. 找日期
    date_col = find_column(df.columns, ['date', 'yyyy']) or \
               find_column(df.columns, ['report', 'date'])
    data[date_col] = pd.to_datetime(data[date_col])
    
    # 4. 找多空
    long_col = find_column(df.columns, ['non', 'comm', 'long'])
    short_col = find_column(df.columns, ['non', 'comm', 'short'])
    
    # 5. 计算并清洗 (关键步骤：去重和排序)
    data['Net_Pos'] = data[long_col] - data[short_col]
    data['Date_Display'] = data[date_col]
    
    # ⚠️ 关键修复：去除同一日期的重复数据，并按日期严格排序
    data = data.sort_values('Date_Display')
    data = data.drop_duplicates(subset=['Date_Display'], keep='last')
    
    return data.tail(52) # 最近一年

# --- 🔥 全新升级的绘图引擎 ---
def render_pro_chart(data, title, main_color):
    if data.empty:
        st.warning(f"Waiting for data: {title}")
        return

    # 准备数据
    last_date = data['Date_Display'].iloc[-1].strftime('%Y-%m-%d')
    current_net = data['Net_Pos'].iloc[-1]
    prev_net = data['Net_Pos'].iloc[-2] if len(data) > 1 else current_net
    change = current_net - prev_net
    
    # 情绪判断
    is_bullish = current_net > 0
    sentiment_color = "#00FF7F" if is_bullish else "#FF4B4B" # 荧光绿 vs 亮红
    sentiment_text = "Strong Bullish (强势看多)" if current_net > 0 else "Bearish (看空)"

    # --- 布局：左边指标，右边图表 ---
    col1, col2 = st.columns([1, 3])
    
    with col1:
        st.markdown(f"### {title.split(' ')[0]}") # 显示品种名
        st.caption(f"Report Date: {last_date}")
        
        # 自定义大字体指标
        st.metric(
            label="Net Positions (净持仓)", 
            value=f"{int(current_net):,}", 
            delta=f"{int(change):,}"
        )
        
        # 情绪卡片
        st.markdown(f"""
        <div style="margin-top: 20px; padding: 10px; border-radius: 5px; background-color: rgba(255,255,255,0.05); border-left: 5px solid {sentiment_color}">
            <small style="color: #aaa">Market Sentiment</small><br>
            <strong style="color: {sentiment_color}; font-size: 1.1em">{sentiment_text}</strong>
        </div>
        """, unsafe_allow_html=True)

    with col2:
        fig = go.Figure()

        # 1. 0轴基准线 (参考线)
        fig.add_hline(y=0, line_dash="dash", line_color="gray", opacity=0.5)

        # 2. 主数据线 (平滑曲线 + 渐变填充)
        fig.add_trace(go.Scatter(
            x=data['Date_Display'], 
            y=data['Net_Pos'],
            mode='lines', # 去掉markers让线条更干净，鼠标放上去会有显示
            name='Net Positions',
            line=dict(
                color=main_color, 
                width=3, 
                shape='spline', # 🔥 关键：让线条变得圆润平滑
                smoothing=1.3
            ),
            fill='tozeroy', # 填充到底部0轴
            fillcolor=f"rgba{main_color[3:-1]}, 0.1)" if main_color.startswith('rgba') else main_color.replace(')', ', 0.1)').replace('rgb', 'rgba') 
            # 注意：这里为了简单，你可以把颜色代码换成带透明度的，比如下面我有处理
        ))
        
        # 更新颜色为带透明度的填充
        if main_color == "#FFD700": fill_c = "rgba(255, 215, 0, 0.2)"
        elif main_color == "#00d2ff": fill_c = "rgba(0, 210, 255, 0.2)"
        else: fill_c = "rgba(235, 64, 52, 0.2)"
        
        fig.update_traces(fillcolor=fill_c)

        fig.update_layout(
            title=dict(text=f"{title} Trend", font=dict(size=14, color="#aaa")),
            height=400,
            margin=dict(l=0, r=20, t=30, b=0),
            plot_bgcolor='rgba(0,0,0,0)',
            paper_bgcolor='rgba(0,0,0,0)',
            hovermode="x unified", # 鼠标移动时显示十字准星
            xaxis=dict(
                showgrid=False, 
                title="",
                type="date",
                tickformat="%Y-%m-%d" # 强制显示日期格式
            ),
            yaxis=dict(
                showgrid=True, 
                gridcolor='#333', 
                zeroline=False
            )
        )
        st.plotly_chart(fig, use_container_width=True)
    
    st.divider() # 分割线

# --- 主程序 ---
with st.spinner('Syncing w/ CFTC Servers...'):
    df = get_cftc_data()
    
    # 获取数据
    gold = process_data(df, ["GOLD", "COMMODITY"])
    euro = process_data(df, ["EURO FX", "CHICAGO"])
    gbp = process_data(df, ["BRITISH POUND", "STERLING"])

# --- 渲染界面 (瀑布流式布局) ---
render_pro_chart(gold, "Gold (XAU) / USD", "#FFD700")
render_pro_chart(euro, "Euro (EUR) / USD", "#00d2ff")
render_pro_chart(gbp, "Pound (GBP) / USD", "#eb4034")
