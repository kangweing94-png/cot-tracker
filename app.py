import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import datetime
import requests
import io
import time
import random

# --- 页面配置 ---
st.set_page_config(page_title="Smart Money COT (Auto)", page_icon="⚡", layout="wide")

# --- 侧边栏 ---
with st.sidebar:
    st.header("⚡ 自动抓取系统")
    st.info("系统现在会同时抓取“历史归档”和“本周实时文件”，自动拼合数据以填补空白。")
    
    if st.button("🔄 刷新数据 (Refresh)"):
        st.cache_data.clear()
        st.rerun()

# --- 核心：双源数据抓取与拼合 ---
@st.cache_data(ttl=3600*3) # 缓存3小时
def get_combined_data():
    year = datetime.datetime.now().year
    
    # 1. 定义两个数据源
    # 源 A: 历史大文件 (容易滞后，但包含过去所有数据)
    url_history = f"https://www.cftc.gov/files/dea/history/fut_disagg_txt_{year}.zip"
    # 源 B: 本周实时单页 (绝对最新，但只有这一周的数据)
    url_latest = "https://www.cftc.gov/dea/newcot/f_disagg.txt"
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0 Safari/537.36",
        "Cache-Control": "no-cache"
    }

    df_history = pd.DataFrame()
    df_latest = pd.DataFrame()

    # --- 步骤 1: 下载历史数据 ---
    try:
        # print("Downloading History...")
        r_hist = requests.get(url_history, headers=headers, verify=False, timeout=15)
        if r_hist.status_code == 200:
            df_history = pd.read_csv(io.BytesIO(r_hist.content), compression='zip', low_memory=False)
    except Exception as e:
        print(f"历史数据下载失败: {e}")

    # --- 步骤 2: 下载本周最新数据 ---
    try:
        # print("Downloading Latest...")
        # 加随机数防止缓存
        url_latest_bust = f"{url_latest}?t={int(time.time())}"
        r_last = requests.get(url_latest_bust, headers=headers, verify=False, timeout=10)
        
        if r_last.status_code == 200:
            # 实时文件没有表头(Header)，我们需要借用历史数据的表头
            if not df_history.empty:
                df_latest = pd.read_csv(io.BytesIO(r_last.content), header=None, low_memory=False)
                # 强行把历史数据的列名赋给最新数据，确保能拼起来
                df_latest.columns = df_history.columns
    except Exception as e:
        print(f"实时数据下载失败: {e}")

    # --- 步骤 3: 拼合 (Merge) ---
    if df_history.empty and df_latest.empty:
        return pd.DataFrame()
    
    # 把两份数据上下拼起来
    full_df = pd.concat([df_history, df_latest], ignore_index=True)
    
    return full_df

# --- 数据清洗与计算 ---
def process_data(df, name_keywords):
    if df.empty: return pd.DataFrame()

    # 1. 智能查找列名
    def find_col(keywords):
        for col in df.columns:
            if all(k in str(col).lower() for k in keywords):
                return col
        return None

    # 2. 筛选品种
    name_col = find_col(['market', 'exchange']) or find_col(['contract', 'name'])
    if not name_col: return pd.DataFrame()
    
    mask = df[name_col].apply(lambda x: any(k in str(x).upper() for k in name_keywords))
    data = df[mask].copy()
    if data.empty: return pd.DataFrame()

    # 3. 处理日期
    date_col = find_col(['report', 'date']) or find_col(['as', 'of', 'date'])
    data[date_col] = pd.to_datetime(data[date_col])
    
    # 4. 寻找 "Managed Money" (Smart Money) 数据
    # 基金经理的多单和空单
    long_col = find_col(['money', 'long'])
    short_col = find_col(['money', 'short'])
    
    if not long_col or not short_col: return pd.DataFrame()
    
    # 5. 计算净持仓
    data['Net_Pos'] = data[long_col] - data[short_col]
    data['Date_Display'] = data[date_col]
    
    # 6. 去重 (关键步骤)
    # 因为拼合时可能会有重复的周，我们按日期排序，保留最新的那一行
    data = data.sort_values('Date_Display')
    data = data.drop_duplicates(subset=['Date_Display'], keep='last')
    
    return data.tail(52) # 只取最近一年

# --- 绘图引擎 ---
def render_chart(data, title, main_color):
    if data.empty:
        st.warning(f"数据加载中或暂无数据: {title}")
        return

    # 获取最新一笔数据
    last_date = data['Date_Display'].iloc[-1].strftime('%Y-%m-%d')
    current_net = data['Net_Pos'].iloc[-1]
    
    # 计算变化量
    change = 0
    if len(data) > 1:
        prev_net = data['Net_Pos'].iloc[-2]
        change = current_net - prev_net

    # 判断情绪
    is_bullish = current_net > 0
    sentiment_color = "#00FF7F" if is_bullish else "#FF4B4B"
    sentiment_text = "Bullish (看涨)" if is_bullish else "Bearish (看跌)"

    # 布局
    col1, col2 = st.columns([1, 3])
    
    with col1:
        st.markdown(f"### {title.split(' ')[0]}")
        st.caption(f"最新数据: {last_date}")
        
        # 显示大数字
        st.metric(label="Smart Money Net", value=f"{int(current_net):,}", delta=f"{int(change):,}")
        
        # 情绪卡片
        st.markdown(f"""
        <div style="background-color: rgba(255,255,255,0.05); padding: 10px; border-radius: 5px; border-left: 4px solid {sentiment_color}; margin-top: 10px;">
            <strong style="color: {sentiment_color}">{sentiment_text}</strong>
        </div>
        """, unsafe_allow_html=True)

    with col2:
        fig = go.Figure()
        
        # 0轴线
        fig.add_hline(y=0, line_dash="dash", line_color="gray", opacity=0.5)
        
        # 曲线
        fig.add_trace(go.Scatter(
            x=data['Date_Display'], 
            y=data['Net_Pos'],
            mode='lines',
            name='Managed Money',
            line=dict(color=main_color, width=3, shape='spline', smoothing=1.3),
            fill='tozeroy',
            # 颜色透明度处理
            fillcolor=f"rgba{main_color.replace('#','').replace(')', ', 0.2)')}" if 'rgba' in main_color else main_color 
        ))
        
        # 简单的颜色修正
        fill_c = "rgba(255, 215, 0, 0.2)" # 默认金
        if "00d2ff" in main_color: fill_c = "rgba(0, 210, 255, 0.2)"
        if "eb4034" in main_color: fill_c = "rgba(235, 64, 52, 0.2)"
        fig.update_traces(fillcolor=fill_c)

        fig.update_layout(
            title=dict(text=f"{title} - Managed Money Trend", font=dict(size=14, color="#aaa")),
            height=350,
            margin=dict(l=0, r=10, t=30, b=0),
            plot_bgcolor='rgba(0,0,0,0)',
            paper_bgcolor='rgba(0,0,0,0)',
            xaxis=dict(showgrid=False, title="", type="date", tickformat="%Y-%m-%d"),
            yaxis=dict(showgrid=True, gridcolor='#333', zeroline=False)
        )
        st.plotly_chart(fig, use_container_width=True)
    
    st.divider()

# --- 主程序入口 ---
st.title("Smart Money COT Tracker (Auto-Fetch)")
st.caption("数据源: CFTC Disaggregated Reports (History + Live Merge)")

with st.spinner('正在从 CFTC 官网抓取并拼合最新数据...'):
    # 1. 获取全量数据
    full_df = get_combined_data()
    
    # 2. 筛选品种
    gold = process_data(full_df, ["GOLD", "COMMODITY"])
    euro = process_data(full_df, ["EURO FX", "CHICAGO"])
    gbp = process_data(full_df, ["BRITISH POUND", "STERLING"])

# 3. 渲染
if full_df.empty:
    st.error("无法连接到 CFTC 服务器，请稍后再试或点击侧边栏刷新。")
else:
    render_chart(gold, "Gold (XAUUSD)", "#FFD700")
    render_chart(euro, "Euro (EURUSD)", "#00d2ff")
    render_chart(gbp, "Pound (GBPUSD)", "#eb4034")
