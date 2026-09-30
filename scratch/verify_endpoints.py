import urllib.request

endpoints = [
    'backtest_report.html',
    'gold_report.html',
    'silver_report.html',
    'btc_report.html',
    'eth_report.html',
    'strategy_guide.html',
    'agent_journal.html',
    'gold_journal.html',
    'silver_journal.html',
    'btc_journal.html',
    'eth_journal.html'
]

for ep in endpoints:
    url = f"http://127.0.0.1:5050/{ep}"
    res = urllib.request.urlopen(url)
    print(f"HTTP {res.getcode()} -> {url}")
