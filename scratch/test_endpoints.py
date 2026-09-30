import urllib.request
import json

code = urllib.request.urlopen("http://127.0.0.1:5050/live_journal.html").getcode()
print("live_journal.html HTTP status:", code)

res = json.loads(urllib.request.urlopen("http://127.0.0.1:5050/api/live-status").read().decode("utf-8"))
print("API live-status success:", res.get("success"))
print("API live-status account_id:", res.get("account_id"))
print("API live-status tickers:", res.get("tickers"))
print("API live-status wallet:", res.get("wallet"))
print("API live-status error:", res.get("error"))
print("open_trades count:", len(res.get("open_trades", [])))
print("closed_trades count:", len(res.get("closed_trades", [])))
