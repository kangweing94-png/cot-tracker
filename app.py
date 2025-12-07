import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import datetime
import requests
import io
import time
import random
import pytz
import pandas_datareader.data as web # 新增：宏观数据神器

# --- 页面配置 ---
st.set_page_config(page_title="Smart Money & Macro Pro", page_icon="🏦", layout="wide")

# --- 侧边栏 ---
with st.sidebar:
    st.header("⚡ 控制台")
    if st.button("🔄 刷新全站数据"):
        st.cache_data.clear()
        st.rerun()
    
    st.divider()
    st.caption("数据源:\n1. CFTC (持仓)\n2. FRED (宏观经济)\n3. Federal Reserve (利率)")

# ==============================================================================
# 模块 1: CFTC 持仓数据 (自动抓取 + 拼合)
# ==============================================================================
@st.cache_data(ttl=3600*3)
def get_cftc_data():
    year = datetime.datetime.now().year
    # 模拟用户提到的"2025年政府停摆"场景，如果当前是2024，我们依然去抓取当年的
    
    url_history = f"https://www.cftc.gov/files/dea/history/fut_disagg_txt_{year}.zip"
    url_latest = "https://www.cftc.gov/dea/newcot/f_disagg.txt"
    
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0 Safari/537.36"}
    
    df_hist = pd.DataFrame()
    df_live = pd.DataFrame()

    try:
        r = requests.get(url_history, headers=headers, verify=False, timeout=10)
        if r.status_code == 200:
            df_hist = pd.read_csv(io.BytesIO(r.content), compression='zip', low_memory=False)
    except: pass

    try:
        r2 = requests.get(f"{url_latest}?t={int(time.time())}", headers=headers, verify=False, timeout=5)
        if r2.status_code == 200 and not df_hist.empty:
            df_live = pd.read_csv(io.BytesIO(r2.content), header=None, low_memory=False)
            df_live.columns = df_hist.columns
    except: pass

    if df_hist.empty and df_live.empty: return pd.DataFrame()
    return pd.concat([df_hist, df_live], ignore_index=True)

def process_cftc(df, keywords):
    if df.empty: return pd.DataFrame()
    # 简化版处理逻辑
    try:
        name_col = [c for c in df.columns if 'Market' in str(c) or 'Contract' in str(c)][0]
        date_col = [c for c in df.columns if 'Date' in str(c)][0]
        long_col = [c for c in df.columns if 'Money' in str(c) and 'Long' in str(c)][0]
        short_col = [c for c in df.columns if 'Money' in str(c) and 'Short' in str(c)][0]
        
        mask = df[name_col].apply(lambda x: any(k in str(x).upper() for k in keywords))
        data = df[mask].copy()
        
        data[date_col] = pd.to_datetime(data[date_col])
        data['Net'] = data[long_col] - data[short_col]
        data = data.sort_values(date_col).drop_duplicates(subset=[date_col], keep='last')
        return data.tail(52)
    except: return pd.DataFrame()

# ==============================================================================
# 模块 2: 宏观经济数据 (FRED API)
# ==============================================================================
@st.cache_data(ttl=3600*12)
def get_macro_data():
    # start_date = datetime.datetime(2023, 1, 1) # 获取最近两年的数据
    start_date = datetime.datetime.now() - datetime.timedelta(days=730)
    
    try:
        # 1. 联邦基金利率 (Fed Funds Rate)
        fed_rate = web.DataReader('FEDFUNDS', 'fred', start_date)
        
        # 2. 非农就业 (NFP - Total Nonfarm) -> 计算差值(新增人数)
        nfp = web.DataReader('PAYEMS', 'fred', start_date)
        nfp['Change'] = nfp['PAYEMS'].diff() 
        
        # 3. CPI (Headline & Core) -> 计算年率(YoY)
        cpi = web.DataReader('CPIAUCSL', 'fred', start_date) # Headline
        cpi['YoY'] = cpi['CPIAUCSL'].pct_change(12) * 100
        
        # 4. 初请失业金 (Jobless Claims)
        claims = web.DataReader('ICSA', 'fred', start_date)
        
        return fed_rate, nfp, cpi, claims
    except Exception as e:
        st.error(f"宏观数据获取失败 (FRED源): {e}")
        return None, None, None, None

# ==============================================================================
# 模块 3: UI 渲染组件
# ==============================================================================
def render_news_alert(last_date_obj):
    """检测数据滞后并显示新闻头条"""
    if not last_date_obj: return
    
    days_diff = (datetime.datetime.now() - last_date_obj).days
    
    # 如果数据滞后超过 14 天，触发新闻警报
    if days_diff > 14:
        st.error(f"🚨 **MARKET ALERT: 数据严重滞后 ({days_diff}天)**")
        with st.expander("📰 **News Headline: 为什么数据停更了？** (点击展开)", expanded=True):
            st.markdown(f"""
            #### 🏛️ 美国政府停摆导致 CFTC 报告积压
            **事件影响**: 由于美国政府在 **2025年10月** 期间发生停摆 (Government Shutdown)，CFTC 暂停了所有数据处理。
            
            **当前状态**: 
            * 🚫 **积压中**: 也就是你看到的 {last_date_obj.strftime('%Y-%m-%d')} 数据。
            * ⏳ **补交作业**: CFTC 正在按时间顺序补发历史报告。
            * 📅 **恢复预期**: 预计 2026年1月 才能完全追上实时进度。
            
            *建议: 短期内请更多参考价格行为 (Price Action) 和实时宏观指标。*
            """)

def render_fomc_card():
    """FOMC 会议日程卡片"""
    # 这里硬编码 2025/2026 的一些关键日期 (示例)
    fomc_dates = [
        datetime.date(2025, 12, 10),
        datetime.date(2026, 1, 28),
        datetime.date(2026, 3, 18)
    ]
    today = datetime.date.today()
    next_meet = None
    for d in fomc_dates:
        if d >= today:
            next_meet = d
            break
            
    st.markdown("### 🏦 FOMC 联邦公开市场委员会")
    
    c1, c2 = st.columns([2, 1])
    with c1:
        if next_meet:
            days_left = (next_meet - today).days
            st.info(f"📅 下次利率决议: **{next_meet}** (还剩 {days_left} 天)")
        else:
            st.info("📅 下次会议: 待定 (TBA)")
            
    with c2:
        # 提供官方链接作为"点阵图"的替代方案
        st.link_button("📊 查看最新点阵图 (Fed官网)", "https://www.federalreserve.gov/monetarypolicy/fomcprojtabl20250917.htm")

# ==============================================================================
# 主程序逻辑
# ==============================================================================

# 1. 抓取数据
with st.spinner('正在同步华尔街数据...'):
    cftc_df = get_cftc_data()
    gold_data = process_cftc(cftc_df, ["GOLD", "COMMODITY"])
    euro_data = process_cftc(cftc_df, ["EURO FX", "CHICAGO"])
    
    # 宏观数据
    fed, nfp, cpi, claims = get_macro_data()

# 2. 页面布局
st.title("Smart Money & Macro Dashboard")

# 3. 顶部：新闻警报检测
if not gold_data.empty:
    last_date = gold_data.iloc[-1].name if hasattr(gold_data.iloc[-1], 'name') else gold_data.index[-1]
    # 注意：上面的 process_cftc 返回的是 DataFrame，最后一列是日期
    # 这里我们重新取一下日期对象
    actual_date = gold_data.columns[0] if 'Date' in str(gold_data.columns[0]) else None 
    # 修正：直接用数据里的日期列
    cols = gold_data.columns
    date_col = [c for c in cols if 'Date' in str(c)][0]
    last_date_val = gold_data.iloc[-1][date_col]
    
    render_news_alert(last_date_val)

# 4. 选项卡布局
tab1, tab2 = st.tabs(["📊 COT 机构持仓", "🌍 宏观经济 (Macro)"])

with tab1:
    # 渲染 COT 图表 (复用之前的逻辑，简化展示)
    def simple_chart(data, name, color):
        if data.empty: return
        date_c = [c for c in data.columns if 'Date' in str(c)][0]
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=data[date_c], y=data['Net'], fill='tozeroy', line=dict(color=color), name='Managed Money'))
        fig.update_layout(title=f"{name} Net Positions", height=300, margin=dict(t=30,b=0,l=0,r=0))
        st.plotly_chart(fig, use_container_width=True)

    c1, c2 = st.columns(2)
    with c1: simple_chart(gold_data, "Gold (XAU)", "#FFD700")
    with c2: simple_chart(euro_data, "Euro (EUR)", "#00d2ff")

with tab2:
    # --- 宏观面板 ---
    render_fomc_card()
    st.divider()
    
    if fed is not None:
        # 第一行：关键指标大数字
        m1, m2, m3, m4 = st.columns(4)
        
        # 利率
        curr_rate = fed['FEDFUNDS'].iloc[-1]
        m1.metric("🇺🇸 Fed Funds Rate", f"{curr_rate:.2f}%", help="美联储基准利率")
        
        # CPI 通胀
        curr_cpi = cpi['YoY'].iloc[-1]
        prev_cpi = cpi['YoY'].iloc[-2]
        m2.metric("🔥 CPI Inflation (YoY)", f"{curr_cpi:.1f}%", f"{curr_cpi-prev_cpi:.1f}%", delta_color="inverse")
        
        # NFP 非农
        curr_nfp = int(nfp['Change'].iloc[-1])
        prev_nfp = int(nfp['Change'].iloc[-2])
        m3.metric("👷 NFP (非农新增)", f"{curr_nfp:,} K", f"{curr_nfp-prev_nfp:,} K")
        
        # 失业金
        curr_claims = int(claims['ICSA'].iloc[-1])
        m4.metric("🤕 Jobless Claims", f"{curr_claims:,}", help="初请失业金人数")
        
        st.divider()
        
        # 第二行：图表展示
        c1, c2 = st.columns(2)
        with c1:
            st.subheader("通胀趋势 (CPI YoY)")
            st.line_chart(cpi['YoY'].tail(24)) # 只看最近24个月
        
        with c2:
            st.subheader("就业市场 (NFP Change)")
            st.bar_chart(nfp['Change'].tail(24))
            
    else:
        st.warning("宏观数据加载失败，可能是 FRED 接口暂时繁忙，请稍后刷新。")
