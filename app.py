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
st.set_page_config(page_title="Smart Money Tracker", page_icon="🏦", layout="wide")

# --- 侧边栏：手动修正与控制 ---
with st.sidebar:
    st.header("🔧 数据控制台")
    
    st.info("如果自动数据滞后，请在此手动输入最新一期的净持仓数值（可在 Investing.com 或 Myfxbook 查询）。")
    
    manual_date = st.date_input("最新数据日期", datetime.date.today())
    
    with st.expander("📝 手动录入最新数据 (Optional)", expanded=True):
        manual_gold = st.number_input("Gold 最新净持仓", value=0, help="输入 XAUUSD Managed Money Net Positions")
        manual_euro = st.number_input("Euro 最新净持仓", value=0)
        manual_gbp = st.number_input("GBP 最新净持仓", value=0)
    
    st.divider()
    
    if st.button("🚀 强力刷新数据"):
        st.cache_data.clear()
        st.rerun()
        
    st.caption("数据源: CFTC Disaggregated Report (Managed Money)")

# --- 核心数据下载 (更换为 Disaggregated 源) ---
@st.cache_data(ttl=3600*1)
def get_cftc_data():
    year = datetime.datetime.now().year
    
    # ⚠️ 关键改变：下载 fut_disagg_txt (分类报告) 而不是 deacot (传统报告)
    # 这份报告通常更新更及时，且包含 Managed Money 数据
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0 Safari/537.36",
        "Cache-Control": "no-cache"
    }
    
    # 加上随机数防止缓存
    url = f"https://www.cftc.gov/files/dea/history/fut_disagg_txt_{year}.zip?t={int(time.time())}&r={random.randint(1,1000)}"
    
    status_placeholder = st.empty()
    status_placeholder.text(f"正在连接 CFTC 获取 Smart Money 数据 ({year})...")
    
    try:
        response = requests.get(url, headers=headers, verify=False, timeout=30)
        response.raise_for_status()
        df = pd.read_csv(io.BytesIO(response.content), compression='zip', low_memory=False)
        status_placeholder.empty()
        return df
    except Exception as e:
        status_placeholder.error(f"下载失败: {e}")
        # 失败回退到去年
        try:
            prev_url = f"https://www.cftc.gov/files/dea/history/fut_disagg_txt_{year-1}.zip"
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

def process_data(df, name_keywords, manual_val=0, manual_date_val=None):
    if df.empty: return pd.DataFrame()

    # 1. 找名字
    name_col = find_column(df.columns, ['market', 'exchange']) or \
               find_column(df.columns, ['contract', 'name'])
    if not name_col: return pd.DataFrame()

    # 2. 筛选品种
    mask = df[name_col].apply(lambda x: any(k in str(x).upper() for k in name_keywords))
    data = df[mask].copy()
    if data.empty: return pd.DataFrame()

    # 3. 找日期
    date_col = find_column(df.columns, ['report', 'date']) or \
               find_column(df.columns, ['as', 'of', 'date'])
    data[date_col] = pd.to_datetime(data[date_col])
    
    # 4. 找 Managed Money (Smart Money) 数据
    # 这里的关键词变了：找 "Money", "Long", "Short" (对应 Managed Money)
    long_col = find_column(df.columns, ['money', 'long'])
    short_col = find_column(df.columns, ['money', 'short'])
    
    # 如果找不到 Managed Money，尝试找原来的 Non-Commercial 作为备选
    if not long_col:
        long_col = find_column(df.columns, ['non', 'comm', 'long'])
        short_col = find_column(df.columns, ['non', 'comm', 'short'])

    if not long_col or not short_col: return pd.DataFrame()
    
    # 5. 计算净持仓
    data['Net_Pos'] = data[long_col] - data[short_col]
    data['Date_Display'] = data[date_col]
    
    # 去重排序
    data = data.sort_values('Date_Display')
    data = data.drop_duplicates(subset=['Date_Display'], keep='last')
    data = data.tail(52) # 取最近一年
    
    # --- 🔥 手动数据注入逻辑 ---
    # 如果用户在侧边栏输入了非0的数值，且该日期比CFTC文件里的新，就把它加进去
    if manual_val != 0 and manual_date_val:
        last_file_date = data['Date_Display'].iloc[-1].date()
        if manual_date_val > last_file_date:
            new_row = pd.DataFrame({
                'Date_Display': [pd.to_datetime(manual_date_val)],
                'Net_Pos': [manual_val]
            })
            data = pd.concat([data, new_row], ignore_index=True)
    
    return data

# --- 绘图 ---
def render_chart(data, title, main_color):
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
    is_outdated = days_diff > 14

    is_bullish = current_net > 0
    sentiment_color = "#00FF7F" if is_bullish else "#FF4B4B"
    sentiment_text = "Strong Bullish" if is_bullish else "Bearish"

    col1, col2 = st.columns([1, 3])
    
    with col1:
        st.markdown(f"### {title.split(' ')[0]}")
        st.caption(f"Date: {last_date}")
        
        if is_outdated:
            st.error(f"⚠️ 数据滞后 {days_diff} 天")
            st.caption("建议在侧边栏手动输入最新数据")
        elif days_diff < 5:
            st.success("✅ 数据实时")
            
        st.metric(label="Smart Money Net", value=f"{int(current_net):,}", delta=f"{int(change):,}")
        
        st.markdown(f"""
        <div style="margin-top: 10px; padding: 10px; border-radius: 5px; background-color: rgba(255,255,255,0.05); border-left: 4px solid {sentiment_color}">
            <strong style="color: {sentiment_color}">{sentiment_text}</strong>
        </div>
        """, unsafe_allow_html=True)

    with col2:
        fig = go.Figure()
        fig.add_hline(y=0, line_dash="dash", line_color="gray", opacity=0.5)
        
        # 面积图
        fig.add_trace(go.Scatter(
            x=data['Date_Display'], 
            y=data['Net_Pos'],
            mode='lines',
            name='Managed Money',
            line=dict(color=main_color, width=3, shape='spline', smoothing=1.3),
            fill='tozeroy',
            fillcolor=f"rgba{main_color[3:-1]}, 0.15)" if main_color.startswith('rgba') else main_color.replace(')', ', 0.15)').replace('rgb', 'rgba') 
        ))
        
        # 修正颜色
        if main_color == "#FFD700": fill_c = "rgba(255, 215, 0, 0.2)"
        elif main_color == "#00d2ff": fill_c = "rgba(0, 210, 255, 0.2)"
        else: fill_c = "rgba(235, 64, 52, 0.2)"
        fig.update_traces(fillcolor=fill_c)

        fig.update_layout(
            title=dict(text=f"{title} (Managed Money)", font=dict(size=14, color="#aaa")),
            height=350,
            margin=dict(l=0, r=10, t=30, b=0),
            plot_bgcolor='rgba(0,0,0,0)',
            paper_bgcolor='rgba(0,0,0,0)',
            xaxis=dict(showgrid=False, title="", type="date", tickformat="%Y-%m-%d"),
            yaxis=dict(showgrid=True, gridcolor='#333', zeroline=False)
        )
        st.plotly_chart(fig, use_container_width=True)
    st.divider()

# --- 主程序 ---
st.title("Smart Money COT Tracker")
st.caption("追踪基金经理 (Managed Money) 真实持仓 | 数据源: CFTC Disaggregated")

with st.spinner('正在连接 CFTC Disaggregated 服务器...'):
    df = get_cftc_data()
    
    # 获取用户手动输入的值
    m_gold_val = st.sidebar.session_state.get('manual_gold', 0) if 'manual_gold' in st.sidebar.session_state else 0 # Fix state access
    # Streamlit input可以直接拿到变量
    
    # 处理数据 (传入手动值)
    gold = process_data(df, ["GOLD", "COMMODITY"], manual_gold, manual_date)
    euro = process_data(df, ["EURO FX", "CHICAGO"], manual_euro, manual_date)
    gbp = process_data(df, ["BRITISH POUND", "STERLING"], manual_gbp, manual_date)

render_chart(gold, "Gold (XAUUSD)", "#FFD700")
render_chart(euro, "Euro (EURUSD)", "#00d2ff")
render_chart(gbp, "Pound (GBPUSD)", "#eb4034")
