import os
from urllib.parse import quote
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

from stocks import UNIVERSE, CATEGORIES, ticker_label, currency_label, get_tradingview_symbol, is_indian
from market_calendar import get_market_status
from llm import check_llm_connectivity

if "analysis_period" not in st.session_state:
    st.session_state["analysis_period"] = "1mo"
if "analysis_interval" not in st.session_state:
    st.session_state["analysis_interval"] = "1h"

st.title("📈 AI Trading Council")
st.markdown("*Technical · Momentum · News · Risk — Real-money grade analysis*")

api_ok = bool(
    os.getenv("GEMINI_API_KEY") or 
    os.getenv("GROQ_API_KEY") or 
    os.getenv("OPENAI_API_KEY") or 
    os.getenv("OPENROUTER_API_KEY")
)
status = "✅ API Key(s) Found" if api_ok else "⚠️ API Key Missing — set GEMINI_API_KEY, GROQ_API_KEY, OPENAI_API_KEY, or OPENROUTER_API_KEY"
st.caption(f"🔑 {status}")

if api_ok and "llm_status" not in st.session_state:
    llm_ok, llm_msg = check_llm_connectivity()
    st.session_state["llm_status"] = (llm_ok, llm_msg)

col_conn1, col_conn2 = st.columns([3, 1])
with col_conn1:
    if "llm_status" in st.session_state:
        llm_ok, llm_msg = st.session_state["llm_status"]
        if llm_ok:
            st.caption(f"🤖 LLM: ✅ {llm_msg}")
        else:
            st.warning(f"🤖 LLM: ⚠️ {llm_msg}")
with col_conn2:
    if api_ok:
        if st.button("🧪 Test API", use_container_width=True):
            from llm import test_llm_connectivity_live
            with st.spinner("Testing API key..."):
                ok, msg = test_llm_connectivity_live()
            if ok:
                st.success(msg)
            else:
                st.error(msg)
st.divider()

# ── Watchlist Panel ───────────────────────────────────────────────────
st.subheader("🎓 Expert Watchlist & Actionable Setups")
with st.expander("🔍 View Today's Key Market Setups (Dynamic Scan)", expanded=False):
    st.markdown("This panel performs a real-time scan of high-interest assets to identify key levels, support floors, and timing entry windows.")
    st.caption(
        f"Scan settings: {st.session_state['analysis_period']} @ {st.session_state['analysis_interval']} "
        "(uses the same live analysis inputs as the single-asset view)"
    )
    
    if st.button("⚡ Scan Watchlist Now", use_container_width=True):
        import concurrent.futures
        from core import run_enhanced_analysis
        
        watchlist_tickers = ["WIPRO.NS", "RELIANCE.NS", "PLTR", "BTC-USD", "NVDA"]
        nse_status = get_market_status("RELIANCE.NS")
        nse_open = nse_status["is_open"]
        scan_period = st.session_state["analysis_period"]
        scan_interval = st.session_state["analysis_interval"]
        
        def scan_watchlist_ticker(t):
            if is_indian(t) and not nse_open:
                return t, {
                    "ticker": t,
                    "decision": "MARKET_CLOSED",
                    "market_status": nse_status,
                    "current_price": None,
                    "confidence": 0,
                    "trade": None,
                    "sr_zone": None,
                }
            try:
                # Use 1h timeframe for swing setups
                r = run_enhanced_analysis(ticker=t, period=scan_period, interval=scan_interval)
                return t, r
            except Exception as e:
                return t, e
        
        with st.spinner("Analyzing setups and support/resistance zones..."):
            with concurrent.futures.ThreadPoolExecutor(max_workers=len(watchlist_tickers)) as executor:
                results = list(executor.map(scan_watchlist_ticker, watchlist_tickers))
        
        for t, r in results:
            if isinstance(r, Exception):
                st.error(f"⚠️ Failed to scan {t}: {r}")
                continue
                
            decision = r["decision"]
            if decision == "MARKET_CLOSED":
                st.warning(f"⏸️ {t}: {r.get('market_status', {}).get('message', 'Market closed')}")
                continue
            timeframe = f"{r.get('period', scan_period)} @ {r.get('interval', scan_interval)}"
            price = r["current_price"]
            df_ticker = r["df"]
            support = float(df_ticker.iloc[-1].get("support", 0.0))
            resistance = float(df_ticker.iloc[-1].get("resistance", 0.0))
            rsi = r["rsi"]
            sr_zone = r["sr_zone"]
            cur = currency_label(t)
            
            # Formulate the expert recommendation dynamically
            if decision == "BUY":
                rec = f"🟢 **BUY TRIGGERED**: The council has confirmed a bullish setup. Position size targets an ATR-based entry. Watch the entry zone: **{cur}{r['trade']['entry_zone_low']:,.2f} – {cur}{r['trade']['entry_zone_high']:,.2f}**."
            elif decision == "SELL":
                rec = f"🔴 **SELL TRIGGERED**: The council has confirmed a bearish setup. Position size targets an ATR-based short. Entry zone: **{cur}{r['trade']['entry_zone_low']:,.2f} – {cur}{r['trade']['entry_zone_high']:,.2f}**."
            else:
                # Wait scenarios
                if rsi < 30:
                    rec = f"⚠️ **OVERSOLD BOUNCE CANDIDATE**: Price is heavily oversold (RSI: {rsi:.1f}). Do not catch a falling knife. Wait for a green hourly candle to close above support at **{cur}{support:,.2f}** before buying."
                elif rsi > 70:
                    rec = f"⚠️ **OVERBOUGHT REVERSAL CANDIDATE**: Price is overbought (RSI: {rsi:.1f}). Wait for a red hourly candle confirmation near resistance at **{cur}{resistance:,.2f}** to look for short entries."
                elif sr_zone == "Near Support":
                    rec = f"🎯 **SITTING ON SUPPORT**: Trading right above the support floor of **{cur}{support:,.2f}**. This is a prime low-risk bounce setup. Wait for a green confirmation candle to trigger a buy."
                elif sr_zone == "Near Resistance":
                    rec = f"🎯 **TESTING RESISTANCE**: Currently testing the resistance ceiling of **{cur}{resistance:,.2f}**. Wait for either a clean breakout close above this line, or a reversal red candle to short."
                else:
                    rec = f"⚖️ **CONSOLIDATING**: Asset is trading in the middle of its channel (Support: {cur}{support:,.2f} | Resistance: {cur}{resistance:,.2f}). The risk-reward is currently neutral. Wait for the price to move closer to the boundaries."
            
            # Render asset card
            col_a, col_b = st.columns([1, 3])
            with col_a:
                st.markdown(f"### **{t}**")
                st.caption(f"Timeframe: {timeframe}")
                st.markdown(f"**Price**: {cur}{price:,.2f}")
                if decision == "BUY":
                    st.success(f"🟢 BUY ({r['confidence']}%)")
                elif decision == "SELL":
                    st.error(f"🔴 SELL ({r['confidence']}%)")
                else:
                    st.warning(f"🟡 WAIT ({r['confidence']}%)")
            with col_b:
                st.markdown(f"**Expert Insight**:")
                st.info(rec)
            st.divider()

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
    interval_label = st.selectbox(
        "Candle Interval",
        ["1 Minute (Scalping)", "5 Minutes (Intraday)", "15 Minutes (Short Swing)", "1 Hour (Swing)", "1 Day (Positional)"],
        index=1,
        key="analysis_interval_label",
    )
    
    interval_map = {
        "1 Minute (Scalping)": "1m",
        "5 Minutes (Intraday)": "5m",
        "15 Minutes (Short Swing)": "15m",
        "1 Hour (Swing)": "1h",
        "1 Day (Positional)": "1d"
    }
    final_interval = interval_map[interval_label]
    st.session_state["analysis_interval"] = final_interval

    # Show all lookback ranges at all times to keep UI consistent and powerful
    lookback_opts = ["1 Day", "5 Days", "1 Month", "3 Months", "6 Months", "1 Year", "2 Years", "Max"]
    # Match default selection "1 Month" if available (index 2)
    lookback_label = st.selectbox(
        "Lookback Range",
        lookback_opts,
        index=2,
        key="analysis_period_label",
    )

    period_map = {
        "1 Day": "1d",
        "5 Days": "5d",
        "1 Month": "1mo",
        "3 Months": "3mo",
        "6 Months": "6mo",
        "1 Year": "1y",
        "2 Years": "2y",
        "Max": "max"
    }
    raw_period = period_map[lookback_label]
    st.session_state["analysis_period"] = raw_period

    # Resolve yfinance API limits behind the scenes and display helper notes
    adjusted = False
    limit_reason = ""
    period = raw_period

    if final_interval == "1m" and raw_period not in ("1d", "5d"):
        period = "5d"
        adjusted = True
        limit_reason = "⚠️ yfinance limits 1-minute data to the last 7 days. Using **5 Days** lookback instead."
    elif final_interval in ("5m", "15m") and raw_period not in ("1d", "5d", "1mo"):
        period = "1mo"
        adjusted = True
        limit_reason = "⚠️ yfinance limits 5m/15m data to the last 60 days. Using **1 Month** lookback instead."
    elif final_interval == "1h" and raw_period in ("1y", "2y", "max"):
        if raw_period == "max":
            period = "2y"
            adjusted = True
            limit_reason = "⚠️ yfinance limits 1-hour data to the last 730 days. Using **2 Years** lookback instead."

    if adjusted:
        st.warning(limit_reason)

    st.divider()
    st.subheader("💰 Risk Management")
    capital      = st.number_input("Capital (₹)", min_value=1000.0, value=50_000.0, step=5_000.0)
    risk_percent = st.slider("Risk Per Trade (%)", 0.5, 5.0, 1.0, 0.25)
    max_risk_inr = capital * risk_percent / 100
    st.info(f"Max loss per trade: **₹{max_risk_inr:,.0f}**")

    st.divider()
    st.subheader("📈 Live Chart")
    chart_src = st.radio("Provider", ["TradingView", "Binance", "Yahoo"])
    tv_sym = get_tradingview_symbol(ticker)
    if chart_src == "TradingView":
        chart_url = f"https://www.tradingview.com/chart/?symbol={quote(tv_sym, safe='')}"
        st.caption(f"TradingView symbol: {tv_sym}")
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
        # Keep only the last 24h worth of candles for the daily snapshot metrics
        # NSE has 74 5-min candles, Crypto has 288 5-min candles.
        cpd = 74 if (ticker.endswith(".NS") or ticker.endswith(".BO")) else 288
        day_snap = snap.iloc[-min(len(snap), cpd):]
        cp  = day_snap.iloc[-1]["Close"]
        chg = cp - day_snap.iloc[0]["Close"]
        pct = chg / day_snap.iloc[0]["Close"] * 100
        cur = currency_label(ticker)
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Price",    f"{cur}{cp:,.4f}", f"{pct:+.2f}%")
        c2.metric("24h High", f"{cur}{day_snap['High'].max():,.4f}")
        c3.metric("24h Low",  f"{cur}{day_snap['Low'].min():,.4f}")
        c4.metric("Volume",   f"{day_snap['Volume'].sum()/1e6:.2f}M")
    else:
        st.warning("⚠️ Live price unavailable. Check connection before analysing.")
except Exception:
    st.warning("⚠️ Live price unavailable.")

# ── Action Buttons ────────────────────────────────────────────────────
st.divider()

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
    import concurrent.futures
    import pandas as pd

    st.subheader("🔄 Multi-Asset Scan")
    scan_results = []
    
    # Run the scans in parallel using ThreadPoolExecutor
    def scan_single_ticker(t):
        try:
            r = run_enhanced_analysis(
                ticker=t, period=period, interval=final_interval,
                capital=capital, risk_percent=risk_percent,
            )
            trade = r.get("trade") or {}
            timeframe = f"{r.get('period', scan_period)} @ {r.get('interval', scan_interval)}"
            return {
                "Ticker":     t,
                "Asset":      UNIVERSE[t][0],
                "Timeframe":  timeframe,
                "Signal":     r["decision"],
                "Conf %":     f"{r['confidence']}%",
                "Price":      f"{currency_label(t)}{r['current_price']:,.4f}",
                "RSI":        f"{r['rsi']:.1f}",
                "ADX":        f"{r['adx']:.1f}",
                "Zone":       r["sr_zone"],
                "R:R":        f"1:{trade.get('risk_reward_ratio','—')}" if trade else "—",
                "Target":     f"{currency_label(t)}{trade['target_price']:,.4f}" if trade else "—",
                "Stop":       f"{currency_label(t)}{trade['stop_loss']:,.4f}" if trade else "—",
            }
        except Exception as e:
            return {
                "Ticker": t, "Asset": UNIVERSE[t][0],
                "Timeframe": f"{scan_period} @ {scan_interval}",
                "Signal": "ERROR", "Conf %": "—", "Price": "—",
                "RSI": "—", "ADX": "—", "Zone": str(e)[:50],
                "R:R": "—", "Target": "—", "Stop": "—",
            }

    with st.spinner(f"Scanning {len(scan_tickers)} assets in parallel..."):
        with concurrent.futures.ThreadPoolExecutor(max_workers=min(len(scan_tickers), 10)) as executor:
            futures = [executor.submit(scan_single_ticker, t) for t in scan_tickers]
            for future in concurrent.futures.as_completed(futures):
                scan_results.append(future.result())

    # Sort results by Ticker to keep UI clean and deterministic
    scan_results.sort(key=lambda x: x["Ticker"])

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

    if decision == "MARKET_CLOSED":
        st.warning(f"⏸️ {result.get('market_status', {}).get('message', 'Market closed')}")
        st.info("No analysis was run, so this does not count as WAIT or a trade signal.")
        st.stop()

    actual_interval = result.get("interval", final_interval)
    actual_period = result.get("period", period)
    st.success(f"✅ Live data: **{data_source.upper()}** · {result['data_points']} candles · {lookback_label} @ {actual_interval}")
    if actual_interval != final_interval:
        st.warning(f"⚠️ **Fallback Active**: The system fell back from **{final_interval}** to **{actual_interval}** data because the requested intraday interval returned no valid rows (often due to zero index volume on yfinance).")
    st.caption(f"Timeframe used: {actual_period} @ {actual_interval}")
    
    if result['data_points'] < 30:
        st.warning(f"⚠️ Only {result['data_points']} candles available — indicators may be less reliable. For best accuracy, use a longer timeframe or try again during market hours.")
    elif result['data_points'] < 55:
        st.info(f"ℹ️ {result['data_points']} candles — sufficient for analysis but more data would improve accuracy.")

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

    # ── Interactive Chart ──────────────────────────────────────────
    st.divider()
    st.markdown("### 📊 Live Price Chart")
    with st.expander("💡 How to read this chart (Help Guide)", expanded=False):
        st.markdown("""
        * **Candlestick Bars (Green / Red)**:
          * **Green** = Bullish candle (the price closed higher than it opened).
          * **Red** = Bearish candle (the price closed lower than it opened).
          * The thin line 'wicks' at the top/bottom show the highest and lowest prices reached during that candle interval.
        * **Moving Averages (Lines overlaying the price)**:
          * **EMA 9 (Blue)**: Short-term momentum trend.
          * **EMA 35 (Yellow)**: Medium-term trend.
          * **EMA 50 (Purple)**: Major trend direction.
          * *When fast lines (Blue) cross above slow lines (Purple), it signals a bullish momentum shift.*
        * **Horizontal Dashed Lines**:
          * **Support (Dashed Green)**: Price floor where buyers historically step in to support the price.
          * **Resistance (Dashed Red)**: Price ceiling where sellers historically step in to reject the price.
        * **Trade Overlays (Dashed Target & Stop lines)**:
          * **TARGET (Green)**: The take-profit target price where you should lock in gains.
          * **STOP LOSS (Red)**: The risk cutoff price. If the price falls below this, exit the trade to protect capital.
          * **ENTRY ZONE (Shaded Area)**: The optimal price range recommended for entering the trade.
        """)
    try:
        import plotly.graph_objects as go
        from plotly.subplots import make_subplots

        chart_df = result.get("df")
        if chart_df is not None and not chart_df.empty:
            # Show last 120 candles for standard, or less if not available
            max_candles = 120
            plot_df = chart_df.iloc[-min(len(chart_df), max_candles):]

            # Subplots: Row 1 = Candlestick + EMAs (82%), Row 2 = Volume (18%)
            fig = make_subplots(
                rows=2, cols=1, 
                shared_xaxes=True, 
                vertical_spacing=0.03, 
                row_width=[0.18, 0.82]
            )

            # Candlestick chart
            fig.add_trace(
                go.Candlestick(
                    x=plot_df.index,
                    open=plot_df["Open"],
                    high=plot_df["High"],
                    low=plot_df["Low"],
                    close=plot_df["Close"],
                    name="OHLC",
                    increasing_line_color="#22c55e",
                    decreasing_line_color="#ef4444"
                ),
                row=1, col=1
            )

            # EMA Indicators
            if "ema9" in plot_df.columns:
                fig.add_trace(go.Scatter(x=plot_df.index, y=plot_df["ema9"], name="EMA 9", line=dict(color="#3b82f6", width=1.0)), row=1, col=1)
            if "ema35" in plot_df.columns:
                fig.add_trace(go.Scatter(x=plot_df.index, y=plot_df["ema35"], name="EMA 35", line=dict(color="#eab308", width=1.0)), row=1, col=1)
            if "ema50" in plot_df.columns:
                fig.add_trace(go.Scatter(x=plot_df.index, y=plot_df["ema50"], name="EMA 50", line=dict(color="#a855f7", width=1.5)), row=1, col=1)

            # Support & Resistance Lines
            latest_row = plot_df.iloc[-1]
            support_val = float(latest_row.get("support", 0))
            resistance_val = float(latest_row.get("resistance", 0))
            
            # Use currency label of ticker
            cur_sym = currency_label(ticker)
            
            if support_val > 0:
                fig.add_hline(y=support_val, line_dash="dash", line_color="#10b981", line_width=1, annotation_text=f"Support ({cur_sym}{support_val:,.2f})", annotation_position="bottom left", row=1, col=1)
            if resistance_val > 0:
                fig.add_hline(y=resistance_val, line_dash="dash", line_color="#f43f5e", line_width=1, annotation_text=f"Resistance ({cur_sym}{resistance_val:,.2f})", annotation_position="top left", row=1, col=1)

            # Fibonacci retracement overlay
            fib_specs = [
                ("fib_500", "#f59e0b"),
                ("fib_618", "#a855f7"),
            ]
            for fib_key, fib_color in fib_specs:
                fib_val = latest_row.get(fib_key)
                if fib_val is not None and fib_val == fib_val:
                    fib_label = "Fib 50.0%" if fib_key == "fib_500" else "Fib 61.8%"
                    fig.add_hline(
                        y=float(fib_val),
                        line_dash="dot",
                        line_color=fib_color,
                        line_width=1,
                        annotation_text=f"{fib_label} ({cur_sym}{float(fib_val):,.2f})",
                        annotation_position="top left",
                        row=1,
                        col=1,
                    )

            # Visual overlay of stop loss & target if BUY/SELL or WAIT triggered
            if trade:
                is_hypo = trade.get("is_hypothetical", False)
                entry_low = trade.get("entry_zone_low", 0)
                entry_high = trade.get("entry_zone_high", 0)
                stop_loss = trade.get("stop_loss", 0)
                target_price = trade.get("target_price", 0)
                fib_anchor = trade.get("fib_anchor")

                target_lbl = "Hypothetical TARGET" if is_hypo else "TARGET"
                stop_lbl = "Hypothetical STOP" if is_hypo else "STOP LOSS"
                entry_lbl = "HYPOTHETICAL ENTRY" if is_hypo else "ENTRY ZONE"
                line_col_target = "#cbd5e1" if is_hypo else "#10b981"
                line_col_stop = "#cbd5e1" if is_hypo else "#f43f5e"
                rect_color = "#cbd5e1" if is_hypo else "#3b82f6"
                
                # Target Line
                fig.add_hline(y=target_price, line_dash="dot", line_color=line_col_target, line_width=2, annotation_text=f"{target_lbl} ({cur_sym}{target_price:,.2f})", annotation_position="top right", row=1, col=1)
                # Stop Loss Line
                fig.add_hline(y=stop_loss, line_dash="dot", line_color=line_col_stop, line_width=2, annotation_text=f"{stop_lbl} ({cur_sym}{stop_loss:,.2f})", annotation_position="bottom right", row=1, col=1)
                # Entry Zone shading
                fig.add_hrect(y0=entry_low, y1=entry_high, fillcolor=rect_color, opacity=0.08, line_width=0, annotation_text=entry_lbl, annotation_position="left", row=1, col=1)
                if fib_anchor:
                    fig.add_hline(
                        y=float(fib_anchor),
                        line_dash="dashdot",
                        line_color="#f59e0b",
                        line_width=2,
                        annotation_text=f"Fib anchor ({cur_sym}{float(fib_anchor):,.2f})",
                        annotation_position="top right",
                        row=1,
                        col=1,
                    )

            # Volume bars chart
            v_colors = ["#22c55e" if close >= open else "#ef4444" for open, close in zip(plot_df["Open"], plot_df["Close"])]
            fig.add_trace(
                go.Bar(
                    x=plot_df.index,
                    y=plot_df["Volume"],
                    name="Volume",
                    marker_color=v_colors,
                    opacity=0.5,
                    showlegend=False
                ),
                row=2, col=1
            )

            # Dark theme layout matching Streamlit custom styling
            fig.update_layout(
                template="plotly_dark",
                xaxis_rangeslider_visible=False,
                height=480,
                margin=dict(l=10, r=10, t=10, b=10),
                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
                paper_bgcolor="#0e1117",
                plot_bgcolor="#1e1e2e"
            )
            
            fig.update_yaxes(title_text=f"Price ({cur_sym})", row=1, col=1)
            fig.update_yaxes(title_text="Volume", row=2, col=1)

            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No chart data available.")
    except Exception as e:
        st.warning(f"⚠️ Unable to render interactive chart: {e}")

    # ── Market Playbook ────────────────────────────────────────────
    st.divider()
    market_env = result.get("market_env")
    if market_env:
        st.markdown("### 🎓 Market Playbook & Suitability")
        st.markdown(f"**Current Regime:** {market_env['verdict']}")
        st.markdown(f"👉 **Trading Suitability:** {market_env['suitability']}")
        
        m_col1, m_col2 = st.columns(2)
        with m_col1:
            st.markdown("**🟢 Opportunities (Pros)**")
            if market_env["pros"]:
                for pro in market_env["pros"]: st.markdown(f"- {pro}")
            else:
                st.markdown("- No major trend advantages currently.")
        with m_col2:
            st.markdown("**🔴 Risks (Cons)**")
            if market_env["cons"]:
                for con in market_env["cons"]: st.markdown(f"- {con}")
            else:
                st.markdown("- Risk levels are normal.")
                
        st.caption(
            f"📅 **Best Days to Trade:** {market_env['best_days_to_trade']}  |  "
            f"⛔ **Avoid Hours:** {market_env['avoid_trading']}"
        )

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

    # ── WAIT Analysis ──────────────────────────────────────────────
    if decision == "WAIT" and wait_analysis:
        st.divider()
        st.markdown("### 🟡 WAIT — Why Not Trading Now")
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

    # ── TRADE PLAN / HYPOTHETICAL SIZING ───────────────────────────
    if trade:
        is_hypo = trade.get("is_hypothetical", False)
        st.divider()
        if is_hypo:
            st.markdown("## 📊 Hypothetical Trade Setup")
            st.warning(
                "⚠️ **Hypothetical Sizing Notice**: The current Council Decision is **WAIT**. "
                "The levels and risk metrics below are calculated using active indicators and S/R levels. "
                "If you decide to force-enter or override the wait signal, use these risk boundaries to protect your capital."
            )
        else:
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

        # ── TradingView Order Ticket ─────────────────────────────
        st.divider()
        from trade_levels import get_tif_for_asset, validate_trade_setup

        tif_info   = get_tif_for_asset(ticker, actual_interval)
        tv_sym     = get_tradingview_symbol(ticker)
        entry_mid  = round((trade["entry_zone_low"] + trade["entry_zone_high"]) / 2, 4)
        qty        = trade["position_size"]
        sl         = trade["stop_loss"]
        tp         = trade["target_price"]
        order_side = "BUY" if trade["decision"] == "BUY" else "SELL"

        # Validation
        is_valid, val_errors = validate_trade_setup(trade["decision"], conf, trade)

        # Chart URL  (opens TradingView chart for the symbol)
        chart_open_url = f"https://www.tradingview.com/chart/?symbol={quote(tv_sym, safe='')}"

        if is_hypo:
            st.markdown("### 📊 TradingView Order Ticket *(Hypothetical Override)*")
            st.warning(
                "⚠️ Council says **WAIT**. You are overriding the signal. "
                "Treat position size as guidance only — reduce size if uncertain."
            )
        else:
            st.markdown("### 📊 TradingView Order Ticket")

        # Validation banner
        if not is_valid:
            for err in val_errors:
                if "overriding" in err.lower() or "hypothetical" in err.lower() or "marginal" in err.lower():
                    st.warning(f"⚠️ {err}")
                else:
                    st.error(f"❌ {err}")
        elif val_errors:
            # warnings only (low-confidence, marginal R:R)
            for err in val_errors:
                st.warning(f"⚠️ {err}")

        # TIF / expiry callout
        st.info(
            f"**⏱️ TIF: {tif_info['tif']}  ·  Order type: {tif_info['order_type']}**  "
            f"  |  {tif_info['expiry_note']}  \n"
            f"_{tif_info['tif_note']}_"
        )

        # Main ticket card (copy-friendly)
        import datetime as _dt
        card_tag  = "HYPOTHETICAL OVERRIDE" if is_hypo else "TRADE SETUP"
        generated = _dt.datetime.now().strftime("%Y-%m-%d %H:%M")

        st.code(f"""
╔══════════════════════════════════════════════════════════╗
   📋  {card_tag}  —  {asset_name}
   TradingView Symbol : {tv_sym}
   Generated          : {generated}
╠══════════════════════════════════════════════════════════╣

  ── ORDER ────────────────────────────────────────────────
  Side          :  {order_side}
  Order Type    :  {tif_info['order_type']}  (Limit)
  TIF           :  {tif_info['tif']}          ← set in order panel
  Expiry note   :  {tif_info['expiry_note']}

  ── FILL THIS IN TRADINGVIEW ─────────────────────────────
  Symbol        :  {tv_sym}
  Qty / Units   :  {qty:.6f}
  Limit Price   :  {cur}{entry_mid:,.4f}    ← entry zone midpoint
  Stop Loss     :  {cur}{sl:,.4f}    ← set as bracket SL
  Take Profit   :  {cur}{tp:,.4f}    ← set as bracket TP

  ── CONTEXT ──────────────────────────────────────────────
  Entry Zone    :  {cur}{trade['entry_zone_low']:,.4f}  →  {cur}{trade['entry_zone_high']:,.4f}
  Current Price :  {cur}{trade['current_price']:,.4f}
  ATR           :  {cur}{atr_used:.4f}
  Timing        :  {trade['timing']}

  ── YOUR RISK ────────────────────────────────────────────
  Capital       :  ₹{trade['capital_inr']:,.0f}
  Max Risk      :  ₹{trade['max_risk_inr']:,.0f}  ({trade['risk_percent']}% of capital)
  Entry Cost    :  ₹{trade['entry_cost_inr']:,.0f}
  Expected Gain :  ₹{trade['expected_profit_inr']:,.0f}  (+{trade['profit_pct']:.2f}%)
  Max Loss      :  ₹{trade['max_loss_inr']:,.0f}  (-{trade['loss_pct']:.2f}%)
  R:R           :  1 : {rr:.2f}   {verdict}

  Confidence    :  {conf}%
  Data Source   :  {data_source.upper()}
╚══════════════════════════════════════════════════════════╝
""", language="text")

        # Single action button
        st.caption(
            "👆 Copy the ticket above, then click the button to open your TradingView chart "
            "and paste the values into the order panel manually."
        )
        st.link_button(
            f"📊 Open {asset_name} Chart in TradingView",
            chart_open_url,
            use_container_width=True,
        )

    # ── Historical Memory ──────────────────────────────────────────
    past_signals = result.get("past_signals", [])
    ticker_stats = result.get("ticker_stats")

    if ticker_stats or past_signals:
        st.divider()
        st.subheader("📚 Your Track Record")

        if ticker_stats:
            ts1, ts2, ts3, ts4, ts5, ts6, ts7, ts8, ts9 = st.columns(9)
            ts1.metric("Total Signals", ticker_stats["total"])
            ts2.metric("✅ Wins",        ticker_stats["wins"])
            ts3.metric("❌ Losses",      ticker_stats["losses"])
            ts4.metric("⏰ Expired",     ticker_stats.get("expired", 0))
            ts5.metric("Win Rate",       f"{ticker_stats['win_rate']}%",
                       delta_color="normal" if ticker_stats["win_rate"] >= 50 else "inverse")
            ts6.metric("Avg Win",        f"+{ticker_stats['avg_win']}%")
            ts7.metric("Avg Loss",       f"{ticker_stats['avg_loss']}%")
            ts8.metric("Fill Rate",      f"{ticker_stats.get('fill_rate', 0)}%")
            ts9.metric("Unfilled",       ticker_stats.get("unfilled", 0))

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
    
    from llm import get_last_error
    last_err = get_last_error()
    
    def render_agent_output(val):
        if "all LLMs unavailable" in str(val):
            st.error("❌ LLM Call Failed: All models unavailable.")
            st.info(f"🔍 **Last Captured API Error:**\n`{last_err}`")
        else:
            st.write(val)

    with st.expander("📉 Technical Agent",             expanded=False): render_agent_output(result["technical"])
    with st.expander("⚡ Momentum Agent",              expanded=False): render_agent_output(result["momentum"])
    with st.expander("📰 News Agent",                  expanded=False):
        if result.get("headlines"):
            st.markdown("**Headlines used:**")
            for h in result["headlines"]: st.markdown(f"- {h}")
            st.divider()
        render_agent_output(result["news"])
    with st.expander("🛡️ Risk Agent",                  expanded=False): render_agent_output(result["risk"])
    with st.expander("🗂️ Decision Memory (last 10)",   expanded=False): st.json(result["memory"])
