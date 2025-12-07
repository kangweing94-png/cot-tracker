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

# ========= TradingEconomics API Key (已替换) =========
TE_API_KEY = "a7d624f316a049e:nmasw3jt5rkbeoi"


# ========= 侧边栏 =========
with st.sidebar:
    st.header("⚡ 控制台")
    if st.button("🔄 刷新全站数据"):
        st.cache_data.clear()
        st.rerun()

    st.divider()
    st.caption("数据源:\n- CFTC\n- TradingEconomics\n- MacroMicro 本地 CSV\n- FRED + 本地备份")


# ======================================================================
# 模块 1: CFTC 核心逻辑
# ======================================================================
@st.cache_data(ttl=3600*3)
def get_cftc_data():
    year = datetime.datetime.now().year
    url_history = f"https://www.cftc.gov/files/dea/history/fut_disagg_txt_{year}.zip"
    url_latest = "https://www.cftc.gov/dea/newcot/f_disagg.txt"

    headers = {"User-Agent": "Mozilla/5.0"}

    df_hist = pd.DataFrame()
    df_live = pd.DataFrame()

    try:
        r = requests.get(url_history, headers=headers, verify=False, timeout=10)
        if r.status_code == 200:
            df_hist = pd.read_csv(io.BytesIO(r.content), compression="zip", low_memory=False)
    except:
        pass

    try:
        r2 = requests.get(url_latest, headers=headers, verify=False, timeout=5)
        if r2.status_code == 200 and not df_hist.empty:
            df_live = pd.read_csv(io.BytesIO(r2.content), header=None, low_memory=False)
            df_live.columns = df_hist.columns
    except:
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
    if df.empty:
        return pd.DataFrame()

    name_col = find_column(df.columns, ["market"]) or find_column(df.columns, ["contract"])
    if not name_col:
        return pd.DataFrame()

    mask = df[name_col].apply(lambda x: any(k in str(x).upper() for k in name_keywords))
    data = df[mask].copy()

    if data.empty:
        return pd.DataFrame()

    date_col = find_column(df.columns, ["date"])
    data[date_col] = pd.to_datetime(data[date_col])

    long_col = find_column(df.columns, ["money", "long"])
    short_col = find_column(df.columns, ["money", "short"])
    if not long_col or not short_col:
        return pd.DataFrame()

    data["Net"] = data[long_col] - data[short_col]
    data["Date_Display"] = data[date_col]
    data = data.sort_values("Date_Display").drop_duplicates("Date_Display", keep="last")

    return data.tail(52)


# ======================================================================
# TradingEconomics / MacroMicro / FRED
# ======================================================================

def _fetch_tradingeconomics(country, indicator):
    url = f"https://api.tradingeconomics.com/historical/country/{country}/indicator/{indicator}"
    params = {"c": TE_API_KEY, "format": "json"}

    try:
        r = requests.get(url, params=params, timeout=8)
        r.raise_for_status()
        js = r.json()
        if not js:
            return None

        df = pd.DataFrame(js)
        date_col = "Date" if "Date" in df else "date"
        value_col = "Value" if "Value" in df else "value"

        df[date_col] = pd.to_datetime(df[date_col])
        df = df[[date_col, value_col]].rename(columns={date_col: "DATE", value_col: "VALUE"})
        df.set_index("DATE", inplace=True)
        df.sort_index(inplace=True)
        return df
    except:
        return None


def _fetch_mm_local(filename):
    path = os.path.join(DATA_DIR, filename)
    if not os.path.exists(path):
        return None
    try:
        df = pd.read_csv(path)
        df["DATE"] = pd.to_datetime(df["DATE"])
        df.set_index("DATE", inplace=True)
        df.sort_index(inplace=True)
        return df
    except:
        return None


def _fetch_fred_with_backup(series, backup):
    base = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series}"
    try:
        r = requests.get(base, timeout=6)
        r.raise_for_status()
        df = pd.read_csv(io.BytesIO(r.content))
        df["DATE"] = pd.to_datetime(df["DATE"])
        df = df[["DATE", series]].rename(columns={series: "VALUE"})
        df.set_index("DATE", inplace=True)
        df.sort_index(inplace=True)
        df.to_csv(os.path.join(DATA_DIR, backup))
        return df, "FRED 在线"
    except:
        try:
            df = pd.read_csv(os.path.join(DATA_DIR, backup))
            df["DATE"] = pd.to_datetime(df["DATE"])
            df.set_index("DATE", inplace=True)
            df.sort_index(inplace=True)
            return df, "FRED 本地备份"
        except:
            return None, "无数据"


def _prioritize(*sources):
    final = None
    for s in sources:
        if s is None:
            continue
        if isinstance(s, pd.DataFrame):
            s = s["VALUE"]
        if final is None:
            final = s.copy()
        else:
            final = final.combine_first(s)
    return final


@st.cache_data(ttl=3600*6)
def get_macro_multi():
    sources = {}

    # ==== Fed Funds ====
    te_rate = _fetch_tradingeconomics("united states", "interest rate")
    fred_rate, fred_rate_src = _fetch_fred_with_backup("FEDFUNDS", "fedfunds.csv")
    fed = _prioritize(te_rate, fred_rate)
    sources["fed_funds"] = "TE" if te_rate is not None else fred_rate_src

    # ==== CPI YoY ====
    te_cpi = _fetch_tradingeconomics("united states", "inflation rate")
    mm_cpi = _fetch_mm_local("mm_us_cpi_yoy.csv")
    fred_cpi, fred_cpi_src = _fetch_fred_with_backup("CPIAUCSL", "cpi.csv")

    if fred_cpi is not None:
        fred_cpi_yoy = fred_cpi["VALUE"].pct_change(12) * 100
    else:
        fred_cpi_yoy = None

    cpi = _prioritize(te_cpi, mm_cpi, fred_cpi_yoy)
    sources["cpi_yoy"] = "TE" if te_cpi is not None else ("MM CSV" if mm_cpi is not None else fred_cpi_src)

    # ==== NFP ====
    te_nfp = _fetch_tradingeconomics("united states", "non farm payrolls")
    mm_nfp = _fetch_mm_local("mm_us_nfp_change.csv")
    fred_nfp, fred_nfp_src = _fetch_fred_with_backup("PAYEMS", "nfp.csv")
    fred_nfp_change = fred_nfp["VALUE"].diff() if fred_nfp is not None else None

    nfp = _prioritize(te_nfp, mm_nfp, fred_nfp_change)
    sources["nfp_change"] = "TE" if te_nfp is not None else ("MM CSV" if mm_nfp is not None else fred_nfp_src)

    # ==== Jobless Claims ====
    te_claim = _fetch_tradingeconomics("united states", "jobless claims")
    mm_claim = _fetch_mm_local("mm_us_jobless_claims.csv")
    fred_claim, fred_claim_src = _fetch_fred_with_backup("ICSA", "claims.csv")

    jobless = _prioritize(te_claim, mm_claim, fred_claim)
    sources["jobless_claims"] = "TE" if te_claim is not None else ("MM CSV" if mm_claim is not None else fred_claim_src)

    # ==== Build DataFrame ====
    data = {
        "fed_funds": fed,
        "cpi_yoy": cpi,
        "nfp_change": nfp,
        "jobless_claims": jobless,
    }

    # 过滤掉 None
    data = {k: v for k, v in data.items() if v is not None}

    if not data:
        return pd.DataFrame(), sources

    df = pd.concat(data.values(), axis=1)
    df.columns = data.keys()
    df.sort_index(inplace=True)
    return df, sources


# ======================================================================
# UI 组件
# ======================================================================
def render_news_alert(last_date):
    if pd.isnull(last_date):
        return
    diff = (datetime.datetime.now() - last_date).days
    if diff > 14:
        st.error(f"⚠️ CFTC 数据已滞后 {diff} 天")


def render_fomc_card():
    next_meet = datetime.date(2025, 12, 10)
    days = (next_meet - datetime.date.today()).days
    st.info(f"📅 下次 FOMC：{next_meet}（剩 {days} 天）")


# ======================================================================
# 主程序
# ======================================================================
with st.spinner("同步数据中…"):
    cftc_df = get_cftc_data()
    gold = process_cftc(cftc_df, ["GOLD"])
    euro = process_cftc(cftc_df, ["EURO"])
    macro_df, macro_src = get_macro_multi()

st.title("Smart Money & Macro Dashboard")

# CFTC 警告
if not gold.empty:
    render_news_alert(gold.iloc[-1]["Date_Display"])

tab1, tab2 = st.tabs(["📊 COT 持仓", "🌍 宏观经济"])

with tab1:
    st.subheader("Gold")
    if not gold.empty:
        st.line_chart(gold.set_index("Date_Display")["Net"])

    st.subheader("EUR")
    if not euro.empty:
        st.line_chart(euro.set_index("Date_Display")["Net"])


with tab2:
    st.subheader("📌 数据来源")
    st.json(macro_src)

    if macro_df.empty:
        st.warning("没有任何宏观数据可用，请检查 API Key 或网络")
    else:
        st.line_chart(macro_df)
