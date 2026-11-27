"""Application settings and strategy rulebook YAML loader."""

from functools import lru_cache
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    """Environment-backed runtime settings (secrets stay in .env)."""

    model_config = SettingsConfigDict(
        env_file=str(PROJECT_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    KITE_API_KEY: str = ""
    KITE_API_SECRET: str = ""
    KITE_REDIRECT_URL: str = "http://127.0.0.1:8000/api/kite/callback"
    ANGEL_API_KEY: str = ""
    ANGEL_CLIENT_CODE: str = ""
    ANGEL_PIN: str = ""
    ANGEL_TOTP_SECRET: str = ""
    TAILSCALE_ALLOWED_ORIGINS: str = ""
    DATABASE_PATH: str = "backend/data/hify_options.db"
    RULES_PATH: str = "config/rules.yaml"
    APP_HOST: str = "0.0.0.0"
    APP_PORT: int = 8000
    FRONTEND_PORT: int = 3011

    def resolved_database_path(self) -> Path:
        path = Path(self.DATABASE_PATH)
        return path if path.is_absolute() else PROJECT_ROOT / path

    def resolved_rules_path(self) -> Path:
        path = Path(self.RULES_PATH)
        return path if path.is_absolute() else PROJECT_ROOT / path

    def tailscale_origins_list(self) -> list[str]:
        if not self.TAILSCALE_ALLOWED_ORIGINS.strip():
            return []
        return [
            origin.strip().rstrip("/")
            for origin in self.TAILSCALE_ALLOWED_ORIGINS.split(",")
            if origin.strip() and origin.strip() != "*"
        ]


class CapitalRules(BaseModel):
    total_capital_inr: int = 2500000
    tier: str = "25L"
    max_naked_positions: int = Field(default=4, ge=1)
    max_hedged_positions: int = Field(default=6, ge=1)
    cut_exposure_at_nifty_ath_pct: float = 50.0


class BeatenDownRules(BaseModel):
    large_cap_min: float = 25.0
    mid_cap_min: float = 30.0
    small_cap_min: float = 35.0


class StockSelectionRules(BaseModel):
    universe: str = "NSE_FNO"
    min_institutional_holding_pct: float = 70.0
    require_below_median_pe: bool = True
    exclude_psu_unless_hedged: bool = True
    beaten_down_from_ath_pct: BeatenDownRules = Field(default_factory=BeatenDownRules)


class EntryTriggerRules(BaseModel):
    require_red_candle: bool = True
    min_intraday_drop_pct: float = 2.0
    require_lower_blue_line_zone: bool = True
    order_type: Literal["LIMIT"] = "LIMIT"
    max_option_bid_ask_spread_pct: float = 5.0
    max_future_bid_ask_spread_pct: float = 1.5


class PpmTierRules(BaseModel):
    aggressive_min_pct: float = 6.0
    normal_min_pct: float = 3.0
    conservative_max_pct: float = 3.0


class ProfitBookingDecayRules(BaseModel):
    intraday_1_day: float = 30.0
    fast_2_to_3_days: float = 45.0
    mid_month_gtt: float = 50.0
    expiry_week_min: float = 70.0
    expiry_week_max: float = 80.0


class RolloverRules(BaseModel):
    allow_roll_down_strike: bool = False
    pivot_to_far_future_if_illiquid: bool = True
    physical_delivery_cutoff_days: int = 2


class HedgingRules(BaseModel):
    bull_put_spread_otm_distance_pct: float = 10.0
    portfolio_nifty_hedge_annual_budget_pct: float = 2.0
    shift_nifty_hedge_on_crash_pct: float = 8.0


class RulesConfig(BaseModel):
    capital: CapitalRules = Field(default_factory=CapitalRules)
    stock_selection: StockSelectionRules = Field(default_factory=StockSelectionRules)
    entry_triggers: EntryTriggerRules = Field(default_factory=EntryTriggerRules)
    ppm_tiers: PpmTierRules = Field(default_factory=PpmTierRules)
    profit_booking_decay_pct: ProfitBookingDecayRules = Field(
        default_factory=ProfitBookingDecayRules
    )
    rollover: RolloverRules = Field(default_factory=RolloverRules)
    hedging: HedgingRules = Field(default_factory=HedgingRules)


@lru_cache
def get_settings() -> Settings:
    return Settings()


def load_rules_config(rules_path: str | Path | None = None) -> RulesConfig:
    """Load rules.yaml, falling back to config/rules.example.yaml if absent."""
    settings = get_settings()
    target = Path(rules_path) if rules_path is not None else settings.resolved_rules_path()
    if not target.is_absolute():
        target = PROJECT_ROOT / target

    fallback = PROJECT_ROOT / "config" / "rules.example.yaml"
    source = target if target.exists() else fallback
    if not source.exists():
        return RulesConfig()

    with source.open("r", encoding="utf-8") as fh:
        raw = yaml.safe_load(fh) or {}
    return RulesConfig.model_validate(raw)
