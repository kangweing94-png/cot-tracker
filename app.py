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

# 👉 TradingEconomics API key（自己去官网注册一个，然后填在这里）
TE_API_KEY = "a7d624f316a049e:nmasw3jt5rkbeoi"  # 建议改成用 st.secrets 管理


# ========= 侧边栏 =========
with st.sidebar:
    st.header("⚡ 控制台")
    if st.button("🔄 刷新全站数据"):
        st.cache_data.clear()
        st.rerun()

    st.divider()
    st.caption("数据源:\n- CFTC\n- TradingEconomics\n- MacroMicro 本地 CSV\n- FRED + 本地备份")


# ==============================================================================
# 模块 1: CFTC 核心逻辑（和你之前的一样）
# ==============================================================================
@st.cache_data(ttl=3600 * 3)
def get_cftc_data():
    year = datetime.datetime.now().year
    url_history = f"https://www.cftc.gov/files/dea/history/fut_disagg_txt_{year}.zip"
    url_latest = "https://www.cftc.gov/dea/newcot/f_disagg.txt"

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0 Safari/537.36"
    }

    df_hist = pd.DataFrame()
    df_live = pd.DataFrame()

    # 历史
    try:
        r = requests.get(url_history, headers=headers, verify=False, timeout=10)
        if r.status_code == 200:
            df_hist = pd.read_csv(io.BytesIO(r.content), compression="zip", low_memory=False)
    except Exception:
        pass

    # 本周
    try:
        r2 = requests.get(
            f"{url_latest}?t={int(time.time())}",
            headers=headers,
            verify=False,
            timeout=5,
        )
        if r2.status_code == 200 and not df_hist.empty:
            df_live = pd.read_csv(io.BytesIO(r2.content), header=None, low_memory=False)
            df_live.columns = df_hist.columns
    except Exception:
        pass

    if df_hist.empty and df_live.empty:
        return pd.DataFrame()
    return pd.concat([df_hist, df_live], ignore_index=True)


def find_column(columns, keywords):
    for col in columns:
        col_lower = str(col).lower()
        if all(k in col_lower for k in keywords):
            return col
    return None


def process_cftc(df, name_keywords):
    if df.empty:
        return pd.DataFrame()

    name_col = find_column(df.columns, ["market", "exchange"]) or find_column(
        df.columns, ["contract", "name"]
    )
    if not name_col:
        return pd.DataFrame()

    mask = df[name_col].apply(lambda x: any(k in str(x).upper() for k in name_keywords))
    data = df[mask].copy()
    if data.empty:
        return pd.DataFrame()

    date_col = find_column(df.columns, ["report", "date"]) or find_column(
        df.columns, ["as", "of", "date"]
    )
    data[date_col] = pd.to_datetime(data[date_col])

    long_col = find_column(df.columns, ["money", "long"])
    short_col = find_column(df.columns, ["money", "short"])
    if not long_col or not short_col:
        return pd.DataFrame()

    data["Net"] = data[long_col] - data[short_col]
    data["Date_Display"] = data[date_col]

    data = data.sort_values("Date_Display")
    data = data.drop_duplicates(subset=["Date_Display"], keep="last")
    return data.tail(52)


# ==============================================================================
# 模块 2: 多数据源宏观引擎
# TradingEconomics + MacroMicro (CSV) + FRED(带本地备份)
# ==============================================================================

def _fetch_tradingeconomics(country: str, indicator: str):
    """TradingEconomics: 按国家 + 指标 获取历史数据"""
    if not TE_API_KEY or TE_API_KEY == "your_tradingeconomics_key_here":
        return None

    url = f"https://api.tradingeconomics.com/historical/country/{country}/indicator/{indicator}"
    params = {"c": TE_API_KEY, "format": "json"}
    try:
        r = requests.get(url, params=params, timeout=8)
        r.raise_for_status()
        js = r.json()
        if not js:
            return None
        df = pd.DataFrame(js)
        # 常见字段: 'Date', 'Value'
        date_col = "Date" if "Date" in df.columns else "date"
        val_col = "Value" if "Value" in df.columns else "value"
        df[date_col] = pd.to_datetime(df[date_col])
        df = df[[date_col, val_col]].rename(columns={date_col: "DATE", val_col: "VALUE"})
        df.set_index("DATE", inplace=True)
        df.sort_index(inplace=True)
        return df
    except Exception:
        return None


def _fetch_macromicro_local(filename: str):
    """MacroMicro 或你自己整理的 CSV，本地文件，字段: DATE, VALUE"""
    path = os.path.join(DATA_DIR, filename)
    if not os.path.exists(path):
        return None
    try:
        df = pd.read_csv(path)
        if "DATE" not in df.columns or "VALUE" not in df.columns:
            return None
        df["DATE"] = pd.to_datetime(df["DATE"])
        df.set_index("DATE", inplace=True)
        df.sort_index(inplace=True)
        return df
    except Exception:
        return None


def _fetch_fred_with_backup(series_id: str, backup_name: str):
    """FRED CSV + 本地备份，返回 df(index=DATE, VALUE)"""
    base_url = "https://fred.stlouisfed.org/graph/fredgraph.csv?id="
    url = base_url + series_id
    headers = {"User-Agent": "Mozilla/5.0"}

    # 在线
    try:
        r = requests.get(url, headers=headers, timeout=6)
        r.raise_for_status()
        df = pd.read_csv(io.BytesIO(r.content))
        df["DATE"] = pd.to_datetime(df["DATE"])
        val_col = series_id
        df = df[["DATE", val_col]].rename(columns={val_col: "VALUE"})
        df.set_index("DATE", inplace=True)
        df.sort_index(inplace=True)
        # 备份
        df.to_csv(os.path.join(DATA_DIR, backup_name))
        return df, "FRED 在线"
    except Exception:
        # 本地备份
        try:
            path = os.path.join(DATA_DIR, backup_name)
            df = pd.read_csv(path)
            df["DATE"] = pd.to_datetime(df["DATE"])
            df.set_index("DATE", inplace=True)
            df.sort_index(inplace=True)
            return df, "FRED 本地备份"
        except Exception:
            return None, "无数据"


def _prioritize_series(*series_list):
    """按顺序合并多个 series / df，优先前面的非空值"""
    final = None
    for s in series_list:
        if s is None:
            continue
        if isinstance(s, pd.DataFrame):
            s = s["VALUE"]
        if final is None:
            final = s.copy()
        else:
            final = final.combine_first(s)
    return final


@st.cache_data(ttl=3600 * 6)
def get_macro_multi():
    """
    返回:
        macro_df: index=DATE, columns=[fed_funds, cpi_yoy, nfp_change, jobless_claims]
        sources: dict，记录每个指标最终主要来源
    """

    sources = {}

    # ===== Fed Funds 利率 =====
    # 优先 TradingEconomics (美国 Interest Rate)，再 FRED(FEDFUNDS)
    te_rate = _fetch_tradingeconomics("united states", "interest rate")
    fred_rate_df, fred_rate_src = _fetch_fred_with_backup("FEDFUNDS", "fedfunds.csv")

    fed_funds_series = _prioritize_series(te_rate, fred_rate_df)
    if fed_funds_series is not None:
        if te_rate is not None:
            sources["fed_funds"] = "TradingEconomics 优先 (FRED 兜底)"
        else:
            sources["fed_funds"] = fred_rate_src
    else:
        sources["fed_funds"] = "无数据"

    # ===== CPI YoY =====
    # 1) TradingEconomics: Inflation Rate (就是 YoY)
    # 2) MacroMicro 本地 CSV: mm_us_cpi_yoy.csv
    # 3) FRED: CPIAUCSL 自己算 YoY
    te_cpi = _fetch_tradingeconomics("united states", "inflation rate")
    mm_cpi = _fetch_macromicro_local("mm_us_cpi_yoy.csv")

    fred_cpi_df, fred_cpi_src = _fetch_fred_with_backup("CPIAUCSL", "cpi.csv")
    if fred_cpi_df is not None:
        fred_cpi_yoy = fred_cpi_df["VALUE"].pct_change(12) * 100
        fred_cpi_yoy = fred_cpi_yoy.to_frame("VALUE")
    else:
        fred_cpi_yoy = None

    cpi_series = _prioritize_series(te_cpi, mm_cpi, fred_cpi_yoy)
    if cpi_series is not None:
        if te_cpi is not None:
            sources["cpi_yoy"] = "TradingEconomics (Inflation Rate)"
        elif mm_cpi is not None:
            sources["cpi_yoy"] = "MacroMicro 本地 CSV"
        else:
            sources["cpi_yoy"] = f"{fred_cpi_src} (CPIAUCSL 计算 YoY)"
    else:
        sources["cpi_yoy"] = "无数据"

    # ===== NFP Change =====
    # 1) TradingEconomics: Non Farm Payrolls
    # 2) MacroMicro: mm_us_nfp_change.csv
    # 3) FRED: PAYEMS.diff()
    te_nfp = _fetch_tradingeconomics("united states", "non farm payrolls")
    mm_nfp = _fetch_macromicro_local("mm_us_nfp_change.csv")

    fred_nfp_df, fred_nfp_src = _fetch_fred_with_backup("PAYEMS", "nfp.csv")
    if fred_nfp_df is not None:
        fred_nfp_change = fred_nfp_df["VALUE"].diff()
        fred_nfp_change = fred_nfp_change.to_frame("VALUE")
    else:
        fred_nfp_change = None

    nfp_series = _prioritize_series(te_nfp, mm_nfp, fred_nfp_change)
    if nfp_series is not None:
        if te_nfp is not None:
            sources["nfp_change"] = "TradingEconomics (Non Farm Payrolls)"
        elif mm_nfp is not None:
            sources["nfp_change"] = "MacroMicro 本地 CSV"
        else:
            sources["nfp_change"] = f"{fred_nfp_src} (PAYEMS 差分)"
    else:
        sources["nfp_change"] = "无数据"

    # ===== Jobless Claims =====
    # 1) TradingEconomics: Jobless Claims
    # 2) MacroMicro CSV
    # 3) FRED: ICSA
    te_claims = _fetch_tradingeconomics("united states", "jobless claims")
    mm_claims = _fetch_macromicro_local("mm_us_jobless_claims.csv")
    fred_claims_df, fred_claims_src = _fetch_fred_with_backup("ICSA", "claims.csv")

    claims_series = _prioritize_series(te_claims, mm_claims, fred_claims_df)
    if claims_series is not None:
        if te_claims is not None:
            sources["jobless_claims"] = "TradingEconomics (Jobless Claims)"
        elif mm_claims is not None:
            sources["jobless_claims"] = "MacroMicro 本地 CSV"
        else:
            sources["jobless_claims"] = fred_claims_src
    else:
        sources["jobless_claims"] = "无数据"

    # 组装统一 DataFrame
    macro_df = pd.DataFrame(
        {
            "fed_funds": fed_funds_series,
            "cpi_yoy": cpi_series,
            "nfp_change": nfp_series,
            "jobless_claims": claims_series,
        }
    )

    macro_df.sort_index(inplace=True)

    return macro_df, sources


# ==============================================================================
# UI 组件
# ==============================================================================
def render_news_alert(last_date_obj):
    if pd.isnull(last_date_obj):
        return
    days_diff = (datetime.datetime.now() - last_date_obj).days
    if days_diff > 14:
        st.error(f"🚨 MARKET ALERT: 数据严重滞后 ({days_diff}天)")
        with st.expander("📰 News Headline: 为什么数据停更了？（点击展开）", expanded=True):
            st.markdown(
                f"""
#### 🏛️ 美国政府停摆导致 CFTC 报告积压
**事件影响**: 由于美国政府在 2025年10月 期间发生停摆 (Government Shutdown)，CFTC 暂停了所有数据处理。

**当前状态**: 正在按顺序补发历史报告，预计 2026年1月 恢复正常。

*此数据最后更新于: {last_date_obj.strftime('%Y-%m-%d')}*
"""
            )


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
            st.info(f"📅 下次利率决议: **{next_meet}** (还剩 {days} 天)")
        else:
            st.info("📅 下次会议: 待定")
    with c2:
        st.link_button(
            "📊 查看最新点阵图",
            "https://www.federalreserve.gov/monetarypolicy/fomcprojtabl20250917.htm",
        )


# ==============================================================================
# 主程序
# ==============================================================================
with st.spinner("正在同步华尔街数据..."):
    cftc_df = get_cftc_data()
    gold_data = process_cftc(cftc_df, ["GOLD", "COMMODITY"])
    euro_data = process_cftc(cftc_df, ["EURO FX", "CHICAGO"])

    macro_df, macro_sources = get_macro_multi()

st.title("Smart Money & Macro Dashboard")

# 顶部 CFTC 数据警报
if not gold_data.empty:
    last_val = gold_data.iloc[-1]
    render_news_alert(last_val["Date_Display"])

tab1, tab2 = st.tabs(["📊 COT 机构持仓", "🌍 宏观经济 (Multi-Source)"])

# ---------- Tab1: COT ----------
with tab1:

    def simple_chart(data, name, color):
        if data.empty:
            st.warning(f"{name}: 暂无数据")
            return
        last_date = data["Date_Display"].iloc[-1].strftime("%Y-%m-%d")
        net_pos = int(data["Net"].iloc[-1])
        st.metric(f"{name} Managed Money", f"{net_pos:,}", f"Report: {last_date}")

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
        fig.update_layout(height=350, margin=dict(t=10, b=0, l=0, r=0))
        st.plotly_chart(fig, use_container_width=True)

    c1, c2 = st.columns(2)
    with c1:
        simple_chart(gold_data, "Gold (XAU)", "#FFD700")
    with c2:
        simple_chart(euro_data, "Euro (EUR)", "#00d2ff")

# ---------- Tab2: 宏观 ----------
with tab2:
    render_fomc_card()
    st.divider()

    if not macro_df.empty:
        latest = macro_df.dropna().iloc[-1]

        m1, m2, m3, m4 = st.columns(4)

        # Fed Rate
        if pd.notna(latest.get("fed_funds", None)):
            m1.metric(
                "🇺🇸 Fed Funds Rate",
                f"{latest['fed_funds']:.2f}%",
                help=macro_sources.get("fed_funds", ""),
            )
        else:
            m1.write("Fed Funds: 无数据")

        # CPI YoY
        if pd.notna(latest.get("cpi_yoy", None)):
            m2.metric(
                "🔥 CPI (YoY)",
                f"{latest['cpi_yoy']:.1f}%",
                help=macro_sources.get("cpi_yoy", ""),
            )
        else:
            m2.write("CPI YoY: 无数据")

        # NFP Change
        if pd.notna(latest.get("nfp_change", None)):
            m3.metric(
                "👷 NFP Change",
                f"{int(latest['nfp_change']):,}",
                help=macro_sources.get("nfp_change", ""),
            )
        else:
            m3.write("NFP Change: 无数据")

        # Jobless Claims
        if pd.notna(latest.get("jobless_claims", None)):
            m4.metric(
                "🤕 Jobless Claims",
                f"{int(latest['jobless_claims']):,}",
                help=macro_sources.get("jobless_claims", ""),
            )
        else:
            m4.write("Jobless Claims: 无数据")

        st.caption(
            "数据优先级：TradingEconomics → MacroMicro 本地 CSV → FRED + 本地备份。鼠标移到指标卡上的 ⓘ 可查看具体来源。"
        )

        st.divider()

        c1, c2 = st.columns(2)
        with c1:
            st.subheader("通胀趋势 (CPI YoY)")
            if macro_df["cpi_yoy"].notna().sum() > 0:
                st.line_chart(macro_df["cpi_yoy"].tail(36))
            else:
                st.info("暂无 CPI YoY 数据")

        with c2:
            st.subheader("就业市场 (NFP Change)")
            if macro_df["nfp_change"].notna().sum() > 0:
                st.bar_chart(macro_df["nfp_change"].tail(36))
            else:
                st.info("暂无 NFP Change 数据")

        st.subheader("初请失业金 (Jobless Claims)")
        if macro_df["jobless_claims"].notna().sum() > 0:
            st.line_chart(macro_df["jobless_claims"].tail(36))
        else:
            st.info("暂无 Jobless Claims 数据")
    else:
        st.warning("宏观数据全部来源都不可用，请检查网络或 API 设置。")
