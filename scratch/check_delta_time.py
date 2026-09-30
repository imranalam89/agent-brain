import requests

base = 'https://api.india.delta.exchange'
for ep in ['/v2/time', '/v2/server_time', '/v2/system/time', '/v2/products', '/v2/tickers']:
    r = requests.get(base + ep)
    print(ep, r.status_code, r.headers.get('date'))
