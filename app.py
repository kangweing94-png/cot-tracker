import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import cot_reports as cot
import datetime

# --- 页面设置 ---
st.set_page_config(page_title="COT Tracker Pro", page_icon="📈", layout="centered")

st.title("COT 机构持仓追踪 (2025 Pro)")
st.info("数据来源: CFTC 官方报告 (Legacy Report - Futures Only)")

# --- 核心函数: 获取真实数据 ---
@st.cache_data(ttl=3600*6) # 缓存6小时
def get_cftc_data():
    # 获取当前年份
    current_year = datetime.datetime.now().year
    
    # 尝试下载今年的数据
    try:
        # print(f"正在下载 {current_year} 年数据...")
        df = cot.cot_year(current_year, cot_report_type='legacy_fut')
    except Exception as e:
        st.warning(f"下载 {current_year} 数据失败，尝试使用去年数据。错误: {e}")
        df = cot.cot_year(current_year - 1, cot_report_type='legacy_fut')
    
    return df

# --- 智能数据处理函数 (修复报错的核心) ---
def process_data(df, keywords):
    # 1. 自动寻找正确的"名字"列
    # CFTC有时候叫 'Contract Name'，有时候叫 'Market_and_Exchange_Names'
    possible_names = ['Contract Name', 'Market_and_Exchange_Names', 'Market and Exchange Names']
    name_col = None
    
    for col in possible_names:
        if col in df.columns:
            name_col = col
            break
            
    if name_col is None:
        st.error(f"严重错误: 找不到合约名称列。现有列名: {list(df.columns)}")
        st.stop()

    # 2. 筛选特定品种 (支持列表模糊匹配)
    # 只要包含 keywords 里的任意一个词，就选出来
    mask = df[name_col].apply(lambda x: any(k in str(x).upper() for k in keywords))
    data = df[mask].copy()
    
    if data.empty:
        return pd.DataFrame() # 返回空表

    # 3. 整理日期格式 (自动寻找日期列)
    date_cols = ['As of Date in Form YYYY-MM-DD', 'Report_Date_as_YYYY-MM-DD']
    date_col = next((c for c in date_cols if c in df.columns), None)
    
    if date_col:
        data[date_col] = pd.to_datetime(data[date_col])
        data = data.sort_values(date_col)
    
    # 4. 计算"投机者净持仓" (Net Non-Commercial)
    # 同样需要兼容不同的列名格式
    try:
        # 尝试标准命名
        long_col = 'Non-Commercial Positions-Long (All)'
        short_col = 'Non-Commercial Positions-Short (All)'
        
        # 如果找不到，尝试原始缩写命名 (CFTC原始文件常见格式)
        if long_col not in data.columns:
            long_col = 'NonComm_Positions_Long_All'
            short_col = 'NonComm_Positions_Short_All'
            
        data['Net_Pos'] = data[long_col] - data[short_col]
        data['Date_Clean'] = data[date_col] # 统一日期列名方便画图
        
    except KeyError as e:
        st.error(f"数据列名解析失败: {e}")
        st.write("现有列名:", data.columns.tolist())
        st.stop()
    
    return data.tail(52) # 取最近一年的数据 (52周)

# --- 主程序 ---
with st.spinner('正在连接 CFTC 官网获取 2025 最新数据...'):
    try:
        raw_df = get_cftc_data()
        
        # 定义关键词 (使用列表，更精准)
        # GOLD
        data_gold = process_data(raw_df, ["GOLD", "COMMODITY EXCHANGE"])
        # EURO
        data_euro = process_data(raw_df, ["EURO FX", "CHICAGO MERCANTILE EXCHANGE"])
        # GBP
        data_gbp  = process_data(raw_df, ["BRITISH POUND", "STERLING"])
        
    except Exception as e:
        st.error(f"程序运行出错: {e}")
        st.stop()

# --- 绘图函数 ---
def render_chart(data, title, color_code):
    if data.empty:
        st.warning(f"暂无数据: {title}。可能由于CFTC名称变更或数据缺失。")
        return

    last_date = data['Date_Clean'].iloc[-1].strftime('%Y-%m-%d')
    current_net = data['Net_Pos'].iloc[-1]
    
    # 防止数据只有一行导致报错
    if len(data) > 1:
        prev_net = data['Net_Pos'].iloc[-2]
        delta = current_net - prev_net
    else:
        delta = 0
    
    sentiment_color = "green" if current_net > 0 else "red"
    sentiment_text = "Bullish (看涨)" if current_net > 0 else "Bearish (看跌)"

    st.metric(label=f"Net Positions ({last_date})", value=f"{int(current_net):,}", delta=f"{int(delta):,}")
    st.caption(f"机构情绪: :{sentiment_color}[{sentiment_text}]")

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=data['Date_Clean'], 
        y=data['Net_Pos'],
        mode='lines+markers',
        name='Net Speculator Pos',
        line=dict(color=color_code, width=2),
        fill='tozeroy'
    ))

    fig.update_layout(
        title=title,
        xaxis_title="Date",
        yaxis_title="Net Contracts",
        height=350,
        margin=dict(l=20, r=20, t=40, b=20),
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
