import os
from dotenv import load_dotenv
import streamlit as st

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

# ── Safe imports (no network calls at import time) ───────────────
from stocks import UNIVERSE, CATEGORIES, ticker_label

# ── Header ───────────────────────────────────────────────────────
st.title("📈 AI Trading Intelligence Platform")
st.markdown("*Multi-Agent Council · Technical + Momentum + News + Risk*")

api_ok = bool(os.getenv("OPENROUTER_API_KEY"))
st.caption("🔑 API: " + ("✅ Connected" if api_ok else "⚠️ Offline Mode"))
st.divider()

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
    capital = st.number_input("Your Capital (₹)", min_value=1000.0, value=50_000.0, step=5_000.0)
    risk_percent = st.slider("Risk Per Trade (%)", 0.5, 10.0, 1.0, 0.25)
    st.info(f"💡 Max risk/trade: **₹{capital * risk_percent / 100:,.0f}**")

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
    with st.spinner("Fetching live price..."):
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
    else:
        st.info("Market data unavailable — click Analyse to proceed.")
except Exception:
    st.info("Market data unavailable — click Analyse to proceed.")

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

    # ── Signal Breakdown ─────────────────────────────────────────
    st.divider()
    st.markdown("### 🔬 Signal Breakdown — Why this decision?")

    from decision import _parse_signal
    tech_sig = _parse_signal(result["technical"])
    mom_sig  = _parse_signal(result["momentum"])
    rsi_v    = result["rsi"]
    macd_v   = result["macd_hist"]
    rsi_sig  = "🟢 BUY" if rsi_v < 40 else ("🔴 SELL" if rsi_v > 60 else "🟡 Neutral")
    macd_sig = "🟢 BUY" if macd_v > 0 else "🔴 SELL"
    risk_u   = result["risk"].upper()
    risk_lbl = "🔴 High" if "RISK: HIGH" in risk_u else ("🟡 Medium" if "RISK: MEDIUM" in risk_u else "🟢 Low")
    risk_act = "⛔ Avoid" if ("RISK: HIGH" in risk_u and "AVOID" in risk_u) else "✅ Trade"

    sb1, sb2, sb3, sb4, sb5, sb6 = st.columns(6)
    sb1.metric("Technical Agent", "🟢 BUY" if tech_sig=="BUY" else ("🔴 SELL" if tech_sig=="SELL" else "🟡 WAIT"), "×3 weight")
    sb2.metric("Momentum Agent",  "🟢 BUY" if mom_sig=="BUY"  else ("🔴 SELL" if mom_sig=="SELL"  else "🟡 WAIT"), "×2 weight")
    sb3.metric("RSI Signal",      rsi_sig,  f"{rsi_v:.1f}")
    sb4.metric("MACD Signal",     macd_sig, f"{macd_v:.4f}")
    sb5.metric("Risk Level",      risk_lbl)
    sb6.metric("Risk Action",     risk_act)

    # Vote tally
    buy_v  = (3 if tech_sig=="BUY"  else 0) + (2 if mom_sig=="BUY"  else 0)
    sell_v = (3 if tech_sig=="SELL" else 0) + (2 if mom_sig=="SELL" else 0)
    ind_buy  = sum([rsi_v < 40, macd_v > 0])
    ind_sell = sum([rsi_v > 60, macd_v < 0])
    if ind_buy >= 2:    buy_v  += 2
    elif ind_buy == 1:  buy_v  += 1
    if ind_sell >= 2:   sell_v += 2
    elif ind_sell == 1: sell_v += 1

    bar_buy  = "🟩" * buy_v  + "⬜" * (7 - buy_v)
    bar_sell = "🟥" * sell_v + "⬜" * (7 - sell_v)
    st.markdown(f"""
| | Votes | Bar (max 7) |
|---|---|---|
| 🟢 BUY  | **{buy_v}** | {bar_buy} |
| 🔴 SELL | **{sell_v}** | {bar_sell} |

> Needs **3+ votes** to trigger · Final call: **{decision}** {"✅" if decision != "WAIT" else "⏸️"}
""")

    # ── Trading Plan ─────────────────────────────────────────────
    if trade:
        st.divider()
        st.markdown("## 📊 Trading Plan")

        rate = trade.get("usd_inr_rate", 84.0)
        st.caption(f"💱 USD/INR rate used: ₹{rate:.2f}  |  Your capital: ₹{trade['capital_inr']:,.0f} (≈ ${trade['capital_usd']:,.0f})")

        st.markdown("### ⏰ Entry Timing")
        e1, e2 = st.columns(2)
        e1.metric("Current Price",  f"${trade['current_price']:,.2f}")
        e1.write(f"**Timing:** {trade['timing']}")
        e2.metric("Entry Zone",
                  f"${trade['entry_zone_low']:,.2f} – ${trade['entry_zone_high']:,.2f}")

        st.markdown("### 💼 Position Sizing")
        p1, p2, p3 = st.columns(3)
        p1.metric("Capital Used",  f"₹{trade['capital_inr']:,.0f}")
        p2.metric("Position Size", f"{trade['position_size']:.6f} units")
        p3.metric("Entry Cost",    f"₹{trade['entry_cost_inr']:,.0f}")

        st.markdown("### 🎯 Expected Outcome")
        o1, o2, o3, o4 = st.columns(4)
        o1.metric("Target Price",   f"${trade['target_price']:,.2f}", f"+{trade['profit_pct']:.2f}%")
        o2.metric("Expected Profit",f"₹{trade['expected_profit_inr']:,.0f}", delta_color="normal")
        o3.metric("Stop Loss",      f"${trade['stop_loss']:,.2f}", f"-{trade['loss_pct']:.2f}%")
        o4.metric("Max Loss",       f"₹{trade['max_loss_inr']:,.0f}", delta_color="inverse")

        rr = trade["risk_reward_ratio"]
        if rr >= 2:
            st.success(f"✅ **R:R = 1:{rr:.2f}** — Good setup")
        elif rr >= 1.5:
            st.info(f"⚠️ **R:R = 1:{rr:.2f}** — Acceptable")
        else:
            st.error(f"❌ **R:R = 1:{rr:.2f}** — Poor risk/reward, consider skipping")

        # ── Ready to Trade Card ──────────────────────────────────
        st.divider()
        st.markdown("### 🚀 Ready to Trade — Copy this into Groww / Zerodha")

        platform_note = {
            "BUY":  "Open Groww/Zerodha → Search asset → Place **CNC or MIS BUY order**",
            "SELL": "Open Groww/Zerodha → Search asset → Place **CNC or MIS SELL order**",
        }.get(decision, "")

        rr_verdict = "✅ Good setup — go ahead" if rr >= 2 else ("⚠️ Acceptable — proceed carefully" if rr >= 1.5 else "❌ Poor R:R — consider skipping")

        st.code(f"""
╔══════════════════════════════════════════════════╗
   📋  TRADE SETUP  —  {asset_name} ({ticker})
╠══════════════════════════════════════════════════╣
  Action      :  {decision}
  Asset       :  {asset_name} ({ticker})

  ── PRICE LEVELS (in $) ─────────────────────────
  Current Price :  ${trade['current_price']:,.2f}
  Entry Zone    :  ${trade['entry_zone_low']:,.2f}  →  ${trade['entry_zone_high']:,.2f}
  Stop Loss     :  ${trade['stop_loss']:,.2f}   ← set this immediately on entry
  Target        :  ${trade['target_price']:,.2f}   ← take profit here

  ── YOUR MONEY (in ₹) ───────────────────────────
  Capital       :  ₹{trade['capital_inr']:,.0f}
  Max Risk      :  ₹{trade['max_risk_inr']:,.0f}  ({trade['risk_percent']}% of capital)
  Entry Cost    :  ₹{trade['entry_cost_inr']:,.0f}
  Expected Profit: ₹{trade['expected_profit_inr']:,.0f}  (+{trade['profit_pct']:.2f}%)
  Max Loss      :  ₹{trade['max_loss_inr']:,.0f}  (-{trade['loss_pct']:.2f}%)

  ── POSITION ────────────────────────────────────
  Quantity      :  {trade['position_size']:.6f} units
  Timing        :  {trade['timing']}

  ── VERDICT ─────────────────────────────────────
  Risk/Reward   :  1 : {rr:.2f}
  Assessment    :  {rr_verdict}
╚══════════════════════════════════════════════════╝
""", language="text")

        st.caption(f"💡 {platform_note}")

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