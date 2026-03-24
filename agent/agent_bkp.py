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

# Initialize Gemini Client
client = genai.Client(api_key=GEMINI_API_KEY)

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
        signals = response.json()
        if not isinstance(signals, list):
            logger.error("Invalid response format from Quant Engine.")
            return []
        return signals
    except requests.exceptions.RequestException as e:
        logger.error(f"Failed to fetch signals from {QUANT_ENGINE_URL}: {e}")
        return []

def fetch_rss_feed(url: str, limit: int = 3) -> str:
    """Safely fetches and parses an RSS feed into clean text. Immune to basic bot blocks."""
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
    try:
        res = requests.get(url, headers=headers, timeout=5)
        res.raise_for_status()
        
        # Requires 'lxml' installed
        soup = BeautifulSoup(res.content, 'xml')
        items = soup.find_all('item', limit=limit)
        
        texts = []
        for item in items:
            title = item.title.text if item.title else ""
            texts.append(f"- {title}")
            
        return " | ".join(texts)
    except Exception as e:
        logger.warning(f"RSS fetch failed for {url}: {e}")
        return ""

def scrape_sentiment(ticker: str) -> str:
    """
    UPGRADE: Triangulates sentiment from multiple machine-readable sources.
    Fails open: if one source fails, it uses the others.
    """
    logger.info(f"Gathering multi-source intelligence for {ticker}...")
    
    # Source 1: Yahoo Finance RSS
    yahoo_url = f"https://feeds.finance.yahoo.com/rss/2.0/headline?s={ticker}&region=US&lang=en-US"
    yahoo_news = fetch_rss_feed(yahoo_url, limit=4)
    
    # Source 2: Google News RSS
    encoded_ticker = urllib.parse.quote(f"{ticker} stock")
    google_url = f"https://news.google.com/rss/search?q={encoded_ticker}&hl=en-US&gl=US&ceid=US:en"
    google_news = fetch_rss_feed(google_url, limit=4)
    
    if not yahoo_news and not google_news:
        return ""
        
    return f"YAHOO FINANCE FEED:\n{yahoo_news}\n\nBROADER MARKET FEED:\n{google_news}"

def analyze_with_gemini(signal: Dict, sentiment_text: str) -> Optional[Dict]:
    """
    UPGRADE: Passes data to Gemini with strict anti-hallucination, contradiction rules,
    and absolute zero temperature for deterministic outputs.
    """
    ticker = signal.get("ticker", "UNKNOWN")
    price = signal.get("price", 0)
    target = signal.get("target", 0)
    stop_loss = signal.get("stop_loss", 0)
    
    prompt = f"""
    You are an elite quantitative trading architect evaluating a swing trade.
    
    QUANT DATA:
    Ticker: {ticker}
    Current Price: {price}
    Target: {target}
    Stop Loss: {stop_loss}
    
    MULTI-SOURCE SENTIMENT DATA:
    {sentiment_text if sentiment_text else "CRITICAL: No recent news available. Evaluate strictly on technicals with high caution."}
    
    EVALUATION RULES:
    1. CONTRADICTION CHECK: If the Quant Data suggests a long position, but the Sentiment Data contains critical legal, regulatory, or catastrophic news, you MUST lower the conviction_score significantly.
    2. NO HALLUCINATION: Base your rationale ONLY on the text provided above. Do not invent news.
    3. SCORING: 
       - 80-100: Perfect alignment between technicals and sentiment.
       - 50-79: Acceptable setup, standard market risks.
       - 0-49: Conflicting data, high risk of false positive.
       
    Provide your output in strict JSON format.
    """

    try:
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=SignalOutput,
                temperature=0.0 # Absolute determinism
            ),
        )
        return json.loads(response.text)
    except Exception as e:
        logger.error(f"Gemini Analysis failed for {ticker}: {e}")
        return None

def send_telegram_alert(signal: Dict, analysis: Dict):
    """Dispatches the formatted message and inline keyboard to Telegram."""
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    
    ticker = signal.get("ticker", "UNKNOWN")
    price = signal.get("price")
    target = signal.get("target")
    sl = signal.get("stop_loss")
    sig_id = signal.get("signal_id", "000")
    
    if not analysis:
        text = f"🚨 **SYSTEM FALLBACK: {ticker}** 🚨\n" \
               f"Price: {price} | TGT: {target} | SL: {sl}\n" \
               f"⚠️ AI Sentiment analysis failed. Manual review required."
    else:
        text = f"📊 **TRADE ALERT: {ticker}**\n\n" \
               f"**Metrics:** Price: {price} | TGT: {target} | SL: {sl}\n" \
               f"**Conviction Score:** {analysis.get('conviction_score', 'N/A')}/100\n\n" \
               f"**Pitch:**\n{analysis.get('pitch', 'N/A')}\n\n" \
               f"**Rationale:**\n{analysis.get('rationale', 'N/A')}\n\n" \
               f"**Risks:**\n{analysis.get('risks', 'N/A')}"

    # Telegram 64-Byte Limit Mitigation
    safe_sig_id = str(sig_id)[:40] 
    keyboard = {
        "inline_keyboard": [
            [
                {
                    "text": "✅ EXECUTE", 
                    "callback_data": json.dumps({"a": "E", "i": safe_sig_id}, separators=(',', ':'))
                },
                {
                    "text": "❌ REJECT", 
                    "callback_data": json.dumps({"a": "R", "i": safe_sig_id}, separators=(',', ':'))
                }
            ]
        ]
    }

    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text,
        "parse_mode": "Markdown",
        "reply_markup": json.dumps(keyboard)
    }

    try:
        res = requests.post(url, json=payload, timeout=10)
        res.raise_for_status()
        logger.info(f"Successfully sent Telegram alert for {ticker}")
    except Exception as e:
        logger.error(f"Failed to send Telegram alert for {ticker}: {e}")

# -------------------------------------------------------------------------
# PIPELINE ORCHESTRATION
# -------------------------------------------------------------------------
def run_pipeline():
    logger.info("Starting scheduled signal pipeline...")
    signals = fetch_signals()
    
    if not signals:
        logger.info("No signals found or Quant Engine unreachable. Pipeline sleeping.")
        return

    for signal in signals:
        ticker = signal.get("ticker")
        if not ticker:
            continue
            
        logger.info(f"Processing signal for {ticker}...")
        
        sentiment_text = scrape_sentiment(ticker)
        analysis = analyze_with_gemini(signal, sentiment_text)
        send_telegram_alert(signal, analysis)
        
        # Polite delay to prevent API rate limiting across scraping & LLM
        time.sleep(2)
        
    logger.info("Pipeline run complete.")

def main():
    logger.info("Container C (Intelligence Orchestrator) started.")
    logger.info("System configured for Asia/Kolkata timezone.")
    
    schedule.every().day.at("09:25").do(run_pipeline)
    schedule.every().day.at("14:50").do(run_pipeline)

    while True:
        schedule.run_pending()
        time.sleep(30)

if __name__ == "__main__":
    main()
