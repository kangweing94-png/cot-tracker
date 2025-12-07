import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import datetime
import requests
import io
import time
import numpy as np # 用于处理 NaN

# --- 页面配置 ---
st.set_page_config(page_title="Smart Money & Macro Pro", page_icon="🏦", layout="wide")

# --- 侧边栏 ---
with st.sidebar:
    st.header("⚡ 控制台")
    if st.button("🔄 刷新全站数据"):
        st.cache_data.clear()
        st.rerun()

    st.divider()
    st.caption("数据源:\n- CFTC (COT) - 自动抓取\n- FRED (宏观经济) - 纯 CSV 模式")

# ======================================================================
# 模块 1: CFTC 核心逻辑（恢复 Gold 精度）
# ======================================================================
@st.cache_data(ttl=3600 * 3)
def get_cftc_data():
    year = datetime.datetime.now().year
    # 采用 Disaggregated 报告 (Managed Money)
    url_history = f"https://www.cftc.gov/files/dea/history/fut_disagg_txt_{year}.zip"
    url_latest = "https://www.cftc.gov/dea/newcot/f_disagg.txt"

    headers = {"User-Agent": "Mozilla/5.0"}
    
    df_hist = pd.DataFrame()
    df_live = pd.DataFrame()

    # 1. 历史包 (带时间戳防 CDN 缓存)
    try:
        url_hist_bust = f"{url_history}?t={int(time.time())}"
        r = requests.get(url_hist_bust, headers=headers, verify=False, timeout=10)
        if r.status_code == 200:
            df_hist = pd.read_csv(io.BytesIO(r.content), compression="zip", low_memory=False)
    except Exception:
        pass

    # 2. 最新一周 (实时)
    try:
        r2 = requests.get(f"{url_latest}?t={int(time.time())}", headers=headers, verify=False, timeout=5)
        if r2.status_code == 200 and not df_hist.empty:
            df_live = pd.read_csv(io.BytesIO(r2.content), header=None, low_memory=False)
            df_live.columns = df_hist.columns # 强行对齐列名
    except Exception:
        pass

    if df_hist.empty and df_live.empty:
        return pd.DataFrame()

    return pd.concat([df_hist, df_live], ignore_index=True)


def find_column(columns, keywords):
    for col in columns:
        c = str(col).lower()
        if all(k in c for k in keywords):
            return col
    return None


def process_cftc(df, name_keywords):
    """恢复最精度的 Gold/Euro 数据处理逻辑"""
    if df.empty: return pd.DataFrame()

    try:
        # 1. 找名字 (Name/Market)
        name_col = find_column(df.columns, ['market', 'exchange']) or find_column(df.columns, ['contract', 'name'])
        if not name_col: return pd.DataFrame()

        # 2. 筛选
        def _match_name(x):
            s = str(x).upper()
            return any(k.upper() in s for k in name_keywords)

        mask = df[name_col].apply(_match_name)
        data = df[mask].copy()
        if data.empty: return pd.DataFrame()

        # 3. 日期列
        date_col = find_column(df.columns, ["report", "date"]) or find_column(df.columns, ["as", "of", "date"])
        if not date_col: return pd.DataFrame()
        
        data[date_col] = pd.to_datetime(data[date_col], errors="coerce")
        data = data.dropna(subset=[date_col])

        # 4. Managed Money 多空列
        long_col = find_column(df.columns, ["money", "long"])
        short_col = find_column(df.columns, ["money", "short"])
        if not long_col or not short_col: return pd.DataFrame()

        data["Net"] = data[long_col].astype(float) - data[short_col].astype(float)
        data["Date_Display"] = data[date_col]

        # 5. 去重
        data = data.sort_values("Date_Display")
        data = data.drop_duplicates(subset=["Date_Display"], keep="last")

        return data.tail(156)

    except Exception:
        return pd.DataFrame()


# ======================================================================
# 模块 2: FRED 宏观数据（纯 CSV 模式）
# ======================================================================
@st.cache_data(ttl=3600 * 3)
def get_macro_from_fred():
    """直接读取 FRED CSV，不依赖 API Key"""
    base_url = "https://fred.stlouisfed.org/graph/fredgraph.csv?id="
    
    def fetch_fred_csv(series_id):
        try:
            url = f"{base_url}{series_id}"
            headers = {"User-Agent": "Mozilla/5.0"}
            
            r = requests.get(url, headers=headers, timeout=8)
            r.raise_for_status()
            
            df = pd.read_csv(io.StringIO(r.text))
            df['DATE'] = pd.to_datetime(df['DATE'])
            df.set_index('DATE', inplace=True)
            return df
        except Exception:
            return None

    # Series IDs
    fed_raw = fetch_fred_csv('FEDFUNDS')
    nfp_raw = fetch_fred_csv('PAYEMS')
    cpi_raw = fetch_fred_csv('CPIAUCSL')
    claims_raw = fetch_fred_csv('ICSA')
    
    series_map = {}
    if fed_raw is not None: series_map['fed_funds'] = fed_raw['FEDFUNDS']
    if nfp_raw is not None: series_map['nfp_change'] = nfp_raw['PAYEMS'].diff()
    if cpi_raw is not None: series_map['cpi_yoy'] = cpi_raw['CPIAUCSL'].pct_change(12) * 100
    if claims_raw is not None: series_map['jobless_claims'] = claims_raw['ICSA']
    
    if not series_map: return pd.DataFrame()

    macro_df = pd.concat(series_map.values(), axis=1)
    macro_df.columns = list(series_map.keys())
    macro_df.sort_index(inplace=True)

    return macro_df

# ======================================================================
# UI 组件
# ======================================================================
def render_cftc_alert(last_date):
    if pd.isnull(last_date) or last_date.year < 2000: return
    days_diff = (datetime.datetime.now() - last_date).days
    
    if days_diff > 21:
        st.error(f"🚨 **MARKET ALERT: 数据严重滞后 ({days_diff}天)**")
        with st.expander("📰 **News Headline: 为什么数据停更了？** (点击展开)", expanded=True):
            st.markdown(f"""
            #### 🏛️ 美国政府停摆导致 CFTC 报告积压
            **事件影响**: 由于美国政府在 **2025年10月** 期间发生停摆 (Government Shutdown)，CFTC 暂停了所有数据处理。
            
            **当前状态**: 正在按顺序补发历史报告，预计 2026年1月 恢复正常。
            
            *此数据最后更新于: {last_date.strftime('%Y-%m-%d')}*
            """)

def render_fomc_card():
    fomc_dates = [datetime.date(2025, 12, 10), datetime.date(2026, 1, 28), datetime.date(2026, 3, 18)]
    today = datetime.date.today()
    next_meet = next((d for d in fomc_dates if d >= today), None)
            
    st.markdown("### 🏦 FOMC 联邦公开市场委员会")
    c1, c2 = st.columns([2, 1])
    with c1:
        if next_meet:
            days = (next_meet - today).days
            st.info(f"📅 下次利率决议: **{next_meet}**（还剩 {days} 天）")
        else:
            st.info("📅 下次会议：待定")
    with c2:
        st.link_button("📊 查看最新点阵图", "https://www.federalreserve.gov/monetarypolicy/fomcprojtabl20250917.htm")

def cot_chart(data, title, color):
    if data.empty:
        st.warning(f"{title}: 暂无数据（请检查 CFTC 官网是否有更新）")
        return

    last_row = data.iloc[-1]
    last_date = last_row["Date_Display"].strftime("%Y-%m-%d")
    net = int(last_row["Net"])

    st.metric(f"{title} Managed Money", f"{net:,}", f"报告日期: {last_date}")

    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=data["Date_Display"],
            y=data["Net"],
            fill="tozeroy",
            line=dict(color=color),
            name="Net Pos",
        )
    )
    fig.update_layout(
        height=300,
        margin=dict(t=10, b=0, l=0, r=0),
        xaxis_title="Report Date",
        yaxis_title="Net Position",
    )
    st.plotly_chart(fig, use_container_width=True)

# ======================================================================
# 主程序
# ======================================================================
with st.spinner("正在同步 COT & 宏观数据…"):
    # CFTC 数据抓取
    cftc_df = get_cftc_data()
    gold_data = process_cftc(cftc_df, ["GOLD", "COMMODITY"])
    euro_data = process_cftc(cftc_df, ["EURO FX"])
    gbp_data = process_cftc(cftc_df, ["BRITISH POUND"])
    
    # 宏观数据抓取
    macro_df = get_macro_from_fred()

st.title("Smart Money & Macro Dashboard")

# 顶部：CFTC 警报
if not gold_data.empty:
    render_cftc_alert(gold_data.iloc[-1]["Date_Display"])

tab1, tab2 = st.tabs(["📊 COT 持仓（EUR / GBP / XAU）", "🌍 宏观经济"])

# ---------- Tab1: COT ----------
with tab1:
    c1, c2 = st.columns(2)
    with c1:
        st.subheader("Euro (EUR) 期货 - Managed Money 净持仓")
        cot_chart(euro_data, "Euro (EUR)", "#00d2ff")
    with c2:
        st.subheader("British Pound (GBP) 期货 - Managed Money 净持仓")
        cot_chart(gbp_data, "British Pound (GBP)", "#ff7f0e")

    st.subheader("Gold (XAU) 期货 - Managed Money 净持仓")
    cot_chart(gold_data, "Gold (XAU)", "#FFD700")


# ---------- Tab2: 宏观 ----------
with tab2:
    render_fomc_card()
    st.divider()

    if macro_df.empty:
        st.warning("FRED 数据未能拉取，宏观区暂时空白。")
    else:
        latest = macro_df.dropna().iloc[-1] if not macro_df.dropna().empty else pd.Series()

        m1, m2, m3, m4 = st.columns(4)
        
        # 指标展示
        if "fed_funds" in macro_df.columns and not latest.empty and pd.notna(latest.get("fed_funds", None)):
            m1.metric("🇺🇸 Fed Funds Rate", f"{latest['fed_funds']:.2f}%")
        
        if "cpi_yoy" in macro_df.columns and not latest.empty and pd.notna(latest.get("cpi_yoy", None)):
            m2.metric("🔥 CPI (YoY)", f"{latest['cpi_yoy']:.1f}%")
        
        if "nfp_change" in macro_df.columns and not latest.empty and pd.notna(latest.get("nfp_change", None)):
            m3.metric("👷 NFP Change", f"{int(latest['nfp_change']):,}")

        if "jobless_claims" in macro_df.columns and not latest.empty and pd.notna(latest.get("jobless_claims", None)):
            m4.metric("🤕 Jobless Claims", f"{int(latest['jobless_claims']):,}")

        st.divider()

        # 图表展示
        c1, c2 = st.columns(2)
        with c1:
            st.subheader("通胀趋势 (CPI YoY)")
            if "cpi_yoy" in macro_df.columns: st.line_chart(macro_df["cpi_yoy"].tail(60))
        
        with c2:
            st.subheader("就业市场 (NFP Change)")
            if "nfp_change" in macro_df.columns: st.bar_chart(macro_df["nfp_change"].tail(60))

        st.subheader("初请失业金 (Jobless Claims)")
        if "jobless_claims" in macro_df.columns: st.line_chart(macro_df["jobless_claims"].tail(60))
