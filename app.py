import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import datetime
import pytz
import requests
import io
import time
import random

# --- 页面设置 ---
st.set_page_config(page_title="COT Pro Dashboard", page_icon="📊", layout="wide")

# --- 侧边栏 ---
with st.sidebar:
    st.header("📅 CFTC 实时状态")
    
    tz_my = pytz.timezone('Asia/Kuala_Lumpur')
    now_my = datetime.datetime.now(tz_my)
    
    st.info(f"当前时间 (MYT):\n{now_my.strftime('%Y-%m-%d %H:%M')}")
    
    st.divider()
    if st.button("🚀 强力刷新 (Force Fetch)"):
        st.cache_data.clear()
        st.rerun()

# --- 核心数据下载 (增强版) ---
@st.cache_data(ttl=3600*1) # 缩短缓存时间到1小时
def get_cftc_data():
    year = datetime.datetime.now().year
    
    # 1. 设置伪装头部 (非常重要，防止被拦截)
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
        "Cache-Control": "no-cache", 
        "Pragma": "no-cache"
    }

    # 2. 构造带时间戳的 URL (防止服务器缓存)
    ts = int(time.time())
    url = f"https://www.cftc.gov/files/dea/history/deacot{year}.zip?t={ts}&r={random.randint(1, 10000)}"
    
    status_placeholder = st.empty()
    status_placeholder.text(f"正在尝试从 CFTC 下载最新数据 ({year})...")
    
    try:
        # 3. 发起请求
        response = requests.get(url, headers=headers, verify=False, timeout=30)
        response.raise_for_status()
        
        # 4. 读取数据
        df = pd.read_csv(io.BytesIO(response.content), compression='zip', low_memory=False)
        status_placeholder.empty()
        return df
        
    except Exception as e:
        status_placeholder.error(f"下载 2025 数据失败: {e}")
        # 如果今年失败，尝试回退到去年作为保底
        try:
            prev_url = f"https://www.cftc.gov/files/dea/history/deacot{year-1}.zip"
            df = pd.read_csv(prev_url, compression='zip', low_memory=False)
            return df
        except:
            return pd.DataFrame()

# --- 数据处理 ---
def find_column(columns, keywords):
    for col in columns:
        col_lower = str(col).lower()
        if all(k in col_lower for k in keywords):
            return col
    return None

def process_data(df, name_keywords):
    if df.empty: return pd.DataFrame()

    # 找名字
    name_col = find_column(df.columns, ['market', 'exchange']) or \
               find_column(df.columns, ['contract', 'name'])
    if not name_col: return pd.DataFrame()

    # 筛选
    mask = df[name_col].apply(lambda x: any(k in str(x).upper() for k in name_keywords))
    data = df[mask].copy()
    
    # 找日期
    date_col = find_column(df.columns, ['report', 'date']) or \
               find_column(df.columns, ['as', 'of', 'date'])
    if not date_col: return pd.DataFrame()
    
    data[date_col] = pd.to_datetime(data[date_col])
    
    # 找多空
    long_col = find_column(df.columns, ['non', 'comm', 'long'])
    short_col = find_column(df.columns, ['non', 'comm', 'short'])
    
    if not long_col or not short_col: return pd.DataFrame()
    
    # 计算
    data['Net_Pos'] = data[long_col] - data[short_col]
    data['Date_Display'] = data[date_col]
    
    # 去重逻辑
    data = data.sort_values('Date_Display')
    data = data.drop_duplicates(subset=['Date_Display'], keep='last')
    
    return data.tail(52)

# --- 绘图 ---
def render_pro_chart(data, title, main_color):
    if data.empty:
        st.warning(f"暂无数据: {title}")
        return

    last_date_obj = data['Date_Display'].iloc[-1]
    last_date = last_date_obj.strftime('%Y-%m-%d')
    current_net = data['Net_Pos'].iloc[-1]
    
    if len(data) > 1:
        prev_net = data['Net_Pos'].iloc[-2]
        change = current_net - prev_net
    else:
        change = 0
    
    # 智能检查: 数据是否严重滞后
    days_diff = (datetime.datetime.now() - last_date_obj).days
    is_outdated = days_diff > 14 

    sentiment_color = "#00FF7F" if current_net > 0 else "#FF4B4B"
    sentiment_text = "Bullish" if current_net > 0 else "Bearish"

    col1, col2 = st.columns([1, 3])
    
    with col1:
        st.markdown(f"### {title.split(' ')[0]}")
        st.caption(f"最新报告日期: {last_date}")
        
        if is_outdated:
            st.error(f"⚠️ 数据严重滞后 ({days_diff} 天)")
            st.info("提示: CFTC 官网可能尚未更新 2025 年总表，这是政府端的延迟。")
        else:
            st.success("✅ 数据已更新")
            
        st.metric(label="Net Positions", value=f"{int(current_net):,}", delta=f"{int(change):,}")
        
        st.markdown(f"""
        <div style="margin-top: 20px; padding: 10px; border-radius: 5px; background-color: rgba(255,255,255,0.05); border-left: 5px solid {sentiment_color}">
            <strong style="color: {sentiment_color}; font-size: 1.1em">{sentiment_text}</strong>
        </div>
        """, unsafe_allow_html=True)

    with col2:
        fig = go.Figure()
        fig.add_hline(y=0, line_dash="dash", line_color="gray", opacity=0.5)
        fig.add_trace(go.Scatter(
            x=data['Date_Display'], 
            y=data['Net_Pos'],
            mode='lines',
            name='Net Positions',
            line=dict(color=main_color, width=3, shape='spline', smoothing=1.3),
            fill='tozeroy',
            fillcolor=f"rgba{main_color[3:-1]}, 0.1)" if main_color.startswith('rgba') else main_color.replace(')', ', 0.1)').replace('rgb', 'rgba') 
        ))
        
        if main_color == "#FFD700": fill_c = "rgba(255, 215, 0, 0.2)"
        elif main_color == "#00d2ff": fill_c = "rgba(0, 210, 255, 0.2)"
        else: fill_c = "rgba(235, 64, 52, 0.2)"
        fig.update_traces(fillcolor=fill_c)

        fig.update_layout(
            title=dict(text=f"{title} Trend", font=dict(size=14, color="#aaa")),
            height=380,
            margin=dict(l=0, r=20, t=30, b=0),
            plot_bgcolor='rgba(0,0,0,0)',
            paper_bgcolor='rgba(0,0,0,0)',
            xaxis=dict(showgrid=False, title="", type="date", tickformat="%Y-%m-%d"),
            yaxis=dict(showgrid=True, gridcolor='#333', zeroline=False)
        )
        st.plotly_chart(fig, use_container_width=True)
    st.divider()

# --- 主程序 ---
st.title("COT 机构持仓透视 (Pro)")

with st.spinner('正在连接 CFTC 美国政府服务器...'):
    df = get_cftc_data()
    gold = process_data(df, ["GOLD", "COMMODITY"])
    euro = process_data(df, ["EURO FX", "CHICAGO"])
    gbp = process_data(df, ["BRITISH POUND", "STERLING"])

render_pro_chart(gold, "Gold (XAU) / USD", "#FFD700")
render_pro_chart(euro, "Euro (EUR) / USD", "#00d2ff")
render_pro_chart(gbp, "Pound (GBP) / USD", "#eb4034")
