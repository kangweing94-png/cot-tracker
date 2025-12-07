import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import datetime
import requests
import io
import time
import os

# ========= 全局配置 =========
st.set_page_config(page_title="Smart Money & Macro Pro", page_icon="🏦", layout="wide")

DATA_DIR = "data"
os.makedirs(DATA_DIR, exist_ok=True)

# ========= TradingEconomics API Key（你的） =========
TE_API_KEY = "a7d624f316a049e:nmasw3jt5rkbeoi"


# ========= 侧边栏 =========
with st.sidebar:
    st.header("⚡ 控制台")
    if st.button("🔄 刷新全站数据"):
        st.cache_data.clear()
        st.rerun()

    st.divider()
    st.caption("数据源:\n- CFTC (COT)\n- TradingEconomics (Macro)")


# ======================================================================
# 模块 1: CFTC 核心逻辑（XAU / EUR / GBP）
# ======================================================================
@st.cache_data(ttl=3600 * 3)
def get_cftc_data():
    year = datetime.datetime.now().year
    url_history = f"https://www.cftc.gov/files/dea/history/fut_disagg_txt_{year}.zip"
    url_latest = "https://www.cftc.gov/dea/newcot/f_disagg.txt"

    headers = {"User-Agent": "Mozilla/5.0"}

    df_hist = pd.DataFrame()
    df_live = pd.DataFrame()

    # 历史包
    try:
        r = requests.get(url_history, headers=headers, verify=False, timeout=10)
        if r.status_code == 200:
            df_hist = pd.read_csv(
                io.BytesIO(r.content), compression="zip", low_memory=False
            )
    except Exception:
        pass

    # 最新一周
    try:
        r2 = requests.get(
            f"{url_latest}?t={int(time.time())}",
            headers=headers,
            verify=False,
            timeout=5,
        )
        if r2.status_code == 200 and not df_hist.empty:
            df_live = pd.read_csv(
                io.BytesIO(r2.content), header=None, low_memory=False
            )
            df_live.columns = df_hist.columns
    except Exception:
        pass

    if df_hist.empty and df_live.empty:
        return pd.DataFrame()

    return pd.concat([df_hist, df_live], ignore_index=True)


def find_column(columns, keywords):
    """在列名中找到同时包含所有 keywords 的列"""
    for col in columns:
        c = str(col).lower()
        if all(k in c for k in keywords):
            return col
    return None


def process_cftc(df, name_keywords):
    """按 name_keywords 筛选某个品种，并算 Managed Money 净持仓"""
    if df.empty:
        return pd.DataFrame()

    # 品种名称列
    name_col = (
        find_column(df.columns, ["market", "name"])
        or find_column(df.columns, ["market"])
        or find_column(df.columns, ["contract"])
    )
    if not name_col:
        return pd.DataFrame()

    mask = df[name_col].apply(
        lambda x: any(k in str(x).upper() for k in name_keywords)
    )
    data = df[mask].copy()
    if data.empty:
        return pd.DataFrame()

    # 日期列
    date_col = (
        find_column(df.columns, ["report", "date"])
        or find_column(df.columns, ["as", "of", "date"])
        or find_column(df.columns, ["date"])
    )
    if not date_col:
        return pd.DataFrame()

    data[date_col] = pd.to_datetime(data[date_col], errors="coerce")
    data = data.dropna(subset=[date_col])

    # Managed Money 多空
    long_col = find_column(df.columns, ["money", "long"])
    short_col = find_column(df.columns, ["money", "short"])
    if not long_col or not short_col:
        return pd.DataFrame()

    data["Net"] = data[long_col] - data[short_col]
    data["Date_Display"] = data[date_col]

    data = data.sort_values("Date_Display")
    data = data.drop_duplicates(subset=["Date_Display"], keep="last")

    return data.tail(156)  # 三年左右周数据


# ======================================================================
# 模块 2: TradingEconomics 宏观数据
# ======================================================================

def _te_historical(country: str, indicator: str):
    """
    从 TradingEconomics 拉一个国家 + 指标的历史数据
    返回 df(index=DATE, columns=['VALUE']) 或 None
    """
    if not TE_API_KEY:
        return None

    url = f"https://api.tradingeconomics.com/historical/country/{country}/indicator/{indicator}"
    params = {"c": TE_API_KEY, "f": "json"}

    try:
        r = requests.get(url, params=params, timeout=8)
        r.raise_for_status()
        js = r.json()
        if not js:
            return None

        df = pd.DataFrame(js)

        # 适配字段名（官方文档：DateTime + Value）:contentReference[oaicite:0]{index=0}
        candidates_date = ["DateTime", "Date", "date", "Datetime", "datetime"]
        candidates_val = ["Value", "Close", "value", "close"]

        date_col = next((c for c in candidates_date if c in df.columns), None)
        val_col = next((c for c in candidates_val if c in df.columns), None)

        if not date_col or not val_col:
            return None

        df[date_col] = pd.to_datetime(df[date_col])
        df = df[[date_col, val_col]].rename(
            columns={date_col: "DATE", val_col: "VALUE"}
        )
        df.set_index("DATE", inplace=True)
        df.sort_index(inplace=True)
        return df

    except Exception:
        return None


@st.cache_data(ttl=3600 * 3)
def get_macro_from_te():
    """
    从 TradingEconomics 获取美国核心宏观：
    - fed_funds: 利率
    - cpi_yoy: 通胀
    - nfp_change: 非农变化
    - jobless_claims: 初请
    """
    sources = {}

    # 利率
    fed_df = _te_historical("united states", "interest rate")
    if fed_df is not None:
        fed_series = fed_df["VALUE"]
        sources["fed_funds"] = "TradingEconomics - Interest Rate (United States)"
    else:
        fed_series = None
        sources["fed_funds"] = "无数据"

    # 通胀 (Inflation Rate，本身就是 YoY)
    cpi_df = _te_historical("united states", "inflation rate")
    if cpi_df is not None:
        cpi_series = cpi_df["VALUE"]
        sources["cpi_yoy"] = "TradingEconomics - Inflation Rate (United States)"
    else:
        cpi_series = None
        sources["cpi_yoy"] = "无数据"

    # 非农 (Non Farm Payrolls)，取变化
    nfp_df = _te_historical("united states", "non farm payrolls")
    if nfp_df is not None:
        nfp_change = nfp_df["VALUE"].diff()
        sources["nfp_change"] = "TradingEconomics - Non Farm Payrolls (diff)"
    else:
        nfp_change = None
        sources["nfp_change"] = "无数据"

    # 初请 (Initial Jobless Claims / Jobless Claims 二选一)
    claims_df = _te_historical("united states", "initial jobless claims")
    if claims_df is None:
        claims_df = _te_historical("united states", "jobless claims")

    if claims_df is not None:
        claims_series = claims_df["VALUE"]
        sources["jobless_claims"] = "TradingEconomics - Jobless Claims (United States)"
    else:
        claims_series = None
        sources["jobless_claims"] = "无数据"

    # 组装
    series_map = {
        "fed_funds": fed_series,
        "cpi_yoy": cpi_series,
        "nfp_change": nfp_change,
        "jobless_claims": claims_series,
    }

    non_null = {k: v for k, v in series_map.items() if v is not None}

    if not non_null:
        return pd.DataFrame(), sources

    macro_df = pd.concat(non_null.values(), axis=1)
    macro_df.columns = list(non_null.keys())
    macro_df.sort_index(inplace=True)

    return macro_df, sources


# ======================================================================
# UI 组件
# ======================================================================
def render_cftc_alert(last_date):
    if pd.isnull(last_date):
        return
    diff = (datetime.datetime.now() - last_date).days
    if diff > 21:
        st.error(f"⚠️ CFTC 数据已滞后 {diff} 天（可能政府停摆或官网维护）")


def render_fomc_card():
    fomc_dates = [
        datetime.date(2025, 12, 10),
        datetime.date(2026, 1, 28),
        datetime.date(2026, 3, 18),
    ]
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
        st.link_button(
            "📊 查看最新点阵图",
            "https://www.federalreserve.gov/monetarypolicy/fomcprojtabl20250917.htm",
        )


def cot_chart(data, title, color):
    if data.empty:
        st.warning(f"{title}: 暂无数据")
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
            name="Net",
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
    # CFTC
    cftc_df = get_cftc_data()
    xau_data = process_cftc(cftc_df, ["GOLD"])
    eur_data = process_cftc(cftc_df, ["EURO FX"])
    gbp_data = process_cftc(cftc_df, ["BRITISH POUND"])

    # 宏观（TradingEconomics）
    macro_df, macro_sources = get_macro_from_te()

st.title("Smart Money & Macro Dashboard")

# CFTC 顶部警报
if not xau_data.empty:
    render_cftc_alert(xau_data.iloc[-1]["Date_Display"])

tab1, tab2 = st.tabs(["📊 COT 持仓（XAU / EUR / GBP）", "🌍 宏观经济（TradingEconomics）"])


# ---------- Tab1: COT ----------
with tab1:
    c1, c2 = st.columns(2)
    with c1:
        st.subheader("Gold (XAU) 期货 - Managed Money 净持仓")
        cot_chart(xau_data, "Gold (XAU)", "#FFD700")
    with c2:
        st.subheader("Euro (EUR) 期货 - Managed Money 净持仓")
        cot_chart(eur_data, "Euro (EUR)", "#00d2ff")

    st.subheader("British Pound (GBP) 期货 - Managed Money 净持仓")
    cot_chart(gbp_data, "British Pound (GBP)", "#ff7f0e")


# ---------- Tab2: 宏观 ----------
with tab2:
    render_fomc_card()
    st.divider()

    st.subheader("📌 数据来源")
    st.json(macro_sources)

    if macro_df.empty:
        st.warning("没有任何宏观数据可用，请检查 TradingEconomics API Key 或网络连接。")
    else:
        latest = macro_df.dropna().iloc[-1]

        m1, m2, m3, m4 = st.columns(4)

        # Fed Funds
        if "fed_funds" in macro_df.columns and pd.notna(latest.get("fed_funds", None)):
            m1.metric(
                "🇺🇸 Fed Funds / Interest Rate",
                f"{latest['fed_funds']:.2f}%",
                help=macro_sources.get("fed_funds", ""),
            )
        else:
            m1.write("Fed Funds: 无数据")

        # CPI YoY
        if "cpi_yoy" in macro_df.columns and pd.notna(latest.get("cpi_yoy", None)):
            m2.metric(
                "🔥 CPI (YoY)",
                f"{latest['cpi_yoy']:.1f}%",
                help=macro_sources.get("cpi_yoy", ""),
            )
        else:
            m2.write("CPI YoY: 无数据")

        # NFP Change
        if "nfp_change" in macro_df.columns and pd.notna(
            latest.get("nfp_change", None)
        ):
            m3.metric(
                "👷 NFP Change",
                f"{int(latest['nfp_change']):,}",
                help=macro_sources.get("nfp_change", ""),
            )
        else:
            m3.write("NFP Change: 无数据")

        # Jobless Claims
        if "jobless_claims" in macro_df.columns and pd.notna(
            latest.get("jobless_claims", None)
        ):
            m4.metric(
                "🤕 Jobless Claims",
                f"{int(latest['jobless_claims']):,}",
                help=macro_sources.get("jobless_claims", ""),
            )
        else:
            m4.write("Jobless Claims: 无数据")

        st.divider()

        c1, c2 = st.columns(2)
        with c1:
            st.subheader("通胀趋势 (CPI YoY)")
            if macro_df["cpi_yoy"].notna().sum() > 0:
                st.line_chart(macro_df["cpi_yoy"].tail(60))
            else:
                st.info("暂无 CPI YoY 数据")

        with c2:
            st.subheader("就业市场 - 非农变化 (NFP Change)")
            if macro_df["nfp_change"].notna().sum() > 0:
                st.bar_chart(macro_df["nfp_change"].tail(60))
            else:
                st.info("暂无 NFP Change 数据")

        st.subheader("初请失业金 (Jobless Claims)")
        if "jobless_claims" in macro_df.columns and macro_df["jobless_claims"].notna().sum() > 0:
            st.line_chart(macro_df["jobless_claims"].tail(60))
        else:
            st.info("暂无 Jobless Claims 数据")
