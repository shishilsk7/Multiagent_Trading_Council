import os
from dotenv import load_dotenv
import streamlit as st

load_dotenv(override=True)

st.set_page_config(
    page_title="Trading Council",
    layout="wide",
    initial_sidebar_state="expanded",
    page_icon="📈",
)

st.markdown("""
<style>
[data-testid="metric-container"] {
    background: #1e1e2e;
    border-radius: 8px;
    padding: 12px;
}
.stExpander { border: 1px solid #333 !important; border-radius: 8px !important; }
.risk-banner {
    background: #3d1a1a;
    border-left: 4px solid #ef4444;
    padding: 12px 16px;
    border-radius: 4px;
    margin: 8px 0;
}
.vote-bar { font-size: 1.1em; letter-spacing: 2px; }
</style>
""", unsafe_allow_html=True)

from stocks import UNIVERSE, CATEGORIES, ticker_label, currency_label

st.title("📈 AI Trading Council")
st.markdown("*Technical · Momentum · News · Risk — Real-money grade analysis*")

api_ok = bool(os.getenv("OPENROUTER_API_KEY"))
status = "✅ API Connected" if api_ok else "⚠️ API Key Missing — set OPENROUTER_API_KEY"
st.caption(f"🔑 {status}")
st.divider()

# ── Sidebar ──────────────────────────────────────────────────────────
with st.sidebar:
    st.header("⚙️ Settings")

    st.subheader("🎯 Asset")
    cat_filter = st.selectbox("Category", ["All"] + CATEGORIES)
    filtered   = {k: v for k, v in UNIVERSE.items() if cat_filter == "All" or v[1] == cat_filter}
    t_opts     = list(filtered.keys())
    t_labels   = [ticker_label(t) for t in t_opts]
    sel_label  = st.selectbox("Asset", t_labels)
    ticker     = t_opts[t_labels.index(sel_label)]
    asset_name, asset_cat = UNIVERSE[ticker]
    st.info(f"**{asset_name}** | {asset_cat}")

    st.divider()
    st.subheader("🔍 Multi-Scan")
    scan_enabled = st.checkbox("Enable")
    scan_tickers = []
    if scan_enabled:
        scan_tickers = st.multiselect(
            "Assets to scan", options=t_opts, default=t_opts[:4],
            format_func=lambda t: f"{t} – {UNIVERSE[t][0]}",
        )

    st.divider()
    st.subheader("📊 Timeframe")
    timeframe = st.selectbox(
        "Period",
        ["1 Hour", "4 Hours", "1 Day", "3 Days", "1 Week", "1 Month"],
        index=2,
    )
    interval = st.selectbox("Interval", ["1m", "5m", "15m", "1h", "1d"], index=1)

    st.divider()
    st.subheader("💰 Risk Management")
    capital      = st.number_input("Capital (₹)", min_value=1000.0, value=50_000.0, step=5_000.0)
    risk_percent = st.slider("Risk Per Trade (%)", 0.5, 5.0, 1.0, 0.25)
    max_risk_inr = capital * risk_percent / 100
    st.info(f"Max loss per trade: **₹{max_risk_inr:,.0f}**")

    st.divider()
    st.subheader("📈 Live Chart")
    chart_src = st.radio("Provider", ["TradingView", "Binance", "Yahoo"])
    sym = ticker.replace("-USD", "USD").replace("-", "")
    if chart_src == "TradingView":
        chart_url = f"https://www.tradingview.com/chart/?symbol={sym}"
    elif chart_src == "Binance":
        bsym = ticker.replace("-USD", "USDT").replace("-", "")
        chart_url = f"https://www.binance.com/en/trade/{bsym}"
    else:
        chart_url = f"https://finance.yahoo.com/quote/{ticker}"
    st.link_button(f"📊 Open {chart_src}", chart_url, use_container_width=True)

    st.divider()
    st.subheader("⏱️ Auto-Refresh")
    auto_refresh = st.checkbox("Enable (intraday)", value=False)
    refresh_secs = st.slider("Interval (seconds)", 30, 300, 60, step=30, disabled=not auto_refresh)

# ── Live Snapshot ─────────────────────────────────────────────────────
st.subheader(f"📊 {asset_name} ({ticker})")
try:
    from data import fetch_ticker_timeframe

    @st.cache_data(ttl=300, show_spinner=False)
    def _cached_snapshot(t):
        return fetch_ticker_timeframe(t, period="1d", interval="5m")

    with st.spinner("Fetching price..."):
        snap = _cached_snapshot(ticker)
    if not snap.empty and snap.attrs.get("source") != "mock":
        cp  = snap.iloc[-1]["Close"]
        chg = cp - snap.iloc[0]["Close"]
        pct = chg / snap.iloc[0]["Close"] * 100
        cur = currency_label(ticker)
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Price",    f"{cur}{cp:,.4f}", f"{pct:+.2f}%")
        c2.metric("24h High", f"{cur}{snap['High'].max():,.4f}")
        c3.metric("24h Low",  f"{cur}{snap['Low'].min():,.4f}")
        c4.metric("Volume",   f"{snap['Volume'].sum()/1e6:.2f}M")
    else:
        st.warning("⚠️ Live price unavailable. Check connection before analysing.")
except Exception:
    st.warning("⚠️ Live price unavailable.")

# ── Action Buttons ────────────────────────────────────────────────────
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

col1, col2 = st.columns([3, 1])
run_single = col1.button(f"🔍 Analyse {asset_name}", type="primary", use_container_width=True)
run_scan   = col2.button("🔄 Multi-Scan", use_container_width=True) if scan_enabled else False

# ── Risk Disclaimer ───────────────────────────────────────────────────
st.markdown("""
<div class="risk-banner">
⚠️ <strong>Risk Disclosure:</strong> This tool is for decision support only.
All trades carry risk of loss. Never invest more than you can afford to lose.
Past signal performance does not guarantee future results.
Always set stop-losses before entering any trade.
</div>
""", unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════════════
# MULTI-SCAN
# ══════════════════════════════════════════════════════════════════════
if run_scan and scan_enabled and scan_tickers:
    from core import run_enhanced_analysis
    import pandas as pd

    st.subheader("🔄 Multi-Asset Scan")
    scan_results = []
    prog = st.progress(0, text="Scanning...")

    for i, t in enumerate(scan_tickers):
        prog.progress((i + 1) / len(scan_tickers), text=f"Scanning {t}…")
        try:
            r = run_enhanced_analysis(
                ticker=t, period=period, interval=final_interval,
                capital=capital, risk_percent=risk_percent,
            )
            trade = r.get("trade") or {}
            scan_results.append({
                "Ticker":     t,
                "Asset":      UNIVERSE[t][0],
                "Signal":     r["decision"],
                "Conf %":     f"{r['confidence']}%",
                "Price":      f"{currency_label(t)}{r['current_price']:,.4f}",
                "RSI":        f"{r['rsi']:.1f}",
                "ADX":        f"{r['adx']:.1f}",
                "Zone":       r["sr_zone"],
                "R:R":        f"1:{trade.get('risk_reward_ratio','—')}" if trade else "—",
                "Target":     f"{currency_label(t)}{trade['target_price']:,.4f}" if trade else "—",
                "Stop":       f"{currency_label(t)}{trade['stop_loss']:,.4f}" if trade else "—",
            })
        except Exception as e:
            scan_results.append({
                "Ticker": t, "Asset": UNIVERSE[t][0],
                "Signal": "ERROR", "Conf %": "—", "Price": "—",
                "RSI": "—", "ADX": "—", "Zone": str(e)[:50],
                "R:R": "—", "Target": "—", "Stop": "—",
            })
    prog.empty()

    df_scan = pd.DataFrame(scan_results)

    def color_signal(val):
        if val == "BUY":   return "background-color:#1a4731; color:#4ade80"
        if val == "SELL":  return "background-color:#4a1a1a; color:#f87171"
        if val == "WAIT":  return "background-color:#3a3a1a; color:#facc15"
        if val == "ERROR": return "background-color:#2a1a2a; color:#c084fc"
        return ""

    st.dataframe(
        df_scan.style.applymap(color_signal, subset=["Signal"]),
        use_container_width=True, hide_index=True,
    )

    buys  = [r for r in scan_results if r["Signal"] == "BUY"]
    sells = [r for r in scan_results if r["Signal"] == "SELL"]
    if buys:
        st.success("🟢 BUY: " + "  |  ".join(f"{r['Ticker']} {r['Conf %']} R:R {r['R:R']}" for r in buys))
    if sells:
        st.error("🔴 SELL: " + "  |  ".join(f"{r['Ticker']} {r['Conf %']} R:R {r['R:R']}" for r in sells))
    st.divider()


# ══════════════════════════════════════════════════════════════════════
# SINGLE ASSET ANALYSIS
# ══════════════════════════════════════════════════════════════════════
if "last_result" not in st.session_state:
    st.session_state["last_result"] = None
    st.session_state["last_result_time"] = None

if run_single:
    from core import run_enhanced_analysis

    with st.spinner(f"🤖 Analysing {asset_name} — running 4 agents in parallel…"):
        try:
            st.session_state["last_result"] = run_enhanced_analysis(
                ticker=ticker, period=period, interval=final_interval,
                capital=capital, risk_percent=risk_percent,
            )
            st.session_state["last_result_time"] = __import__('datetime').datetime.now().strftime("%H:%M:%S")
        except Exception as e:
            st.error(f"❌ Analysis failed: {e}")
            st.stop()

if st.session_state["last_result"] is not None:
    result = st.session_state["last_result"]
    if st.session_state["last_result_time"]:
        st.caption(f"Last run: {st.session_state['last_result_time']} — change settings and click Analyse to refresh")

    # auto-refresh trigger (only when a result exists)
    if auto_refresh:
        import time
        time.sleep(refresh_secs)
        st.rerun()

    decision      = result["decision"]
    conf          = result["confidence"]
    trade         = result["trade"]
    wait_analysis = result["wait_analysis"]
    breakdown     = result.get("vote_breakdown", {})
    data_source   = result["data_source"]

    st.success(f"✅ Live data: **{data_source.upper()}** · {result['data_points']} candles · {timeframe} @ {final_interval}")

    # ── Main Decision ──────────────────────────────────────────────
    st.markdown("---")
    st.markdown("## 🏛️ Council Decision")

    d1, d2, d3, d4, d5 = st.columns(5)

    if decision == "BUY":
        d1.success("## 🟢 BUY")
    elif decision == "SELL":
        d1.error("## 🔴 SELL")
    else:
        d1.warning("## 🟡 WAIT")

    conf_label = "High 🔥" if conf >= 70 else ("Medium" if conf >= 50 else "Low ⚠️")
    d2.metric("Confidence",  f"{conf}%", conf_label,
              delta_color="normal" if conf >= 65 else ("off" if conf >= 50 else "inverse"))
    d3.metric("Price",       f"{currency_label(ticker)}{result['current_price']:,.4f}")
    d4.metric("S/R Zone",    result["sr_zone"])
    d5.metric("Trend",       result["trend_str"][:20])

    # Indicators row
    st.markdown("#### 📐 Key Indicators")
    k1, k2, k3, k4, k5, k6 = st.columns(6)
    rsi_v  = result["rsi"]
    adx_v  = result["adx"]
    atr_v  = result["atr"]
    macd_v = result["macd_hist"]

    k1.metric("RSI(14)",  f"{rsi_v:.1f}",
              "⬆️ Overbought" if rsi_v > 70 else ("⬇️ Oversold" if rsi_v < 30 else "✅ Normal"),
              delta_color="inverse" if rsi_v > 70 else ("normal" if rsi_v < 30 else "off"))
    k2.metric("ADX",      f"{adx_v:.1f}",
              "Trending" if adx_v > 25 else "Ranging",
              delta_color="normal" if adx_v > 25 else "inverse")
    k3.metric("ATR",      f"{currency_label(ticker)}{atr_v:.4f}",
              f"{(atr_v/result['current_price']*100):.2f}% of price")
    k4.metric("MACD Hist", f"{macd_v:.5f}",
              "▲ Bullish" if macd_v > 0 else "▼ Bearish",
              delta_color="normal" if macd_v > 0 else "inverse")
    k5.metric("Patterns", len(result.get("patterns", [])))
    k6.metric("Candles",  result["data_points"])

    # ── Vote Breakdown ─────────────────────────────────────────────
    st.divider()
    st.markdown("### 🔬 How the Decision Was Made")

    from decision import _parse_signal
    tech_sig = _parse_signal(result["technical"])
    mom_sig  = _parse_signal(result["momentum"])
    risk_u   = result["risk"].upper()
    risk_lbl = "🔴 High" if "RISK: HIGH" in risk_u else ("🟡 Medium" if "RISK: MEDIUM" in risk_u else "🟢 Low")
    risk_act = "⛔ AVOID" if ("RISK: HIGH" in risk_u and "AVOID" in risk_u) else "✅ Trade"

    sb1, sb2, sb3, sb4, sb5, sb6 = st.columns(6)
    sb1.metric("Technical",  "🟢 BUY" if tech_sig=="BUY" else ("🔴 SELL" if tech_sig=="SELL" else "🟡 WAIT"), "×3 weight")
    sb2.metric("Momentum",   "🟢 BUY" if mom_sig=="BUY"  else ("🔴 SELL" if mom_sig=="SELL"  else "🟡 WAIT"), "×2 weight")
    sb3.metric("RSI Signal", "🟢 BUY" if rsi_v < 40 else ("🔴 SELL" if rsi_v > 60 else "🟡 Neutral"), f"{rsi_v:.1f}")
    sb4.metric("MACD",       "🟢 ▲" if macd_v > 0 else "🔴 ▼", f"{macd_v:.5f}")
    sb5.metric("Risk Level", risk_lbl)
    sb6.metric("Risk Action", risk_act)

    # Vote bars with actual counts from breakdown
    buy_v  = breakdown.get("total_buy", 0)
    sell_v = breakdown.get("total_sell", 0)
    veto   = breakdown.get("hard_veto", False)
    reason = breakdown.get("reason", "")

    bar_buy  = "🟩" * buy_v  + "⬜" * max(0, 7 - buy_v)
    bar_sell = "🟥" * sell_v + "⬜" * max(0, 7 - sell_v)

    st.markdown(f"""
| | Votes | Visual (max 7) |
|---|---|---|
| 🟢 BUY  | **{buy_v}/7** | <span class="vote-bar">{bar_buy}</span> |
| 🔴 SELL | **{sell_v}/7** | <span class="vote-bar">{bar_sell}</span> |

**Decision logic:** {reason} {"| ⛔ Hard veto active" if veto else ""}
> Threshold: 4+ votes = confident signal · 3 votes = borderline · <3 = WAIT
""", unsafe_allow_html=True)

    # Patterns
    patterns = result.get("patterns", [])
    if patterns and patterns != ["No clear pattern"]:
        st.markdown("**📊 Active Patterns:** " + "  ·  ".join(patterns))

    # ── TRADE PLAN ─────────────────────────────────────────────────
    if trade:
        st.divider()
        st.markdown("## 📊 Trade Plan")

        rate = trade.get("usd_inr_rate", 84.0)
        atr_used = trade.get("atr_used", 0)
        st.caption(
            f"💱 USD/INR: ₹{rate:.2f}  ·  "
            f"Capital: ₹{trade['capital_inr']:,.0f} (≈ ${trade['capital_usd']:,.0f})  ·  "
            f"Stop/Target based on ATR = ${atr_used:.4f}"
        )

        # Entry
        st.markdown("### ⏰ Entry")
        e1, e2, e3 = st.columns(3)
        cur = currency_label(ticker)
        e1.metric("Current Price",  f"{cur}{trade['current_price']:,.4f}")
        e2.metric("Entry Zone",     f"{cur}{trade['entry_zone_low']:,.4f} → {cur}{trade['entry_zone_high']:,.4f}")
        e3.info(f"**⏱️ Timing:** {trade['timing']}")

        # Levels
        st.markdown("### 🎯 Levels & P&L")
        l1, l2, l3, l4 = st.columns(4)
        l1.metric("🎯 Target",          f"{cur}{trade['target_price']:,.4f}",
                  f"+{trade['profit_pct']:.2f}%", delta_color="normal")
        l2.metric("✅ Expected Profit",  f"₹{trade['expected_profit_inr']:,.0f}",
                  f"+{trade['profit_pct']:.2f}%", delta_color="normal")
        l3.metric("🛑 Stop Loss",        f"{cur}{trade['stop_loss']:,.4f}",
                  f"-{trade['loss_pct']:.2f}%", delta_color="inverse")
        l4.metric("❌ Max Loss",          f"₹{trade['max_loss_inr']:,.0f}",
                  f"-{trade['loss_pct']:.2f}%", delta_color="inverse")

        # Position
        st.markdown("### 💼 Position")
        p1, p2, p3, p4 = st.columns(4)
        p1.metric("Capital",        f"₹{trade['capital_inr']:,.0f}")
        p2.metric("Max Risk",       f"₹{trade['max_risk_inr']:,.0f}", f"{trade['risk_percent']}%")
        p3.metric("Position Size",  f"{trade['position_size']:.6f} units")
        p4.metric("Entry Cost",     f"₹{trade['entry_cost_inr']:,.0f}")

        # R:R verdict
        rr = trade["risk_reward_ratio"]
        verdict = trade.get("rr_verdict", "")
        if rr >= 2.0:
            st.success(f"**R:R = 1:{rr:.2f}** — {verdict}")
        elif rr >= 1.5:
            st.info(f"**R:R = 1:{rr:.2f}** — {verdict}")
        else:
            st.error(f"**R:R = 1:{rr:.2f}** — {verdict}")

        # ── Copyable Trade Card ──────────────────────────────────
        st.divider()
        st.markdown("### 🚀 Copy Into Groww / Zerodha")
        broker_note = {
            "BUY":  "Groww/Zerodha → Search asset → CNC or MIS BUY order",
            "SELL": "Groww/Zerodha → Search asset → CNC or MIS SELL/SHORT order",
        }.get(decision, "")

        st.code(f"""
╔═══════════════════════════════════════════════════════╗
   📋  TRADE SETUP  —  {asset_name} ({ticker})
   Generated: {__import__('datetime').datetime.now().strftime('%Y-%m-%d %H:%M')}
╠═══════════════════════════════════════════════════════╣
  Action        :  {decision}
  Confidence    :  {conf}%
  Data Source   :  {data_source.upper()}

  ── PRICE LEVELS ─────────────────────────────────────
  Current Price :  {cur}{trade['current_price']:,.4f}
  Entry Zone    :  {cur}{trade['entry_zone_low']:,.4f}  →  {cur}{trade['entry_zone_high']:,.4f}
  Stop Loss     :  {cur}{trade['stop_loss']:,.4f}   ← SET THIS FIRST on entry
  Target        :  {cur}{trade['target_price']:,.4f}   ← Take profit here

  ── YOUR MONEY (₹) ───────────────────────────────────
  Capital       :  ₹{trade['capital_inr']:,.0f}
  Max Risk      :  ₹{trade['max_risk_inr']:,.0f}  ({trade['risk_percent']}% of capital)
  Entry Cost    :  ₹{trade['entry_cost_inr']:,.0f}
  Expected Gain :  ₹{trade['expected_profit_inr']:,.0f}  (+{trade['profit_pct']:.2f}%)
  Max Loss      :  ₹{trade['max_loss_inr']:,.0f}  (-{trade['loss_pct']:.2f}%)

  ── POSITION ─────────────────────────────────────────
  Quantity      :  {trade['position_size']:.6f} units
  ATR (volatility): ${atr_used:.4f}
  Timing        :  {trade['timing']}

  ── RISK/REWARD ──────────────────────────────────────
  R:R Ratio     :  1 : {rr:.2f}
  Verdict       :  {verdict}
╚═══════════════════════════════════════════════════════╝
""", language="text")
        st.caption(f"💡 {broker_note}")

    # ── WAIT Analysis ──────────────────────────────────────────────
    else:
        st.divider()
        st.markdown("### 🟡 WAIT — Why Not Trading Now")
        if wait_analysis:
            w1, w2 = st.columns([2, 1])
            with w1:
                st.error(f"**Reason:** {wait_analysis['reason']}")
                st.markdown("**⚠️ Risk Factors**")
                for rf in wait_analysis["risk_factors"]:
                    st.markdown(f"- {rf}")
                st.markdown("**🎯 Wait For**")
                for wf in wait_analysis["waiting_for"]:
                    st.markdown(f"- {wf}")
                if wait_analysis.get("potential_loss"):
                    st.error(f"**Forcing a trade now risks:** {wait_analysis['potential_loss']}")
            with w2:
                st.warning(f"⏰ **Check again in:** {wait_analysis['next_check']}")
                st.info(f"💡 **Recommendation:**\n{wait_analysis['recommendation']}")

    # ── Historical Memory ──────────────────────────────────────────
    past_signals = result.get("past_signals", [])
    ticker_stats = result.get("ticker_stats")

    if ticker_stats or past_signals:
        st.divider()
        st.subheader("📚 Your Track Record")

        if ticker_stats:
            ts1, ts2, ts3, ts4, ts5, ts6, ts7 = st.columns(7)
            ts1.metric("Total Signals", ticker_stats["total"])
            ts2.metric("✅ Wins",        ticker_stats["wins"])
            ts3.metric("❌ Losses",      ticker_stats["losses"])
            ts4.metric("⏰ Expired",     ticker_stats.get("expired", 0))
            ts5.metric("Win Rate",       f"{ticker_stats['win_rate']}%",
                       delta_color="normal" if ticker_stats["win_rate"] >= 50 else "inverse")
            ts6.metric("Avg Win",        f"+{ticker_stats['avg_win']}%")
            ts7.metric("Avg Loss",       f"{ticker_stats['avg_loss']}%")

        if past_signals:
            st.markdown("##### 🔁 Similar Past Setups")
            for ps in past_signals:
                icon = "✅" if "TARGET" in ps["outcome"] else "❌"
                pct  = f"+{ps['outcome_pct']}%" if ps['outcome_pct'] > 0 else f"{ps['outcome_pct']}%"
                ind  = ps["indicators"]
                with st.expander(f"{icon} {ps['decision']} on {ps['id']} → {ps['outcome']} ({pct})", expanded=False):
                    c1, c2, c3, c4 = st.columns(4)
                    ps_cur = currency_label(ticker)
                    c1.metric("Entry",  f"{ps_cur}{ps['entry_price']:,.4f}")
                    c2.metric("Target", f"{ps_cur}{ps['target_price']:,.4f}")
                    c3.metric("Stop",   f"{ps_cur}{ps['stop_loss']:,.4f}")
                    c4.metric("Result", pct, delta_color="normal" if ps['outcome_pct'] > 0 else "inverse")
                    st.caption(
                        f"Conditions: RSI {ind.get('rsi')} · "
                        f"MACD {'▲' if ind.get('macd_hist', 0) > 0 else '▼'} · "
                        f"Zone: {ind.get('sr_zone')} · Confidence: {ps['confidence']}%"
                    )
        else:
            st.info("No similar resolved signals yet. They appear here once your BUY/SELL signals hit target or stop.")

    # ── Agent Detail ───────────────────────────────────────────────
    st.divider()
    st.subheader("🧠 Agent Reasoning")
    with st.expander("📉 Technical Agent",             expanded=False): st.write(result["technical"])
    with st.expander("⚡ Momentum Agent",              expanded=False): st.write(result["momentum"])
    with st.expander("📰 News Agent",                  expanded=False):
        if result.get("headlines"):
            st.markdown("**Headlines used:**")
            for h in result["headlines"]: st.markdown(f"- {h}")
            st.divider()
        st.write(result["news"])
    with st.expander("🛡️ Risk Agent",                  expanded=False): st.write(result["risk"])
    with st.expander("🗂️ Decision Memory (last 10)",   expanded=False): st.json(result["memory"])
