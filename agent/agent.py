import os
import sys
import time
import json
import logging
import urllib.parse
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
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
QUANT_ENGINE_URL = os.getenv("QUANT_ENGINE_URL", "http://python-engine:8000/signals")

if not all([GEMINI_API_KEY, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID]):
    logger.critical("CRITICAL: Missing required environment variables. Exiting.")
    sys.exit(1)

client = genai.Client(api_key=GEMINI_API_KEY)

# -------------------------------------------------------------------------
# SHORT-TERM MEMORY (DEDUPLICATION)
# -------------------------------------------------------------------------
processed_signals_today = set()

def clear_memory():
    processed_signals_today.clear()
    logger.info("Cleared daily signal memory for the new trading day.")

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
        response = requests.get(QUANT_ENGINE_URL, timeout=10)
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

    ═══════════════════════════════════════════
    TRADE CONTEXT
    ═══════════════════════════════════════════
    Strategy Type : {signal.get('strategy_type', 'SWING')}
    Market Regime : {market_regime}
    Ticker        : {ticker}
    Entry Price   : ₹{price}
    Stop Loss     : ₹{stop_loss}
    Target        : ₹{target}
    Net EV        : ₹{signal.get('net_ev', 'N/A')}
    Score         : {signal.get('score', 'N/A')}/100
    Volume Ratio  : {signal.get('volume_ratio', 'N/A')}x
    RSI           : {signal.get('rsi_14', 'N/A')}
    RS Score      : {signal.get('rs_score', 'N/A')} (vs Nifty, 20-day)

    ═══════════════════════════════════════════
    REGIME-SPECIFIC INSTRUCTIONS
    ═══════════════════════════════════════════

    IF regime is "BEAR_RS_ONLY":
    Be EXTREMELY cynical. The broad market is falling.
    This stock is only being evaluated because its math shows
    outperformance vs the Nifty. Your primary job here is to
    determine WHY it is outperforming:
    - Quiet institutional accumulation (VALID) → keep conviction high
    - Unverified rumour, single contract win, retail social media hype → 
        REDUCE conviction_score below 50 immediately
    - Short-covering rally in a falling stock → REDUCE below 40
    - If you cannot determine a credible structural reason from the
        sentiment data: REDUCE below 55

    IF strategy is "MOMENTUM" (intraday):
    Evaluate whether the news/catalyst justifies a 3-hour sustained
    move, not just a 15-minute spike.
    - Genuine earnings beat, sector tailwind → conviction can be high
    - Single news headline with no follow-through evidence → max 65
    - No news at all (pure technical breakout) → max 70
    - Negative news despite price rising → REDUCE below 45

    IF regime is "CAUTION":
    Apply the same cynicism as BEAR_RS_ONLY but one level less severe.
    Reduce all scores by 10 points before outputting.

    IF regime is "BULL" and strategy is "SWING":
    Standard evaluation. Do not manufacture cynicism.
    Follow the contradiction check rules below.

    ═══════════════════════════════════════════
    UNIVERSAL EVALUATION RULES
    ═══════════════════════════════════════════

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

    ═══════════════════════════════════════════
    MULTI-SOURCE SENTIMENT DATA
    ═══════════════════════════════════════════
    {sentiment_text if sentiment_text else
    "NO SENTIMENT DATA AVAILABLE. Evaluate on technicals only. "
    "Apply caution: absence of news for an active signal is unusual. "
    "Cap conviction at 70 unless regime is BULL."}

    Respond in strict JSON matching the required schema.
    No markdown. No explanation outside the JSON fields.
    """
    # prompt = f"""
    # You are an elite quantitative trading architect evaluating a swing trade.
    
    # QUANT DATA:
    # Ticker: {ticker}
    # Current Price: {price}
    # Target: {target}
    # Stop Loss: {stop_loss}
    
    # MULTI-SOURCE SENTIMENT DATA:
    # {sentiment_text if sentiment_text else "CRITICAL: No recent news available. Evaluate strictly on technicals with high caution."}
    
    # EVALUATION RULES:
    # 1. CONTRADICTION CHECK: If the Quant Data suggests a long position, but the Sentiment Data contains critical legal, regulatory, or catastrophic news, you MUST lower the conviction_score significantly.
    # 2. DO NOT override the quant edge unless a strong contradiction exists. Do not overreact to weak or routine news.
    # 3. NO HALLUCINATION: Base your rationale ONLY on the text provided above. Do not invent news.
    # 4. SCORING: 
    #    - 80-100: Perfect alignment between technicals and sentiment.
    #    - 60-79: Acceptable setup, standard market risks.
    #    - 0-59: Conflicting data, high risk of false positive.
       
    # Provide your output in strict JSON format.
    # """
    try:
        response = client.models.generate_content(
            model='gemini-2.0-flash',
            contents=prompt,

            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=SignalOutput,
                temperature=0.0
            ),
        )
        return response.parsed.model_dump() if response.parsed else json.loads(response.text)
    except Exception as e:
        logger.error(f"Gemini Analysis failed for {ticker}: {e}")
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

    safe_sig_id = str(sig_id)[:40] 
    keyboard = {
        "inline_keyboard": [
            [
                {"text": "✅ EXECUTE", "callback_data": json.dumps({"a": "E", "i": safe_sig_id}, separators=(',', ':'))},
                {"text": "❌ REJECT", "callback_data": json.dumps({"a": "R", "i": safe_sig_id}, separators=(',', ':'))}
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
            msg = "🟢 **MARKET OPEN**\nTrading Sentinel is ONLINE.\nQuant Engine: ✅ Healthy\nAgent: ✅ Active\nReady to hunt. 🦅"
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

        sentiment_text = scrape_sentiment(ticker)
        analysis       = analyze_with_gemini(signal, sentiment_text, regime)

        if analysis and analysis.get('conviction_score', 0) < 50:
            logger.info(f"Momentum {ticker} skipped. Low conviction: "
                        f"{analysis.get('conviction_score')}")
            processed_signals_today.add(sig_id)
            continue

        send_momentum_telegram_alert(signal, analysis, momentum_pool)
        processed_signals_today.add(sig_id)
        time.sleep(2)

def send_momentum_telegram_alert(
    signal: Dict, analysis: Dict, momentum_pool: float
):
    """Distinct format from swing alerts — clearly labelled INTRADAY."""
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
                f"Price: ₹{price} | VWAP: ₹{vwap}\n"
                f"Target: ₹{target} | SL: ₹{sl}\n"
                f"⚠️ AI analysis failed. Manual review required.\n"
                f"Auto-square at 15:15 IST.")
    else:
        text = (f"{header}\n\n"
                f"Entry: ₹{price} | VWAP: ₹{vwap}\n"
                f"Target: ₹{target} | SL: ₹{sl}\n"
                f"Cost ratio: {ratio:.1%} of expected profit\n"
                f"Conviction: {analysis.get('conviction_score')}/100\n\n"
                f"Pitch: {analysis.get('pitch', 'N/A')}\n"
                f"Risk: {analysis.get('risks', 'N/A')}\n\n"
                f"⚠️ INTRADAY: Auto-square at 15:15 IST regardless of P&L.")

    sig_id = f"{ticker}_MOM"[:40]
    keyboard = {
        "inline_keyboard": [[
            {"text": "✅ EXECUTE INTRADAY",
             "callback_data": json.dumps(
                 {"a": "EM", "i": sig_id}, separators=(',', ':')
             )},
            {"text": "❌ REJECT",
             "callback_data": json.dumps(
                 {"a": "R", "i": sig_id}, separators=(',', ':')
             )}
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
        sentiment_text = scrape_sentiment(ticker)
        analysis = analyze_with_gemini(signal, sentiment_text,regime)
        
        if analysis and analysis.get('conviction_score', 0) < 50:
            logger.info(f"Skipped {ticker}. Low conviction score: {analysis.get('conviction_score')}")
            processed_signals_today.add(sig_id)
            continue
            
        send_telegram_alert(signal, analysis)
        processed_signals_today.add(sig_id)
        time.sleep(2)
        
    logger.info("Pipeline run complete.")
"""
def main():
    logger.info("Container C (Intelligence Orchestrator) started.")
    logger.info("System configured for Asia/Kolkata timezone.")
    
    for day in [schedule.every().monday, schedule.every().tuesday, 
                schedule.every().wednesday, schedule.every().thursday, 
                schedule.every().friday]:
        day.at("09:15").do(system_health_check, event_type="OPEN")
        day.at("15:30").do(system_health_check, event_type="CLOSE")
        day.at("09:25").do(run_pipeline)
        day.at("14:50").do(run_pipeline)

    schedule.every().day.at("00:00").do(clear_memory)

    while True:
        schedule.run_pending()
        time.sleep(30)

def main():
    logger.info("Container C (Intelligence Orchestrator) started.")
    logger.info("System configured for Asia/Kolkata timezone.")
    
    # Bulletproof Weekday Scheduling
    weekdays = [
        schedule.every().monday, schedule.every().tuesday, 
        schedule.every().wednesday, schedule.every().thursday, 
        schedule.every().friday
    ]
    
    for day in weekdays:
        day.at("09:15").do(system_health_check, event_type="OPEN")
    #for day in weekdays:
        #day.at(":20").do(run_pipeline) # Runs 5 minutes past every hour        
    #for day in weekdays:
        #day.at("11:20").do(run_pipeline)

    for day in weekdays:
        day.at("09:25").do(run_pipeline)
        
    for day in weekdays:
        day.at("14:50").do(run_pipeline)
        
    for day in weekdays:
        day.at("15:30").do(system_health_check, event_type="CLOSE")

    schedule.every().day.at("00:00").do(clear_memory)

    while True:
        schedule.run_pending()
        time.sleep(30)
if __name__ == "__main__":
    main()
"""
def main():
    logger.info("Container C (Intelligence Orchestrator) started.")
    logger.info("System configured for Asia/Kolkata timezone.")
    
    # Brute-force distinct alarm generation
    days = ["monday", "tuesday", "wednesday", "thursday", "friday"]
    
    for day in days:
        # getattr() creates a BRAND NEW schedule object for every single line
        getattr(schedule.every(), day).at("09:15").do(system_health_check, event_type="OPEN")
        getattr(schedule.every(), day).at("09:25").do(run_pipeline)
        getattr(schedule.every(), day).at("14:50").do(run_pipeline)
        getattr(schedule.every(), day).at("15:30").do(system_health_check, event_type="CLOSE")

    schedule.every().day.at("00:00").do(clear_memory)
    momentum_hours = ["10:55", "11:55", "12:55", "13:55", "14:55"]
    for day in days:
        for t in momentum_hours:
            getattr(schedule.every(), day).at(t).do(run_momentum_pipeline)
    while True:
        schedule.run_pending()
        time.sleep(30)

if __name__ == "__main__":
    main()
