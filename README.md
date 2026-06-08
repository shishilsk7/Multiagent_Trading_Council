# Multi-Agent Trading Council

A Streamlit-based trading analysis platform that combines market data, technical indicators, news sentiment, risk checks, and LLM agent outputs into a single BUY / SELL / WAIT decision with trade planning and historical outcome tracking.

## What this project does

- Fetches market candles for crypto, US assets, Indian assets, and commodity symbols.
- Computes technical indicators (EMA, MACD, RSI, ADX, Stochastic, Bollinger Bands, ATR, support/resistance, volume signals).
- Runs four LLM-based specialist agents:
  - Technical agent
  - Momentum agent
  - News sentiment agent
  - Risk agent
- Applies deterministic voting logic to produce a final decision.
- Produces trade levels and position sizing for non-WAIT decisions.
- Explains WAIT scenarios with concrete risk factors and re-check guidance.
- Stores short-term decision memory and long-term outcome memory for learning context.

## Repository structure (file-by-file)

### Core app and orchestration

- `app.py`
  - Main Streamlit UI.
  - Sidebar controls: asset, timeframe, interval, capital, risk %, chart link, optional multi-asset scan.
  - Live snapshot metrics from `data.fetch_ticker_timeframe`.
  - Runs `core.run_enhanced_analysis` for single asset and scan workflows.
  - Renders decision cards, vote breakdown, trade plan, WAIT explanation, historical memory, and raw agent outputs.

- `core.py`
  - Main orchestrator.
  - `run_enhanced_analysis(...)` pipeline:
    1. Fetch candles
    2. Add indicators
    3. Update outcomes for unresolved historical signals
    4. Build context (patterns, S/R zone, volume, trend, headlines, memory summary)
    5. Query all four LLM agents
    6. Decide via weighted voting
    7. Score confidence
    8. Build trade levels or WAIT analysis
    9. Store new decision and signal memory
    10. Return rich result dict for UI
  - `analyze_wait_scenario(...)` provides detailed “why wait” analysis.
  - `run()` legacy wrapper for backward compatibility.

### Agent prompts and model calls

- `agents.py`
  - Prompt builders for:
    - `technical_agent(...)`
    - `momentum_agent(...)`
    - `news_agent(...)`
    - `risk_agent(...)`
  - Prompts force strict structured output formats.

- `llm.py`
  - Loads environment variables.
  - Defines role-specific model fallback lists using OpenRouter.
  - `ask_llm(role, prompt)` with automatic fallback and timeout handling.
  - Returns WAIT fallback message when API/model is unavailable.

### Data and indicators

- `data.py`
  - `fetch_ticker_timeframe(...)` with source fallback chain:
    1. Yahoo Finance (`yfinance`)
    2. Binance (mapped crypto tickers only)
    3. Generated mock data
  - Tags returned DataFrame with `attrs["source"]` and `attrs["ticker"]`.
  - Includes BTC-compatible wrapper helpers.

- `indicators.py`
  - `add_indicators(df)` computes all indicator columns and drops NaNs.
  - `interpret_patterns(latest)` builds human-readable technical pattern notes.
  - `sr_zone(latest)`, `volume_state(latest)`, `trend_strength(latest)` classify market state.

### Decision, confidence, and trade plan logic

- `decision.py`
  - `_parse_signal(text)` robustly parses LLM text into BUY/SELL/WAIT.
  - `decide(tech, mom, risk, latest=None)` weighted voting system:
    - Technical: weight 3
    - Momentum: weight 2
    - Indicators: up to weight 2
    - Hard risk veto when both “RISK: HIGH” and “AVOID” are present.

- `confidence.py`
  - `confidence(...)` returns bounded confidence score (10–95).
  - Combines agent alignment + risk text + optional raw indicator context.

- `trade_levels.py`
  - Gets USD/INR rate (API with fallback).
  - Builds entry zone, stop, and target by decision/SR context.
  - Computes position size based on risk %.
  - Returns INR-focused expected outcome metrics and risk/reward ratio.

### Universe and news context

- `stocks.py`
  - Asset universe across crypto, commodities, US equities, India equities/indices.
  - Category metadata and ticker labeling helpers.
  - Query builder for news search text.
  - INR/USD display utility helpers for Indian assets.

- `news.py`
  - Pulls Google News RSS by query.
  - Filters to fresh entries (`max_age_hours`) and returns timestamped headlines.

### Memory and learning persistence

- `memory.py`
  - Saves latest 10 short-term decisions in `decision_memory.json`.
  - Exposes `load`, `save`, `add`, `summarize`.

- `outcome_memory.py`
  - Persists BUY/SELL signals in `outcome_memory.json`.
  - Marks outcomes when stop or target gets hit on later runs.
  - Finds similar historical setups and computes ticker-level stats (win rate, avg win/loss).

### Other files

- `requirements.txt`
  - Runtime dependencies (`streamlit`, `pandas`, `numpy`, `yfinance`, `ta`, `feedparser`, `openai`, `python-dotenv`, `requests`).

- `.gitignore`
  - Ignores Python artifacts, env folders, secret files, and generated memory/backup files.

- `ENHANCEMENT_SUMMARY.md`
  - Historical enhancement notes; useful context, but not the source of truth over code.

## End-to-end execution flow

1. UI receives ticker/timeframe/risk inputs.
2. Candle data is fetched and normalized.
3. Indicators are calculated.
4. News headlines are fetched for asset context.
5. Agent prompts are constructed and sent to LLMs.
6. Final decision is computed with weighted + indicator-based voting.
7. Confidence is scored.
8. If decision is BUY/SELL:
   - Trade levels + sizing are generated
   - New signal is stored in outcome memory
9. If decision is WAIT:
   - WAIT reasoning block is generated
10. Similar past signals and track record stats are attached for display.
11. UI renders full analysis and stores short-term decision memory.

## Setup and run

1. Create and activate Python virtual environment.
2. Install dependencies:
   - `pip install -r requirements.txt`
3. Create env file:
   - `.env`
   - Add `OPENROUTER_API_KEY=<your_key>`
4. Start app:
   - `streamlit run app.py`

## Data + fallback behavior

- Price data fallback: yfinance → Binance (selected crypto tickers) → mock data.
- LLM fallback: role-specific model list; returns WAIT-like fallback text if unavailable.
- FX fallback: exchangerate API → fixed 84.0.
- News fallback: returns empty list if feed parse fails.

## Persistence files generated at runtime

- `decision_memory.json` (short-term last decisions)
- `outcome_memory.json` (signal outcomes and performance history)

These files are local state and are intended to grow with usage.
