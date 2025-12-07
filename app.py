import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import cot_reports as cot
import datetime

# --- 页面设置 ---
st.set_page_config(page_title="COT Tracker Pro", page_icon="📈", layout="centered")

st.title("COT 机构持仓追踪 (Smart Fix)")
st.info("数据来源: CFTC 官方报告 (Legacy Report - Futures Only)")

# --- 核心函数: 获取数据 ---
@st.cache_data(ttl=3600*6)
def get_cftc_data():
    current_year = datetime.datetime.now().year
    try:
        # 优先下载 2025 数据
        df = cot.cot_year(current_year, cot_report_type='legacy_fut')
    except Exception:
        # 如果失败，回退到 2024
        df = cot.cot_year(current_year - 1, cot_report_type='legacy_fut')
    return df

# --- 智能列名搜索 (解决报错的关键) ---
def find_column(columns, keywords):
    """
    在所有列名中，寻找包含所有关键词的那一列。
    例如: keywords=['non', 'comm', 'long'] -> 匹配 'Non-Commercial Positions-Long (All)'
    """
    for col in columns:
        # 把列名转成小写来比较，忽略大小写差异
        col_lower = str(col).lower()
        # 检查是否包含所有关键词
        if all(k in col_lower for k in keywords):
            return col
    return None

# --- 数据处理 ---
def process_data(df, name_keywords):
    # 1. 寻找合约名称列 (Contract Name)
    name_col = find_column(df.columns, ['contract', 'name']) or \
               find_column(df.columns, ['market', 'exchange'])
    
    if not name_col:
        st.error(f"严重错误: 找不到合约名称列。")
        st.write("现有列名:", list(df.columns))
        st.stop()

    # 2. 筛选品种 (比如 XAUUSD)
    # 只要包含关键词就匹配 (例如 "GOLD")
    mask = df[name_col].apply(lambda x: any(k in str(x).upper() for k in name_keywords))
    data = df[mask].copy()
    
    if data.empty:
        return pd.DataFrame()

    # 3. 寻找日期列
    date_col = find_column(df.columns, ['date', 'yyyy']) or \
               find_column(df.columns, ['report', 'date'])
    
    if date_col:
        data[date_col] = pd.to_datetime(data[date_col])
        data = data.sort_values(date_col)
    
    # 4. 寻找多空持仓列 (关键步骤)
    # 我们找包含 "non", "comm", "long" 的列 -> 多头
    long_col = find_column(df.columns, ['non', 'comm', 'long'])
    # 我们找包含 "non", "comm", "short" 的列 -> 空头
    short_col = find_column(df.columns, ['non', 'comm', 'short'])

    # 如果还是找不到，把所有列名打印出来给用户看 (调试用)
    if not long_col or not short_col:
        st.error("无法找到 'Non-Commercial' 持仓数据列。")
        st.write("请检查下方的所有列名，寻找类似 'Non-Comm' 的字段:")
        st.write(list(df.columns)) # 打印出所有列名以便排查
        st.stop()

    # 计算净持仓
    data['Net_Pos'] = data[long_col] - data[short_col]
    data['Date_Display'] = data[date_col]
    
    return data.tail(52) # 只取最近一年

# --- 主程序 ---
with st.spinner('正在获取数据并智能解析...'):
    try:
        raw_df = get_cftc_data()
        
        # 定义搜索关键词
        data_gold = process_data(raw_df, ["GOLD", "COMMODITY"])
        data_euro = process_data(raw_df, ["EURO FX", "CHICAGO"])
        data_gbp  = process_data(raw_df, ["BRITISH POUND", "STERLING"])
        
    except Exception as e:
        st.error(f"发生未知错误: {e}")
        st.stop()

# --- 绘图 ---
def render_chart(data, title, color_code):
    if data.empty:
        st.warning(f"暂无数据: {title}")
        return

    last_date = data['Date_Display'].iloc[-1].strftime('%Y-%m-%d')
    current_net = data['Net_Pos'].iloc[-1]
    
    if len(data) > 1:
        prev_net = data['Net_Pos'].iloc[-2]
        delta = current_net - prev_net
    else:
        delta = 0
    
    sentiment_color = "green" if current_net > 0 else "red"
    sentiment_text = "Bullish" if current_net > 0 else "Bearish"

    st.metric(label=f"Net Positions ({last_date})", value=f"{int(current_net):,}", delta=f"{int(delta):,}")
    st.caption(f"Sentiment: :{sentiment_color}[{sentiment_text}]")

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=data['Date_Display'], 
        y=data['Net_Pos'],
        mode='lines+markers',
        name='Net Speculator',
        line=dict(color=color_code, width=2),
        fill='tozeroy'
    ))

    fig.update_layout(
        title=title,
        height=350,
        margin=dict(l=20, r=20, t=40, b=20),
        plot_bgcolor='rgba(0,0,0,0)',
        paper_bgcolor='rgba(0,0,0,0)',
        font=dict(color="white"),
        xaxis=dict(showgrid=False),
        yaxis=dict(showgrid=True, gridcolor='#333')
    )
    st.plotly_chart(fig, use_container_width=True)

# --- 选项卡 ---
tab1, tab2, tab3 = st.tabs(["Gold", "Euro", "GBP"])

with tab1:
    render_chart(data_gold, "Gold (XAUUSD) Net Positions", "#FFD700")
with tab2:
    render_chart(data_euro, "Euro (EURUSD) Net Positions", "#00d2ff")
with tab3:
    render_chart(data_gbp, "Pound (GBPUSD) Net Positions", "#eb4034")
