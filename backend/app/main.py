"""FastAPI entrypoint for HIFY Option Selling System."""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import RulesConfig, get_settings, load_rules_config
from app.db import init_db
from app.routers import backoffice, kite, orders, paper, retrospective, scanner, universe


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize SQLite database and load strategy rules on startup."""
    db_path = init_db()
    rules = load_rules_config()
    app.state.db_path = str(db_path)
    app.state.db_initialized = True
    app.state.rules = rules
    yield


def create_app() -> FastAPI:
    """Build and configure the FastAPI application."""
    settings = get_settings()
    app = FastAPI(
        title="HIFY Option Selling System",
        version="0.1.0",
        description="Wheel Discipline Engine & After-Market Option Selling Cockpit",
        lifespan=lifespan,
    )

    allowed_origins = [
        f"http://localhost:{settings.FRONTEND_PORT}",
        f"http://127.0.0.1:{settings.FRONTEND_PORT}",
        *settings.tailscale_origins_list(),
    ]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_origin_regex=r"^https?://(100\.\d{1,3}\.\d{1,3}\.\d{1,3}|[a-zA-Z0-9-]+\.[a-zA-Z0-9-]+\.ts\.net)(:\d+)?$",
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/health")
    def health_check() -> dict[str, object]:
        rules: RulesConfig = getattr(app.state, "rules", load_rules_config())
        return {
            "status": "ok",
            "capital_tier": rules.capital.tier,
            "max_naked_positions": rules.capital.max_naked_positions,
            "max_hedged_positions": rules.capital.max_hedged_positions,
            "db_initialized": bool(getattr(app.state, "db_initialized", False)),
        }

    @app.get("/api/config/rules", response_model=RulesConfig)
    def get_rules_config() -> RulesConfig:
        return getattr(app.state, "rules", load_rules_config())

    app.include_router(kite.router)
    app.include_router(scanner.router)
    app.include_router(orders.router)
    app.include_router(paper.router)
    app.include_router(retrospective.router)
    app.include_router(backoffice.router)
    app.include_router(universe.router)

    return app


app = create_app()
