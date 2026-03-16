import feedparser
import logging

log = logging.getLogger(__name__)

BAD_KEYWORDS = [
    "hack", "breach", "ban", "lawsuit",
    "crash", "scam", "fraud", "bankrupt",
    "regulation", "sec", "shutdown", "delisting"
]

FEEDS = [
    "https://cointelegraph.com/rss",
    "https://www.coindesk.com/arc/outboundfeeds/rss/"
]

def check_news(symbol):
    try:
        coin = symbol.replace("/USDT", "").lower()
        
        for url in FEEDS:
            feed = feedparser.parse(url)
            for entry in feed.entries[:15]:
                title = entry.title.lower()
                if coin in title:
                    if any(kw in title for kw in BAD_KEYWORDS):
                        log.warning(f"⚠️ خبر سلبي لـ {symbol}: {entry.title}")
                        return False
        return True

    except Exception as e:
        log.error(f"خطأ الأخبار: {e}")
        return True
