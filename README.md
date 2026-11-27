# HIFY Option Selling System (Systematic Wheel & Discipline Engine)

A standalone, rule-driven option selling, after-market opportunity scanner, and **Alert Trigger Order (ATO / GTT)** execution system built on:
- **Strategy Knowledge Base:** `D:\AI Projects\FNO KBase\Handmade_Notes_with_AI` (`Oct_Batch_Class_1` – `Oct_Batch_Class_10`)
- **Design System:** HIFY Tracker Brand Guidelines (*"Gold Identity + Neutral Intelligence"*) — visual match only, no coupling to `hify-tracker`
- **Broker Integration:** Zerodha Kite Connect (API + GTT / Alert-Triggered Limit Orders)
- **Access Model:** Runs locally on your home laptop (Python FastAPI + Next.js) and streams cleanly to your **mobile phone via Tailscale** when you are at the office.

---

## Core Workflow (After-Market Decisions + Manual Control First)
1. **Scan (After-Market):** Identify beaten-down, fundamentally strong F&O stocks ("Dhool Chaat").
2. **Stage (Manual Approval):** Review Red Candle + IV + Lower Blue Line + 5% Liquidity + ₹25L Aukaat cap, then stage **Limit-Only ATO / GTT** orders for the next session.
3. **Wait & Protect:** Monitor live Kite positions from desktop or phone (Tailscale) with **Decay Lock** (prevents early profit booking) and **Same-Strike Rollover** staging.
4. **Test Safely:** Use the built-in **Paper / Strategy Lab** (completely isolated from live Kite orders) to validate new ATO triggers and decay rules.
5. **Improve Continuously:** Convert every mistake in `docs/LESSONS_LEARNT.md` into a hard system guardrail before ever enabling Phase 3 autopilot.

---

## Folder Structure
```text
D:\AI Projects\Trading Log\OptionSelling\
├── README.md
├── config/
│   └── rules.example.yaml         # Configurable strategy parameters & ₹25L capital tier
├── docs/
│   ├── PROJECT_SCOPE.md           # Finalized scope, Tailscale mobile access & boundaries
│   ├── STRATEGY_RULEBOOK.md       # Complete rules from FNO KBase (Classes 1–10)
│   ├── BRAND_TOKENS.md            # HIFY Tracker UI/UX & color tokens
│   ├── KITE_INTEGRATION_PLAN.md   # Zerodha Kite Connect + After-Market ATO/GTT architecture
│   └── LESSONS_LEARNT.md          # Living mistake log -> system guardrails
├── backend/                       # Python FastAPI + Scanner + Kite Connect engine (next)
├── frontend/                      # HIFY-branded Next.js mobile-ready UI (next)
└── data/                          # Local SQLite DB, watchlists, and paper-lab logs
```
