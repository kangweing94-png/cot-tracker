import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import cot_reports as cot
import datetime
import pytz # 用于处理时区

# --- 页面设置 ---
st.set_page_config(page_title="COT Pro Dashboard", page_icon="📊", layout="wide")

# --- 侧边栏：发布时间与控制台 ---
with st.sidebar:
    st.header("📅 CFTC 发布时间表")
    
    # 1. 计算下次发布时间
    # CFTC 规则: 每周五美东时间 15:30 (马来西亚时间周六凌晨 03:30 或 04:30)
    tz_et = pytz.timezone('US/Eastern')
    tz_my = pytz.timezone('Asia/Kuala_Lumpur')
    
    now_et = datetime.datetime.now(tz_et)
    # 找到本周五
    friday = now_et + datetime.timedelta((4 - now_et.weekday()) % 7)
    release_time = friday.replace(hour=15, minute=30, second=0, microsecond=0)
    
    # 如果现在已经过了周五发布时间，就显示下周五
    if now_et > release_time:
        release_time += datetime.timedelta(days=7)
    
    release_my = release_time.astimezone(tz_my)
    
    st.info(f"""
    **下一次数据更新:**
    
    🇺🇸 美东: {release_time.strftime('%A, %b %d %H:%M')}
    🇲🇾 大马: {release_my.strftime('%A, %b %d %H:%M')}
    
    *(数据通常滞后3天，反映的是周二的持仓)*
    """)
    
    st.divider()
    
    st.write("🔧 **系统控制**")
    if st.button("🔄 强制刷新数据 (Clear Cache)"):
        st.cache_data.clear()
        st.rerun()

# --- 核心数据逻辑 ---
@st.cache_data(ttl=3600*12) # 缓存12小时
def get_cftc_data():
    current_year = datetime.datetime.now().year
    try:
        # 优先下载 2025
        df = cot.cot_year(current_year, cot_report_type='legacy_fut')
    except:
        # 失败则尝试 2024
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
    
    # 5. 计算并清洗
    data['Net_Pos'] = data[long_col] - data[short_col]
    data['Date_Display'] = data[date_col]
    
    # 去重并排序
    data = data.sort_values('Date_Display')
    data = data.drop_duplicates(subset=['Date_Display'], keep='last')
    
    return data.tail(52)

# --- 绘图引擎 ---
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
    
    # 检查数据是否过期 (超过10天没更新)
    days_diff = (datetime.datetime.now() - last_date_obj).days
    is_outdated = days_diff > 10

    # 情绪判断
    is_bullish = current_net > 0
    sentiment_color = "#00FF7F" if is_bullish else "#FF4B4B"
    sentiment_text = "Bullish (看涨)" if is_bullish else "Bearish (看跌)"

    col1, col2 = st.columns([1, 3])
    
    with col1:
        st.markdown(f"### {title.split(' ')[0]}")
        st.caption(f"Report Date: {last_date}")
        
        if is_outdated:
            st.error(f"⚠️ 数据似乎未更新 (滞后 {days_diff} 天)")
        
        st.metric(
            label="Net Positions", 
            value=f"{int(current_net):,}", 
            delta=f"{int(change):,}"
        )
        
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
        
        # 修正颜色透明度逻辑
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
            hovermode="x unified",
            xaxis=dict(showgrid=False, title="", type="date", tickformat="%Y-%m-%d"),
            yaxis=dict(showgrid=True, gridcolor='#333', zeroline=False)
        )
        st.plotly_chart(fig, use_container_width=True)
    
    st.divider()

# --- 主程序 ---
st.title("COT 机构持仓透视 (Live)")

with st.spinner('Checking for new data...'):
    df = get_cftc_data()
    gold = process_data(df, ["GOLD", "COMMODITY"])
    euro = process_data(df, ["EURO FX", "CHICAGO"])
    gbp = process_data(df, ["BRITISH POUND", "STERLING"])

render_pro_chart(gold, "Gold (XAU) / USD", "#FFD700")
render_pro_chart(euro, "Euro (EUR) / USD", "#00d2ff")
render_pro_chart(gbp, "Pound (GBP) / USD", "#eb4034")
