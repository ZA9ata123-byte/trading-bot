import ccxt, json, os
from dotenv import load_dotenv
load_dotenv()

exchange = ccxt.binance({
    'apiKey': os.getenv('BINANCE_API_KEY'),
    'secret': os.getenv('BINANCE_API_SECRET'),
    'enableRateLimit': True
})

if not os.path.exists('open_trades.json'):
    print('لا صفقات')
else:
    trades = json.load(open('open_trades.json'))
    if not trades:
        print('💼 لا صفقات مفتوحة')
    else:
        print(f"💼 مفتوحة: {len(trades)}")
        for t in trades:
            p = exchange.fetch_ticker(t['symbol'])['last']
            pnl = (p - t['entry_price']) / t['entry_price'] * 100
            profit = 50 * (p - t['entry_price']) / t['entry_price'] - 0.10
            emoji = "✅" if profit > 0 else "❌"
            print(f"{emoji} {t['symbol']} | دخول:${t['entry_price']} | دبا:${p} | {pnl:+.2f}% | ${profit:+.4f}")
