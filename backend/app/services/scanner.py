"""Dhool Chaat After-Market Scanner service."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from app.config import RulesConfig
from app.kite_client import KiteService, calculate_spread_pct
from app.services.fundamentals import (
    evaluate_fundamental_checks,
    evaluate_fundamental_pass,
    get_all_cached_fundamentals,
    get_all_technicals_cache,
    hydrate_scanner_cache,
)
from app.services.guardrails import get_aukaat_counts
from app.services.universe import (
    ScannerSlicer,
    UniverseType,
    list_indices,
    list_universe_stocks,
    seed_f40_e40_if_empty,
)

CapTier = Literal["large", "mid", "small"]
PpmTier = Literal["Aggressive", "Normal", "Conservative"]
Moneyness = Literal["ATM", "OTM", "ITM"]


class StockCandidateInput(BaseModel):
    """Input data for evaluating a single F&O stock against Dhool Chaat rules."""

    symbol: str = Field(..., min_length=1)
    company_name: str = ""
    sector: str = ""
    cap_tier: CapTier = "large"
    ath_price: float = Field(..., gt=0)
    current_price: float = Field(..., gt=0)
    institutional_holding_pct: float = Field(..., ge=0, le=100)
    current_pe: float = Field(..., ge=0)
    median_pe: float = Field(..., gt=0)
    is_red_candle: bool = True
    intraday_drop_pct: float = 0.0
    lower_blue_line: float = Field(..., gt=0)
    option_instrument: str | None = None
    option_strike: float | None = None
    option_bid: float = Field(default=0.0, ge=0)
    option_ask: float = Field(default=0.0, ge=0)
    bid_ask_spread_pct: float | None = Field(default=None, ge=0)
    premium: float = Field(..., ge=0)
    lot_size: int = Field(..., gt=0)
    margin_required: float = Field(..., gt=0)
    is_psu: bool = False
    iv_pct: float = Field(default=0.0, ge=0)
    hv_spike_ratio: float = Field(default=1.0, ge=0)
    universe_tags: list[str] = Field(default_factory=list)
    high_52w: float = Field(default=0.0, ge=0)
    high_52w_drop_pct: float = Field(default=0.0, ge=0)
    sma_200: float = Field(default=0.0, ge=0)
    dma200_pct: float = 0.0
    instrument_type: str = "EQ"
    data_source: str = "sample"
    fundamentals: dict[str, Any] = Field(default_factory=dict)
    fundamental_checks: dict[str, bool | None] = Field(default_factory=dict)
    fundamental_passed: bool | None = None


class ScannerResultItem(BaseModel):
    """Evaluated scanner output for a single stock candidate."""

    symbol: str
    company_name: str
    sector: str
    cap_tier: CapTier
    current_price: float
    ath_price: float
    ath_drop_pct: float
    required_ath_drop_pct: float
    high_52w: float = 0.0
    high_52w_drop_pct: float = 0.0
    sma_200: float = 0.0
    dma200_pct: float = 0.0
    institutional_holding_pct: float
    current_pe: float
    median_pe: float
    is_red_candle: bool
    intraday_drop_pct: float
    lower_blue_line: float
    lower_blue_line_distance_pct: float
    suggested_moneyness: Moneyness
    option_instrument: str | None = None
    option_strike: float | None = None
    option_bid: float
    option_ask: float
    bid_ask_spread_pct: float
    premium: float
    lot_size: int
    margin_required: float
    ppm_pct: float
    ppm_tier: PpmTier
    iv_pct: float = 0.0
    hv_spike_ratio: float = 1.0
    theta_opportunity_score: float = 0.0
    universe_tags: list[str] = Field(default_factory=list)
    instrument_type: str = "EQ"
    data_source: str = "sample"
    fundamentals: dict[str, Any] = Field(default_factory=dict)
    fundamental_checks: dict[str, bool | None] = Field(default_factory=dict)
    fundamental_passed: bool | None = None
    is_psu: bool
    requires_hedge: bool
    hedge_note: str | None = None
    passed: bool
    rejection_reasons: list[str] = Field(default_factory=list)


class ScannerResponse(BaseModel):
    """Response payload for scanner endpoints."""

    total_evaluated: int
    passed_count: int
    rejected_count: int
    quotes_refreshed: bool = False
    universe_type: ScannerSlicer | UniverseType | None = None
    slicer: str | None = None
    freshness: str = "cached"
    synced_at: str | None = None
    aukaat_summary: dict[str, int | bool] = Field(default_factory=dict)
    items: list[ScannerResultItem]


def calculate_lower_blue_line(closes: list[float]) -> float:
    """Return exact Lower Blue Line envelope value: SMA(200) * 0.86."""
    if not closes:
        return 0.0
    window = closes[-200:] if len(closes) >= 200 else closes
    sma200 = sum(window) / len(window)
    return round(sma200 * 0.86, 2)


def calculate_theta_opportunity_score(
    ppm_pct: float,
    iv_pct: float,
    hv_spike_ratio: float,
    spread_pct: float,
    is_red_candle: bool,
) -> float:
    """Rank beaten-down setups by High Volatility (IV/HV spike) + PPM + tight spread."""
    iv_component = min(iv_pct, 80.0) * 0.6 if iv_pct > 0 else 15.0
    hv_component = max(0.0, (hv_spike_ratio - 1.0) * 20.0)
    ppm_component = min(ppm_pct, 12.0) * 3.0
    spread_penalty = min(spread_pct, 10.0) * 1.5
    candle_bonus = 5.0 if is_red_candle else 0.0
    return round(max(0.0, iv_component + hv_component + ppm_component + candle_bonus - spread_penalty), 2)


def calculate_ath_drop_pct(ath_price: float, current_price: float) -> float:
    """Return percentage drop from All-Time High (clamped at 0.0 if at/above ATH)."""
    if ath_price <= 0:
        return 0.0
    drop = ((ath_price - current_price) / ath_price) * 100.0
    return round(max(0.0, drop), 2)


def calculate_52w_drop_pct(high_52w: float, current_price: float) -> float:
    """Return percentage drop from 52-Week High (clamped at 0.0 if at/above 52W High)."""
    if high_52w <= 0:
        return 0.0
    drop = ((high_52w - current_price) / high_52w) * 100.0
    return round(max(0.0, drop), 2)


def calculate_dma200_pct(current_price: float, sma_200: float) -> float:
    """Return percentage distance vs 200 DMA: ((current_price - sma_200) / sma_200) * 100."""
    if sma_200 <= 0:
        return 0.0
    return round(((current_price - sma_200) / sma_200) * 100.0, 2)


def calculate_ppm_pct(premium: float, lot_size: int, margin_required: float) -> float:
    """Calculate Percentage Gain per Margin: ((premium * lot_size) / margin_required) * 100."""
    if margin_required <= 0 or lot_size <= 0 or premium < 0:
        return 0.0
    return round(((premium * lot_size) / margin_required) * 100.0, 2)


def classify_ppm_tier(ppm_pct: float, rules: RulesConfig) -> PpmTier:
    """Classify PPM into Aggressive (>6%), Normal (3%-6%), or Conservative (<3%)."""
    if ppm_pct > rules.ppm_tiers.aggressive_min_pct:
        return "Aggressive"
    if ppm_pct >= rules.ppm_tiers.normal_min_pct:
        return "Normal"
    return "Conservative"


def suggest_strike_moneyness(current_price: float, lower_blue_line: float) -> Moneyness:
    """Suggest Put strike moneyness relative to the Lower Blue Line envelope."""
    if lower_blue_line <= 0:
        return "ATM"
    ratio = (current_price - lower_blue_line) / lower_blue_line
    if ratio > 0.01:
        return "OTM"
    if ratio < -0.01:
        return "ITM"
    return "ATM"


def _required_ath_drop_for_tier(cap_tier: CapTier, rules: RulesConfig) -> float:
    tier_map = {
        "large": rules.stock_selection.beaten_down_from_ath_pct.large_cap_min,
        "mid": rules.stock_selection.beaten_down_from_ath_pct.mid_cap_min,
        "small": rules.stock_selection.beaten_down_from_ath_pct.small_cap_min,
    }
    return tier_map[cap_tier]


def evaluate_candidate(candidate: StockCandidateInput, rules: RulesConfig) -> ScannerResultItem:
    """Evaluate a single stock candidate against all Dhool Chaat Strategy Rulebook checks."""
    ath_drop_pct = calculate_ath_drop_pct(candidate.ath_price, candidate.current_price)
    required_ath_drop = _required_ath_drop_for_tier(candidate.cap_tier, rules)
    high_52w_drop_pct = (
        calculate_52w_drop_pct(candidate.high_52w, candidate.current_price)
        if candidate.high_52w > 0
        else round(candidate.high_52w_drop_pct, 2)
    )
    dma200_pct = (
        calculate_dma200_pct(candidate.current_price, candidate.sma_200)
        if candidate.sma_200 > 0
        else round(candidate.dma200_pct, 2)
    )

    lower_blue_line_distance_pct = round(
        ((candidate.current_price - candidate.lower_blue_line) / candidate.lower_blue_line) * 100.0,
        2,
    )
    suggested_moneyness = suggest_strike_moneyness(
        candidate.current_price, candidate.lower_blue_line
    )

    spread_pct = (
        round(candidate.bid_ask_spread_pct, 2)
        if candidate.bid_ask_spread_pct is not None
        else calculate_spread_pct(candidate.option_bid, candidate.option_ask)
    )

    ppm_pct = calculate_ppm_pct(
        candidate.premium, candidate.lot_size, candidate.margin_required
    )
    ppm_tier = classify_ppm_tier(ppm_pct, rules)

    rejections: list[str] = []

    if ath_drop_pct < required_ath_drop:
        rejections.append(
            f"ATH drop {ath_drop_pct:.2f}% < required {required_ath_drop:.2f}% ({candidate.cap_tier} cap)"
        )

    min_inst = rules.stock_selection.min_institutional_holding_pct
    if candidate.institutional_holding_pct < min_inst:
        rejections.append(
            f"Institutional holding {candidate.institutional_holding_pct:.1f}% < {min_inst:.1f}%"
        )

    if rules.stock_selection.require_below_median_pe and candidate.current_pe >= candidate.median_pe:
        rejections.append(
            f"PE {candidate.current_pe:.1f} >= Median PE {candidate.median_pe:.1f}"
        )

    if rules.entry_triggers.require_red_candle and not candidate.is_red_candle:
        rejections.append("Not forming a Red Candle (intraday panic required)")

    if (
        rules.entry_triggers.require_lower_blue_line_zone
        and lower_blue_line_distance_pct > 5.0
    ):
        rejections.append(
            f"Price {lower_blue_line_distance_pct:.2f}% above Lower Blue Line (> 5.0% zone)"
        )

    max_spread = rules.entry_triggers.max_option_bid_ask_spread_pct
    if spread_pct > max_spread:
        rejections.append(
            f"Option bid-ask spread {spread_pct:.2f}% > {max_spread:.2f}% liquidity limit"
        )

    requires_hedge = bool(candidate.is_psu and rules.stock_selection.exclude_psu_unless_hedged)
    hedge_note = (
        "PSU stock: Bull Put Spread required (naked Put disallowed per Rulebook)"
        if requires_hedge
        else None
    )

    theta_score = calculate_theta_opportunity_score(
        ppm_pct=ppm_pct,
        iv_pct=candidate.iv_pct,
        hv_spike_ratio=candidate.hv_spike_ratio,
        spread_pct=spread_pct,
        is_red_candle=candidate.is_red_candle,
    )

    return ScannerResultItem(
        symbol=candidate.symbol.upper(),
        company_name=candidate.company_name or candidate.symbol.upper(),
        sector=candidate.sector,
        cap_tier=candidate.cap_tier,
        current_price=candidate.current_price,
        ath_price=candidate.ath_price,
        ath_drop_pct=ath_drop_pct,
        required_ath_drop_pct=required_ath_drop,
        high_52w=candidate.high_52w,
        high_52w_drop_pct=high_52w_drop_pct,
        sma_200=candidate.sma_200,
        dma200_pct=dma200_pct,
        institutional_holding_pct=candidate.institutional_holding_pct,
        current_pe=candidate.current_pe,
        median_pe=candidate.median_pe,
        is_red_candle=candidate.is_red_candle,
        intraday_drop_pct=candidate.intraday_drop_pct,
        lower_blue_line=candidate.lower_blue_line,
        lower_blue_line_distance_pct=lower_blue_line_distance_pct,
        suggested_moneyness=suggested_moneyness,
        option_instrument=candidate.option_instrument,
        option_strike=candidate.option_strike,
        option_bid=candidate.option_bid,
        option_ask=candidate.option_ask,
        bid_ask_spread_pct=spread_pct,
        premium=candidate.premium,
        lot_size=candidate.lot_size,
        margin_required=candidate.margin_required,
        ppm_pct=ppm_pct,
        ppm_tier=ppm_tier,
        iv_pct=candidate.iv_pct,
        hv_spike_ratio=candidate.hv_spike_ratio,
        theta_opportunity_score=theta_score,
        universe_tags=candidate.universe_tags,
        instrument_type=candidate.instrument_type,
        data_source=candidate.data_source,
        fundamentals=candidate.fundamentals,
        fundamental_checks=candidate.fundamental_checks,
        fundamental_passed=candidate.fundamental_passed,
        is_psu=candidate.is_psu,
        requires_hedge=requires_hedge,
        hedge_note=hedge_note,
        passed=len(rejections) == 0,
        rejection_reasons=rejections,
    )


def _sample_super45_universe() -> list[StockCandidateInput]:
    """Curated NSE F&O / Super 45 sample universe for after-market & dry-run scans."""
    return [
        # Passing Large Cap (Aggressive PPM, ATM near Lower Blue Line)
        StockCandidateInput(
            symbol="TATAMOTORS",
            company_name="Tata Motors Ltd",
            sector="Automobile",
            cap_tier="large",
            ath_price=1179.0,
            current_price=825.0,
            institutional_holding_pct=74.5,
            current_pe=11.8,
            median_pe=16.5,
            is_red_candle=True,
            intraday_drop_pct=-2.8,
            lower_blue_line=822.0,
            option_instrument="NFO:TATAMOTORS26NOV820PE",
            option_strike=820.0,
            option_bid=28.5,
            option_ask=29.2,
            premium=28.8,
            lot_size=550,
            margin_required=245000.0,
            is_psu=False,
        ),
        # Passing Large Cap (Normal PPM, OTM slightly above Lower Blue Line)
        StockCandidateInput(
            symbol="ASIANPAINT",
            company_name="Asian Paints Ltd",
            sector="Consumer Durables",
            cap_tier="large",
            ath_price=3568.0,
            current_price=2490.0,
            institutional_holding_pct=78.2,
            current_pe=48.5,
            median_pe=62.0,
            is_red_candle=True,
            intraday_drop_pct=-2.2,
            lower_blue_line=2410.0,
            option_instrument="NFO:ASIANPAINT26NOV2450PE",
            option_strike=2450.0,
            option_bid=42.0,
            option_ask=43.1,
            premium=42.5,
            lot_size=200,
            margin_required=195000.0,
            is_psu=False,
        ),
        # Passing Large Cap (Conservative PPM, ITM below Lower Blue Line)
        StockCandidateInput(
            symbol="INDUSINDBK",
            company_name="IndusInd Bank Ltd",
            sector="Banking",
            cap_tier="large",
            ath_price=1694.0,
            current_price=1040.0,
            institutional_holding_pct=76.0,
            current_pe=10.2,
            median_pe=15.4,
            is_red_candle=True,
            intraday_drop_pct=-3.1,
            lower_blue_line=1080.0,
            option_instrument="NFO:INDUSINDBK26NOV1060PE",
            option_strike=1060.0,
            option_bid=18.5,
            option_ask=19.1,
            premium=18.8,
            lot_size=500,
            margin_required=340000.0,
            is_psu=False,
        ),
        # Passing Mid Cap (>=30% ATH drop)
        StockCandidateInput(
            symbol="BANDHANBNK",
            company_name="Bandhan Bank Ltd",
            sector="Banking",
            cap_tier="mid",
            ath_price=272.0,
            current_price=176.0,
            institutional_holding_pct=71.8,
            current_pe=12.4,
            median_pe=18.0,
            is_red_candle=True,
            intraday_drop_pct=-2.6,
            lower_blue_line=175.0,
            option_instrument="NFO:BANDHANBNK26NOV175PE",
            option_strike=175.0,
            option_bid=5.4,
            option_ask=5.6,
            premium=5.5,
            lot_size=2800,
            margin_required=275000.0,
            is_psu=False,
        ),
        # Passing Small Cap (>=35% ATH drop)
        StockCandidateInput(
            symbol="CHAMBLFERT",
            company_name="Chambal Fertilisers & Chemicals",
            sector="Chemicals",
            cap_tier="small",
            ath_price=575.0,
            current_price=365.0,
            institutional_holding_pct=72.4,
            current_pe=13.1,
            median_pe=15.9,
            is_red_candle=True,
            intraday_drop_pct=-2.4,
            lower_blue_line=360.0,
            option_instrument="NFO:CHAMBLFERT26NOV360PE",
            option_strike=360.0,
            option_bid=11.0,
            option_ask=11.4,
            premium=11.2,
            lot_size=1900,
            margin_required=310000.0,
            is_psu=False,
        ),
        # Passing PSU Stock -> requires_hedge=True (Bull Put Spread)
        StockCandidateInput(
            symbol="COALINDIA",
            company_name="Coal India Ltd",
            sector="Metals & Mining",
            cap_tier="large",
            ath_price=544.0,
            current_price=395.0,
            institutional_holding_pct=84.0,
            current_pe=7.8,
            median_pe=9.5,
            is_red_candle=True,
            intraday_drop_pct=-2.1,
            lower_blue_line=392.0,
            option_instrument="NFO:COALINDIA26NOV395PE",
            option_strike=395.0,
            option_bid=12.4,
            option_ask=12.8,
            premium=12.6,
            lot_size=2100,
            margin_required=410000.0,
            is_psu=True,
        ),
        # Rejected: Bid-Ask Spread > 5%
        StockCandidateInput(
            symbol="ASTRAL",
            company_name="Astral Ltd",
            sector="Building Materials",
            cap_tier="mid",
            ath_price=2454.0,
            current_price=1640.0,
            institutional_holding_pct=75.1,
            current_pe=64.0,
            median_pe=78.0,
            is_red_candle=True,
            intraday_drop_pct=-2.3,
            lower_blue_line=1630.0,
            option_instrument="NFO:ASTRAL26NOV1640PE",
            option_strike=1640.0,
            option_bid=34.0,
            option_ask=38.0,
            premium=36.0,
            lot_size=425,
            margin_required=290000.0,
            is_psu=False,
        ),
        # Rejected: Institutional Holding < 70%
        StockCandidateInput(
            symbol="RBLBANK",
            company_name="RBL Bank Ltd",
            sector="Banking",
            cap_tier="small",
            ath_price=300.0,
            current_price=180.0,
            institutional_holding_pct=58.5,
            current_pe=11.0,
            median_pe=14.5,
            is_red_candle=True,
            intraday_drop_pct=-2.7,
            lower_blue_line=182.0,
            option_instrument="NFO:RBLBANK26NOV180PE",
            option_strike=180.0,
            option_bid=6.2,
            option_ask=6.4,
            premium=6.3,
            lot_size=2500,
            margin_required=260000.0,
            is_psu=False,
        ),
        # Rejected: Current PE > Median PE & Green Candle
        StockCandidateInput(
            symbol="TITAN",
            company_name="Titan Company Ltd",
            sector="Consumer Durables",
            cap_tier="large",
            ath_price=3886.0,
            current_price=2890.0,
            institutional_holding_pct=81.0,
            current_pe=76.5,
            median_pe=68.0,
            is_red_candle=False,
            intraday_drop_pct=0.8,
            lower_blue_line=2850.0,
            option_instrument="NFO:TITAN26NOV2880PE",
            option_strike=2880.0,
            option_bid=52.0,
            option_ask=53.0,
            premium=52.5,
            lot_size=175,
            margin_required=230000.0,
            is_psu=False,
        ),
        # Rejected: Insufficient ATH drop (< 25% for large cap)
        StockCandidateInput(
            symbol="HDFCBANK",
            company_name="HDFC Bank Ltd",
            sector="Banking",
            cap_tier="large",
            ath_price=1880.0,
            current_price=1640.0,
            institutional_holding_pct=86.5,
            current_pe=18.2,
            median_pe=21.0,
            is_red_candle=True,
            intraday_drop_pct=-2.0,
            lower_blue_line=1635.0,
            option_instrument="NFO:HDFCBANK26NOV1640PE",
            option_strike=1640.0,
            option_bid=24.0,
            option_ask=24.6,
            premium=24.3,
            lot_size=550,
            margin_required=310000.0,
            is_psu=False,
        ),
    ]


class DhoolChaatScanner:
    """After-market & dry-run scanner enforcing Dhool Chaat strategy rules."""

    def __init__(
        self,
        rules: RulesConfig,
        kite_service: KiteService | None = None,
        universe: list[StockCandidateInput] | None = None,
    ) -> None:
        self.rules = rules
        self.kite_service = kite_service
        self._custom_universe = universe is not None
        self.universe = universe if universe is not None else _sample_super45_universe()

    def _load_slicer_candidates(
        self,
        universe_type: ScannerSlicer | UniverseType | None = None,
    ) -> tuple[list[StockCandidateInput], str | None]:
        """Load slicer symbols from SQLite universe/indices + technicals + fundamentals caches."""
        seed_f40_e40_if_empty()
        sample_map = {item.symbol.upper(): item for item in _sample_super45_universe()}
        target_rows: dict[str, dict[str, Any]] = {}

        if universe_type == "INDICES":
            for idx in list_indices():
                sym = str(idx["symbol"]).upper()
                target_rows[sym] = {
                    "symbol": sym,
                    "cap_tier": idx.get("cap_tier", "large"),
                    "sector": idx.get("sector", "Index"),
                    "lot_size": int(idx.get("lot_size") or 0),
                    "instrument_type": "INDEX",
                    "universe_tags": ["INDICES"],
                }
        elif universe_type in ("F40", "E40"):
            for row in list_universe_stocks(universe_type=universe_type):
                sym = str(row["symbol"]).upper()
                target_rows[sym] = {
                    **row,
                    "symbol": sym,
                    "instrument_type": "EQ",
                    "universe_tags": [universe_type],
                }
        elif universe_type == "NSE_FNO":
            fno_rows = list_universe_stocks(universe_type="NSE_FNO")
            if not fno_rows:
                fno_rows = list_universe_stocks()
            for row in fno_rows:
                sym = str(row["symbol"]).upper()
                u_tag = str(row["universe_type"])
                if sym in target_rows:
                    if u_tag not in target_rows[sym]["universe_tags"]:
                        target_rows[sym]["universe_tags"].append(u_tag)
                else:
                    target_rows[sym] = {
                        **row,
                        "symbol": sym,
                        "instrument_type": "EQ",
                        "universe_tags": [u_tag],
                    }
        else:
            for row in list_universe_stocks():
                sym = str(row["symbol"]).upper()
                u_tag = str(row["universe_type"])
                if sym in target_rows:
                    if u_tag not in target_rows[sym]["universe_tags"]:
                        target_rows[sym]["universe_tags"].append(u_tag)
                else:
                    target_rows[sym] = {
                        **row,
                        "symbol": sym,
                        "instrument_type": "EQ",
                        "universe_tags": [u_tag],
                    }
            for idx in list_indices():
                sym = str(idx["symbol"]).upper()
                if sym not in target_rows:
                    target_rows[sym] = {
                        "symbol": sym,
                        "cap_tier": idx.get("cap_tier", "large"),
                        "sector": idx.get("sector", "Index"),
                        "lot_size": int(idx.get("lot_size") or 0),
                        "instrument_type": "INDEX",
                        "universe_tags": ["INDICES"],
                    }
        technicals_cache = get_all_technicals_cache()
        has_live_cache = any(
            str(v.get("data_source") or "") == "live" for v in technicals_cache.values()
        )
        if universe_type is None and not has_live_cache:
            for sym, sample_item in sample_map.items():
                if sym not in target_rows:
                    target_rows[sym] = {
                        "symbol": sym,
                        "cap_tier": sample_item.cap_tier,
                        "sector": sample_item.sector,
                        "lot_size": sample_item.lot_size,
                        "instrument_type": "EQ",
                        "universe_tags": ["NSE_FNO"],
                    }
        missing = [sym for sym in target_rows if sym not in technicals_cache]
        if missing:
            hydrate_scanner_cache(
                symbols=missing,
                include_indices=(universe_type in (None, "INDICES")),
                fetch_fundamentals=False,
                kite_service=self.kite_service,
            )
            technicals_cache = get_all_technicals_cache()

        fundamentals_cache = get_all_cached_fundamentals()

        timestamps = [
            str(technicals_cache[s]["updated_at"])
            for s in target_rows
            if s in technicals_cache and technicals_cache[s].get("updated_at")
        ]
        synced_at = max(timestamps) if timestamps else None

        candidates: list[StockCandidateInput] = []
        for sym, meta in target_rows.items():
            tech = technicals_cache.get(sym, {})
            fund = fundamentals_cache.get(sym)
            sample = sample_map.get(sym)
            fund_checks = evaluate_fundamental_checks(fund) if fund else {}
            fund_passed = evaluate_fundamental_pass(fund) if fund else None
            tech_source = str(tech.get("data_source") or "sample")

            if has_live_cache and tech_source != "live":
                continue

            if not has_live_cache and sample is not None and tech_source != "live":
                candidates.append(
                    sample.model_copy(
                        update={
                            "universe_tags": meta["universe_tags"],
                            "high_52w": float(tech.get("high_52w") or sample.ath_price),
                            "sma_200": float(
                                tech.get("sma_200") or round(sample.lower_blue_line / 0.86, 2)
                            ),
                            "data_source": tech_source if tech else "sample",
                            "fundamentals": fund or {},
                            "fundamental_checks": fund_checks,
                            "fundamental_passed": fund_passed,
                        }
                    )
                )
                continue

            current_price = float(tech.get("current_price") or 0.0) or 100.0
            ath_price = float(tech.get("ath_price") or 0.0) or current_price
            high_52w = float(tech.get("high_52w") or 0.0) or ath_price
            sma_200 = float(tech.get("sma_200") or 0.0) or current_price
            lower_blue_line = float(tech.get("lower_blue_line") or 0.0) or round(
                sma_200 * 0.86, 2
            )

            inst_pct = float(fund.get("institutional_holding_pct") or 0.0) if fund else 0.0
            inst_pct = max(0.0, min(100.0, inst_pct))
            current_pe = float(fund.get("current_pe") or 0.0) if fund else 0.0
            median_pe = float(fund.get("pe_median_5y") or 0.0) if fund else 0.0
            if median_pe <= 0:
                median_pe = 20.0

            raw_cap = fund.get("cap_tier") if fund else None
            cap_tier: CapTier = (
                raw_cap if raw_cap in ("large", "mid", "small") else meta.get("cap_tier", "large")
            )
            lot_size = int(tech.get("lot_size") or meta.get("lot_size") or 0)
            if lot_size <= 0:
                lot_size = 1
            margin_required = float(tech.get("margin_required") or 0.0)
            if margin_required <= 0:
                margin_required = round(max(1.0, current_price * lot_size * 0.20), 2)

            candidates.append(
                StockCandidateInput(
                    symbol=sym,
                    company_name=sym,
                    sector=str(meta.get("sector") or ""),
                    cap_tier=cap_tier,
                    ath_price=ath_price,
                    current_price=current_price,
                    high_52w=high_52w,
                    sma_200=sma_200,
                    institutional_holding_pct=inst_pct,
                    current_pe=current_pe,
                    median_pe=median_pe,
                    is_red_candle=bool(tech.get("is_red_candle")),
                    intraday_drop_pct=float(tech.get("intraday_drop_pct") or 0.0),
                    lower_blue_line=lower_blue_line,
                    option_instrument=tech.get("option_instrument"),
                    option_strike=tech.get("option_strike"),
                    option_bid=float(tech.get("option_bid") or 0.0),
                    option_ask=float(tech.get("option_ask") or 0.0),
                    bid_ask_spread_pct=float(tech.get("bid_ask_spread_pct") or 0.0),
                    premium=float(tech.get("premium") or 0.0),
                    lot_size=lot_size,
                    margin_required=margin_required,
                    is_psu=bool(fund.get("is_psu")) if fund else False,
                    iv_pct=float(tech.get("iv_pct") or 0.0),
                    hv_spike_ratio=float(tech.get("hv_spike_ratio") or 1.0),
                    universe_tags=meta["universe_tags"],
                    instrument_type=str(
                        meta.get("instrument_type") or tech.get("instrument_type") or "EQ"
                    ),
                    data_source=tech_source,
                    fundamentals=fund or {},
                    fundamental_checks=fund_checks,
                    fundamental_passed=fund_passed,
                )
            )

        return candidates, synced_at

    def _enrich_live_quotes(self, candidates: list[StockCandidateInput]) -> tuple[list[StockCandidateInput], bool]:
        """Optionally enrich option bid/ask and spread from Kite when connected."""
        if self.kite_service is None or not self.kite_service._is_live():
            return candidates, False

        instruments = [c.option_instrument for c in candidates if c.option_instrument]
        if not instruments:
            return candidates, False

        quote_resp = self.kite_service.get_quote(instruments)
        if quote_resp.get("is_dry_run"):
            return candidates, False
        quotes = quote_resp.get("quotes", {})
        enriched: list[StockCandidateInput] = []
        for candidate in candidates:
            if candidate.option_instrument and candidate.option_instrument in quotes:
                q = quotes[candidate.option_instrument]
                best_bid = float(q.get("best_bid", candidate.option_bid) or 0.0)
                best_ask = float(q.get("best_ask", candidate.option_ask) or 0.0)
                spread = float(
                    q.get("bid_ask_spread_pct", calculate_spread_pct(best_bid, best_ask))
                )
                enriched.append(
                    candidate.model_copy(
                        update={
                            "option_bid": best_bid,
                            "option_ask": best_ask,
                            "bid_ask_spread_pct": spread,
                        }
                    )
                )
            else:
                enriched.append(candidate)
        return enriched, True

    def evaluate_list(
        self,
        candidates: list[StockCandidateInput],
        *,
        include_rejected: bool = True,
        universe_type: ScannerSlicer | UniverseType | None = None,
        cap_tier: str | None = None,
        ppm_tier: str | None = None,
        min_ath_drop_pct: float | None = None,
        min_52w_drop_pct: float | None = None,
        min_dma200_drop_pct: float | None = None,
        red_candle_only: bool = False,
        min_intraday_drop_pct: float | None = None,
        max_spread_pct: float | None = None,
        refresh_live_quotes: bool = False,
        synced_at: str | None = None,
    ) -> ScannerResponse:
        """Evaluate an explicit list of candidates against RulesConfig."""
        working = candidates
        if universe_type and self._custom_universe:
            if universe_type == "INDICES":
                allowed_syms = {row["symbol"] for row in list_indices()}
            else:
                allowed_syms = {
                    row["symbol"]
                    for row in list_universe_stocks(universe_type=universe_type)
                }
            if allowed_syms:
                filtered_working = [c for c in working if c.symbol.upper() in allowed_syms]
                if filtered_working:
                    working = filtered_working

        quotes_refreshed = False
        if refresh_live_quotes:
            working, quotes_refreshed = self._enrich_live_quotes(working)

        evaluated = [evaluate_candidate(item, self.rules) for item in working]
        passed_count = sum(1 for item in evaluated if item.passed)
        rejected_count = len(evaluated) - passed_count

        filtered = evaluated
        if not include_rejected:
            filtered = [item for item in filtered if item.passed]
        if cap_tier:
            target_cap = cap_tier.strip().lower()
            filtered = [item for item in filtered if item.cap_tier.lower() == target_cap]
        if ppm_tier:
            target_ppm = ppm_tier.strip().lower()
            filtered = [item for item in filtered if item.ppm_tier.lower() == target_ppm]
        if min_ath_drop_pct is not None:
            filtered = [item for item in filtered if item.ath_drop_pct >= min_ath_drop_pct]
        if min_52w_drop_pct is not None:
            filtered = [item for item in filtered if item.high_52w_drop_pct >= min_52w_drop_pct]
        if min_dma200_drop_pct is not None:
            filtered = [item for item in filtered if item.dma200_pct <= -min_dma200_drop_pct]
        if red_candle_only:
            filtered = [item for item in filtered if item.is_red_candle]
        if min_intraday_drop_pct is not None:
            filtered = [
                item
                for item in filtered
                if item.is_red_candle and abs(item.intraday_drop_pct) >= min_intraday_drop_pct
            ]
        if max_spread_pct is not None:
            filtered = [item for item in filtered if item.bid_ask_spread_pct <= max_spread_pct]

        filtered.sort(
            key=lambda item: (item.passed, item.theta_opportunity_score, item.ppm_pct),
            reverse=True,
        )

        aukaat = get_aukaat_counts()
        naked_max = self.rules.capital.max_naked_positions
        aukaat_summary: dict[str, int | bool] = {
            "naked_used": aukaat["naked_count"],
            "naked_max": naked_max,
            "naked_free": max(0, naked_max - aukaat["naked_count"]),
            "total_used": aukaat["total_count"],
            "hedged_max": self.rules.capital.max_hedged_positions,
            "can_open_new": aukaat["naked_count"] < naked_max,
        }

        sources = {item.data_source for item in evaluated}
        if quotes_refreshed or "live" in sources:
            freshness = "live"
        elif "dry_run" in sources:
            freshness = "dry_run"
        elif "cached" in sources:
            freshness = "cached"
        else:
            freshness = "offline" if not evaluated else "cached"

        return ScannerResponse(
            total_evaluated=len(evaluated),
            passed_count=passed_count,
            rejected_count=rejected_count,
            quotes_refreshed=quotes_refreshed,
            universe_type=universe_type,
            slicer=universe_type or "ALL",
            freshness=freshness,
            synced_at=synced_at,
            aukaat_summary=aukaat_summary,
            items=filtered,
        )

    def scan(
        self,
        *,
        include_rejected: bool = False,
        universe_type: ScannerSlicer | UniverseType | None = None,
        cap_tier: str | None = None,
        ppm_tier: str | None = None,
        min_ath_drop_pct: float | None = None,
        min_52w_drop_pct: float | None = None,
        min_dma200_drop_pct: float | None = None,
        red_candle_only: bool = False,
        min_intraday_drop_pct: float | None = None,
        max_spread_pct: float | None = None,
        refresh_live_quotes: bool = False,
    ) -> ScannerResponse:
        """Scan F40 / E40 / All NSE F&O / INDICES universe (no S200)."""
        synced_at: str | None = None
        if self._custom_universe:
            candidates = self.universe
        else:
            candidates, synced_at = self._load_slicer_candidates(universe_type=universe_type)
        return self.evaluate_list(
            candidates,
            include_rejected=include_rejected,
            universe_type=universe_type,
            cap_tier=cap_tier,
            ppm_tier=ppm_tier,
            min_ath_drop_pct=min_ath_drop_pct,
            min_52w_drop_pct=min_52w_drop_pct,
            min_dma200_drop_pct=min_dma200_drop_pct,
            red_candle_only=red_candle_only,
            min_intraday_drop_pct=min_intraday_drop_pct,
            max_spread_pct=max_spread_pct,
            refresh_live_quotes=refresh_live_quotes,
            synced_at=synced_at,
        )
