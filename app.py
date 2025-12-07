import streamlit as st
import pandas as pd
import plotly.graph_objects as go

# --- 页面设置 ---
st.set_page_config(page_title="COT Tracker", page_icon="📈", layout="centered")

# 为了在手机上好看，隐藏默认的菜单和页脚
hide_st_style = """
            <style>
            #MainMenu {visibility: hidden;}
            footer {visibility: hidden;}
            header {visibility: hidden;}
            /* 调整手机端内边距 */
            .block-container {padding-top: 1rem; padding-bottom: 0rem;}
            </style>
            """
st.markdown(hide_st_style, unsafe_allow_html=True)

st.title("COT 机构持仓追踪")

# --- 模拟数据 (这里以后可以用 Python 爬虫替换) ---
# 结构：日期，投机者净持仓 (Net Non-Commercial)
data_source = {
    'XAUUSD (Gold)': {
        'dates': ['2023-11-01', '2023-11-08', '2023-11-15', '2023-11-22', '2023-11-29'],
        'net_positions': [180000, 195000, 210000, 198000, 205000],
        'sentiment': '看涨 (Bullish)'
    },
    'EURUSD (Euro)': {
        'dates': ['2023-11-01', '2023-11-08', '2023-11-15', '2023-11-22', '2023-11-29'],
        'net_positions': [-15000, -12000, 5000, 12000, 8000],
        'sentiment': '中性 (Neutral)'
    },
    'GBPUSD (Pound)': {
        'dates': ['2023-11-01', '2023-11-08', '2023-11-15', '2023-11-22', '2023-11-29'],
        'net_positions': [-25000, -30000, -28000, -15000, -10000],
        'sentiment': '看跌 (Bearish)'
    }
}

# --- 选项卡界面 ---
tab1, tab2, tab3 = st.tabs(["XAUUSD", "EURUSD", "GBPUSD"])

def render_tab(pair_name):
    data = data_source[pair_name]
    current_net = data['net_positions'][-1]
    prev_net = data['net_positions'][-2]
    delta = current_net - prev_net
    
    # 1. 显示关键指标
    col1, col2 = st.columns(2)
    with col1:
        st.metric(label="最新净持仓 (Net)", value=f"{current_net:,}", delta=f"{delta:,}")
    with col2:
        st.info(f"情绪: {data['sentiment']}")
        
    # 2. 绘制图表 (使用 Plotly，手机交互更好)
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=data['dates'], 
        y=data['net_positions'],
        mode='lines+markers',
        name='Net Positions',
        line=dict(color='#00d2ff', width=3),
        fill='tozeroy' # 填充颜色
    ))
    
    fig.update_layout(
        title=f"{pair_name} 机构净持仓趋势",
        xaxis_title="",
        yaxis_title="合约数量",
        margin=dict(l=20, r=20, t=40, b=20),
        height=300,
        paper_bgcolor='rgba(0,0,0,0)', # 透明背景
        plot_bgcolor='rgba(0,0,0,0)',
        font=dict(color="white")
    )
    
    st.plotly_chart(fig, use_container_width=True)
    
    st.caption("数据来源: CFTC (Simulated)")

with tab1:
    render_tab('XAUUSD (Gold)')
with tab2:
    render_tab('EURUSD (Euro)')
with tab3:
    render_tab('GBPUSD (Pound)')