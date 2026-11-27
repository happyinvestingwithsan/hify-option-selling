"""Screener.in Fundamental Fetcher & SQLite Cache (Standalone for OptionSelling)."""

from __future__ import annotations

import json
import math
import re
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any

from app.db import db_session
from app.kite_client import KiteService
from app.services.universe import BASELINE_INDICES, list_universe_stocks

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"


def _fetch_text(url: str, timeout: int = 12) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", errors="ignore")


def _extract_last_pct(section: str, label: str) -> float | None:
    idx = section.find(label)
    if idx == -1:
        return None
    snippet = section[idx : idx + 600]
    matches = re.findall(r"([\d.]+)\s*%", snippet)
    return float(matches[-1]) if matches else None


def _extract_top_ratio(html: str, name_fragment: str) -> float | None:
    for m in re.finditer(r"<li[^>]*>([\s\S]*?)</li>", html, re.I):
        block = m.group(1)
        if name_fragment.lower() in block.lower():
            num_m = re.search(r'<span class="number">([\d,.\-]+)</span>', block, re.I)
            if num_m:
                try:
                    return float(num_m.group(1).replace(",", ""))
                except ValueError:
                    return None
    return None


def _extract_pl_peaks(html: str) -> tuple[float | None, float | None, float | None, float | None, float | None]:
    """Return (peak_sales_10y, latest_sales, peak_pat_10y, latest_pat, interest_coverage)."""
    pl_idx = html.find('id="profit-loss"')
    if pl_idx == -1:
        return None, None, None, None, None
    sec = html[pl_idx : pl_idx + 25000]
    rows = re.findall(r"<tr[^>]*>([\s\S]*?)</tr>", sec, re.I)
    sales_vals: list[float] = []
    pat_vals: list[float] = []
    op_profit: float | None = None
    interest: float | None = None

    for row in rows:
        tds = [re.sub(r"<[^>]+>", "", td).strip() for td in re.findall(r"<td[^>]*>([\s\S]*?)</td>", row, re.I)]
        if len(tds) < 2:
            continue
        hdr = tds[0].lower()
        nums: list[float] = []
        for val in tds[1:]:
            cleaned = val.replace(",", "").replace("%", "").strip()
            try:
                nums.append(float(cleaned))
            except ValueError:
                continue
        if not nums:
            continue
        if hdr.startswith("sales") or hdr.startswith("revenue"):
            sales_vals = [v for v in nums if v > 0]
        elif "net profit" in hdr:
            pat_vals = nums
        elif "operating profit" in hdr and op_profit is None:
            op_profit = nums[-1]
        elif hdr.startswith("interest") and interest is None:
            interest = abs(nums[-1])

    peak_sales = max(sales_vals) if sales_vals else None
    latest_sales = sales_vals[-1] if sales_vals else None
    peak_pat = max(pat_vals) if pat_vals else None
    latest_pat = pat_vals[-1] if pat_vals else None
    icr = (op_profit / interest) if (op_profit is not None and interest and interest > 0) else (99.0 if op_profit is not None else None)
    return peak_sales, latest_sales, peak_pat, latest_pat, icr


def evaluate_fundamental_checks(record: dict[str, Any]) -> dict[str, bool | None]:
    """Return per-gate fundamental pass/fail flags without hiding rows."""
    pub = record.get("public_holding_pct")
    pledge = record.get("promoter_pledge_pct")
    pe = record.get("current_pe")
    pe5 = record.get("pe_median_5y")
    roce = record.get("roce_pct")
    roe = record.get("roe_pct")
    d_e = record.get("debt_to_equity")

    if roce is None and roe is None:
        roce_or_roe_ok: bool | None = None
    else:
        roce_or_roe_ok = bool(
            (roce is not None and roce >= 12.0) or (roe is not None and roe >= 10.0)
        )

    return {
        "public_lt_30": None if pub is None else pub < 30.0,
        "pledge_lt_5": None if pledge is None else pledge < 5.0,
        "pe_lt_70": None if pe is None else pe < 70.0,
        "pe_lt_5y_median": None if (pe is None or pe5 is None) else pe < pe5,
        "roce_or_roe_ok": roce_or_roe_ok,
        "de_le_025": None if d_e is None else d_e <= 0.25,
    }


def evaluate_fundamental_pass(record: dict[str, Any]) -> bool:
    """Evaluate cached fundamental record against Rulebook + 1.8.6 equity gates."""
    checks = evaluate_fundamental_checks(record)
    return all(flag is not False for flag in checks.values())


def fetch_and_cache_fundamentals(symbol: str, db_path: str | Path | None = None) -> dict[str, Any]:
    """Fetch Screener.in consolidated page + Median PE chart API and cache in SQLite."""
    sym = symbol.strip().upper()
    if not re.fullmatch(r"[A-Z0-9&-]{1,30}", sym):
        raise ValueError(f"Invalid NSE symbol '{symbol}'.")
    html = ""
    try:
        html = _fetch_text(f"https://www.screener.in/company/{sym}/consolidated/")
    except Exception:
        html = _fetch_text(f"https://www.screener.in/company/{sym}/")

    m_id = re.search(r'data-company-id=["\'](\d+)["\']', html, re.I)
    company_id = m_id.group(1) if m_id else None

    sh_idx = html.find('id="shareholding"')
    sh_sec = html[sh_idx : sh_idx + 15000] if sh_idx != -1 else ""
    public_pct = _extract_last_pct(sh_sec, "Public")
    pledge_pct = _extract_last_pct(sh_sec, "Pledged")
    inst_pct = round(100.0 - public_pct, 2) if public_pct is not None else None

    market_cap = _extract_top_ratio(html, "Market Cap")
    current_pe = _extract_top_ratio(html, "Stock P/E")
    roce_pct = _extract_top_ratio(html, "ROCE")
    roe_pct = _extract_top_ratio(html, "ROE")
    debt_eq = _extract_top_ratio(html, "Debt to equity")

    cap_tier = "large"
    if market_cap is not None:
        if market_cap < 5000:
            cap_tier = "small"
        elif market_cap < 20000:
            cap_tier = "mid"

    pe3 = pe5 = pe10 = None
    if company_id:
        for days, key in ((1095, "3y"), (1825, "5y"), (3650, "10y")):
            try:
                raw = _fetch_text(
                    f"https://www.screener.in/api/company/{company_id}/chart/?q=Price+to+Earning-Median+PE-EPS&days={days}&consolidated=true"
                )
                payload = json.loads(raw)
                ds = next((d for d in payload.get("datasets", []) if d.get("metric") == "Median PE"), None)
                if ds and ds.get("values"):
                    val = float(ds["values"][-1][1])
                    if key == "3y":
                        pe3 = val
                    elif key == "5y":
                        pe5 = val
                    else:
                        pe10 = val
            except Exception:
                continue

    peak_sales, latest_sales, peak_pat, latest_pat, icr = _extract_pl_peaks(html)
    record: dict[str, Any] = {
        "symbol": sym,
        "market_cap_cr": market_cap,
        "cap_tier": cap_tier,
        "current_pe": current_pe,
        "pe_median_3y": pe3,
        "pe_median_5y": pe5,
        "pe_median_10y": pe10,
        "roce_pct": roce_pct,
        "roe_pct": roe_pct,
        "debt_to_equity": debt_eq,
        "net_debt_to_equity": debt_eq,
        "public_holding_pct": public_pct,
        "institutional_holding_pct": inst_pct,
        "promoter_pledge_pct": pledge_pct if pledge_pct is not None else 0.0,
        "peak_sales_10y": peak_sales,
        "latest_sales": latest_sales,
        "peak_pat_10y": peak_pat,
        "latest_pat": latest_pat,
        "interest_coverage": icr,
        "is_psu": 0,
    }
    record["fundamental_passed"] = 1 if evaluate_fundamental_pass(record) else 0

    with db_session(db_path) as conn:
        conn.execute(
            """
            INSERT INTO fundamentals_cache (
                symbol, market_cap_cr, cap_tier, current_pe, pe_median_3y, pe_median_5y, pe_median_10y,
                roce_pct, roe_pct, debt_to_equity, net_debt_to_equity, public_holding_pct,
                institutional_holding_pct, promoter_pledge_pct, peak_sales_10y, latest_sales,
                peak_pat_10y, latest_pat, interest_coverage, is_psu, fundamental_passed, updated_at
            ) VALUES (
                :symbol, :market_cap_cr, :cap_tier, :current_pe, :pe_median_3y, :pe_median_5y, :pe_median_10y,
                :roce_pct, :roe_pct, :debt_to_equity, :net_debt_to_equity, :public_holding_pct,
                :institutional_holding_pct, :promoter_pledge_pct, :peak_sales_10y, :latest_sales,
                :peak_pat_10y, :latest_pat, :interest_coverage, :is_psu, :fundamental_passed, datetime('now')
            )
            ON CONFLICT(symbol) DO UPDATE SET
                market_cap_cr=excluded.market_cap_cr, cap_tier=excluded.cap_tier,
                current_pe=excluded.current_pe, pe_median_3y=excluded.pe_median_3y,
                pe_median_5y=excluded.pe_median_5y, pe_median_10y=excluded.pe_median_10y,
                roce_pct=excluded.roce_pct, roe_pct=excluded.roe_pct,
                debt_to_equity=excluded.debt_to_equity, net_debt_to_equity=excluded.net_debt_to_equity,
                public_holding_pct=excluded.public_holding_pct,
                institutional_holding_pct=excluded.institutional_holding_pct,
                promoter_pledge_pct=excluded.promoter_pledge_pct,
                peak_sales_10y=excluded.peak_sales_10y, latest_sales=excluded.latest_sales,
                peak_pat_10y=excluded.peak_pat_10y, latest_pat=excluded.latest_pat,
                interest_coverage=excluded.interest_coverage,
                fundamental_passed=excluded.fundamental_passed, updated_at=datetime('now')
            """,
            record,
        )
    return record


def get_cached_fundamentals(symbol: str, db_path: str | Path | None = None) -> dict[str, Any] | None:
    """Return cached fundamentals row for symbol if present."""
    with db_session(db_path) as conn:
        row = conn.execute(
            "SELECT * FROM fundamentals_cache WHERE symbol = ?",
            (symbol.strip().upper(),),
        ).fetchone()
    return dict(row) if row else None


def get_all_cached_fundamentals(db_path: str | Path | None = None) -> dict[str, dict[str, Any]]:
    """Return all cached fundamentals keyed by uppercase symbol."""
    with db_session(db_path) as conn:
        rows = conn.execute("SELECT * FROM fundamentals_cache").fetchall()
    return {str(r["symbol"]).upper(): dict(r) for r in rows}


def upsert_technicals_cache(records: list[dict[str, Any]], db_path: str | Path | None = None) -> int:
    """Upsert scanner technicals and option quote snapshots into scanner_technicals_cache."""
    if not records:
        return 0
    count = 0
    with db_session(db_path) as conn:
        for rec in records:
            payload = {
                "symbol": str(rec["symbol"]).strip().upper(),
                "instrument_type": rec.get("instrument_type", "EQ"),
                "current_price": rec.get("current_price"),
                "open_price": rec.get("open_price"),
                "high_price": rec.get("high_price"),
                "low_price": rec.get("low_price"),
                "prev_close": rec.get("prev_close"),
                "ath_price": rec.get("ath_price"),
                "high_52w": rec.get("high_52w"),
                "sma_200": rec.get("sma_200"),
                "lower_blue_line": rec.get("lower_blue_line"),
                "is_red_candle": int(rec.get("is_red_candle", 0) or 0),
                "intraday_drop_pct": float(rec.get("intraday_drop_pct", 0.0) or 0.0),
                "hv_20": float(rec.get("hv_20", 0.0) or 0.0),
                "iv_pct": float(rec.get("iv_pct", 0.0) or 0.0),
                "hv_spike_ratio": float(rec.get("hv_spike_ratio", 1.0) or 1.0),
                "option_instrument": rec.get("option_instrument"),
                "option_strike": rec.get("option_strike"),
                "option_expiry": rec.get("option_expiry"),
                "option_bid": float(rec.get("option_bid", 0.0) or 0.0),
                "option_ask": float(rec.get("option_ask", 0.0) or 0.0),
                "bid_ask_spread_pct": float(rec.get("bid_ask_spread_pct", 0.0) or 0.0),
                "premium": float(rec.get("premium", 0.0) or 0.0),
                "lot_size": int(rec.get("lot_size", 0) or 0),
                "margin_required": float(rec.get("margin_required", 0.0) or 0.0),
                "data_source": str(rec.get("data_source", "cached")),
            }
            conn.execute(
                """
                INSERT INTO scanner_technicals_cache (
                    symbol, instrument_type, current_price, open_price, high_price, low_price,
                    prev_close, ath_price, high_52w, sma_200, lower_blue_line,
                    is_red_candle, intraday_drop_pct, hv_20, iv_pct, hv_spike_ratio,
                    option_instrument, option_strike, option_expiry, option_bid, option_ask,
                    bid_ask_spread_pct, premium, lot_size, margin_required, data_source, updated_at
                ) VALUES (
                    :symbol, :instrument_type, :current_price, :open_price, :high_price, :low_price,
                    :prev_close, :ath_price, :high_52w, :sma_200, :lower_blue_line,
                    :is_red_candle, :intraday_drop_pct, :hv_20, :iv_pct, :hv_spike_ratio,
                    :option_instrument, :option_strike, :option_expiry, :option_bid, :option_ask,
                    :bid_ask_spread_pct, :premium, :lot_size, :margin_required, :data_source, datetime('now')
                )
                ON CONFLICT(symbol) DO UPDATE SET
                    instrument_type=excluded.instrument_type,
                    current_price=excluded.current_price,
                    open_price=excluded.open_price,
                    high_price=excluded.high_price,
                    low_price=excluded.low_price,
                    prev_close=excluded.prev_close,
                    ath_price=excluded.ath_price,
                    high_52w=excluded.high_52w,
                    sma_200=excluded.sma_200,
                    lower_blue_line=excluded.lower_blue_line,
                    is_red_candle=excluded.is_red_candle,
                    intraday_drop_pct=excluded.intraday_drop_pct,
                    hv_20=excluded.hv_20,
                    iv_pct=excluded.iv_pct,
                    hv_spike_ratio=excluded.hv_spike_ratio,
                    option_instrument=excluded.option_instrument,
                    option_strike=excluded.option_strike,
                    option_expiry=excluded.option_expiry,
                    option_bid=excluded.option_bid,
                    option_ask=excluded.option_ask,
                    bid_ask_spread_pct=excluded.bid_ask_spread_pct,
                    premium=excluded.premium,
                    lot_size=excluded.lot_size,
                    margin_required=excluded.margin_required,
                    data_source=excluded.data_source,
                    updated_at=datetime('now')
                """,
                payload,
            )
            count += 1
    return count


def get_all_technicals_cache(db_path: str | Path | None = None) -> dict[str, dict[str, Any]]:
    """Return all cached scanner technicals keyed by uppercase symbol."""
    with db_session(db_path) as conn:
        rows = conn.execute("SELECT * FROM scanner_technicals_cache").fetchall()
    return {str(r["symbol"]).upper(): dict(r) for r in rows}


def _compute_hv(closes: list[float], window: int) -> float:
    if len(closes) < window + 1:
        return 0.0
    sub = closes[-(window + 1) :]
    returns = [
        math.log(sub[i] / sub[i - 1])
        for i in range(1, len(sub))
        if sub[i - 1] > 0 and sub[i] > 0
    ]
    if len(returns) < 2:
        return 0.0
    mean_r = sum(returns) / len(returns)
    variance = sum((r - mean_r) ** 2 for r in returns) / (len(returns) - 1)
    return round(math.sqrt(variance) * math.sqrt(252.0) * 100.0, 2)


def hydrate_scanner_cache(
    symbols: list[str] | None = None,
    include_indices: bool = True,
    fetch_fundamentals: bool = False,
    kite_service: KiteService | None = None,
    db_path: str | Path | None = None,
) -> dict[str, Any]:
    """Hydrate scanner_technicals_cache (and optionally fundamentals_cache) for universe + indices."""
    index_map = {item["symbol"]: item for item in BASELINE_INDICES}
    universe_lot_map: dict[str, int] = {}
    for row in list_universe_stocks(db_path=db_path):
        sym_u = str(row["symbol"]).upper()
        if int(row.get("lot_size") or 0) > 0:
            universe_lot_map[sym_u] = int(row["lot_size"])

    targets: list[tuple[str, str]] = []
    seen: set[str] = set()
    if symbols is not None:
        for raw in symbols:
            sym = raw.strip().upper()
            if sym and sym not in seen:
                seen.add(sym)
                inst_type = "INDEX" if sym in index_map else "EQ"
                targets.append((sym, inst_type))
    else:
        for row in list_universe_stocks(db_path=db_path):
            sym = str(row["symbol"]).strip().upper()
            if sym and sym not in seen:
                seen.add(sym)
                targets.append((sym, "EQ"))
        if include_indices:
            for item in BASELINE_INDICES:
                sym = item["symbol"]
                if sym not in seen:
                    seen.add(sym)
                    targets.append((sym, "INDEX"))

    fundamentals_fetched = 0
    fundamentals_errors = 0
    if fetch_fundamentals:
        for sym, inst_type in targets:
            if inst_type != "EQ":
                continue
            try:
                fetch_and_cache_fundamentals(sym, db_path=db_path)
                fundamentals_fetched += 1
            except Exception:
                fundamentals_errors += 1

    service = kite_service or KiteService(db_path=db_path)
    spot_map: dict[str, str] = {}
    for sym, inst_type in targets:
        if inst_type == "INDEX" and sym in index_map:
            spot_map[sym] = index_map[sym]["kite_spot"]
        else:
            spot_map[sym] = f"NSE:{sym}"

    spot_quotes: dict[str, dict[str, Any]] = {}
    data_source = "dry_run"
    spot_instruments = list(spot_map.values())
    for i in range(0, len(spot_instruments), 200):
        chunk = spot_instruments[i : i + 200]
        resp = service.get_quote(chunk)
        if not resp.get("is_dry_run", True):
            data_source = "live"
        spot_quotes.update(resp.get("quotes", {}))

    if data_source != "live":
        from app.angel_client import AngelDataService

        angel = AngelDataService()
        if angel.ensure_session():
            return _hydrate_via_angel(
                targets=targets,
                index_map=index_map,
                universe_lot_map=universe_lot_map,
                angel=angel,
                fundamentals_fetched=fundamentals_fetched,
                fundamentals_errors=fundamentals_errors,
                db_path=db_path,
            )

    nfo_instruments = service.get_nfo_instruments()

    staged_records: list[dict[str, Any]] = []
    option_instruments: list[str] = []
    for sym, inst_type in targets:
        spot_key = spot_map[sym]
        q = spot_quotes.get(spot_key, {})
        ohlc = q.get("ohlc", {}) or {}
        current_price = float(q.get("last_price") or 0.0)
        open_price = float(ohlc.get("open") or current_price)
        high_price = float(ohlc.get("high") or current_price)
        low_price = float(ohlc.get("low") or current_price)
        prev_close = float(ohlc.get("close") or current_price)
        is_red_candle = 1 if (open_price > 0 and current_price < open_price) else 0
        intraday_drop_pct = (
            round(((prev_close - current_price) / prev_close) * 100.0, 2)
            if (prev_close > 0 and current_price < prev_close)
            else 0.0
        )

        token = int(q.get("instrument_token") or 0)
        candles = service.get_historical_daily(token, days=365) if token > 0 else []
        closes = [float(c["close"]) for c in candles if c.get("close")]
        highs = [float(c["high"]) for c in candles if c.get("high")]
        lows = [float(c["low"]) for c in candles if c.get("low")]

        ath_price = round(max(highs), 2) if highs else current_price
        high_52w = round(max(highs[-252:]), 2) if highs else current_price
        sma_200 = round(sum(closes[-200:]) / len(closes[-200:]), 2) if closes else current_price
        lower_blue_line = round(sma_200 * 0.86, 2) if sma_200 > 0 else round(current_price * 0.86, 2)
        hv_20 = _compute_hv(closes, 20)
        hv_5 = _compute_hv(closes, 5)
        hv_spike_ratio = round(hv_5 / hv_20, 2) if hv_20 > 0 and hv_5 > 0 else 1.0

        nfo_prefix = index_map[sym]["nfo_prefix"] if inst_type == "INDEX" and sym in index_map else sym
        target_strike = lower_blue_line or current_price
        opt = service.find_atm_or_lbl_put(nfo_prefix, target_strike, nfo_instruments=nfo_instruments)

        lot_size = (
            int(opt.get("lot_size") or 0)
            if opt
            else (index_map[sym]["lot_size"] if inst_type == "INDEX" and sym in index_map else universe_lot_map.get(sym, 0))
        )
        opt_tradingsymbol = str(opt.get("tradingsymbol")) if opt else None
        if opt_tradingsymbol:
            option_instruments.append(f"NFO:{opt_tradingsymbol}")

        staged_records.append(
            {
                "symbol": sym,
                "instrument_type": inst_type,
                "current_price": current_price,
                "open_price": open_price,
                "high_price": high_price,
                "low_price": low_price,
                "prev_close": prev_close,
                "ath_price": ath_price,
                "high_52w": high_52w,
                "sma_200": sma_200,
                "lower_blue_line": lower_blue_line,
                "is_red_candle": is_red_candle,
                "intraday_drop_pct": intraday_drop_pct,
                "hv_20": hv_20,
                "iv_pct": round(hv_20 * 1.05, 2) if hv_20 > 0 else 0.0,
                "hv_spike_ratio": hv_spike_ratio,
                "option_instrument": opt_tradingsymbol,
                "option_strike": float(opt["strike"]) if opt and opt.get("strike") is not None else None,
                "option_expiry": str(opt["expiry"]) if opt and opt.get("expiry") is not None else None,
                "option_bid": 0.0,
                "option_ask": 0.0,
                "bid_ask_spread_pct": 0.0,
                "premium": 0.0,
                "lot_size": lot_size,
                "margin_required": 0.0,
                "data_source": data_source,
            }
        )

    option_quotes: dict[str, dict[str, Any]] = {}
    unique_opt_insts = list(dict.fromkeys(option_instruments))
    for i in range(0, len(unique_opt_insts), 200):
        chunk = unique_opt_insts[i : i + 200]
        resp = service.get_quote(chunk)
        if resp.get("is_dry_run"):
            for rec in staged_records:
                rec["data_source"] = "dry_run"
        option_quotes.update(resp.get("quotes", {}))

    for rec in staged_records:
        opt_sym = rec.get("option_instrument")
        if opt_sym:
            oq = option_quotes.get(f"NFO:{opt_sym}", {})
            bid = float(oq.get("best_bid") or 0.0)
            ask = float(oq.get("best_ask") or 0.0)
            last_px = float(oq.get("last_price") or 0.0)
            rec["option_bid"] = bid
            rec["option_ask"] = ask
            rec["bid_ask_spread_pct"] = float(oq.get("bid_ask_spread_pct") or 0.0)
            rec["premium"] = bid if bid > 0 else last_px
        strike_val = float(rec.get("option_strike") or 0.0)
        lot_val = int(rec.get("lot_size") or 0)
        if strike_val > 0 and lot_val > 0:
            rec["margin_required"] = round(strike_val * lot_val * 0.20, 2)

    hydrated = upsert_technicals_cache(staged_records, db_path=db_path)
    return {
        "hydrated": hydrated,
        "eq_count": sum(1 for _, t in targets if t == "EQ"),
        "index_count": sum(1 for _, t in targets if t == "INDEX"),
        "fundamentals_fetched": fundamentals_fetched,
        "fundamentals_errors": fundamentals_errors,
        "data_source": data_source,
    }


def _hydrate_via_angel(
    *,
    targets: list[tuple[str, str]],
    index_map: dict[str, dict[str, Any]],
    universe_lot_map: dict[str, int],
    angel: Any,
    fundamentals_fetched: int,
    fundamentals_errors: int,
    db_path: str | Path | None = None,
) -> dict[str, Any]:
    """Hydrate scanner_technicals_cache using read-only Angel One SmartAPI live quotes & 5Y candles."""
    import time as _time

    spot_tokens: dict[str, str] = {}
    for sym, inst_type in targets:
        tok = angel.get_spot_token(sym, instrument_type=inst_type)
        if tok:
            spot_tokens[sym] = tok

    spot_quotes = angel.get_market_quotes("NSE", list(spot_tokens.values()))
    existing_cache = get_all_technicals_cache(db_path=db_path)
    today_prefix = datetime.now().strftime("%Y-%m-%d")
    staged_records: list[dict[str, Any]] = []
    opt_tokens: list[str] = []

    for idx_pos, (sym, inst_type) in enumerate(targets):
        tok = spot_tokens.get(sym)
        q = spot_quotes.get(tok, {}) if tok else {}
        current_price = float(q.get("last_price") or 0.0)
        if current_price <= 0:
            continue
        open_price = float(q.get("open") or current_price)
        high_price = float(q.get("high") or current_price)
        low_price = float(q.get("low") or current_price)
        prev_close = float(q.get("close") or current_price)
        is_red_candle = 1 if (open_price > 0 and current_price < open_price) else 0
        intraday_drop_pct = (
            round(((prev_close - current_price) / prev_close) * 100.0, 2)
            if (prev_close > 0 and current_price < prev_close)
            else 0.0
        )

        cached_row = existing_cache.get(sym)
        has_today_hist = bool(
            cached_row
            and cached_row.get("data_source") == "live"
            and str(cached_row.get("updated_at") or "").startswith(today_prefix)
            and float(cached_row.get("ath_price") or 0.0) > 0
            and float(cached_row.get("sma_200") or 0.0) > 0
        )

        if has_today_hist and cached_row:
            ath_price = round(max(float(cached_row["ath_price"]), high_price), 2)
            q_52w = float(q.get("week52_high") or 0.0)
            high_52w = round(q_52w if q_52w > 0 else float(cached_row.get("high_52w") or ath_price), 2)
            sma_200 = float(cached_row["sma_200"])
            lower_blue_line = float(cached_row.get("lower_blue_line") or round(sma_200 * 0.86, 2))
            hv_20 = float(cached_row.get("hv_20") or 0.0)
            hv_spike_ratio = float(cached_row.get("hv_spike_ratio") or 1.0)
        else:
            candles = angel.get_historical_daily(tok, exchange="NSE", days=1825) if tok else []
            if idx_pos + 1 < len(targets):
                _time.sleep(0.25)

            closes = [float(c["close"]) for c in candles if c.get("close")]
            highs = [float(c["high"]) for c in candles if c.get("high")]
            ath_price = round(max(highs), 2) if highs else current_price
            q_52w = float(q.get("week52_high") or 0.0)
            high_52w = round(q_52w if q_52w > 0 else (max(highs[-252:]) if highs else current_price), 2)
            sma_200 = round(sum(closes[-200:]) / len(closes[-200:]), 2) if closes else current_price
            lower_blue_line = round(sma_200 * 0.86, 2) if sma_200 > 0 else round(current_price * 0.86, 2)
            hv_20 = _compute_hv(closes, 20)
            hv_5 = _compute_hv(closes, 5)
            hv_spike_ratio = round(hv_5 / hv_20, 2) if hv_20 > 0 and hv_5 > 0 else 1.0

        nfo_prefix = index_map[sym].get("nfo_prefix", sym) if inst_type == "INDEX" and sym in index_map else sym
        opt = angel.find_atm_or_lbl_put(nfo_prefix, lower_blue_line or current_price)

        lot_size = (
            int(opt.get("lot_size") or 0)
            if opt and int(opt.get("lot_size") or 0) > 0
            else (index_map[sym]["lot_size"] if inst_type == "INDEX" and sym in index_map else universe_lot_map.get(sym, 0))
        )
        opt_token = str(opt["token"]) if opt and opt.get("token") else None
        if opt_token:
            opt_tokens.append(opt_token)

        staged_records.append(
            {
                "symbol": sym,
                "instrument_type": inst_type,
                "current_price": current_price,
                "open_price": open_price,
                "high_price": high_price,
                "low_price": low_price,
                "prev_close": prev_close,
                "ath_price": ath_price,
                "high_52w": high_52w,
                "sma_200": sma_200,
                "lower_blue_line": lower_blue_line,
                "is_red_candle": is_red_candle,
                "intraday_drop_pct": intraday_drop_pct,
                "hv_20": hv_20,
                "iv_pct": round(hv_20 * 1.05, 2) if hv_20 > 0 else 0.0,
                "hv_spike_ratio": hv_spike_ratio,
                "option_instrument": str(opt["tradingsymbol"]) if opt else None,
                "option_token": opt_token,
                "option_strike": float(opt["strike"]) if opt and opt.get("strike") is not None else None,
                "option_expiry": str(opt["expiry"]) if opt and opt.get("expiry") is not None else None,
                "option_bid": 0.0,
                "option_ask": 0.0,
                "bid_ask_spread_pct": 0.0,
                "premium": 0.0,
                "lot_size": lot_size,
                "margin_required": 0.0,
                "data_source": "live" if spot_quotes else "cached",
            }
        )

    option_quotes = angel.get_market_quotes("NFO", opt_tokens) if opt_tokens else {}
    for rec in staged_records:
        otok = rec.pop("option_token", None)
        if otok and otok in option_quotes:
            oq = option_quotes[otok]
            bid = float(oq.get("best_bid") or 0.0)
            ask = float(oq.get("best_ask") or 0.0)
            last_px = float(oq.get("last_price") or 0.0)
            rec["option_bid"] = bid
            rec["option_ask"] = ask
            rec["bid_ask_spread_pct"] = float(oq.get("bid_ask_spread_pct") or 0.0)
            rec["premium"] = bid if bid > 0 else last_px
        strike_val = float(rec.get("option_strike") or 0.0)
        lot_val = int(rec.get("lot_size") or 0)
        if strike_val > 0 and lot_val > 0:
            rec["margin_required"] = round(strike_val * lot_val * 0.20, 2)

    hydrated = upsert_technicals_cache(staged_records, db_path=db_path)
    return {
        "hydrated": hydrated,
        "eq_count": sum(1 for r in staged_records if r["instrument_type"] == "EQ"),
        "index_count": sum(1 for r in staged_records if r["instrument_type"] == "INDEX"),
        "fundamentals_fetched": fundamentals_fetched,
        "fundamentals_errors": fundamentals_errors,
        "data_source": "live" if staged_records else "dry_run",
    }
