import os
import sys
import time
import json
import logging
import structlog
import threading
import urllib.parse
from datetime import datetime
from typing import List, Dict, Optional
import requests
from bs4 import BeautifulSoup
import schedule
from google import genai
from google.genai import types
from pydantic import BaseModel

# -------------------------------------------------------------------------
# CONFIG & LOGGING
# -------------------------------------------------------------------------
# [ROADMAP-4.7 2026-07-13] structlog, matching python-engine's pipeline.
#
# The agent was the last container still on a bare logging.basicConfig, so its
# lines rendered differently from every other service and could not carry
# structured key/values. The pipeline below is a deliberate mirror of
# python-engine/logging_setup.py -- same TimeStamper format, same
# ConsoleRenderer, colours off (the docker json-file driver strips ANSI anyway).
#
# It is DUPLICATED rather than imported, and that is not laziness: the agent is
# a separate docker build context and cannot see ../python-engine. Sharing it
# would mean restructuring the build for a 20-line config. (Roadmap 4.2 is the
# cautionary tale in the other direction -- do not invent shared structure that
# does not fit.)
#
# The rendered shape is preserved on purpose: timestamp, level, message, in that
# order. The 2026-07-13 forensics were done by eye against these logs, and a
# format churn that broke `docker logs agent | grep` would cost more than it
# gained. Existing logger.info(f"...") call sites keep working unchanged --
# structlog takes the message as the event.
#
# stdlib logging is wired to the same formatter so `schedule`, `requests` and
# `urllib3` do not punch through with a different shape.
_timestamper = structlog.processors.TimeStamper(
    fmt="%Y-%m-%d %H:%M:%S",
    utc=False,  # local time = IST in this container (TZ=Asia/Kolkata)
)

structlog.configure(
    processors=[
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        _timestamper,
        structlog.processors.format_exc_info,
        structlog.dev.ConsoleRenderer(colors=False, event_key="event"),
    ],
    wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
    logger_factory=structlog.PrintLoggerFactory(file=sys.stdout),
    cache_logger_on_first_use=True,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)

logger = structlog.get_logger("agent")

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
QUANT_ENGINE_URL = os.getenv("QUANT_ENGINE_URL", "http://python-engine:8000/signals")

# [HIGH-007 / ROADMAP-4.5 2026-07-13] Snapshot registration.
#
# This container is the ONLY thing that decides what numbers the operator
# sees on an EXEC/EM button. Until now it sent the button and threw the
# payload away -- so node-gateway, on the press, had to go and re-ask the
# engine what the signal was, and executed whatever came back. That is not
# the same object: /signals serves `current_signals`, which run_screener
# replaces wholesale on every run, and the momentum list is in-memory and
# dies with the engine process (as it did on 2026-07-13 at 09:44).
#
# So register the exact payload here, under the SAME id that goes into
# callback_data, before the button is shown. What the operator approves is
# then what executes.
NODE_GATEWAY_URL = os.getenv("NODE_GATEWAY_URL", "http://node-gateway:3000")
INTERNAL_API_SECRET = os.getenv("INTERNAL_API_SECRET", "")


def register_approved_snapshot(sig_id: str, ticker: str, action: str, payload: dict) -> bool:
    """Persist the payload we are about to display, keyed by its callback id.

    Best-effort BY DESIGN, and the asymmetry is deliberate: if registration
    fails we still send the alert, because node falls back to the old live
    re-fetch and a slightly-stale trade beats no trade at all. But it logs
    loudly, and node logs `approved_snapshot_missing` on the press, so the
    fallback can never be mistaken for the happy path.
    """
    try:
        resp = requests.post(
            f"{NODE_GATEWAY_URL}/api/internal/register-signal",
            json={
                "signal_id": sig_id,
                "ticker": ticker,
                "action": action,
                "payload": payload,
            },
            headers={"X-Internal-Secret": INTERNAL_API_SECRET},
            timeout=5,
        )
        resp.raise_for_status()
        body = resp.json()
        if not body.get("registered"):
            # Already present -- the snapshot is immutable and first-wins, so
            # this is correct behaviour on a re-alert, not an error.
            logger.info(f"Snapshot already registered for {sig_id} (first-wins)")
        else:
            logger.info(f"Registered approved snapshot for {sig_id}")
        return True
    except Exception as e:
        logger.error(
            f"Snapshot registration FAILED for {sig_id}: {e} -- "
            f"alert will still be sent; node will fall back to a live re-fetch "
            f"and the executed numbers may differ from those displayed."
        )
        return False

if not all([GEMINI_API_KEY, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID]):
    logger.critical("CRITICAL: Missing required environment variables. Exiting.")
    sys.exit(1)

client = genai.Client(api_key=GEMINI_API_KEY)

# -------------------------------------------------------------------------
# SHORT-TERM MEMORY (DEDUPLICATION)
# -------------------------------------------------------------------------
# [ROADMAP-4.7 2026-07-13] Dedup state is now DURABLE.
#
# It used to be a bare in-memory set, so any agent bounce forgot everything it
# had already alerted and re-sent EXEC buttons for signals the operator had
# already seen -- and, worse, may have already acted on. Duplicate buttons for
# a live trade are not a cosmetic annoyance.
#
# Persisted to /tmp, not /data: the agent mounts /data READ-ONLY (it only reads
# scheduler_tick.json for the freeze watchdog), and its heartbeat already lives
# in /tmp for the same reason. /tmp survives a process crash and a `docker
# restart` -- which is the bounce that actually happens -- and is lost only on
# a full container recreate, where re-alerting is the lesser evil anyway.
#
# Day-stamped: a file from a previous day must never suppress today's alerts.
DEDUP_FILE = "/tmp/agent_dedup.json"

processed_signals_today = set()


def _today_str() -> str:
    # Container runs TZ=Asia/Kolkata, so this is already the IST trading day.
    return datetime.now().strftime("%Y-%m-%d")


def _load_dedup_state() -> None:
    """Restore today's alerted ids on boot. Never raises: a corrupt or absent
    file must degrade to 'remember nothing' (re-alert), never to a crash."""
    try:
        with open(DEDUP_FILE) as fh:
            state = json.load(fh)
        if state.get("date") != _today_str():
            logger.info("Dedup file is from a previous day -- starting fresh.")
            return
        processed_signals_today.update(state.get("ids", []))
        logger.info(
            f"Restored {len(processed_signals_today)} already-alerted signal(s) "
            f"from {DEDUP_FILE} -- a restart will not re-alert them."
        )
    except FileNotFoundError:
        pass
    except Exception as e:
        logger.error(f"Could not read dedup state ({e}) -- starting fresh.")


def _save_dedup_state() -> None:
    """Atomic write: a torn file read on the next boot would silently drop the
    dedup memory, which is the exact failure this whole mechanism exists to
    prevent."""
    try:
        tmp = f"{DEDUP_FILE}.tmp"
        with open(tmp, "w") as fh:
            json.dump(
                {"date": _today_str(), "ids": sorted(processed_signals_today)}, fh
            )
        os.replace(tmp, DEDUP_FILE)
    except Exception as e:
        logger.error(f"Could not persist dedup state: {e}")


def mark_processed(sig_id: str) -> None:
    """Record an alerted signal, durably."""
    processed_signals_today.add(sig_id)
    _save_dedup_state()


def clear_memory():
    processed_signals_today.clear()
    _save_dedup_state()
    logger.info("Cleared daily signal memory for the new trading day.")

# -------------------------------------------------------------------------
# LIVENESS: OWN HEARTBEAT (roadmap 2.2) + ENGINE FREEZE WATCHDOG (2.4)
# -------------------------------------------------------------------------
# [ROADMAP-2.2 2026-07-12] This container had no healthcheck at all: if
# it died or hung, momentum EXEC alerts stopped with zero alarm. The
# Dockerfile HEALTHCHECK compares this file's mtime against a 15-min
# threshold; autoheal (docker-compose) restarts the container when it
# turns unhealthy. Touched from the main loop (every 30s) AND at the top
# of each per-signal iteration, so a long Gemini batch can't trip a
# false unhealthy while real work is progressing.
HEARTBEAT_FILE = "/tmp/agent_heartbeat"

def touch_heartbeat():
    """Must never raise -- liveness reporting can't break the pipeline."""
    try:
        with open(HEARTBEAT_FILE, "w") as fh:
            fh.write(str(time.time()))
    except Exception as e:
        logger.error(f"Heartbeat touch failed: {e}")

# [ROADMAP-2.4 2026-07-12] External loop-progress watchdog for the
# engine. python-engine's APScheduler writes /data/scheduler_tick.json
# every 60s FROM THE SCHEDULER LOOP ITSELF (its daemon-thread liveness
# heartbeat deliberately keeps ticking through a frozen loop, so it
# cannot detect this). We are a separate process in a separate
# container: if that file goes stale during market hours, jobs have
# stopped firing -- the 2026-07-07 pattern that ran 6h32m unnoticed.
# Alert goes straight to the Telegram API (not via node's /notify) so
# it works no matter what state the other containers are in.
SCHEDULER_TICK_FILE = "/data/scheduler_tick.json"
ENGINE_FREEZE_THRESHOLD_SEC = 600         # 10 min = ten missed 60s ticks
ENGINE_FREEZE_ALERT_COOLDOWN_SEC = 1800   # re-page at most every 30 min
_engine_freeze_last_alert_ts: Optional[float] = None

def _is_market_hours(now=None) -> bool:
    """Mon-Fri 09:15-15:30. Container TZ is Asia/Kolkata, so naive
    datetime.now() is IST. No holiday check needed: the engine's tick
    job runs 24/7, so on a holiday the file is fresh anyway."""
    from datetime import datetime
    now = now or datetime.now()
    if now.weekday() >= 5:
        return False
    minutes = now.hour * 60 + now.minute
    return 9 * 60 + 15 <= minutes <= 15 * 60 + 30

def read_scheduler_tick_age(path=None) -> Optional[float]:
    """Seconds since the engine's last scheduler tick, or None when the
    file is missing/unreadable (engine down, pre-2.4 build, or /data
    not mounted)."""
    path = path or SCHEDULER_TICK_FILE
    try:
        with open(path) as fh:
            payload = json.load(fh)
        return max(0.0, time.time() - float(payload["ts_epoch"]))
    except Exception:
        return None

def check_engine_liveness():
    """Scheduled every 5 min; alerts (cooldown 30 min) when the engine's
    scheduler tick is stale or missing during market hours."""
    global _engine_freeze_last_alert_ts
    if not _is_market_hours():
        return
    age = read_scheduler_tick_age()
    if age is not None and age < ENGINE_FREEZE_THRESHOLD_SEC:
        return

    now = time.time()
    if (_engine_freeze_last_alert_ts is not None
            and now - _engine_freeze_last_alert_ts < ENGINE_FREEZE_ALERT_COOLDOWN_SEC):
        return
    _engine_freeze_last_alert_ts = now

    if age is None:
        msg = ("🧊 ENGINE WATCHDOG: cannot read the scheduler tick file "
               f"({SCHEDULER_TICK_FILE}). python-engine may be DOWN, or /data "
               "is not mounted. Check: docker ps && docker logs python-engine")
    else:
        msg = ("🧊 ENGINE LOOP FROZEN? python-engine's scheduler tick is "
               f"{int(age // 60)} min old (threshold {ENGINE_FREEZE_THRESHOLD_SEC // 60} min). "
               "Jobs have stopped firing -- the 2026-07-07 freeze pattern. "
               "Check: docker logs python-engine --since 15m | grep penny_liveness_tick "
               "(ticks present = loop frozen, restart the container; "
               "ticks absent = process dead).")
    logger.error(f"Engine liveness watchdog firing: age={age}")

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    try:
        requests.post(url, json={"chat_id": TELEGRAM_CHAT_ID, "text": msg}, timeout=10)
    except Exception as e:
        logger.error(f"Failed to send engine watchdog alert: {e}")

# -------------------------------------------------------------------------
# SCHEMAS
# -------------------------------------------------------------------------
class SignalOutput(BaseModel):
    conviction_score: int
    pitch: str
    rationale: str
    risks: str

# -------------------------------------------------------------------------
# CORE FUNCTIONS
# -------------------------------------------------------------------------
def fetch_signals() -> List[Dict]:
    """Fetch raw quant signals from Container B."""
    try:
        # [ROADMAP-4.7 2026-07-13] Send the internal secret. /signals is not
        # gated on the engine side today, so this changes nothing yet -- which
        # is exactly why it should go in NOW rather than being discovered as a
        # 403 on the morning someone gates it. The sibling momentum poll below
        # already sends it; this was the odd one out.
        response = requests.get(
            QUANT_ENGINE_URL,
            headers={"X-Internal-Secret": INTERNAL_API_SECRET},
            timeout=10,
        )
        response.raise_for_status()
        data = response.json()
        
        # CRITICAL FIX: Unwrap the PortfolioResponse envelope
        signals = data.get("signals", [])
        
        if not isinstance(signals, list):
            logger.error("Invalid response format from Quant Engine.")
            return []
        return signals
    except requests.exceptions.RequestException as e:
        logger.error(f"Failed to fetch signals from {QUANT_ENGINE_URL}: {e}")
        return []

def fetch_rss_feed(url: str, limit: int = 3) -> str:
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
    try:
        res = requests.get(url, headers=headers, timeout=5)
        res.raise_for_status()
        soup = BeautifulSoup(res.content, 'xml')
        items = soup.find_all('item', limit=limit)
        texts = [f"- {item.title.text if item.title else ''}" for item in items]
        return " | ".join(texts)
    except Exception as e:
        logger.warning(f"RSS fetch failed for {url}: {e}")
        return ""

def scrape_sentiment(ticker: str) -> str:
    logger.info(f"Gathering multi-source intelligence for {ticker}...")
    yahoo_url = f"https://feeds.finance.yahoo.com/rss/2.0/headline?s={ticker}&region=US&lang=en-US"
    yahoo_news = fetch_rss_feed(yahoo_url, limit=4)
    
    encoded_ticker = urllib.parse.quote(f"{ticker} stock")
    google_url = f"https://news.google.com/rss/search?q={encoded_ticker}&hl=en-US&gl=US&ceid=US:en"
    google_news = fetch_rss_feed(google_url, limit=4)
    
    if not yahoo_news and not google_news:
        return ""
    return f"YAHOO FINANCE FEED:\n{yahoo_news}\n\nBROADER MARKET FEED:\n{google_news}"

def analyze_with_gemini(
    signal: Dict,
    sentiment_text: str,
    market_regime: str = "UNKNOWN"
) -> Optional[Dict]:
    ticker = signal.get("ticker", "UNKNOWN")
    price = signal.get("close", 0)     # FIX: Aligned with models.py
    target = signal.get("target_1", 0) # FIX: Aligned with models.py
    stop_loss = signal.get("stop_loss", 0)

    prompt = f"""
    You are a cynical, risk-first quantitative trading analyst.
    Your job is NOT to find reasons to approve trades.
    Your job is to find reasons to REJECT them.
    Only approve a trade if the evidence is overwhelmingly clean.

    ===========================================
    TRADE CONTEXT
    ===========================================
    Strategy Type : {signal.get('strategy_type', 'SWING')}
    Market Regime : {market_regime}
    Ticker        : {ticker}
    Entry Price   : Rs{price}
    Stop Loss     : Rs{stop_loss}
    Target        : Rs{target}
    Net EV        : Rs{signal.get('net_ev', 'N/A')}
    Score         : {signal.get('score', 'N/A')}/100
    Volume Ratio  : {signal.get('volume_ratio', 'N/A')}x
    RSI           : {signal.get('rsi_14', 'N/A')}
    RS Score      : {signal.get('rs_score', 'N/A')} (vs Nifty, 20-day)

    ===========================================
    REGIME-SPECIFIC INSTRUCTIONS
    ===========================================

    IF regime is "BEAR_RS_ONLY":
    Be EXTREMELY cynical. The broad market is falling.
    This stock is only being evaluated because its math shows
    outperformance vs the Nifty. Your primary job here is to
    determine WHY it is outperforming:
    - Quiet institutional accumulation (VALID) -> keep conviction high
    - Unverified rumour, single contract win, retail social media hype -> 
        REDUCE conviction_score below 50 immediately
    - Short-covering rally in a falling stock -> REDUCE below 40
    - If you cannot determine a credible structural reason from the
        sentiment data: REDUCE below 55

    IF strategy is "MOMENTUM" (intraday):
    Evaluate whether the news/catalyst justifies a 3-hour sustained
    move, not just a 15-minute spike.
    - Genuine earnings beat, sector tailwind -> conviction can be high
    - Single news headline with no follow-through evidence -> max 65
    - No news at all (pure technical breakout) -> max 70
    - Negative news despite price rising -> REDUCE below 45

    IF regime is "CAUTION":
    Apply the same cynicism as BEAR_RS_ONLY but one level less severe.
    Reduce all scores by 10 points before outputting.

    IF regime is "BULL" and strategy is "SWING":
    Standard evaluation. Do not manufacture cynicism.
    Follow the contradiction check rules below.

    ===========================================
    UNIVERSAL EVALUATION RULES
    ===========================================

    1. CONTRADICTION CHECK:
    If sentiment reveals critical legal, regulatory, fraud,
    accounting irregularity, or catastrophic operational news
    that contradicts a long position: REDUCE below 35.

    2. NO HALLUCINATION:
    Base rationale ONLY on the text provided.
    Do not invent news. Do not cite sources not in the data.
    If no sentiment data: say so explicitly in rationale.

    3. DO NOT over-react to routine market news.
    Quarterly results in line with estimates = neutral.
    Standard analyst upgrades/downgrades = minor adjustment only.

    4. SCORING SCALE:
    80-100 : Clean setup, sentiment confirms technicals
    60-79  : Acceptable, standard market risks present
    50-59  : Marginal, one significant concern exists
    0-49   : High risk of false positive, do not execute

    ===========================================
    MULTI-SOURCE SENTIMENT DATA
    ===========================================
    {sentiment_text if sentiment_text else
    "NO SENTIMENT DATA AVAILABLE. Evaluate on technicals only. "
    "Apply caution: absence of news for an active signal is unusual. "
    "Cap conviction at 70 unless regime is BULL."}

    Respond in strict JSON matching the required schema.
    No markdown. No explanation outside the JSON fields.
    """
    # [LOW-004] Enforce a 30-second timeout on the Gemini API call to prevent
    # blocking the entire synchronous pipeline if the API hangs.
    result_holder: Dict = {}

    def _call_gemini():
        try:
            # [AUDIT-FIX-GEMINI 2026-06-26] gemini-2.0-flash was retired by
            # Google and now returns 404 NOT_FOUND ("This model
            # models/gemini-2.0-flash is no longer available"). Every
            # momentum intelligence call fails today; the Telegram send
            # still goes out with the bare ticker (different outbound path)
            # but the operator never sees the Gemini enrichment. Move to
            # gemini-2.5-flash (matches the backup agent's model).
            resp = client.models.generate_content(
                model='gemini-2.5-flash',
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=SignalOutput,
                    temperature=0.0
                ),
            )
            result_holder['response'] = resp
        except Exception as exc:
            result_holder['error'] = exc

    gemini_thread = threading.Thread(target=_call_gemini, daemon=True)
    gemini_thread.start()
    gemini_thread.join(timeout=30)

    if gemini_thread.is_alive():
        logger.error(f"Gemini timeout (30s) for {ticker} - analysis skipped")
        return None
    if 'error' in result_holder:
        logger.error(f"Gemini Analysis failed for {ticker}: {result_holder['error']}")
        return None

    response = result_holder['response']
    if response.parsed:
        return response.parsed.model_dump()

    # [ROADMAP-4.7 2026-07-13] Was a bare `json.loads(response.text)`.
    #
    # This is the ONE place in the system where a third party's free-text
    # output is parsed with no guard. Gemini is a language model: it can
    # return prose, a fenced ```json block, or a truncated object, and any of
    # those raise here. The exception propagated out of the conviction gate
    # and killed the whole poll -- so a single malformed Gemini reply could
    # take out every EXEC alert in the batch. (That is the same failure shape
    # as the 2026-07-10 HUDCO stall, fixed on the loop side; this is the hole
    # it came through.)
    #
    # Return None instead: the callers already treat a None analysis as
    # "AI failed, manual review required" and STILL send the alert with a
    # SYSTEM FALLBACK banner. Losing the AI opinion must never lose the trade.
    try:
        return json.loads(response.text)
    except (json.JSONDecodeError, TypeError, AttributeError) as e:
        preview = (getattr(response, "text", "") or "")[:200]
        logger.error(
            f"Gemini returned unparseable output for {ticker}: {e} -- "
            f"proceeding without analysis. First 200 chars: {preview!r}"
        )
        return None

def send_telegram_alert(signal: Dict, analysis: Dict):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    
    ticker = signal.get("ticker", "UNKNOWN")
    price = signal.get("close")     # FIX: Aligned with models.py
    target = signal.get("target_1") # FIX: Aligned with models.py
    sl = signal.get("stop_loss")
    sig_id = ticker                 # FIX: Deduplication ID is now the ticker
    
    if not analysis:
        text = f"🚨 **SYSTEM FALLBACK: {ticker}** 🚨\nPrice: {price} | TGT: {target} | SL: {sl}\n⚠️ AI Sentiment analysis failed. Manual review required."
    else:
        text = f"📊 **TRADE ALERT: {ticker}**\n\n**Metrics:** Price: {price} | TGT: {target} | SL: {sl}\n**Conviction Score:** {analysis.get('conviction_score', 'N/A')}/100\n\n**Pitch:**\n{analysis.get('pitch', 'N/A')}\n\n**Rationale:**\n{analysis.get('rationale', 'N/A')}\n\n**Risks:**\n{analysis.get('risks', 'N/A')}"

    # [CRIT-001/002] Unified callback format: ACTION:signal_id:unix_ts
    # Keeps payload well under Telegram's 64-byte callback_data limit.
    # Action EXEC matches the handler in node-gateway/server/index.js.
    safe_sig_id = str(sig_id)[:40]
    ts = int(time.time())

    # [HIGH-007 2026-07-13] Register BEFORE the button exists. If the operator
    # can press it, the snapshot behind it must already be on disk.
    register_approved_snapshot(safe_sig_id, ticker, "EXEC", signal)

    keyboard = {
        "inline_keyboard": [
            [
                {"text": "✅ EXECUTE", "callback_data": f"EXEC:{safe_sig_id}:{ts}"},
                {"text": "❌ REJECT",  "callback_data": f"REJ:{safe_sig_id}:{ts}"}
            ]
        ]
    }
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": "Markdown", "reply_markup": json.dumps(keyboard)}
    try:
        res = requests.post(url, json=payload, timeout=10)
        res.raise_for_status()
        logger.info(f"Successfully sent Telegram alert for {ticker}")
    except Exception as e:
        logger.error(f"Failed to send Telegram alert for {ticker}: {e}")

# -------------------------------------------------------------------------
# PIPELINE ORCHESTRATION
# -------------------------------------------------------------------------
def system_health_check(event_type: str):
    logger.info(f"Running {event_type} heartbeat check...")
    health_url = QUANT_ENGINE_URL.replace("/signals", "/health")
    
    try:
        # Interrogate the Python Engine
        res = requests.get(health_url, timeout=5)
        res.raise_for_status()
        
        if event_type == "OPEN":
            msg = "✅ **MARKET OPEN**\nTrading Sentinel is ONLINE.\nQuant Engine: ✅ Healthy\nAgent: ✅ Active\nReady to hunt. 🦅"
        else:
            msg = "🛑 **MARKET CLOSED**\nTrading Sentinel is SLEEPING.\nQuant Engine: ✅ Survived the day\nSee you tomorrow. 🌙"

    except Exception as e:
        # The Engine is dead or unreachable
        msg = f"🚨 **CRITICAL SYSTEM FAILURE** 🚨\nEvent: {event_type}\nError: Quant Engine Unreachable!\nDetails: `{e}`\n⚠️ Wake up and check Docker!"

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": msg, "parse_mode": "Markdown"}
    try:
        requests.post(url, json=payload, timeout=10)
    except Exception as e:
        logger.error(f"Failed to send heartbeat to Telegram: {e}")

MOMENTUM_ENGINE_URL = os.getenv(
    "QUANT_ENGINE_URL", "http://python-engine:8000"
).replace("/signals", "") + "/momentum-signals"

def run_momentum_pipeline():
    """Poll Container B momentum signals and process them."""
    logger.info("Starting momentum signal pipeline...")
    try:
        resp = requests.get(MOMENTUM_ENGINE_URL, timeout=10)
        resp.raise_for_status()
        data           = resp.json()
        signals        = data.get("signals", [])
        regime         = data.get("market_regime", "UNKNOWN")
        momentum_pool  = data.get("momentum_pool", 0)
    except Exception as e:
        logger.error(f"Failed to fetch momentum signals: {e}")
        return

    if not signals:
        return

    for signal in signals:
        ticker  = signal.get("ticker")
        sig_id  = f"{ticker}_MOM"   # prevent collision with swing dedup

        if not ticker:
            continue
        if sig_id in processed_signals_today:
            logger.info(f"Momentum signal {sig_id} already processed. Skipping.")
            continue

        # [FIX 2026-07-11 STALL] Isolate each signal. On 2026-07-10 the
        # loop died after COCHINSHIP and HUDCO (same snapshot) was never
        # processed -- one raised exception killed every signal after it
        # in the batch. On failure the signal is NOT marked processed, so
        # the next poll retries it (bounded: polls run every 15 min).
        touch_heartbeat()  # [ROADMAP-2.2] progressing, not hung
        try:
            sentiment_text = scrape_sentiment(ticker)
            analysis       = analyze_with_gemini(signal, sentiment_text, regime)

            if analysis and analysis.get('conviction_score', 0) < 50:
                logger.info(f"Momentum {ticker} skipped. Low conviction: "
                            f"{analysis.get('conviction_score')}")
                # [FIX 2026-07-11 SILENT-VETO] Tell the operator. Before
                # this, a Gemini veto was invisible: the engine's summary
                # said "accepted" but no button alert ever arrived.
                send_conviction_veto_notice(signal, analysis)
                mark_processed(sig_id)
                continue

            send_momentum_telegram_alert(signal, analysis, momentum_pool)
            mark_processed(sig_id)
        except Exception as e:
            logger.error(
                f"Momentum pipeline error for {ticker} (will retry next "
                f"poll): {e}", exc_info=True
            )
        time.sleep(2)

def send_conviction_veto_notice(signal: Dict, analysis: Dict):
    """Plain informational message (no buttons) when the Gemini gate
    vetoes an engine-accepted momentum signal. Failures are logged and
    swallowed -- the veto notice must never break the pipeline."""
    url    = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    ticker = signal.get("ticker", "UNKNOWN")
    score  = analysis.get('conviction_score', 'N/A')
    text = (f"🧠 MOMENTUM VETO: {ticker}\n"
            f"Engine accepted, Gemini conviction {score}/100 (<50) - "
            f"no EXEC button sent.\n"
            f"Rationale: {analysis.get('rationale', 'N/A')}")
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": text}
    try:
        res = requests.post(url, json=payload, timeout=10)
        res.raise_for_status()
        logger.info(f"Conviction veto notice sent: {ticker}")
    except Exception as e:
        logger.error(f"Conviction veto notice failed: {ticker}: {e}")

def send_momentum_telegram_alert(
    signal: Dict, analysis: Dict, momentum_pool: float
):
    """Distinct format from swing alerts - clearly labelled INTRADAY."""
    url    = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    ticker = signal.get("ticker", "UNKNOWN")
    price  = signal.get("close")
    target = signal.get("target_1")
    sl     = signal.get("stop_loss")
    vwap   = signal.get("vwap")
    ptype  = signal.get("product_type", "MIS")
    ratio  = signal.get("cost_ratio", 0)

    header = f"⚡ INTRADAY MOMENTUM: {ticker} ({ptype})"

    if not analysis:
        text = (f"{header}\n"
                f"Price: Rs{price} | VWAP: Rs{vwap}\n"
                f"Target: Rs{target} | SL: Rs{sl}\n"
                f"⚠️ AI analysis failed. Manual review required.\n"
                f"Auto-square at 15:15 IST.")
    else:
        text = (f"{header}\n\n"
                f"Entry: Rs{price} | VWAP: Rs{vwap}\n"
                f"Target: Rs{target} | SL: Rs{sl}\n"
                f"Cost ratio: {ratio:.1%} of expected profit\n"
                f"Conviction: {analysis.get('conviction_score')}/100\n\n"
                f"Pitch: {analysis.get('pitch', 'N/A')}\n"
                f"Risk: {analysis.get('risks', 'N/A')}\n\n"
                f"⚠️ INTRADAY: Auto-square at 15:15 IST regardless of P&L.")

    # [CRIT-001/002] Unified callback format: ACTION:signal_id:unix_ts
    sig_id = f"{ticker}_MOM"[:40]
    ts = int(time.time())

    # [HIGH-007 2026-07-13] Register BEFORE the button exists. The engine's
    # momentum list lives only in memory -- a restart wipes it and the press
    # then dies with "Momentum signal not found in Engine state". This row is
    # on disk and survives that.
    register_approved_snapshot(sig_id, ticker, "EM", signal)

    keyboard = {
        "inline_keyboard": [[
            {"text": "✅ EXECUTE INTRADAY",
             "callback_data": f"EM:{sig_id}:{ts}"},
            {"text": "❌ REJECT",
             "callback_data": f"REJ:{sig_id}:{ts}"}
        ]]
    }
    payload = {
        "chat_id":      TELEGRAM_CHAT_ID,
        "text":         text,
        "parse_mode":   "Markdown",
        "reply_markup": json.dumps(keyboard)
    }
    try:
        res = requests.post(url, json=payload, timeout=10)
        res.raise_for_status()
        logger.info(f"Momentum Telegram sent: {ticker}")
    except Exception as e:
        logger.error(f"Momentum Telegram failed: {ticker}: {e}")

def run_pipeline():
    # Fetch regime from Container B health/signals endpoint
    logger.info("Starting scheduled signal pipeline...")
    try:
        resp = requests.get(
            QUANT_ENGINE_URL, timeout=10
        )
        data       = resp.json()
        signals    = data.get("signals", [])
        regime     = data.get("market_regime", "UNKNOWN")
    except Exception as e:
        logger.error(f"Failed to fetch signals: {e}")
        return
    
    if not signals:
        logger.info("No signals found or Quant Engine unreachable. Pipeline sleeping.")
        return

    for signal in signals:
        ticker = signal.get("ticker")
        sig_id = ticker # FIX: Use ticker for deduplication
        
        if not ticker: continue
            
        if sig_id in processed_signals_today:
            logger.info(f"Signal {sig_id} already processed today. Skipping.")
            continue
            
        logger.info(f"Processing signal for {ticker}...")
        touch_heartbeat()  # [ROADMAP-2.2] progressing, not hung
        # [FIX 2026-07-11 STALL] Same per-signal isolation as the momentum
        # pipeline: one bad ticker must not kill the rest of the batch.
        try:
            sentiment_text = scrape_sentiment(ticker)
            analysis = analyze_with_gemini(signal, sentiment_text,regime)

            if analysis and analysis.get('conviction_score', 0) < 50:
                logger.info(f"Skipped {ticker}. Low conviction score: {analysis.get('conviction_score')}")
                mark_processed(sig_id)
                continue

            send_telegram_alert(signal, analysis)
            mark_processed(sig_id)
        except Exception as e:
            logger.error(
                f"Swing pipeline error for {ticker} (will retry next run): {e}",
                exc_info=True
            )
        time.sleep(2)
        
    logger.info("Pipeline run complete.")
def main():
    logger.info("Container C (Intelligence Orchestrator) started.")
    logger.info("System configured for Asia/Kolkata timezone.")

    # [ROADMAP-4.7 2026-07-13] Restore today's already-alerted signals BEFORE
    # the first poll, or the restart we are trying to survive re-alerts them
    # in the very next cycle.
    _load_dedup_state()
    
    # Brute-force distinct alarm generation
    days = ["monday", "tuesday", "wednesday", "thursday", "friday"]
    
    for day in days:
        # getattr() creates a BRAND NEW schedule object for every single line
        getattr(schedule.every(), day).at("09:15").do(system_health_check, event_type="OPEN")
        getattr(schedule.every(), day).at("09:25").do(run_pipeline)
        getattr(schedule.every(), day).at("14:50").do(run_pipeline)
        getattr(schedule.every(), day).at("15:30").do(system_health_check, event_type="CLOSE")

    schedule.every().day.at("00:00").do(clear_memory)
    # [FIX 2026-07-11 POLL-CADENCE] The engine scans every 15 min
    # (:00/:15/:30/:45, 10:15-14:45 IST) and /momentum-signals is now
    # cumulative-for-the-day, but polling hourly still delays button
    # alerts by up to an hour (on 2026-07-10 the hourly poll of the old
    # per-scan snapshot saw only 3 of 17 signals). Poll ~10 min after
    # each scan starts (scans take 5.6-9.1 min), plus 15:10/15:25
    # stragglers for overrunning scans (the 15:09 trio case).
    # processed_signals_today dedupes, so extra polls are idempotent.
    momentum_poll_times = [
        f"{h:02d}:{m:02d}" for h in range(10, 15) for m in (10, 25, 40, 55)
    ] + ["15:10", "15:25"]
    for day in days:
        for t in momentum_poll_times:
            getattr(schedule.every(), day).at(t).do(run_momentum_pipeline)

    # [ROADMAP-2.4 2026-07-12] Engine loop-progress watchdog (self-gates
    # to market hours; alerts when /data/scheduler_tick.json goes stale).
    schedule.every(5).minutes.do(check_engine_liveness)

    touch_heartbeat()  # [ROADMAP-2.2] healthy from the first HEALTHCHECK
    while True:
        schedule.run_pending()
        touch_heartbeat()  # [ROADMAP-2.2] main loop alive
        time.sleep(30)

if __name__ == "__main__":
    main()
