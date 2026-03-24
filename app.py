import os
from dotenv import load_dotenv
import streamlit as st
from datetime import datetime

load_dotenv(override=True)

st.set_page_config(
    page_title="Trading Intelligence Platform",
    layout="wide",
    initial_sidebar_state="expanded",
    page_icon="📈",
)

# ── CSS ─────────────────────────────────────────────────────────
st.markdown("""
<style>
[data-testid="metric-container"] { background:#1e1e2e; border-radius:8px; padding:12px; }
.stExpander { border:1px solid #333 !important; border-radius:8px !important; }
</style>
""", unsafe_allow_html=True)

# ── Header ───────────────────────────────────────────────────────
st.title("📈 AI Trading Intelligence Platform")
st.markdown("*Multi-Agent Council · Technical + Momentum + News + Risk*")

api_ok = bool(os.getenv("OPENROUTER_API_KEY"))
st.caption("🔑 API: " + ("✅ Connected" if api_ok else "⚠️ Offline Mode"))
st.divider()

# ── Sidebar ──────────────────────────────────────────────────────
from stocks import UNIVERSE, CATEGORIES, ticker_label

with st.sidebar:
    st.header("⚙️ Settings")

    # Asset picker
    st.subheader("🎯 Asset Selection")
    cat_filter = st.selectbox("Filter by Category", ["All"] + CATEGORIES)

    filtered = {
        k: v for k, v in UNIVERSE.items()
        if cat_filter == "All" or v[1] == cat_filter
    }
    ticker_options = list(filtered.keys())
    ticker_labels  = [ticker_label(t) for t in ticker_options]

    selected_label = st.selectbox("Select Asset", ticker_labels)
    ticker = ticker_options[ticker_labels.index(selected_label)]
    asset_name, asset_cat = UNIVERSE[ticker]

    st.info(f"**{asset_name}** | {asset_cat}")

    # Multi-asset scan
    st.divider()
    st.subheader("🔍 Quick Multi-Scan")
    scan_enabled = st.checkbox("Enable Multi-Asset Scan")
    if scan_enabled:
        scan_tickers = st.multiselect(
            "Assets to scan",
            options=ticker_options,
            default=ticker_options[:4],
            format_func=lambda t: f"{t} – {UNIVERSE[t][0]}",
        )

    # Timeframe
    st.divider()
    st.subheader("📊 Timeframe")
    timeframe = st.selectbox(
        "Historical Period",
        ["1 Hour", "4 Hours", "1 Day", "3 Days", "1 Week", "1 Month"],
        index=2,
    )
    interval = st.selectbox("Data Interval", ["1m", "5m", "15m", "1h", "1d"], index=1)

    # Risk
    st.divider()
    st.subheader("💰 Risk Management")
    capital = st.number_input("Capital ($)", min_value=10.0, value=10_000.0, step=1_000.0)
    risk_percent = st.slider("Risk Per Trade (%)", 0.5, 10.0, 1.0, 0.25)
    st.info(f"💡 Max risk/trade: **${capital * risk_percent / 100:,.2f}**")

    # Charts
    st.divider()
    st.subheader("📈 Live Chart")
    chart_src = st.radio("Provider", ["TradingView", "Binance", "Yahoo"])
    if chart_src == "TradingView":
        sym = ticker.replace("-USD", "USD").replace("-", "")
        chart_url = f"https://www.tradingview.com/chart/?symbol={sym}"
    elif chart_src == "Binance":
        sym = ticker.replace("-USD", "USDT").replace("-", "")
        chart_url = f"https://www.binance.com/en/trade/{sym}"
    else:
        chart_url = f"https://finance.yahoo.com/quote/{ticker}"
    st.link_button(f"📊 Open {chart_src}", chart_url, use_container_width=True)

# ── Live Snapshot ─────────────────────────────────────────────────
st.subheader(f"📊 {asset_name} ({ticker}) — Live Snapshot")
try:
    from data import fetch_ticker_timeframe
    snap = fetch_ticker_timeframe(ticker, period="1d", interval="5m")
    if not snap.empty:
        cp  = snap.iloc[-1]["Close"]
        chg = cp - snap.iloc[0]["Close"]
        pct = chg / snap.iloc[0]["Close"] * 100
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Current Price", f"${cp:,.2f}", f"{pct:+.2f}%")
        c2.metric("24h High",      f"${snap['High'].max():,.2f}")
        c3.metric("24h Low",       f"${snap['Low'].min():,.2f}")
        c4.metric("24h Volume",    f"{snap['Volume'].sum()/1e6:.1f}M")
except Exception:
    st.info("Loading market data...")

# ── Analysis ──────────────────────────────────────────────────────
st.divider()

TIMEFRAME_MAP = {
    "1 Hour":  ("1d", "1m"),
    "4 Hours": ("1d", "5m"),
    "1 Day":   ("1d", "5m"),
    "3 Days":  ("3d", "15m"),
    "1 Week":  ("7d", "1h"),
    "1 Month": ("30d", "1d"),
}
period, interval_default = TIMEFRAME_MAP.get(timeframe, ("1d", "5m"))
final_interval = interval or interval_default

col_btn1, col_btn2 = st.columns([3, 1])
run_single = col_btn1.button(
    f"🔍 Analyse {asset_name} ({ticker})", type="primary", use_container_width=True
)
run_scan   = col_btn2.button("🔄 Multi-Scan", use_container_width=True) if scan_enabled else False


# ──────────────────────────────────────────────────────────────────
# MULTI-SCAN
# ──────────────────────────────────────────────────────────────────
if run_scan and scan_enabled:
    from core import run_enhanced_analysis
    st.subheader("🔄 Multi-Asset Scan Results")
    scan_results = []

    prog = st.progress(0, text="Scanning...")
    for i, t in enumerate(scan_tickers):
        prog.progress((i + 1) / len(scan_tickers), text=f"Scanning {t}…")
        try:
            r = run_enhanced_analysis(
                ticker=t, period=period, interval=final_interval,
                capital=capital, risk_percent=risk_percent
            )
            scan_results.append({
                "Ticker":     t,
                "Asset":      UNIVERSE[t][0],
                "Category":   UNIVERSE[t][1],
                "Signal":     r["decision"],
                "Confidence": f"{r['confidence']}%",
                "Price":      f"${r['current_price']:,.2f}",
                "RSI":        f"{r['rsi']:.1f}",
                "ADX":        f"{r['adx']:.1f}",
                "Zone":       r["sr_zone"],
            })
        except Exception as e:
            scan_results.append({
                "Ticker": t, "Asset": UNIVERSE[t][0],
                "Category": UNIVERSE[t][1],
                "Signal": "ERROR", "Confidence": "—",
                "Price": "—", "RSI": "—", "ADX": "—", "Zone": str(e)[:40],
            })
    prog.empty()

    import pandas as pd
    df_scan = pd.DataFrame(scan_results)

    def color_signal(val):
        if val == "BUY":  return "background-color:#1a4731; color:#4ade80"
        if val == "SELL": return "background-color:#4a1a1a; color:#f87171"
        if val == "WAIT": return "background-color:#3a3a1a; color:#facc15"
        return ""

    st.dataframe(
        df_scan.style.applymap(color_signal, subset=["Signal"]),
        use_container_width=True, hide_index=True
    )

    buys  = [r for r in scan_results if r["Signal"] == "BUY"]
    sells = [r for r in scan_results if r["Signal"] == "SELL"]
    if buys:
        st.success("🟢 **BUY signals:** " + ", ".join(f"{r['Ticker']} ({r['Confidence']})" for r in buys))
    if sells:
        st.error("🔴 **SELL signals:** " + ", ".join(f"{r['Ticker']} ({r['Confidence']})" for r in sells))
    st.divider()


# ──────────────────────────────────────────────────────────────────
# SINGLE ASSET ANALYSIS
# ──────────────────────────────────────────────────────────────────
if run_single:
    from core import run_enhanced_analysis

    with st.spinner(f"🤖 Analysing {asset_name} ({ticker}) — {timeframe} @ {final_interval}…"):
        try:
            result = run_enhanced_analysis(
                ticker=ticker, period=period, interval=final_interval,
                capital=capital, risk_percent=risk_percent,
            )
        except Exception as e:
            st.error(f"Analysis error: {e}")
            st.stop()

    decision      = result["decision"]
    conf          = result["confidence"]
    trade         = result["trade"]
    wait_analysis = result["wait_analysis"]
    tech          = result["technical"]
    mom           = result["momentum"]
    news_text     = result["news"]
    risk_agent_r  = result["risk"]
    headlines     = result["headlines"]
    mem           = result["memory"]
    sr            = result["sr_zone"]
    trend_str     = result["trend_str"]
    current_price = result["current_price"]
    data_source   = result["data_source"]

    # Data source banner
    if data_source == "mock":
        st.warning("⚠️ Using simulated data — live APIs unavailable")
    else:
        st.success(f"✅ Live data: **{data_source.upper()}** · {result['data_points']} candles")

    # ── Council Decision ──────────────────────────────────────────
    st.markdown("### 🏛️ Council Decision")
    c1, c2, c3, c4, c5 = st.columns(5)

    with c1:
        if decision == "BUY":
            st.success(f"## 🟢 BUY")
        elif decision == "SELL":
            st.error(f"## 🔴 SELL")
        else:
            st.warning(f"## 🟡 WAIT")

    c2.metric("Confidence",  f"{conf}%",
              "High" if conf >= 70 else ("Medium" if conf >= 50 else "Low"),
              delta_color="normal" if conf >= 70 else ("off" if conf >= 50 else "inverse"))
    c3.metric("Price",       f"${current_price:,.2f}")
    c4.metric("S/R Zone",    sr)
    c5.metric("Trend",       trend_str[:18])

    # Key indicators row
    st.markdown("#### 📐 Key Indicators")
    ki1, ki2, ki3, ki4, ki5 = st.columns(5)
    ki1.metric("RSI(14)",   f"{result['rsi']:.1f}",
               "Overbought" if result['rsi'] > 70 else ("Oversold" if result['rsi'] < 30 else "Normal"),
               delta_color="inverse" if result['rsi'] > 70 else ("normal" if result['rsi'] < 30 else "off"))
    ki2.metric("ADX",       f"{result['adx']:.1f}",
               "Trending" if result['adx'] > 25 else "Ranging",
               delta_color="normal" if result['adx'] > 25 else "off")
    ki3.metric("ATR",       f"${result['atr']:.2f}")
    ki4.metric("Timeframe", timeframe)
    ki5.metric("Candles",   result["data_points"])

    # ── Trading Plan ─────────────────────────────────────────────
    if trade:
        st.divider()
        st.markdown("## 📊 Trading Plan")

        st.markdown("### ⏰ Entry Timing")
        e1, e2 = st.columns(2)
        e1.metric("Current Price",  f"${trade['current_price']:,.2f}")
        e1.write(f"**Timing:** {trade['timing']}")
        e2.metric("Entry Zone",
                  f"${trade['entry_zone_low']:,.2f} – ${trade['entry_zone_high']:,.2f}")

        st.markdown("### 💼 Position Sizing")
        p1, p2, p3 = st.columns(3)
        p1.metric("Capital Used",    f"${trade['capital_allocated']:,.2f}")
        p2.metric("Position Size",   f"{trade['position_size_btc']:.6f} units")
        p3.metric("Entry Cost",      f"${trade['entry_cost']:,.2f}")

        st.markdown("### 🎯 Expected Outcome")
        o1, o2, o3, o4 = st.columns(4)
        o1.metric("Target",   f"${trade['target_price']:,.2f}", f"+{trade['profit_pct']:.2f}%")
        o2.metric("Profit",   f"${trade['expected_profit']:,.2f}", delta_color="normal")
        o3.metric("Stop Loss",f"${trade['stop_loss']:,.2f}",    f"-{trade['loss_pct']:.2f}%")
        o4.metric("Max Loss", f"${trade['max_loss']:,.2f}",     delta_color="inverse")

        rr = trade["risk_reward_ratio"]
        if rr >= 2:
            st.success(f"✅ **R:R = 1:{rr:.2f}** — Good setup")
        elif rr >= 1.5:
            st.info(f"⚠️ **R:R = 1:{rr:.2f}** — Acceptable")
        else:
            st.error(f"❌ **R:R = 1:{rr:.2f}** — Poor risk/reward, consider skipping")

    # ── WAIT Analysis ────────────────────────────────────────────
    else:
        st.divider()
        st.markdown("### 🟡 WAIT — Market Conditions")
        if wait_analysis:
            w1, w2 = st.columns([2, 1])
            with w1:
                st.markdown("**📋 Why WAIT**")
                st.info(wait_analysis["reason"])
                st.markdown("**⚠️ Risk Factors**")
                for r in wait_analysis["risk_factors"]:
                    st.markdown(f"- {r}")
                st.markdown("**🎯 Waiting For**")
                for w in wait_analysis["waiting_for"]:
                    st.markdown(f"- {w}")
            with w2:
                st.markdown("**⏰ Check Again**")
                st.warning(wait_analysis["next_check"])
                st.markdown("**💡 Recommendation**")
                st.info(wait_analysis["recommendation"])
                if wait_analysis.get("potential_loss"):
                    st.error(f"**Risk of forcing trade:** {wait_analysis['potential_loss']}")

    # ── Agent Details ─────────────────────────────────────────────
    st.divider()
    st.subheader("🧠 Agent Analysis")
    with st.expander("📉 Technical Agent (Chart & Indicators)", expanded=False):
        st.write(tech)
    with st.expander("⚡ Momentum Agent (Trend & Strength)", expanded=False):
        st.write(mom)
    with st.expander("📰 News Agent (Sentiment)", expanded=False):
        if headlines:
            st.markdown("**Latest Headlines:**")
            for h in headlines:
                st.markdown(f"- {h}")
            st.divider()
        st.write(news_text)
    with st.expander("🛡️ Risk Agent (Volatility & Safety)", expanded=False):
        st.write(risk_agent_r)
    with st.expander("🗂️ Decision Memory (last 10)", expanded=False):
        st.json(mem)
