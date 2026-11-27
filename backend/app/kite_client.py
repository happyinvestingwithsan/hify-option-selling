"""Zerodha Kite Connect service wrapper with daily OAuth and offline/dry-run fallback."""

from __future__ import annotations

import json
import re
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from kiteconnect import KiteConnect

from app.config import PROJECT_ROOT, Settings, get_settings
from app.db import db_session

DEFAULT_SESSION_PATH = PROJECT_ROOT / "backend" / "data" / ".kite_session.json"

# Matches standard NSE NFO option/future tradingsymbols, e.g. RELIANCE25MAY1200PE or TCS25MAYFUT
_NFO_OPTION_RE = re.compile(r"^([A-Z0-9&-]+?)(\d{2}[A-Z]{3}|\d{5})(\d+(?:\.\d+)?)(PE|CE)$")
_NFO_FUT_RE = re.compile(r"^([A-Z0-9&-]+?)(\d{2}[A-Z]{3})FUT$")


def parse_nfo_symbol(tradingsymbol: str, default_expiry: str = "") -> tuple[str, float, str, str]:
    """Extract (underlying_symbol, strike, option_type, expiry) from an NFO tradingsymbol."""
    sym = tradingsymbol.strip().upper()
    opt_match = _NFO_OPTION_RE.match(sym)
    if opt_match:
        underlying, expiry_code, strike_str, opt_type = opt_match.groups()
        return underlying, float(strike_str), opt_type, default_expiry or expiry_code

    fut_match = _NFO_FUT_RE.match(sym)
    if fut_match:
        underlying, expiry_code = fut_match.groups()
        return underlying, 0.0, "FUT", default_expiry or expiry_code

    return sym, 0.0, "PE", default_expiry or "UNKNOWN"


def calculate_decay_pct(entry_price: float, current_price: float, side: str) -> float:
    """Calculate option premium decay percentage for SELL/BUY positions."""
    if entry_price <= 0:
        return 0.0
    if side == "SELL":
        return round(((entry_price - current_price) / entry_price) * 100.0, 2)
    return round(((current_price - entry_price) / entry_price) * 100.0, 2)


def calculate_spread_pct(best_bid: float, best_ask: float) -> float:
    """Calculate Bid-Ask spread percentage; returns 100.0 if one side has zero liquidity."""
    if best_ask > 0 and best_bid > 0:
        return round(((best_ask - best_bid) / best_ask) * 100.0, 2)
    if best_ask > 0 or best_bid > 0:
        return 100.0
    return 0.0


class KiteService:
    """Thread-safe wrapper around KiteConnect with session persistence and dry-run fallback."""

    def __init__(
        self,
        settings: Settings | None = None,
        session_path: Path | None = None,
        db_path: str | Path | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.session_path = session_path or DEFAULT_SESSION_PATH
        self.db_path = db_path
        self._access_token: str = ""
        self._user_id: str | None = None
        self._login_time: str | None = None
        self._kite: KiteConnect | None = None
        self._load_session()

    def _has_api_credentials(self) -> bool:
        return bool(self.settings.KITE_API_KEY.strip() and self.settings.KITE_API_SECRET.strip())

    def _is_live(self) -> bool:
        return bool(self.settings.KITE_API_KEY.strip() and self._access_token)

    def _build_kite_client(self) -> KiteConnect | None:
        api_key = self.settings.KITE_API_KEY.strip()
        if not api_key:
            return None
        client = KiteConnect(api_key=api_key)
        if self._access_token:
            client.set_access_token(self._access_token)
        return client

    def _load_session(self) -> None:
        if not self.session_path.exists():
            self._access_token = ""
            self._user_id = None
            self._login_time = None
            self._kite = self._build_kite_client()
            return

        try:
            payload = json.loads(self.session_path.read_text(encoding="utf-8"))
            self._access_token = str(payload.get("access_token", "")).strip()
            self._user_id = payload.get("user_id")
            self._login_time = payload.get("login_time")
        except (OSError, ValueError, TypeError):
            self._access_token = ""
            self._user_id = None
            self._login_time = None

        self._kite = self._build_kite_client()

    def _save_session(self, access_token: str, user_id: str | None, login_time: str) -> None:
        self.session_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "access_token": access_token,
            "user_id": user_id,
            "login_time": login_time,
        }
        self.session_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        self._access_token = access_token
        self._user_id = user_id
        self._login_time = login_time
        self._kite = self._build_kite_client()

    def get_status(self) -> dict[str, Any]:
        """Return Kite connection status without exposing secrets or tokens."""
        self._load_session()
        live = self._is_live()
        return {
            "connected": live,
            "mode": "live" if live else "dry_run",
            "is_dry_run": not live,
            "user_id": self._user_id if live else "DRY_RUN_USER",
            "login_time": self._login_time,
            "api_key_configured": bool(self.settings.KITE_API_KEY.strip()),
        }

    def get_login_url(self) -> dict[str, Any]:
        """Return Zerodha Kite daily OAuth login URL (or dry-run notice if unconfigured)."""
        api_key = self.settings.KITE_API_KEY.strip()
        if not api_key:
            return {
                "login_url": None,
                "mode": "dry_run",
                "is_dry_run": True,
                "message": "KITE_API_KEY is not configured; running in offline dry-run mode.",
            }
        client = self._build_kite_client() or KiteConnect(api_key=api_key)
        return {
            "login_url": client.login_url(),
            "mode": "live" if self._is_live() else "dry_run",
            "is_dry_run": not self._is_live(),
            "message": "Open login_url in browser to complete daily Zerodha OAuth.",
        }

    def exchange_request_token(self, request_token: str) -> dict[str, Any]:
        """Exchange Kite request_token for access_token and persist session locally."""
        token = request_token.strip()
        if not token:
            raise ValueError("request_token must not be empty.")

        if not self._has_api_credentials():
            raise ValueError("KITE_API_KEY and KITE_API_SECRET must be set to exchange request_token.")

        client = KiteConnect(api_key=self.settings.KITE_API_KEY.strip())
        session_data = client.generate_session(
            token,
            api_secret=self.settings.KITE_API_SECRET.strip(),
        )
        access_token = str(session_data.get("access_token", "")).strip()
        if not access_token:
            raise ValueError("Kite generate_session did not return an access_token.")

        user_id = session_data.get("user_id")
        login_time = datetime.now(timezone.utc).isoformat()
        self._save_session(access_token=access_token, user_id=user_id, login_time=login_time)
        return self.get_status()

    def _invalidate_expired_session(self) -> None:
        """Clear stale access_token when Kite rejects it (daily 6 AM IST expiry)."""
        self._access_token = None
        self._kite = None
        if self.session_path.exists():
            try:
                self.session_path.unlink()
            except OSError:
                pass

    def get_margins(self) -> dict[str, Any]:
        """Fetch equity margins (cash, pledged collateral, utilised, total available)."""
        self._load_session()
        if self._is_live() and self._kite is not None:
            try:
                margins = self._kite.margins(segment="equity")
                available = margins.get("available", {})
                utilised = margins.get("utilised", {})
                cash = float(available.get("cash", 0.0) or 0.0)
                collateral = float(available.get("collateral", 0.0) or 0.0)
                debits = float(utilised.get("debits", 0.0) or 0.0)
                net = float(margins.get("net", cash + collateral - debits) or 0.0)
                return {
                    "mode": "live",
                    "is_dry_run": False,
                    "available_cash": round(cash, 2),
                    "collateral_pledged": round(collateral, 2),
                    "utilised_margin": round(debits, 2),
                    "total_available": round(net, 2),
                }
            except Exception as exc:
                if "TokenException" in type(exc).__name__ or "access_token" in str(exc):
                    self._invalidate_expired_session()
                else:
                    raise

        return {
            "mode": "dry_run",
            "is_dry_run": True,
            "available_cash": 650000.0,
            "collateral_pledged": 1850000.0,
            "utilised_margin": 420000.0,
            "total_available": 2080000.0,
        }

    def get_pnl(self) -> dict[str, Any]:
        """Compute realized P&L, unrealized MTM, total P&L, and open positions count."""
        self._load_session()
        if self._is_live() and self._kite is not None:
            try:
                positions_resp = self._kite.positions()
                net_positions = positions_resp.get("net", [])
                realized = 0.0
                unrealized = 0.0
                open_count = 0
                for pos in net_positions:
                    qty = int(pos.get("quantity", 0) or 0)
                    if qty != 0:
                        open_count += 1
                        unrealized += float(pos.get("unrealised", pos.get("m2m", 0.0)) or 0.0)
                    realized += float(pos.get("realised", 0.0) or 0.0)

                return {
                    "mode": "live",
                    "is_dry_run": False,
                    "realized_pnl": round(realized, 2),
                    "unrealized_mtm": round(unrealized, 2),
                    "total_pnl": round(realized + unrealized, 2),
                    "positions_count": open_count,
                }
            except Exception as exc:
                if "TokenException" in type(exc).__name__ or "access_token" in str(exc):
                    self._invalidate_expired_session()
                else:
                    raise

        return {
            "mode": "dry_run",
            "is_dry_run": True,
            "realized_pnl": 18450.0,
            "unrealized_mtm": 12650.0,
            "total_pnl": 31100.0,
            "positions_count": 2,
        }

    def get_orders(self) -> dict[str, Any]:
        """Fetch open/pending orders and active GTT triggers."""
        self._load_session()
        if self._is_live() and self._kite is not None:
            try:
                raw_orders = self._kite.orders()
                open_statuses = {"OPEN", "TRIGGER PENDING", "AMO REQ RECEIVED", "VALIDATION PENDING"}
                open_orders = [
                    {
                        "order_id": o.get("order_id"),
                        "tradingsymbol": o.get("tradingsymbol"),
                        "exchange": o.get("exchange"),
                        "transaction_type": o.get("transaction_type"),
                        "order_type": o.get("order_type"),
                        "product": o.get("product"),
                        "quantity": int(o.get("quantity", 0) or 0),
                        "price": float(o.get("price", 0.0) or 0.0),
                        "status": o.get("status"),
                    }
                    for o in raw_orders
                    if str(o.get("status", "")).upper() in open_statuses
                ]

                raw_gtts = self._kite.get_gtts()
                active_gtts = [
                    {
                        "gtt_id": g.get("id"),
                        "tradingsymbol": g.get("condition", {}).get("tradingsymbol"),
                        "exchange": g.get("condition", {}).get("exchange"),
                        "trigger_type": g.get("type"),
                        "trigger_value": (g.get("condition", {}).get("trigger_values") or [None])[0],
                        "limit_price": (g.get("orders") or [{}])[0].get("price"),
                        "status": g.get("status"),
                    }
                    for g in raw_gtts
                    if str(g.get("status", "")).lower() == "active"
                ]

                return {
                    "mode": "live",
                    "is_dry_run": False,
                    "open_orders": open_orders,
                    "gtts": active_gtts,
                }
            except Exception as exc:
                if "TokenException" in type(exc).__name__ or "access_token" in str(exc):
                    self._invalidate_expired_session()
                else:
                    raise

        return {
            "mode": "dry_run",
            "is_dry_run": True,
            "open_orders": [
                {
                    "order_id": "DRY-ORD-1001",
                    "tradingsymbol": "RELIANCE25MAY1200PE",
                    "exchange": "NFO",
                    "transaction_type": "BUY",
                    "order_type": "LIMIT",
                    "product": "NRML",
                    "quantity": 500,
                    "price": 12.5,
                    "status": "OPEN",
                }
            ],
            "gtts": [
                {
                    "gtt_id": 9001,
                    "tradingsymbol": "INFY25MAY1400PE",
                    "exchange": "NFO",
                    "trigger_type": "single",
                    "trigger_value": 15.0,
                    "limit_price": 14.8,
                    "status": "active",
                }
            ],
        }

    def get_trades_and_sync(self) -> dict[str, Any]:
        """Fetch open positions and closed trades, sync to SQLite, and return both lists."""
        self._load_session()
        if self._is_live() and self._kite is not None:
            try:
                positions_resp = self._kite.positions()
            except Exception as exc:
                if "TokenException" in type(exc).__name__ or "access_token" in str(exc):
                    self._invalidate_expired_session()
                    positions_resp = None
                else:
                    raise
        else:
            positions_resp = None

        if positions_resp is None:
            active_trades = [
                {
                    "tradingsymbol": "RELIANCE25MAY1200PE",
                    "symbol": "RELIANCE",
                    "strike": 1200.0,
                    "option_type": "PE",
                    "expiry": "25MAY",
                    "side": "SELL",
                    "qty": 500,
                    "entry_price": 28.0,
                    "current_price": 16.5,
                    "decay_pct": calculate_decay_pct(28.0, 16.5, "SELL"),
                    "unrealized_pnl": 5750.0,
                    "status": "OPEN",
                },
                {
                    "tradingsymbol": "INFY25MAY1400PE",
                    "symbol": "INFY",
                    "strike": 1400.0,
                    "option_type": "PE",
                    "expiry": "25MAY",
                    "side": "SELL",
                    "qty": 400,
                    "entry_price": 34.0,
                    "current_price": 16.75,
                    "decay_pct": calculate_decay_pct(34.0, 16.75, "SELL"),
                    "unrealized_pnl": 6900.0,
                    "status": "OPEN",
                },
            ]
            closed_trades = [
                {
                    "kite_trade_id": "DRY-TRD-2001",
                    "tradingsymbol": "TCS25MAY3400PE",
                    "symbol": "TCS",
                    "strike": 3400.0,
                    "option_type": "PE",
                    "expiry": "25MAY",
                    "side": "SELL",
                    "qty": 175,
                    "entry_price": 62.0,
                    "exit_price": 24.0,
                    "realized_pnl": 6650.0,
                    "decay_pct": calculate_decay_pct(62.0, 24.0, "SELL"),
                    "exit_reason": "50_PCT_DECAY_GTT",
                }
            ]
            self._sync_to_sqlite(active_trades, closed_trades)
            return {
                "mode": "dry_run",
                "is_dry_run": True,
                "active_trades": active_trades,
                "closed_trades": closed_trades,
            }
        net_positions = positions_resp.get("net", [])
        active_trades: list[dict[str, Any]] = []
        closed_trades: list[dict[str, Any]] = []

        for pos in net_positions:
            tradingsymbol = str(pos.get("tradingsymbol", ""))
            symbol, strike, option_type, expiry = parse_nfo_symbol(tradingsymbol)
            qty = int(pos.get("quantity", 0) or 0)
            last_price = float(pos.get("last_price", 0.0) or 0.0)

            if qty != 0:
                side = "SELL" if qty < 0 else "BUY"
                abs_qty = abs(qty)
                entry_price = float(pos.get("average_price", 0.0) or 0.0)
                active_trades.append(
                    {
                        "tradingsymbol": tradingsymbol,
                        "symbol": symbol,
                        "strike": strike,
                        "option_type": option_type,
                        "expiry": expiry,
                        "side": side,
                        "qty": abs_qty,
                        "entry_price": entry_price,
                        "current_price": last_price,
                        "decay_pct": calculate_decay_pct(entry_price, last_price, side),
                        "unrealized_pnl": float(pos.get("unrealised", pos.get("m2m", 0.0)) or 0.0),
                        "status": "OPEN",
                    }
                )
            else:
                sell_qty = int(pos.get("sell_quantity", 0) or 0)
                buy_qty = int(pos.get("buy_quantity", 0) or 0)
                closed_qty = max(sell_qty, buy_qty)
                if closed_qty == 0:
                    continue
                sell_price = float(pos.get("sell_price", 0.0) or 0.0)
                buy_price = float(pos.get("buy_price", 0.0) or 0.0)
                realized_pnl = float(pos.get("realised", pos.get("pnl", 0.0)) or 0.0)
                entry_price = sell_price if sell_price > 0 else buy_price
                exit_price = buy_price if sell_price > 0 else sell_price
                side = "SELL" if sell_price > 0 else "BUY"
                closed_trades.append(
                    {
                        "kite_trade_id": f"KITE-{tradingsymbol}-{closed_qty}",
                        "tradingsymbol": tradingsymbol,
                        "symbol": symbol,
                        "strike": strike,
                        "option_type": option_type,
                        "expiry": expiry,
                        "side": side,
                        "qty": closed_qty,
                        "entry_price": entry_price,
                        "exit_price": exit_price,
                        "realized_pnl": realized_pnl,
                        "decay_pct": calculate_decay_pct(entry_price, exit_price, side),
                        "exit_reason": "KITE_SYNC",
                    }
                )

        self._sync_to_sqlite(active_trades, closed_trades)
        return {
            "mode": "live",
            "is_dry_run": False,
            "active_trades": active_trades,
            "closed_trades": closed_trades,
        }

    def _sync_to_sqlite(
        self,
        active_trades: list[dict[str, Any]],
        closed_trades: list[dict[str, Any]],
    ) -> None:
        """Persist synced active positions and closed trades idempotently into SQLite."""
        with db_session(self.db_path) as conn:
            for item in active_trades:
                existing = conn.execute(
                    """
                    SELECT id FROM positions
                    WHERE symbol = ? AND strike = ? AND option_type = ? AND expiry = ?
                      AND side = ? AND status = 'OPEN'
                    LIMIT 1
                    """,
                    (
                        item["symbol"],
                        item["strike"],
                        item["option_type"],
                        item["expiry"],
                        item["side"],
                    ),
                ).fetchone()
                if existing:
                    conn.execute(
                        """
                        UPDATE positions
                        SET qty = ?, entry_price = ?, current_price = ?, decay_pct = ?,
                            updated_at = datetime('now')
                        WHERE id = ?
                        """,
                        (
                            item["qty"],
                            item["entry_price"],
                            item["current_price"],
                            item["decay_pct"],
                            existing["id"],
                        ),
                    )
                else:
                    conn.execute(
                        """
                        INSERT INTO positions (
                            symbol, strike, option_type, expiry, side, qty,
                            entry_price, current_price, decay_pct, status
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'OPEN')
                        """,
                        (
                            item["symbol"],
                            item["strike"],
                            item["option_type"],
                            item["expiry"],
                            item["side"],
                            item["qty"],
                            item["entry_price"],
                            item["current_price"],
                            item["decay_pct"],
                        ),
                    )

            for trade in closed_trades:
                conn.execute(
                    """
                    UPDATE positions
                    SET status = 'CLOSED', current_price = ?, decay_pct = ?,
                        realized_pnl = ?, closed_at = datetime('now'), updated_at = datetime('now')
                    WHERE symbol = ? AND strike = ? AND option_type = ? AND expiry = ?
                      AND side = ? AND status = 'OPEN'
                    """,
                    (
                        trade["exit_price"],
                        trade["decay_pct"],
                        trade["realized_pnl"],
                        trade["symbol"],
                        trade["strike"],
                        trade["option_type"],
                        trade["expiry"],
                        trade["side"],
                    ),
                )

                kite_trade_id = trade.get("kite_trade_id")
                existing_hist = None
                if kite_trade_id:
                    existing_hist = conn.execute(
                        "SELECT id FROM trades_history WHERE kite_trade_id = ? LIMIT 1",
                        (kite_trade_id,),
                    ).fetchone()
                if not existing_hist:
                    conn.execute(
                        """
                        INSERT INTO trades_history (
                            symbol, strike, option_type, expiry, side, qty,
                            entry_price, exit_price, realized_pnl, decay_pct,
                            exit_reason, kite_trade_id
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            trade["symbol"],
                            trade["strike"],
                            trade["option_type"],
                            trade["expiry"],
                            trade["side"],
                            trade["qty"],
                            trade["entry_price"],
                            trade["exit_price"],
                            trade["realized_pnl"],
                            trade["decay_pct"],
                            trade.get("exit_reason", "KITE_SYNC"),
                            kite_trade_id,
                        ),
                    )

    @staticmethod
    def _build_dry_run_quotes(cleaned: list[str]) -> dict[str, dict[str, Any]]:
        quotes: dict[str, Any] = {}
        for idx, inst in enumerate(cleaned):
            if inst.startswith("NFO:"):
                base_bid = 24.0 + idx * 5.0
                base_ask = round(base_bid * 1.025, 2)
                last_price = round((base_bid + base_ask) / 2, 2)
                ohlc = {
                    "open": round(last_price * 1.02, 2),
                    "high": round(last_price * 1.04, 2),
                    "low": round(last_price * 0.98, 2),
                    "close": round(last_price * 1.03, 2),
                }
            else:
                spot_base = 1200.0 + (idx % 10) * 150.0
                base_bid = round(spot_base - 0.5, 2)
                base_ask = round(spot_base + 0.5, 2)
                last_price = spot_base
                ohlc = {
                    "open": round(spot_base * 1.01, 2),
                    "high": round(spot_base * 1.015, 2),
                    "low": round(spot_base * 0.99, 2),
                    "close": round(spot_base * 1.012, 2),
                }
            quotes[inst] = {
                "instrument": inst,
                "instrument_token": 100000 + idx,
                "last_price": last_price,
                "best_bid": base_bid,
                "best_ask": base_ask,
                "bid_ask_spread_pct": calculate_spread_pct(base_bid, base_ask),
                "volume": 125000,
                "oi": 450000,
                "ohlc": ohlc,
            }
        return quotes

    def get_quote(self, instruments: list[str]) -> dict[str, Any]:
        """Fetch read-only quotes with best bid/ask and bid_ask_spread_pct."""
        cleaned = [sym.strip() for sym in instruments if sym.strip()]
        if not cleaned:
            return {"mode": "dry_run" if not self._is_live() else "live", "is_dry_run": not self._is_live(), "quotes": {}}

        self._load_session()
        if not self._is_live() or self._kite is None:
            return {"mode": "dry_run", "is_dry_run": True, "quotes": self._build_dry_run_quotes(cleaned)}

        try:
            raw_quotes = self._kite.quote(cleaned)
        except Exception as exc:
            return {
                "mode": "dry_run",
                "is_dry_run": True,
                "quotes": self._build_dry_run_quotes(cleaned),
                "quote_fallback_reason": f"Kite quote unavailable ({type(exc).__name__}); using fallback quote.",
            }
        quotes = {}
        for inst, data in raw_quotes.items():
            depth = data.get("depth", {})
            buy_depth = depth.get("buy", [])
            sell_depth = depth.get("sell", [])
            best_bid = float(buy_depth[0].get("price", 0.0) or 0.0) if buy_depth else 0.0
            best_ask = float(sell_depth[0].get("price", 0.0) or 0.0) if sell_depth else 0.0
            quotes[inst] = {
                "instrument": inst,
                "instrument_token": int(data.get("instrument_token", 0) or 0),
                "last_price": float(data.get("last_price", 0.0) or 0.0),
                "best_bid": best_bid,
                "best_ask": best_ask,
                "bid_ask_spread_pct": calculate_spread_pct(best_bid, best_ask),
                "volume": int(data.get("volume", 0) or 0),
                "oi": int(data.get("oi", 0) or 0),
                "ohlc": data.get("ohlc", {}),
            }
        return {"mode": "live", "is_dry_run": False, "quotes": quotes}

    def get_historical_daily(
        self,
        instrument_token: int,
        days: int = 365,
        from_date: datetime | None = None,
        to_date: datetime | None = None,
    ) -> list[dict[str, Any]]:
        """Fetch daily OHLC candles for an instrument_token with offline/dry-run fallback."""
        end_dt = to_date or datetime.now(timezone.utc)
        start_dt = from_date or (end_dt - timedelta(days=max(1, days)))
        self._load_session()
        if self._is_live() and self._kite is not None and instrument_token > 0:
            try:
                candles = self._kite.historical_data(instrument_token, start_dt, end_dt, "day")
                return list(candles or [])
            except Exception as exc:
                if "TokenException" in type(exc).__name__ or "access_token" in str(exc):
                    self._invalidate_expired_session()

        # Deterministic offline/dry-run daily candles fallback
        total_days = max(1, min((end_dt - start_dt).days or days, 365))
        base_price = 1200.0 + (instrument_token % 10) * 150.0
        candles: list[dict[str, Any]] = []
        for idx in range(total_days):
            candle_dt = start_dt + timedelta(days=idx)
            wave = ((idx % 14) - 7) * 0.004
            close_px = round(base_price * (1.0 + wave), 2)
            candles.append(
                {
                    "date": candle_dt.isoformat(),
                    "open": round(close_px * 1.003, 2),
                    "high": round(close_px * 1.015, 2),
                    "low": round(close_px * 0.985, 2),
                    "close": close_px,
                    "volume": 100000 + idx * 250,
                }
            )
        return candles

    def get_nfo_instruments(self) -> list[dict[str, Any]]:
        """Fetch NFO instruments list with offline/dry-run fallback."""
        self._load_session()
        if self._is_live() and self._kite is not None:
            try:
                return list(self._kite.instruments("NFO") or [])
            except Exception as exc:
                if "TokenException" in type(exc).__name__ or "access_token" in str(exc):
                    self._invalidate_expired_session()

        # Deterministic dry-run NFO PE sample instruments for equities & indices
        expiry = (date.today() + timedelta(days=21)).isoformat()
        samples = [
            ("RELIANCE", 1200.0, 500),
            ("INFY", 1400.0, 400),
            ("TCS", 3400.0, 175),
            ("HDFCBANK", 1600.0, 550),
            ("ICICIBANK", 1200.0, 700),
            ("NIFTY", 24000.0, 75),
            ("BANKNIFTY", 51000.0, 30),
            ("FINNIFTY", 23000.0, 65),
            ("MIDCPNIFTY", 12000.0, 120),
        ]
        expiry_code = (date.today() + timedelta(days=21)).strftime("%y%b").upper()
        return [
            {
                "instrument_token": 500000 + idx,
                "exchange": "NFO",
                "segment": "NFO-OPT",
                "name": sym,
                "tradingsymbol": f"{sym}{expiry_code}{int(strike)}PE",
                "strike": strike,
                "instrument_type": "PE",
                "expiry": expiry,
                "lot_size": lot_size,
            }
            for idx, (sym, strike, lot_size) in enumerate(samples)
        ]

    @staticmethod
    def _parse_expiry_date(raw_expiry: Any) -> date | None:
        if isinstance(raw_expiry, datetime):
            return raw_expiry.date()
        if isinstance(raw_expiry, date):
            return raw_expiry
        if isinstance(raw_expiry, str) and raw_expiry.strip():
            try:
                return date.fromisoformat(raw_expiry.strip()[:10])
            except ValueError:
                return None
        return None

    def find_atm_or_lbl_put(
        self,
        symbol: str,
        target_strike: float,
        nfo_instruments: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any] | None:
        """Find nearest-expiry NFO PE option at or just below target_strike (ATM/LBL)."""
        sym = symbol.strip().upper()
        instruments = nfo_instruments if nfo_instruments is not None else self.get_nfo_instruments()
        today = date.today()

        puts = [
            inst
            for inst in instruments
            if str(inst.get("name") or "").strip().upper() == sym
            and str(inst.get("instrument_type") or "").strip().upper() == "PE"
        ]
        if not puts:
            return None

        # Prefer upcoming expiries >= today; fall back to all puts if expiry unparseable
        dated_puts: list[tuple[date, dict[str, Any]]] = []
        for inst in puts:
            exp_dt = self._parse_expiry_date(inst.get("expiry"))
            if exp_dt is not None and exp_dt >= today:
                dated_puts.append((exp_dt, inst))

        if dated_puts:
            nearest_expiry = min(exp_dt for exp_dt, _ in dated_puts)
            candidates = [inst for exp_dt, inst in dated_puts if exp_dt == nearest_expiry]
        else:
            candidates = puts

        below_or_equal = [
            inst for inst in candidates if float(inst.get("strike") or 0.0) <= target_strike
        ]
        if below_or_equal:
            return max(below_or_equal, key=lambda inst: float(inst.get("strike") or 0.0))

        return min(
            candidates,
            key=lambda inst: abs(float(inst.get("strike") or 0.0) - target_strike),
        )
