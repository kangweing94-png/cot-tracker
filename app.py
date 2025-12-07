import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import datetime
import pytz
import requests
import io

# --- 页面设置 ---
st.set_page_config(page_title="COT Pro Dashboard", page_icon="📊", layout="wide")

# --- 侧边栏 ---
with st.sidebar:
    st.header("📅 CFTC 发布时间表")
    
    tz_et = pytz.timezone('US/Eastern')
    tz_my = pytz.timezone('Asia/Kuala_Lumpur')
    now_et = datetime.datetime.now(tz_et)
    friday = now_et + datetime.timedelta((4 - now_et.weekday()) % 7)
    release_time = friday.replace(hour=15, minute=30, second=0, microsecond=0)
    
    if now_et > release_time:
        release_time += datetime.timedelta(days=7)
    
    release_my = release_time.astimezone(tz_my)
    
    st.info(f"""
    **下一次数据更新:**
    🇺🇸 美东: {release_time.strftime('%b %d %H:%M')}
    🇲🇾 大马: {release_my.strftime('%b %d %H:%M')}
    """)
    
    st.divider()
    if st.button("🔄 强制刷新 (Force Refresh)"):
        st.cache_data.clear()
        st.rerun()

# --- 🔥 核心修复：直连 CFTC 官网下载 ---
@st.cache_data(ttl=3600*6)
def get_cftc_data():
    year = datetime.datetime.now().year
    # CFTC 官方直接下载地址 (Legacy Futures Only)
    # 格式通常是: https://www.cftc.gov/files/dea/history/deacot{year}.zip
    url = f"https://www.cftc.gov/files/dea/history/deacot{year}.zip"
    
    try:
        # 使用 requests 下载 zip 文件
        response = requests.get(url, verify=False) # verify=False 防止SSL证书报错
        response.raise_for_status()
        
        # 直接用 pandas 读取内存中的 zip
        # CFTC 的 zip 里通常只有一个叫 annual.txt 的文件
        df = pd.read_csv(io.BytesIO(response.content), compression='zip', low_memory=False)
        return df
        
    except Exception as e:
        st.error(f"直连 CFTC 失败，尝试读取历史备份... 错误: {e}")
        # 如果今年下载失败（比如年初），尝试去年的
        try:
            prev_url = f"https://www.cftc.gov/files/dea/history/deacot{year-1}.zip"
            df = pd.read_csv(prev_url, compression='zip', low_memory=False)
            return df
        except:
            return pd.DataFrame()

# --- 辅助函数 ---
def find_column(columns, keywords):
    for col in columns:
        col_lower = str(col).lower()
        if all(k in col_lower for k in keywords):
            return col
    return None

def process_data(df, name_keywords):
    if df.empty: return pd.DataFrame()

    # 1. 找名字 (CFTC 原生文件列名通常是 "Market_and_Exchange_Names")
    name_col = find_column(df.columns, ['market', 'exchange']) or \
               find_column(df.columns, ['contract', 'name'])
    
    if not name_col: return pd.DataFrame()

    # 2. 筛选
    mask = df[name_col].apply(lambda x: any(k in str(x).upper() for k in name_keywords))
    data = df[mask].copy()
    if data.empty: return pd.DataFrame()

    # 3. 找日期 (通常是 "Report_Date_as_YYYY-MM-DD")
    date_col = find_column(df.columns, ['report', 'date']) or \
               find_column(df.columns, ['as', 'of', 'date'])
    data[date_col] = pd.to_datetime(data[date_col])
    
    # 4. 找多空 (通常是 "NonComm_Positions_Long_All")
    long_col = find_column(df.columns, ['non', 'comm', 'long'])
    short_col = find_column(df.columns, ['non', 'comm', 'short'])
    
    if not long_col or not short_col: return pd.DataFrame()
    
    # 5. 计算
    data['Net_Pos'] = data[long_col] - data[short_col]
    data['Date_Display'] = data[date_col]
    
    data = data.sort_values('Date_Display')
    data = data.drop_duplicates(subset=['Date_Display'], keep='last')
    
    return data.tail(52)

# --- 绘图 ---
def render_pro_chart(data, title, main_color):
    if data.empty:
        st.warning(f"Waiting for data: {title}")
        return

    last_date_obj = data['Date_Display'].iloc[-1]
    last_date = last_date_obj.strftime('%Y-%m-%d')
    current_net = data['Net_Pos'].iloc[-1]
    
    if len(data) > 1:
        prev_net = data['Net_Pos'].iloc[-2]
        change = current_net - prev_net
    else:
        change = 0
    
    days_diff = (datetime.datetime.now() - last_date_obj).days
    is_outdated = days_diff > 14 # 如果超过14天没更新才报警

    is_bullish = current_net > 0
    sentiment_color = "#00FF7F" if is_bullish else "#FF4B4B"
    sentiment_text = "Bullish" if is_bullish else "Bearish"

    col1, col2 = st.columns([1, 3])
    
    with col1:
        st.markdown(f"### {title.split(' ')[0]}")
        st.caption(f"Report Date: {last_date}")
        
        if is_outdated:
            st.error(f"⚠️ 数据滞后 {days_diff} 天")
            st.caption("尝试点击侧边栏的刷新按钮")
        
        st.metric(label="Net Positions", value=f"{int(current_net):,}", delta=f"{int(change):,}")
        
        st.markdown(f"""
        <div style="margin-top: 20px; padding: 10px; border-radius: 5px; background-color: rgba(255,255,255,0.05); border-left: 5px solid {sentiment_color}">
            <small style="color: #aaa">Market Sentiment</small><br>
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
            height=400,
            margin=dict(l=0, r=20, t=30, b=0),
            plot_bgcolor='rgba(0,0,0,0)',
            paper_bgcolor='rgba(0,0,0,0)',
            xaxis=dict(showgrid=False, title="", type="date", tickformat="%Y-%m-%d"),
            yaxis=dict(showgrid=True, gridcolor='#333', zeroline=False)
        )
        st.plotly_chart(fig, use_container_width=True)
    st.divider()

# --- 主程序 ---
st.title("COT 机构持仓透视 (Direct Source)")

with st.spinner('Downloading directly from CFTC.gov...'):
    df = get_cftc_data()
    # 关键词不需要变，CFTC源文件里名字是一样的
    gold = process_data(df, ["GOLD", "COMMODITY"])
    euro = process_data(df, ["EURO FX", "CHICAGO"])
    gbp = process_data(df, ["BRITISH POUND", "STERLING"])

render_pro_chart(gold, "Gold (XAU) / USD", "#FFD700")
render_pro_chart(euro, "Euro (EUR) / USD", "#00d2ff")
render_pro_chart(gbp, "Pound (GBP) / USD", "#eb4034")
