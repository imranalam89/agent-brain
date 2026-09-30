import os
import sys
import time
import hmac
import hashlib
import json
import requests
import email.utils
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / '.env')
key = os.getenv('DELTA_API_KEY')
secret = os.getenv('DELTA_API_SECRET')
url = 'https://api.india.delta.exchange'

# 1. Probe for server time
probe = requests.get(url + '/v2/tickers', timeout=5)
date_str = probe.headers.get('date')
server_time = int(email.utils.parsedate_to_datetime(date_str).timestamp())
local_time = int(time.time())
offset = server_time - local_time
print(f"Server Time: {server_time} | Local Time: {local_time} | Calculated Offset: {offset}s")

# 2. Make authenticated request using calibrated timestamp
ts = str(int(time.time() + offset))
path = '/v2/wallet/balances'
msg = 'GET' + ts + path
sig = hmac.new(secret.encode('utf-8'), msg.encode('utf-8'), hashlib.sha256).hexdigest()

headers = {
    'api-key': key,
    'timestamp': ts,
    'signature': sig,
    'Content-Type': 'application/json',
    'User-Agent': 'AgentBrain/1.0'
}

r = requests.get(url + path, headers=headers)
print(f"Status Code: {r.status_code}")
print(f"Response: {r.text}")

if not r.json().get('success') and 'server_time' in r.text:
    # Auto-adjust from response context
    data = r.json()
    actual_server_time = data['error']['context']['server_time']
    offset = actual_server_time - int(time.time())
    print(f"\nRe-calibrating with exact server_time {actual_server_time} (offset {offset}s)...")
    ts2 = str(int(time.time() + offset))
    msg2 = 'GET' + ts2 + path
    sig2 = hmac.new(secret.encode('utf-8'), msg2.encode('utf-8'), hashlib.sha256).hexdigest()
    headers['timestamp'] = ts2
    headers['signature'] = sig2
    r2 = requests.get(url + path, headers=headers)
    print(f"Second Attempt Status: {r2.status_code}")
    print(f"Second Attempt Response: {r2.text}")
