import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import cot_reports as cot

# --- 页面设置 ---
st.set_page_config(page_title="COT Tracker Pro", page_icon="📈", layout="centered")

st.title("COT 机构持仓追踪 (Real Data)")
st.info("数据来源: CFTC 官方报告 (Legacy Report - Futures Only)")

# --- 核心函数: 获取真实数据 ---
@st.cache_data(ttl=3600*12) # 缓存12小时，避免每次刷新都去爬CFTC官网
def get_cftc_data():
    # 1. 下载当年的最新 COT 报告 (Legacy 格式是交易员最常用的)
    # 注意: 年份这里写 2024 或 2025，或者用代码自动获取当前年份
    try:
        df = cot.cot_year(2024, cot_report_type='legacy_fut')
    except:
        # 如果2024还没数据或报错，尝试2023作为备用
        df = cot.cot_year(2023, cot_report_type='legacy_fut')
    
    return df

# --- 数据处理函数 ---
def process_data(df, contract_name_keyword):
    # 1. 筛选特定品种 (比如 "GOLD")
    # 我们使用模糊匹配，只要名字里包含关键字就选出来
    mask = df['Contract Name'].str.contains(contract_name_keyword, case=False)
    data = df[mask].copy()
    
    # 2. 整理日期格式
    data['As of Date in Form YYYY-MM-DD'] = pd.to_datetime(data['As of Date in Form YYYY-MM-DD'])
    data = data.sort_values('As of Date in Form YYYY-MM-DD')
    
    # 3. 计算"投机者净持仓" (Net Non-Commercial)
    # 公式 = Non-Commercial Long - Non-Commercial Short
    data['Net_Pos'] = data['Non-Commercial Positions-Long (All)'] - data['Non-Commercial Positions-Short (All)']
    
    return data.tail(20) # 只取最近20周的数据

# --- 加载数据 (显示加载动画) ---
with st.spinner('正在连接 CFTC 官网下载最新数据...'):
    try:
        raw_df = get_cftc_data()
        
        # 定义我们要追踪的三个品种在 CFTC 报告里的名字
        # 这些名字是 CFTC 的官方标准写法
        data_gold = process_data(raw_df, "GOLD - COMMODITY EXCHANGE INC")
        data_euro = process_data(raw_df, "EURO FX - CHICAGO MERCANTILE EXCHANGE")
        data_gbp  = process_data(raw_df, "BRITISH POUND STERLING - CHICAGO MERCANTILE EXCHANGE")
        
    except Exception as e:
        st.error(f"数据获取失败: {e}")
        st.stop()

# --- 绘图函数 ---
def render_chart(data, title, color_code):
    if data.empty:
        st.warning("暂无数据，请检查年份或合约名称。")
        return

    last_date = data['As of Date in Form YYYY-MM-DD'].iloc[-1].strftime('%Y-%m-%d')
    current_net = data['Net_Pos'].iloc[-1]
    prev_net = data['Net_Pos'].iloc[-2]
    delta = current_net - prev_net
    
    # 颜色逻辑
    sentiment_color = "green" if current_net > 0 else "red"
    sentiment_text = "Bullish (看涨)" if current_net > 0 else "Bearish (看跌)"

    # 1. 指标卡片
    st.metric(label=f"Net Positions ({last_date})", value=f"{int(current_net):,}", delta=f"{int(delta):,}")
    st.caption(f"机构情绪: :{sentiment_color}[{sentiment_text}]")

    # 2. 画图
    fig = go.Figure()
    
    # 净持仓线
    fig.add_trace(go.Bar(
        x=data['As of Date in Form YYYY-MM-DD'], 
        y=data['Net_Pos'],
        name='Net Speculator Pos',
        marker_color=color_code
    ))

    fig.update_layout(
        title=title,
        xaxis_title="Date",
        yaxis_title="Net Contracts",
        height=350,
        plot_bgcolor='rgba(0,0,0,0)',
        paper_bgcolor='rgba(0,0,0,0)',
        font=dict(color="white")
    )
    st.plotly_chart(fig, use_container_width=True)

# --- 界面展示 ---
tab1, tab2, tab3 = st.tabs(["Gold (XAU)", "Euro (EUR)", "Pound (GBP)"])

with tab1:
    render_chart(data_gold, "Gold Non-Commercial Net Positions", "#FFD700")
with tab2:
    render_chart(data_euro, "Euro FX Non-Commercial Net Positions", "#00d2ff")
with tab3:
    render_chart(data_gbp, "British Pound Non-Commercial Net Positions", "#eb4034")
