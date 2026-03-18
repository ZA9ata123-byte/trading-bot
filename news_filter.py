import feedparser
import re
import logging

log = logging.getLogger(__name__)

# اخبار خطيرة فقط
BAD_KEYWORDS = [
    "hack", "breach", "exploit",
    "scam", "rug pull", "fraud",
    "bankrupt", "shutdown", "delisting",
    "ponzi", "arrest", "seized", "crash"
]

FEEDS = [
    "https://cointelegraph.com/rss",
    "https://coindesk.com/arc/outboundfeeds/rss/",
    "https://bitcoinmagazine.com/feed",
    "https://decrypt.co/feed",
    "https://cryptonews.com/news/feed/",
    "https://bitcoinist.com/feed/",
    "https://newsbtc.com/feed/",
    "https://ambcrypto.com/feed/",
    "https://www.investing.com/rss/news_301.rss",
    "https://www.reddit.com/r/CryptoCurrency/new/.rss",
    "https://www.reddit.com/r/Bitcoin/new/.rss",
    "https://www.reddit.com/r/ethereum/new/.rss",
    "https://www.reddit.com/r/CryptoMarkets/new/.rss",
]

def check_news(symbol):
    try:
        coin = symbol.replace("/USDT", "").lower()

        for url in FEEDS:
            try:
                feed = feedparser.parse(url)
                for entry in feed.entries[:20]:
                    title = entry.title.lower()

                    # نتحقق أن اسم العملة موجود كلمة كاملة
                    if re.search(r'\b' + re.escape(coin) + r'\b', title):
                        if any(kw in title for kw in BAD_KEYWORDS):
                            log.warning(f"خبر سلبي لـ {symbol}: {entry.title}")
                            return False
            except Exception:
                continue

        return True

    except Exception as e:
        log.error(f"خطأ الاخبار: {e}")
        return True
