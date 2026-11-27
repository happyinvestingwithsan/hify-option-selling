"""Read-Only Angel One SmartAPI Market Data Adapter (Zero Order Execution).

Provides live NSE/NFO quotes (with 5-level depth Bid/Ask), 5-year daily candles,
and NFO option contract lookup using programmatic TOTP login. Never imports or
invokes any order-placement or trading endpoints.
"""

from __future__ import annotations

import json
import time
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import pyotp

from app.config import PROJECT_ROOT, Settings
from app.kite_client import calculate_spread_pct

SCRIP_MASTER_URL = (
    "https://margincalculator.angelbroking.com/OpenAPI_File/files/OpenAPIScripMaster.json"
)
SESSION_FILE = PROJECT_ROOT / "backend" / "data" / ".angel_session.json"
SCRIP_MASTER_FILE = PROJECT_ROOT / "backend" / "data" / ".angel_scrip_master.json"

# Angel One NSE index symbol tokens
ANGEL_INDEX_TOKENS: dict[str, dict[str, str]] = {
    "NIFTY": {"token": "99926000", "tradingsymbol": "Nifty 50", "nfo_name": "NIFTY"},
    "BANKNIFTY": {"token": "99926009", "tradingsymbol": "Nifty Bank", "nfo_name": "BANKNIFTY"},
    "FINNIFTY": {"token": "99926037", "tradingsymbol": "Nifty Fin Service", "nfo_name": "FINNIFTY"},
    "MIDCPNIFTY": {"token": "99926074", "tradingsymbol": "NIFTY MID SELECT", "nfo_name": "MIDCPNIFTY"},
}


class AngelDataService:
    """Strictly read-only Angel One SmartAPI client for market quotes & candles."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or Settings()
        self._smart: Any = None
        self._jwt_token: str | None = None
        self._session_date: str | None = None
        self._scrip_index: dict[str, Any] | None = None
        self._load_cached_session()

    def is_configured(self) -> bool:
        return bool(
            self.settings.ANGEL_API_KEY.strip()
            and self.settings.ANGEL_CLIENT_CODE.strip()
            and self.settings.ANGEL_PIN.strip()
            and self.settings.ANGEL_TOTP_SECRET.strip()
        )

    def _load_cached_session(self) -> None:
        if not SESSION_FILE.exists():
            return
        try:
            data = json.loads(SESSION_FILE.read_text(encoding="utf-8"))
            today = datetime.now().strftime("%Y-%m-%d")
            if data.get("date") == today and data.get("jwt_token"):
                from SmartApi import SmartConnect

                obj = SmartConnect(api_key=self.settings.ANGEL_API_KEY.strip())
                raw_tok = str(data["jwt_token"]).removeprefix("Bearer ").strip()
                obj.setAccessToken(raw_tok)
                if data.get("refresh_token"):
                    obj.setRefreshToken(data["refresh_token"])
                self._smart = obj
                self._jwt_token = raw_tok
                self._session_date = today
        except Exception:
            self._smart = None
            self._jwt_token = None

    def ensure_session(self) -> bool:
        """Return True if a valid today's SmartAPI session is active (auto-login via TOTP)."""
        if not self.is_configured():
            return False
        today = datetime.now().strftime("%Y-%m-%d")
        if self._smart is not None and self._jwt_token and self._session_date == today:
            return True

        try:
            from SmartApi import SmartConnect

            obj = SmartConnect(api_key=self.settings.ANGEL_API_KEY.strip())
            totp = pyotp.TOTP(self.settings.ANGEL_TOTP_SECRET.strip()).now()
            resp = obj.generateSession(
                self.settings.ANGEL_CLIENT_CODE.strip(),
                self.settings.ANGEL_PIN.strip(),
                totp,
            )
            if not resp or not resp.get("status"):
                return False
            data = resp.get("data") or {}
            raw_jwt = data.get("jwtToken") or ""
            jwt_token = str(obj.access_token or raw_jwt).removeprefix("Bearer ").strip()
            refresh_token = data.get("refreshToken")
            if not jwt_token:
                return False

            self._smart = obj
            self._jwt_token = jwt_token
            self._session_date = today

            SESSION_FILE.parent.mkdir(parents=True, exist_ok=True)
            SESSION_FILE.write_text(
                json.dumps(
                    {
                        "date": today,
                        "jwt_token": jwt_token,
                        "refresh_token": refresh_token,
                    }
                ),
                encoding="utf-8",
            )
            return True
        except Exception:
            self._smart = None
            self._jwt_token = None
            return False

    def _load_scrip_master(self) -> dict[str, Any]:
        """Load & index Angel One OpenAPIScripMaster.json (cached daily)."""
        if self._scrip_index is not None:
            return self._scrip_index

        today = datetime.now().strftime("%Y-%m-%d")
        raw_list: list[dict[str, Any]] | None = None
        if SCRIP_MASTER_FILE.exists():
            mtime = datetime.fromtimestamp(SCRIP_MASTER_FILE.stat().st_mtime).strftime("%Y-%m-%d")
            if mtime == today:
                try:
                    raw_list = json.loads(SCRIP_MASTER_FILE.read_text(encoding="utf-8"))
                except Exception:
                    raw_list = None

        if raw_list is None:
            req = urllib.request.Request(
                SCRIP_MASTER_URL,
                headers={"User-Agent": "Mozilla/5.0"},
            )
            with urllib.request.urlopen(req, timeout=30) as resp:
                raw_bytes = resp.read()
            SCRIP_MASTER_FILE.parent.mkdir(parents=True, exist_ok=True)
            SCRIP_MASTER_FILE.write_bytes(raw_bytes)
            raw_list = json.loads(raw_bytes.decode("utf-8"))

        eq_tokens: dict[str, str] = {}
        nfo_puts: dict[str, list[dict[str, Any]]] = {}

        for row in raw_list:
            exch = row.get("exch_seg")
            if exch == "NSE" and row.get("symbol", "").endswith("-EQ"):
                sym = row["symbol"][:-3].upper()
                eq_tokens[sym] = str(row["token"])
            elif exch == "NFO" and row.get("instrumenttype") in ("OPTSTK", "OPTIDX"):
                tsym = str(row.get("symbol") or "")
                if not tsym.endswith("PE"):
                    continue
                name = str(row.get("name") or "").upper()
                if not name:
                    continue
                raw_strike = float(row.get("strike") or 0.0)
                # Angel One stores NFO strike scaled by 100 (e.g., 2400000.0 -> 24000.0)
                strike = round(raw_strike / 100.0, 2) if raw_strike > 100000 else round(raw_strike, 2)
                exp_str = str(row.get("expiry") or "")
                try:
                    exp_dt = datetime.strptime(exp_str, "%d%b%Y").date()
                except Exception:
                    continue
                nfo_puts.setdefault(name, []).append(
                    {
                        "token": str(row["token"]),
                        "tradingsymbol": tsym,
                        "name": name,
                        "strike": strike,
                        "expiry": exp_dt.isoformat(),
                        "expiry_date": exp_dt,
                        "lot_size": int(float(row.get("lotsize") or 0)),
                    }
                )

        self._scrip_index = {"eq_tokens": eq_tokens, "nfo_puts": nfo_puts}
        return self._scrip_index

    def get_spot_token(self, symbol: str, instrument_type: str = "EQ") -> str | None:
        sym = symbol.strip().upper()
        if instrument_type == "INDEX" and sym in ANGEL_INDEX_TOKENS:
            return ANGEL_INDEX_TOKENS[sym]["token"]
        idx = self._load_scrip_master()
        return idx["eq_tokens"].get(sym)

    def find_atm_or_lbl_put(
        self,
        symbol: str,
        target_strike: float,
    ) -> dict[str, Any] | None:
        """Select nearest active monthly/upcoming PE contract closest to target_strike."""
        sym = symbol.strip().upper()
        idx = self._load_scrip_master()
        puts = idx["nfo_puts"].get(sym, [])
        if not puts:
            return None

        today = datetime.now().date()
        future = [p for p in puts if p["expiry_date"] >= today]
        if not future:
            future = puts

        # Prefer expiry >= 7 days out so we don't pick expiring-today weeklies for Wheel
        beyond_week = [p for p in future if (p["expiry_date"] - today).days >= 7]
        pool = beyond_week or future
        nearest_expiry = min(p["expiry_date"] for p in pool)
        same_exp = [p for p in pool if p["expiry_date"] == nearest_expiry]
        chosen = min(same_exp, key=lambda p: abs(p["strike"] - target_strike))
        return {
            "token": chosen["token"],
            "tradingsymbol": chosen["tradingsymbol"],
            "strike": chosen["strike"],
            "expiry": chosen["expiry"],
            "lot_size": chosen["lot_size"],
        }

    def get_market_quotes(
        self,
        exchange: str,
        tokens: list[str],
    ) -> dict[str, dict[str, Any]]:
        """Fetch FULL market quotes (LTP, OHLC, 52W High/Low, Bid/Ask depth) in batches of 50."""
        if not tokens or not self.ensure_session():
            return {}

        results: dict[str, dict[str, Any]] = {}
        unique_tokens = list(dict.fromkeys(str(t) for t in tokens if t))
        for i in range(0, len(unique_tokens), 50):
            chunk = unique_tokens[i : i + 50]
            try:
                resp = self._smart.getMarketData("FULL", {exchange: chunk})
                if resp and resp.get("errorCode") == "AG8001":
                    self._smart = None
                    self._jwt_token = None
                    if self.ensure_session():
                        resp = self._smart.getMarketData("FULL", {exchange: chunk})
                if not resp or not resp.get("status"):
                    continue
                fetched = (resp.get("data") or {}).get("fetched") or []
                for item in fetched:
                    tok = str(item.get("symbolToken") or "")
                    if not tok:
                        continue
                    depth = item.get("depth") or {}
                    buys = depth.get("buy") or []
                    sells = depth.get("sell") or []
                    best_bid = float(buys[0].get("price") or 0.0) if buys else 0.0
                    best_ask = float(sells[0].get("price") or 0.0) if sells else 0.0
                    spread_pct = calculate_spread_pct(best_bid, best_ask)
                    results[tok] = {
                        "token": tok,
                        "tradingsymbol": item.get("tradingSymbol"),
                        "last_price": float(item.get("ltp") or 0.0),
                        "open": float(item.get("open") or 0.0),
                        "high": float(item.get("high") or 0.0),
                        "low": float(item.get("low") or 0.0),
                        "close": float(item.get("close") or 0.0),
                        "week52_high": float(item.get("52WeekHigh") or 0.0),
                        "week52_low": float(item.get("52WeekLow") or 0.0),
                        "best_bid": best_bid,
                        "best_ask": best_ask,
                        "bid_ask_spread_pct": spread_pct,
                    }
            except Exception:
                continue
            if i + 50 < len(unique_tokens):
                time.sleep(0.15)
        return results

    def get_historical_daily(
        self,
        token: str,
        exchange: str = "NSE",
        days: int = 1825,
    ) -> list[dict[str, Any]]:
        """Fetch up to 5 years of daily OHLC candles for ATH, 52W High, SMA200, and HV."""
        if not token or not self.ensure_session():
            return []

        to_dt = datetime.now()
        from_dt = to_dt - timedelta(days=days)
        try:
            resp = self._smart.getCandleData(
                {
                    "exchange": exchange,
                    "symboltoken": str(token),
                    "interval": "ONE_DAY",
                    "fromdate": from_dt.strftime("%Y-%m-%d 09:15"),
                    "todate": to_dt.strftime("%Y-%m-%d 15:30"),
                }
            )
            if resp and resp.get("errorCode") == "AG8001":
                self._smart = None
                self._jwt_token = None
                if self.ensure_session():
                    resp = self._smart.getCandleData(
                        {
                            "exchange": exchange,
                            "symboltoken": str(token),
                            "interval": "ONE_DAY",
                            "fromdate": from_dt.strftime("%Y-%m-%d 09:15"),
                            "todate": to_dt.strftime("%Y-%m-%d 15:30"),
                        }
                    )
            if not resp or not resp.get("status"):
                return []
            rows = resp.get("data") or []
            candles: list[dict[str, Any]] = []
            for r in rows:
                if len(r) < 5:
                    continue
                candles.append(
                    {
                        "date": r[0],
                        "open": float(r[1]),
                        "high": float(r[2]),
                        "low": float(r[3]),
                        "close": float(r[4]),
                        "volume": int(r[5]) if len(r) > 5 else 0,
                    }
                )
            return candles
        except Exception:
            return []
