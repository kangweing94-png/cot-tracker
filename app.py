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

# ========= TradingEconomics API Key（你的，现阶段只用来查状态） =========
TE_API_KEY = "a7d624f316a049e:nmasw3jt5rkbeoi"


# ========= 侧边栏 =========
with st.sidebar:
    st.header("⚡ 控制台")
    if st.button("🔄 刷新全站数据"):
        st.cache_data.clear()
        st.rerun()

    st.divider()
    st.caption("数据源:\n- CFTC (COT)\n- FRED (主数据)\n- TradingEconomics (状态诊断)")


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
    """
    按 name_keywords 筛选某个品种，并算 Managed Money 净持仓
    完全用你之前验证过的逻辑：
      - 名称列: market+exchange 或 contract+name
      - XAU: ["GOLD","COMMODITY"]
      - EUR: ["EURO FX","CHICAGO"]
      - GBP: ["BRITISH POUND","CHICAGO"]
    """
    if df.empty:
        return pd.DataFrame()

    # 1. 合约名称列
    name_col = find_column(df.columns, ["market", "exchange"]) or find_column(
        df.columns, ["contract", "name"]
    )
    if not name_col:
        return pd.DataFrame()

    # 2. 品种筛选
    mask = df[name_col].apply(
        lambda x: any(k in str(x).upper() for k in name_keywords)
    )
    data = df[mask].copy()
    if data.empty:
        return pd.DataFrame()

    # 3. 日期列
    date_col = find_column(df.columns, ["report", "date"]) or find_column(
        df.columns, ["as", "of", "date"]
    )
    if not date_col:
        return pd.DataFrame()
    data[date_col] = pd.to_datetime(data[date_col], errors="coerce")
    data = data.dropna(subset=[date_col])

    # 4. Managed Money 多空列
    long_col = find_column(df.columns, ["money", "long"])
    short_col = find_column(df.columns, ["money", "short"])
    if not long_col or not short_col:
        return pd.DataFrame()

    data["Net"] = data[long_col] - data[short_col]
    data["Date_Display"] = data[date_col]

    data = data.sort_values("Date_Display")
    data = data.drop_duplicates(subset=["Date_Display"], keep="last")

    return data.tail(156)  # 最近三年


# ======================================================================
# 模块 2: FRED 宏观数据 + TE 状态诊断
# ======================================================================

def _fred_series(series_id: str, backup_name: str):
    """
    FRED CSV + 本地备份，返回 (series, status_text)
    """
    base_url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series_id}"
    headers = {"User-Agent": "Mozilla/5.0"}

    # 在线尝试
    try:
        r = requests.get(base_url, headers=headers, timeout=6)
        if r.status_code == 200:
            df = pd.read_csv(io.BytesIO(r.content))
            df["DATE"] = pd.to_datetime(df["DATE"])
            df = df[["DATE", series_id]].rename(columns={series_id: "VALUE"})
            df.set_index("DATE", inplace=True)
            df.sort_index(inplace=True)
            # 备份
            df.to_csv(os.path.join(DATA_DIR, backup_name))
            return df["VALUE"], "FRED 在线"
    except Exception:
        pass

    # 本地备份
    try:
        path = os.path.join(DATA_DIR, backup_name)
        df = pd.read_csv(path)
        df["DATE"] = pd.to_datetime(df["DATE"])
        df.set_index("DATE", inplace=True)
        df.sort_index(inplace=True)
        return df["VALUE"], "FRED 本地备份"
    except Exception:
        return None, "FRED 无数据"


def _te_status_only(country: str, indicator: str):
    """
    只拿 TE 的状态码，不用它的数据
    """
    if not TE_API_KEY:
        return "TE: 没有 API Key"

    url = f"https://api.tradingeconomics.com/historical/country/{country}/indicator/{indicator}"
    params = {"c": TE_API_KEY, "f": "json"}
    try:
        r = requests.get(url, params=params, timeout=5)
        return f"TE {indicator} HTTP {r.status_code}"
    except Exception as e:
        return f"TE {indicator} 请求失败: {type(e).__name__}"


@st.cache_data(ttl=3600 * 3)
def get_macro_fred_only():
    """
    真正用于绘图/指标的宏观数据全部来自 FRED。
    同时做一份 TE 状态报告，方便你之后和 TE 客服对话。
    """
    sources = {}

    # Fed Funds
    fed, fed_src = _fred_series("FEDFUNDS", "fedfunds.csv")
    te_fed_status = _te_status_only("united states", "interest rate")
    sources["fed_funds"] = f"{fed_src} | {te_fed_status}"

    # CPI YoY
    cpi_raw, cpi_src = _fred_series("CPIAUCSL", "cpi.csv")
    if cpi_raw is not None:
        cpi_yoy = cpi_raw.pct_change(12) * 100
    else:
        cpi_yoy = None
    te_cpi_status = _te_status_only("united states", "inflation rate")
    sources["cpi_yoy"] = f"{cpi_src} | {te_cpi_status}"

    # NFP Change
    nfp_raw, nfp_src = _fred_series("PAYEMS", "nfp.csv")
    if nfp_raw is not None:
        nfp_change = nfp_raw.diff()
    else:
        nfp_change = None
    te_nfp_status = _te_status_only("united states", "non farm payrolls")
    sources["nfp_change"] = f"{nfp_src} | {te_nfp_status}"

    # Jobless Claims
    claims_raw, claims_src = _fred_series("ICSA", "claims.csv")
    te_claims_status = _te_status_only("united states", "jobless claims")
    sources["jobless_claims"] = f"{claims_src} | {te_claims_status}"

    # 组装 DataFrame
    series_map = {
        "fed_funds": fed,
        "cpi_yoy": cpi_yoy,
        "nfp_change": nfp_change,
        "jobless_claims": claims_raw,
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
    xau_data = process_cftc(cftc_df, ["GOLD", "COMMODITY"])
    eur_data = process_cftc(cftc_df, ["EURO FX", "CHICAGO"])
    gbp_data = process_cftc(cftc_df, ["BRITISH POUND", "CHICAGO"])

    # 宏观：FRED 为主，TE 做状态诊断
    macro_df, macro_sources = get_macro_fred_only()

st.title("Smart Money & Macro Dashboard")

# CFTC 顶部警报
if not xau_data.empty:
    render_cftc_alert(xau_data.iloc[-1]["Date_Display"])

tab1, tab2 = st.tabs(["📊 COT 持仓（XAU / EUR / GBP）", "🌍 宏观经济（FRED + TE 状态）"])


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

    st.subheader("📌 宏观数据来源（FRED + TE 检测）")
    st.json(macro_sources)

    if macro_df.empty:
        st.warning("FRED 也拉不到数据（网络或被墙），宏观区暂时空白。")
    else:
        latest = macro_df.dropna().iloc[-1]

        m1, m2, m3, m4 = st.columns(4)

        # Fed Funds
        if "fed_funds" in macro_df.columns and pd.notna(latest.get("fed_funds", None)):
            m1.metric(
                "🇺🇸 Fed Funds Rate",
                f"{latest['fed_funds']:.2f}%",
            )
        else:
            m1.write("Fed Funds: 无数据")

        # CPI YoY
        if "cpi_yoy" in macro_df.columns and pd.notna(latest.get("cpi_yoy", None)):
            m2.metric(
                "🔥 CPI (YoY)",
                f"{latest['cpi_yoy']:.1f}%",
            )
        else:
            m2.write("CPI YoY: 无数据")

        # NFP Change
        if "nfp_change" in macro_df.columns and pd.notna(latest.get("nfp_change", None)):
            m3.metric(
                "👷 NFP Change",
                f"{int(latest['nfp_change']):,}",
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
            )
        else:
            m4.write("Jobless Claims: 无数据")

        st.divider()

        c1, c2 = st.columns(2)
        with c1:
            st.subheader("通胀趋势 (CPI YoY)")
            if "cpi_yoy" in macro_df.columns and macro_df["cpi_yoy"].notna().sum() > 0:
                st.line_chart(macro_df["cpi_yoy"].tail(60))
            else:
                st.info("暂无 CPI YoY 数据")

        with c2:
            st.subheader("就业市场 - 非农变化 (NFP Change)")
            if (
                "nfp_change" in macro_df.columns
                and macro_df["nfp_change"].notna().sum() > 0
            ):
                st.bar_chart(macro_df["nfp_change"].tail(60))
            else:
                st.info("暂无 NFP Change 数据")

        st.subheader("初请失业金 (Jobless Claims)")
        if (
            "jobless_claims" in macro_df.columns
            and macro_df["jobless_claims"].notna().sum() > 0
        ):
            st.line_chart(macro_df["jobless_claims"].tail(60))
        else:
            st.info("暂无 Jobless Claims 数据")
