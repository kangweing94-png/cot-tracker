import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import datetime
import requests
import io
import time
import pytz

# --- 页面配置 ---
st.set_page_config(page_title="Smart Money & Macro Pro", page_icon="🏦", layout="wide")

# --- 侧边栏 ---
with st.sidebar:
    st.header("⚡ 控制台")
    if st.button("🔄 刷新全站数据"):
        st.cache_data.clear()
        st.rerun()
    
    st.divider()
    st.caption("数据源:\n1. CFTC (持仓)\n2. FRED (宏观经济)")

# ==============================================================================
# 模块 1: CFTC 核心逻辑 (回滚到最稳定的版本)
# ==============================================================================
@st.cache_data(ttl=3600*3)
def get_cftc_data():
    year = datetime.datetime.now().year
    # 模拟用户提到的"2025年政府停摆"场景
    url_history = f"https://www.cftc.gov/files/dea/history/fut_disagg_txt_{year}.zip"
    url_latest = "https://www.cftc.gov/dea/newcot/f_disagg.txt"
    
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0 Safari/537.36"}
    
    df_hist = pd.DataFrame()
    df_live = pd.DataFrame()

    # 1. 下载历史包
    try:
        r = requests.get(url_history, headers=headers, verify=False, timeout=10)
        if r.status_code == 200:
            df_hist = pd.read_csv(io.BytesIO(r.content), compression='zip', low_memory=False)
    except: pass

    # 2. 下载本周实时包
    try:
        r2 = requests.get(f"{url_latest}?t={int(time.time())}", headers=headers, verify=False, timeout=5)
        if r2.status_code == 200:
            if not df_hist.empty:
                df_live = pd.read_csv(io.BytesIO(r2.content), header=None, low_memory=False)
                df_live.columns = df_hist.columns # 强行对齐列名
    except: pass

    if df_hist.empty and df_live.empty: return pd.DataFrame()
    return pd.concat([df_hist, df_live], ignore_index=True)

# 🔥 关键修复：恢复了 helper 函数，不再使用简化的列表推导
def find_column(columns, keywords):
    for col in columns:
        col_lower = str(col).lower()
        if all(k in col_lower for k in keywords):
            return col
    return None

def process_cftc(df, name_keywords):
    if df.empty: return pd.DataFrame()

    # 1. 找名字 (Name/Market)
    name_col = find_column(df.columns, ['market', 'exchange']) or \
               find_column(df.columns, ['contract', 'name'])
    if not name_col: return pd.DataFrame()

    # 2. 筛选 (Gold/Euro)
    mask = df[name_col].apply(lambda x: any(k in str(x).upper() for k in name_keywords))
    data = df[mask].copy()
    if data.empty: return pd.DataFrame()

    # 3. 找日期 (Date)
    date_col = find_column(df.columns, ['report', 'date']) or \
               find_column(df.columns, ['as', 'of', 'date'])
    data[date_col] = pd.to_datetime(data[date_col])
    
    # 4. 找 Managed Money (Smart Money)
    long_col = find_column(df.columns, ['money', 'long'])
    short_col = find_column(df.columns, ['money', 'short'])
    
    if not long_col or not short_col: return pd.DataFrame()
    
    # 5. 计算净持仓
    data['Net'] = data[long_col] - data[short_col]
    data['Date_Display'] = data[date_col]
    
    # 6. 去重
    data = data.sort_values('Date_Display')
    data = data.drop_duplicates(subset=['Date_Display'], keep='last')
    
    return data.tail(52)

# ==============================================================================
# 模块 2: 宏观经济数据 (纯 CSV 读取版，稳定)
# ==============================================================================
@st.cache_data(ttl=3600*12)
def get_macro_data():
    base_url = "https://fred.stlouisfed.org/graph/fredgraph.csv?id="
    
    def fetch_fred(series_id):
        try:
            # 增加 User-Agent 防止被拒
            headers = {"User-Agent": "Mozilla/5.0"}
            r = requests.get(f"{base_url}{series_id}", headers=headers, timeout=5)
            if r.status_code == 200:
                df = pd.read_csv(io.BytesIO(r.content))
                df['DATE'] = pd.to_datetime(df['DATE'])
                df.set_index('DATE', inplace=True)
                return df
        except: return None
        return None

    # 1. 联邦基金利率
    fed_rate = fetch_fred('FEDFUNDS')
    
    # 2. 非农就业
    nfp = fetch_fred('PAYEMS')
    if nfp is not None: nfp['Change'] = nfp['PAYEMS'].diff()
    
    # 3. CPI 通胀
    cpi = fetch_fred('CPIAUCSL')
    if cpi is not None: cpi['YoY'] = cpi['CPIAUCSL'].pct_change(12) * 100
        
    # 4. 初请失业金
    claims = fetch_fred('ICSA')
    
    return fed_rate, nfp, cpi, claims

# ==============================================================================
# UI 组件
# ==============================================================================
def render_news_alert(last_date_obj):
    if pd.isnull(last_date_obj): return
    days_diff = (datetime.datetime.now() - last_date_obj).days
    
    if days_diff > 14:
        st.error(f"🚨 **MARKET ALERT: 数据严重滞后 ({days_diff}天)**")
        with st.expander("📰 **News Headline: 为什么数据停更了？** (点击展开)", expanded=True):
            st.markdown(f"""
            #### 🏛️ 美国政府停摆导致 CFTC 报告积压
            **事件影响**: 由于美国政府在 **2025年10月** 期间发生停摆 (Government Shutdown)，CFTC 暂停了所有数据处理。
            
            **当前状态**: 正在按顺序补发历史报告，预计 2026年1月 恢复正常。
            
            *此数据最后更新于: {last_date_obj.strftime('%Y-%m-%d')}*
            """)

def render_fomc_card():
    # 简单的 FOMC 下次会议倒计时逻辑
    fomc_dates = [datetime.date(2025, 12, 10), datetime.date(2026, 1, 28), datetime.date(2026, 3, 18)]
    today = datetime.date.today()
    next_meet = next((d for d in fomc_dates if d >= today), None)
            
    st.markdown("### 🏦 FOMC 联邦公开市场委员会")
    c1, c2 = st.columns([2, 1])
    with c1:
        if next_meet:
            days = (next_meet - today).days
            st.info(f"📅 下次利率决议: **{next_meet}** (还剩 {days} 天)")
        else:
            st.info("📅 下次会议: 待定")
    with c2:
        st.link_button("📊 查看最新点阵图", "https://www.federalreserve.gov/monetarypolicy/fomcprojtabl20250917.htm")

# ==============================================================================
# 主程序
# ==============================================================================

with st.spinner('正在同步华尔街数据...'):
    cftc_df = get_cftc_data()
    # 恢复了你最满意的黄金数据处理逻辑
    gold_data = process_cftc(cftc_df, ["GOLD", "COMMODITY"])
    euro_data = process_cftc(cftc_df, ["EURO FX", "CHICAGO"])
    
    # 宏观数据
    fed, nfp, cpi, claims = get_macro_data()

st.title("Smart Money & Macro Dashboard")

# 顶部：新闻警报 (基于黄金数据的日期)
if not gold_data.empty:
    last_val = gold_data.iloc[-1]
    render_news_alert(last_val['Date_Display'])

# 选项卡
tab1, tab2 = st.tabs(["📊 COT 机构持仓", "🌍 宏观经济 (Macro)"])

with tab1:
    def simple_chart(data, name, color):
        if data.empty: 
            st.warning(f"{name}: 暂无数据")
            return
        
        last_date = data['Date_Display'].iloc[-1].strftime('%Y-%m-%d')
        net_pos = int(data['Net'].iloc[-1])
        
        # 指标卡
        st.metric(f"{name} Managed Money", f"{net_pos:,}", f"Report: {last_date}")
        
        # 图表
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=data['Date_Display'], y=data['Net'], fill='tozeroy', line=dict(color=color), name='Net Pos'))
        fig.update_layout(height=350, margin=dict(t=10,b=0,l=0,r=0))
        st.plotly_chart(fig, use_container_width=True)

    c1, c2 = st.columns(2)
    with c1: simple_chart(gold_data, "Gold (XAU)", "#FFD700")
    with c2: simple_chart(euro_data, "Euro (EUR)", "#00d2ff")

with tab2:
    render_fomc_card()
    st.divider()
    
    if fed is not None and not fed.empty:
        m1, m2, m3, m4 = st.columns(4)
        
        # 利率
        curr_rate = fed['FEDFUNDS'].iloc[-1]
        m1.metric("🇺🇸 Fed Funds Rate", f"{curr_rate:.2f}%")
        
        # CPI
        if cpi is not None and len(cpi) > 12:
            curr_cpi = cpi['YoY'].iloc[-1]
            prev_cpi = cpi['YoY'].iloc[-2]
            m2.metric("🔥 CPI (YoY)", f"{curr_cpi:.1f}%", f"{curr_cpi-prev_cpi:.1f}%", delta_color="inverse")
        
        # NFP
        if nfp is not None and len(nfp) > 1:
            curr_nfp = int(nfp['Change'].iloc[-1])
            prev_nfp = int(nfp['Change'].iloc[-2])
            m3.metric("👷 NFP Change", f"{curr_nfp:,} K", f"{curr_nfp-prev_nfp:,} K")
        
        # Claims
        if claims is not None:
            curr_claims = int(claims['ICSA'].iloc[-1])
            m4.metric("🤕 Jobless Claims", f"{curr_claims:,}")
        
        st.divider()
        
        # 图表
        c1, c2 = st.columns(2)
        with c1:
            st.subheader("通胀趋势 (CPI YoY)")
            if cpi is not None: st.line_chart(cpi['YoY'].tail(24))
        
        with c2:
            st.subheader("就业市场 (NFP Change)")
            if nfp is not None: st.bar_chart(nfp['Change'].tail(24))
            
    else:
        st.warning("宏观数据暂不可用 (FRED API 连接超时)，请稍后刷新。")
