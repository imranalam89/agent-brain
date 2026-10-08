import time
import hmac
import hashlib
import json
import urllib.parse
from typing import Dict, Any, List, Optional
import requests

from config.settings import (
    DELTA_ENVIRONMENT,
    DELTA_BASE_URLS,
    DELTA_API_KEY,
    DELTA_API_SECRET
)

class DeltaExchangeClient:
    """
    Client for Delta Exchange (India, Global, and Demo).
    Supports:
    - Public endpoints: Products info, L2 Orderbook (DOM), Candles, and Public Trades (for CVD/Footprint)
    - Private endpoints (HMAC-SHA256): Balances, Order Placement, Bracket SL/TP, and Positions
    """
    def __init__(
        self,
        environment: str = DELTA_ENVIRONMENT,
        api_key: str = DELTA_API_KEY,
        api_secret: str = DELTA_API_SECRET
    ):
        self.environment = environment
        self.base_url = DELTA_BASE_URLS.get(environment, "https://cdn.delta.exchange")
        self.api_key = api_key
        self.api_secret = api_secret
        self.session = requests.Session()
        self.session.headers.update({
            "Content-Type": "application/json",
            "User-Agent": "AgentBrain/1.0"
        })
        self._products_cache: Dict[str, Dict[str, Any]] = {}
        self.server_time_offset = 0
        self._sync_server_time()

    def _sync_server_time(self):
        """Synchronizes local clock with Delta Exchange server time to eliminate signature expiry."""
        try:
            r = self.session.get(self.base_url + "/v2/tickers", timeout=5)
            date_str = r.headers.get("date") or r.headers.get("Date")
            if date_str:
                import email.utils
                server_ts = int(email.utils.parsedate_to_datetime(date_str).timestamp())
                self.server_time_offset = server_ts - int(time.time())
        except Exception:
            pass

    def _generate_signature(self, method: str, path: str, query: str = "", body: str = "") -> tuple[str, str]:
        """Generates HMAC-SHA256 signature with synchronized server timestamp."""
        timestamp = str(int(time.time() + self.server_time_offset))
        message = method + timestamp + path + (f"?{query}" if query else "") + body
        signature = hmac.new(
            self.api_secret.encode("utf-8"),
            message.encode("utf-8"),
            hashlib.sha256
        ).hexdigest()
        return timestamp, signature

    def _request(
        self,
        method: str,
        path: str,
        params: Optional[Dict[str, Any]] = None,
        data: Optional[Dict[str, Any]] = None,
        auth: bool = False
    ) -> Dict[str, Any]:
        url = self.base_url + path
        query_str = urllib.parse.urlencode(params) if params else ""
        body_str = json.dumps(data) if data else ""

        headers = {}
        if auth:
            if not self.api_key or not self.api_secret:
                raise ValueError("Delta API Key and Secret are required for authenticated requests.")
            timestamp, signature = self._generate_signature(method, path, query_str, body_str)
            headers.update({
                "api-key": self.api_key,
                "timestamp": timestamp,
                "signature": signature
            })

        try:
            response = self.session.request(
                method=method,
                url=url,
                params=params,
                data=body_str if data else None,
                headers=headers,
                timeout=10
            )
            
            # Check for signature expiry and auto-retry with Delta's exact server_time
            if response.status_code == 401:
                try:
                    err_json = response.json()
                    err_code = err_json.get("error", {}).get("code")
                    if err_code == "expired_signature":
                        server_time = err_json.get("error", {}).get("context", {}).get("server_time")
                        if server_time:
                            self.server_time_offset = server_time - int(time.time())
                            timestamp, signature = self._generate_signature(method, path, query_str, body_str)
                            headers.update({"timestamp": timestamp, "signature": signature})
                            response = self.session.request(
                                method=method,
                                url=url,
                                params=params,
                                data=body_str if data else None,
                                headers=headers,
                                timeout=10
                            )
                    elif err_code == "ip_not_whitelisted_for_api_key":
                        client_ip = err_json.get("error", {}).get("context", {}).get("client_ip", "Unknown")
                        return {
                            "success": False,
                            "error": f"IP_NOT_WHITELISTED: Your IP ({client_ip}) must be added to your Delta API key settings.",
                            "client_ip": client_ip,
                            "status_code": 401
                        }
                except Exception:
                    pass

            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            resp_body = getattr(e.response, "text", "")
            return {"success": False, "error": str(e), "body": resp_body, "status_code": getattr(e.response, "status_code", None)}

    # ==========================================
    # PUBLIC MARKET DATA ENDPOINTS
    # ==========================================
    def get_products(self) -> List[Dict[str, Any]]:
        """Fetches product specifications (lot sizes, tick size, contract values)."""
        res = self._request("GET", "/v2/products")
        if res.get("success") and "result" in res:
            for p in res["result"]:
                symbol = p.get("symbol")
                if symbol:
                    self._products_cache[symbol] = p
            return res["result"]
        return []

    def get_product_spec(self, symbol: str) -> Dict[str, Any]:
        """Retrieves cached product spec or queries products if not cached."""
        if not self._products_cache:
            self.get_products()
        
        spec = self._products_cache.get(symbol, {})
        if not spec:
            # Fallback reasonable defaults based on Delta Exchange specs
            if "BTC" in symbol:
                return {"symbol": symbol, "contract_value": 0.001, "tick_size": "0.5", "contract_unit": "BTC"}
            elif "XAUT" in symbol:
                return {"symbol": symbol, "contract_value": 0.001, "tick_size": "0.01", "contract_unit": "XAUT"}
            elif "SLV" in symbol:
                return {"symbol": symbol, "contract_value": 1.0, "tick_size": "0.001", "contract_unit": "SLV"}
        return spec

    def get_l2_orderbook(self, symbol: str, depth: int = 50) -> Dict[str, Any]:
        """
        Fetches Level 2 Depth of Market (DOM).
        Returns top bids and asks as standardized [[price, size], ...] pairs.
        Supports customizable depth (default 50 for rich heatmap reconstruction).
        """
        # Delta endpoint: /v2/l2orderbook/{symbol}
        res = self._request("GET", f"/v2/l2orderbook/{symbol}")
        if res.get("success") and "result" in res:
            book = res["result"]
            raw_bids = book.get("buy", [])[:depth]
            raw_asks = book.get("sell", [])[:depth]
            
            bids = []
            for b in raw_bids:
                if isinstance(b, dict):
                    bids.append([float(b.get("price", 0)), float(b.get("size", 0))])
                elif isinstance(b, (list, tuple)) and len(b) >= 2:
                    bids.append([float(b[0]), float(b[1])])

            asks = []
            for a in raw_asks:
                if isinstance(a, dict):
                    asks.append([float(a.get("price", 0)), float(a.get("size", 0))])
                elif isinstance(a, (list, tuple)) and len(a) >= 2:
                    asks.append([float(a[0]), float(a[1])])

            return {"success": True, "bids": bids, "asks": asks}
        return {"success": False, "bids": [], "asks": []}

    def get_ticker(self, symbol: str) -> Dict[str, Any]:
        """Fetches 24h ticker and mark price for a symbol."""
        res = self._request("GET", f"/v2/tickers/{symbol}")
        if res.get("success") and "result" in res:
            return res["result"]
        # Fallback to orderbook midpoint if ticker endpoint fails
        dom = self.get_l2_orderbook(symbol, depth=1)
        bids = dom.get("bids", [])
        asks = dom.get("asks", [])
        mid = 0.0
        if bids and asks:
            mid = round((float(bids[0][0]) + float(asks[0][0])) / 2.0, 2)
        return {"symbol": symbol, "mark_price": mid, "close": mid}


    def get_candles(self, symbol: str, resolution: str = "15m", start: Optional[int] = None, end: Optional[int] = None) -> List[Dict[str, Any]]:
        """
        Fetches historical candles from Delta.
        Resolutions: '1m', '5m', '15m', '1h', '4h', '1d'
        """
        now = int(time.time())
        if not end:
            end = now
        if not start:
            # Default to last 3 days so there are plenty of 15m candles
            start = end - (86400 * 3)

        params = {"symbol": symbol, "resolution": resolution, "start": start, "end": end}

        res = self._request("GET", "/v2/history/candles", params=params)
        if res.get("success") and "result" in res:
            # Standardize candle schema
            raw_candles = res["result"]
            candles = []
            for c in raw_candles:
                c_open = float(c.get("open", 0))
                c_high = float(c.get("high", 0))
                c_low = float(c.get("low", 0))
                c_close = float(c.get("close", 0))
                vol = float(c.get("volume", 0))
                bar_range = max(1e-5, c_high - c_low)

                # Orderflow delta: use API delta if provided; otherwise compute directional body/wick bias delta
                if "delta" in c:
                    bar_delta = float(c["delta"])
                else:
                    body = c_close - c_open
                    lower_wick = min(c_open, c_close) - c_low
                    upper_wick = c_high - max(c_open, c_close)
                    directional_bias = body / bar_range
                    wick_bias = (lower_wick - upper_wick) / bar_range
                    effective_bias = (0.7 * directional_bias) + (0.3 * wick_bias)
                    bar_delta = round(effective_bias * vol, 4)

                candles.append({
                    "timestamp": c.get("time"),
                    "open": c_open,
                    "high": c_high,
                    "low": c_low,
                    "close": c_close,
                    "volume": vol,
                    "delta": bar_delta
                })
            # Sort ascending so candles[-1] is always the latest bar
            candles.sort(key=lambda x: x["timestamp"])
            return candles
        return []

    def get_recent_trades(self, symbol: str, limit: int = 100) -> List[Dict[str, Any]]:
        """
        Fetches recent public trades for Footprint / CVD calculation.
        Each trade has price, size, and side (buy/sell).
        """
        res = self._request("GET", "/v2/trades", params={"symbol": symbol, "limit": limit})
        if res.get("success") and "result" in res:
            return res["result"]
        return []

    # ==========================================
    # AUTHENTICATED TRADING ENDPOINTS
    # ==========================================
    def get_wallet_balances(self) -> Dict[str, Any]:
        """Fetches account balance and available margin."""
        res = self._request("GET", "/v2/wallet/balances", auth=True)
        return res

    def get_positions(self) -> List[Dict[str, Any]]:
        """Fetches active open positions on Delta."""
        res = self._request("GET", "/v2/positions/margined", auth=True)
        if res.get("success") and "result" in res:
            return [p for p in res["result"] if p.get("size", 0) != 0]
        res2 = self._request("GET", "/v2/positions", auth=True)
        if res2.get("success") and "result" in res2:
            return [p for p in res2["result"] if p.get("size", 0) != 0]
        return []

    def place_bracket_order(
        self,
        symbol: str,
        side: str,       # 'buy' or 'sell'
        size: int,       # lot count (integer)
        order_type: str, # 'limit_order' or 'market_order'
        limit_price: Optional[float] = None,
        stop_loss_price: Optional[float] = None,
        take_profit_price: Optional[float] = None
    ) -> Dict[str, Any]:
        """
        Submits order with native exchange-side Bracket Stop-Loss and Take-Profit.
        Guarantees capital safety even if PC loses connection.
        """
        payload: Dict[str, Any] = {
            "product_symbol": symbol,
            "size": size,
            "side": side.lower(),
            "order_type": order_type
        }

        if limit_price and order_type == "limit_order":
            payload["limit_price"] = str(limit_price)

        # Bracket Order parameters
        bracket: Dict[str, Any] = {}
        if stop_loss_price:
            bracket["stop_loss_order"] = {
                "order_type": "market_order",
                "stop_price": str(stop_loss_price)
            }
        if take_profit_price:
            bracket["take_profit_order"] = {
                "order_type": "market_order",
                "stop_price": str(take_profit_price)
            }

        if bracket:
            payload["bracket_order"] = bracket

        return self._request("POST", "/v2/orders", data=payload, auth=True)

    def place_stop_order(
        self,
        symbol: str,
        side: str,       # 'buy' or 'sell' (opposite of open position)
        size: int,
        stop_price: float,
        is_take_profit: bool = False
    ) -> Dict[str, Any]:
        """Places a native reduce-only Stop Loss or Take Profit order on Delta Exchange."""
        payload = {
            "product_symbol": symbol,
            "size": int(size),
            "side": side.lower(),
            "order_type": "market_order",
            "stop_order_type": "take_profit_order" if is_take_profit else "stop_loss_order",
            "stop_price": str(stop_price),
            "reduce_only": True,
            "stop_trigger_method": "mark_price"
        }
        return self._request("POST", "/v2/orders", data=payload, auth=True)

    def cancel_all_orders(self, symbol: Optional[str] = None) -> Dict[str, Any]:
        """Emergency kill switch - cancels all open resting orders."""
        params = {"product_symbol": symbol} if symbol else None
        return self._request("DELETE", "/v2/orders/all", params=params, auth=True)

