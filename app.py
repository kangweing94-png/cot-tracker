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
    st.caption("数据源:\n1. CFTC (持仓)\n2. FRED (宏观经济)\n3. Federal Reserve (利率)")
    
    # 增加调试信息
    st.caption(f"Python Env: Streamlit Cloud")

# ==============================================================================
# 模块 1: CFTC 持仓数据 (自动抓取 + 拼合)
# ==============================================================================
@st.cache_data(ttl=3600*3)
def get_cftc_data():
    year = datetime.datetime.now().year
    
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
        if r2.status_code == 200:
            if not df_hist.empty:
                df_live = pd.read_csv(io.BytesIO(r2.content), header=None, low_memory=False)
                df_live.columns = df_hist.columns
            else:
                # 如果历史下载失败，尝试盲猜列名以防报错（虽然很少见）
                pass 
    except: pass

    if df_hist.empty and df_live.empty: return pd.DataFrame()
    
    # 强力拼合
    return pd.concat([df_hist, df_live], ignore_index=True)

def process_cftc(df, keywords):
    if df.empty: return pd.DataFrame()
    try:
        # 模糊搜索列名
        cols = df.columns
        name_col = next((c for c in cols if 'Market' in str(c) or 'Contract' in str(c)), None)
        date_col = next((c for c in cols if 'Date' in str(c) or 'Report' in str(c)), None)
        long_col = next((c for c in cols if 'Money' in str(c) and 'Long' in str(c)), None)
        short_col = next((c for c in cols if 'Money' in str(c) and 'Short' in str(c)), None)
        
        if not all([name_col, date_col, long_col, short_col]): return pd.DataFrame()
        
        mask = df[name_col].apply(lambda x: any(k in str(x).upper() for k in keywords))
        data = df[mask].copy()
        
        data[date_col] = pd.to_datetime(data[date_col])
        data['Net'] = data[long_col] - data[short_col]
        data = data.sort_values(date_col).drop_duplicates(subset=[date_col], keep='last')
        return data.tail(52)
    except: return pd.DataFrame()

# ==============================================================================
# 模块 2: 宏观经济数据 (直接读取 FRED CSV，无需第三方库)
# ==============================================================================
@st.cache_data(ttl=3600*12)
def get_macro_data():
    # FRED 官方 CSV 接口：https://fred.stlouisfed.org/graph/fredgraph.csv?id=SERIES_ID
    base_url = "https://fred.stlouisfed.org/graph/fredgraph.csv?id="
    
    def fetch_fred(series_id):
        try:
            df = pd.read_csv(f"{base_url}{series_id}")
            df['DATE'] = pd.to_datetime(df['DATE'])
            df.set_index('DATE', inplace=True)
            return df
        except Exception as e:
            print(f"Error fetching {series_id}: {e}")
            return None

    # 1. 联邦基金利率
    fed_rate = fetch_fred('FEDFUNDS')
    
    # 2. 非农就业 (Payrolls)
    nfp = fetch_fred('PAYEMS')
    if nfp is not None:
        nfp['Change'] = nfp['PAYEMS'].diff() # 计算新增人数
    
    # 3. CPI 通胀
    cpi = fetch_fred('CPIAUCSL')
    if cpi is not None:
        cpi['YoY'] = cpi['CPIAUCSL'].pct_change(12) * 100 # 计算年率
        
    # 4. 初请失业金
    claims = fetch_fred('ICSA')
    
    return fed_rate, nfp, cpi, claims

# ==============================================================================
# 模块 3: UI 渲染组件
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
            """)

def render_fomc_card():
    # 模拟 2025/2026 关键日期
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
    gold_data = process_cftc(cftc_df, ["GOLD", "COMMODITY"])
    euro_data = process_cftc(cftc_df, ["EURO FX", "CHICAGO"])
    
    # 获取宏观数据
    fed, nfp, cpi, claims = get_macro_data()

st.title("Smart Money & Macro Dashboard")

# 警报检测
if not gold_data.empty:
    # 兼容性处理：获取最后一行的日期
    date_col = next((c for c in gold_data.columns if 'Date' in str(c)), None)
    if date_col:
        render_news_alert(gold_data.iloc[-1][date_col])

# 选项卡
tab1, tab2 = st.tabs(["📊 COT 机构持仓", "🌍 宏观经济 (Macro)"])

with tab1:
    def simple_chart(data, name, color):
        if data.empty: 
            st.warning(f"{name}: 暂无数据")
            return
        date_c = next((c for c in data.columns if 'Date' in str(c)), None)
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=data[date_c], y=data['Net'], fill='tozeroy', line=dict(color=color), name='Net Pos'))
        fig.update_layout(title=f"{name} Managed Money Net", height=350, margin=dict(t=40,b=0,l=0,r=0))
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
