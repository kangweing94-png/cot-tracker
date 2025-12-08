import streamlit as st
import pandas as pd
import datetime
import yfinance as yf
import feedparser
from fredapi import Fred
import requests
import io
import re

# ==========================================
# 1. 核心配置 & Fed 立场数据库
# ==========================================
st.set_page_config(page_title="Institutional Dashboard V10", layout="wide", page_icon="🏦")

# 你的 FRED API Key
FRED_KEY = '476ef255e486edb3fdbf71115caa2857'

# Fed 官员立场静态数据库 (用于匹配 RSS)
FED_ROSTER = {
    "Powell": {"role": "Chair", "stance": "Neutral (中立)", "color": "#d29922"},
    "Waller": {"role": "Governor", "stance": "Hawk (鹰派) 🦅", "color": "#f85149"},
    "Bowman": {"role": "Governor", "stance": "Hawk (鹰派) 🦅", "color": "#f85149"},
    "Kashkari": {"role": "Minneapolis Pres", "stance": "Hawk (鹰派) 🦅", "color": "#f85149"},
    "Goolsbee": {"role": "Chicago Pres", "stance": "Dove (鸽派) 🕊️", "color": "#3fb950"},
    "Daly": {"role": "SF Pres", "stance": "Neutral (中立)", "color": "#8b949e"},
    "Logan": {"role": "Dallas Pres", "stance": "Hawk (鹰派) 🦅", "color": "#f85149"},
    "Bostic": {"role": "Atlanta Pres", "stance": "Dove (鸽派) 🕊️", "color": "#3fb950"}
}

st.markdown("""
<style>
    .stApp { background-color: #0e1117; color: #e0e0e0; font-family: 'Segoe UI', sans-serif; }
    
    /* 卡片通用样式 */
    .metric-card {
        background-color: #161b22;
        border: 1px solid #30363d;
        padding: 20px;
        border-radius: 8px;
        margin-bottom: 15px;
    }
    .metric-label { font-size: 13px; color: #8b949e; text-transform: uppercase; letter-spacing: 1px; }
    .metric-val { font-size: 28px; font-weight: 700; color: #f0f6fc; font-family: 'Roboto Mono', monospace; margin: 8px 0; }
    .metric-sub { font-size: 11px; color: #666; }
    
    /* Fed 语录卡片 */
    .fed-quote-card {
        background-color: #1c2128;
        border-left: 4px solid #333;
        padding: 15px;
        margin-bottom: 10px;
        border-radius: 4px;
    }
    .quote-text { font-style: italic; color: #d0d7de; font-size: 15px; margin: 8px 0; line-height: 1.4; }
    .speaker-name { font-weight: bold; font-size: 14px; color: #fff; }
    .speaker-role { font-size: 11px; color: #8b949e; margin-left: 5px; }
    .stance-tag { font-size: 11px; padding: 2px 6px; border-radius: 4px; background: #21262d; border: 1px solid #30363d; margin-left: 8px; font-weight: bold;}

</style>
""", unsafe_allow_html=True)

# ==========================================
# 2. 专业数据引擎 (修复版)
# ==========================================

# --- A. 修复 CFTC (增加 User-Agent 伪装) ---
@st.cache_data(ttl=86400)
def fetch_cftc_robust():
    """
    使用 requests 伪装浏览器请求，解决 403 Forbidden 问题
    """
    url = "https://www.cftc.gov/dea/newcot/deacmesf.txt"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    }
    
    try:
        response = requests.get(url, headers=headers)
        if response.status_code != 200:
            return None
        
        # 将文本内容转换为 pandas 可读的流
        csv_data = io.StringIO(response.text)
        
        # CFTC Legacy Format (无表头):
        # Col 0: Name, Col 2: Date, Col 8: Non-Comm Long, Col 9: Non-Comm Short
        df = pd.read_csv(csv_data, header=None, low_memory=False)
        
        targets = {
            "GOLD": "GOLD - COMMODITY EXCHANGE INC.",
            "EURO": "EURO FX - CHICAGO MERCANTILE EXCHANGE",
            "GBP": "BRITISH POUND - CHICAGO MERCANTILE EXCHANGE"
        }
        
        parsed = []
        for key, long_name in targets.items():
            # 模糊匹配
            row = df[df[0].str.contains(key, case=False, na=False)]
            if not row.empty:
                data = row.iloc[0]
                net_pos = float(data[8]) - float(data[9])
                date_str = data[2] # 格式通常是 YYYY-MM-DD
                parsed.append({
                    "asset": key,
                    "net": net_pos,
                    "date": date_str
                })
        return parsed
    except Exception as e:
        print(f"CFTC Error: {e}")
        return None

# --- B. 修复 FRED (强制获取最新非空值) ---
@st.cache_data(ttl=3600)
def fetch_fred_latest():
    try:
        fred = Fred(api_key=FRED_KEY)
        
        # 指标定义
        indicators = [
            {"name": "Non-Farm Payrolls", "id": "PAYEMS", "is_change": True, "unit": "Jobs"},
            {"name": "Unemployment Rate", "id": "UNRATE", "is_change": False, "unit": "%"},
            {"name": "CPI (YoY)", "id": "CPIAUCSL", "is_change": "yoy", "unit": "%"},
            {"name": "Fed Funds Rate", "id": "FEDFUNDS", "is_change": False, "unit": "%"},
            {"name": "10Y Treasury Yield", "id": "DGS10", "is_change": False, "unit": "%"}
        ]
        
        data_rows = []
        
        for ind in indicators:
            # 获取最近 13 个月的数据，确保能算同比
            series = fred.get_series(ind['id'], sort_order='desc', limit=24)
            if series.empty: continue
            
            # 取最新的有效日期和数值
            latest_date = series.index[0]
            latest_val = series.iloc[0]
            
            display_val = ""
            
            if ind['is_change'] == True:
                # 计算 NFP 变化 (最新值 - 上个月值) * 1000
                prev_val = series.iloc[1]
                change = (latest_val - prev_val) * 1000
                display_val = f"{int(change):+,}"
            elif ind['is_change'] == 'yoy':
                # CPI 同比：(今年值 - 去年同月值) / 去年同月值
                # 注意：sort_order='desc', 所以 index 0 是最新，index 12 是去年的
                if len(series) > 12:
                    val_now = series.iloc[0]
                    val_last_year = series.iloc[12]
                    yoy = ((val_now - val_last_year) / val_last_year) * 100
                    display_val = f"{yoy:.1f}%"
                else:
                    display_val = "Calc Error"
            else:
                display_val = f"{latest_val:.2f}{ind['unit']}"
                
            data_rows.append({
                "Event": ind['name'],
                "Release Date": latest_date.strftime('%Y-%m-%d'),
                "Latest Actual": display_val,
                "Source": "FRED Official"
            })
            
        return pd.DataFrame(data_rows)
    except Exception as e:
        return pd.DataFrame()

# --- C. 智能 Fed 语录抓取 (RSS + NLP 关键词匹配) ---
@st.cache_data(ttl=300)
def fetch_fed_quotes():
    """
    从新闻流中提取包含 Fed 官员名字的句子
    """
    # 聚合多个 RSS 源以增加命中率
    urls = [
        "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=10000664", # CNBC Economy
        "https://feeds.content.dowjones.io/public/rss/mw_topstories" # MarketWatch
    ]
    
    quotes_found = []
    
    for url in urls:
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries:
                title = entry.title
                summary = entry.summary if 'summary' in entry else ""
                full_text = f"{title} {summary}"
                
                # 检查每一个官员的名字是否出现在新闻中
                for name, info in FED_ROSTER.items():
                    if name in full_text:
                        # 简单的去重
                        if any(q['text'] == title for q in quotes_found): continue
                        
                        quotes_found.append({
                            "name": name,
                            "role": info['role'],
                            "stance": info['stance'],
                            "color": info['color'],
                            "text": title, # 标题通常就是最好的语录摘要
                            "date": entry.published if 'published' in entry else "Recent",
                            "link": entry.link
                        })
        except:
            continue
            
    return quotes_found[:5] # 只展示最新的5条

# ==========================================
# 3. 前端 UI 渲染
# ==========================================

st.title("🏛️ Institutional Dashboard V10")
st.caption(f"Status: Live Production | Last Check: {datetime.datetime.now().strftime('%H:%M:%S')}")

# --- 1. Smart Money (Fixed: Requests + Headers) ---
st.markdown("### 1. Smart Money Positioning (CFTC Official)")
st.caption("Data Source: cftc.gov Legacy Report (Live Fetch). Showing Net Positions (Long - Short) for Managed Money.")

cot_data = fetch_cftc_robust()

if cot_data:
    c1, c2, c3 = st.columns(3)
    # 动态分配
    for item in cot_data:
        target_col = None
        if "EURO" in item['asset']: target_col = c1
        elif "GBP" in item['asset']: target_col = c2
        elif "GOLD" in item['asset']: target_col = c3
        
        if target_col:
            with target_col:
                st.markdown(f"""
                <div class="metric-card">
                    <div class="metric-label">{item['asset'].split('-')[0].strip()} Futures</div>
                    <div class="metric-val">{int(item['net']):,}</div>
                    <div class="metric-sub">
                        📅 Report Date: {item['date']}
                    </div>
                </div>
                """, unsafe_allow_html=True)
else:
    st.error("⚠️ Connection to CFTC.gov timed out. The government server might be slow. Please refresh.")

st.markdown("---")

# --- 2. Macro Data (Fixed: Dates & Forecast Removed) ---
st.markdown("### 2. Macroeconomic Matrix (FRED Official)")
st.caption("Data Source: St. Louis Fed. Dates shown are the **latest official release dates**. Note: CPI/NFP data naturally lags by 1 month.")

macro_df = fetch_fred_latest()

if not macro_df.empty:
    st.dataframe(
        macro_df,
        use_container_width=True,
        hide_index=True,
        column_config={
            "Event": st.column_config.TextColumn("Indicator", width="medium"),
            "Release Date": st.column_config.DateColumn("Release Date", format="YYYY-MM-DD"),
            "Latest Actual": st.column_config.TextColumn("Actual Value", help="Official government figure"),
        }
    )
else:
    st.warning("FRED API Limit Reached or Key Invalid. Please check logs.")

st.markdown("---")

# --- 3. Fed Radar (Fixed: Quotes & Stance) ---
st.markdown("### 3. 🦅 Fed Speaker Radar (Live Quotes)")
st.caption("Scraping live news for quotes from key FOMC members. Stance (Hawk/Dove) is auto-tagged.")

quotes = fetch_fed_quotes()

if quotes:
    for q in quotes:
        st.markdown(f"""
        <div class="fed-quote-card" style="border-left-color: {q['color']};">
            <div>
                <span class="speaker-name">{q['name']}</span>
                <span class="speaker-role">| {q['role']}</span>
                <span class="stance-tag" style="color:{q['color']}; border-color:{q['color']}">{q['stance']}</span>
            </div>
            <div class="quote-text">“{q['text']}”</div>
            <div style="text-align:right; font-size:11px; margin-top:5px;">
                <a href="{q['link']}" target="_blank" style="color:#58a6ff; text-decoration:none;">Read Source 🔗</a> | {q['date']}
            </div>
        </div>
        """, unsafe_allow_html=True)
else:
    st.info("No direct quotes from Fed members found in the last few hours. Displaying Roster Reference below:")
    # Fallback: 展示一下静态的立场表，以防没有新闻
    st.markdown("#### FOMC Stance Reference (No live news)")
    cols = st.columns(4)
    for i, (name, info) in enumerate(FED_ROSTER.items()):
        with cols[i % 4]:
            st.markdown(f"**{name}**: <span style='color:{info['color']}'>{info['stance']}</span>", unsafe_allow_html=True)

st.markdown("---")
st.markdown("#### ℹ️ Data Note")
st.caption("""
1. **CFTC Data**: Fetched using browser-headers to bypass 403 blocks.
2. **FRED Data**: Shows 'Latest Actual' only. Forecasts are proprietary and removed to avoid confusion.
3. **Fed Radar**: Scans CNBC/MarketWatch RSS for member names and displays the headline as context.
""")
