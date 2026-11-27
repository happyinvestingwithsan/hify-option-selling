# Project Scope — HIFY Option Selling System

**Workspace:** `D:\AI Projects\Trading Log\OptionSelling`  
**Status:** Finalized Scope (Ready for Phase 1 Implementation)

---

## 1. Boundaries & Independence
- **Standalone Project:** Completely independent of `hify-tracker` (no shared database, no shared deployment, zero risk to `hify-tracker`).
- **HIFY Brand Alignment:** Uses the exact HIFY Tracker design system (*"Gold Identity + Neutral Intelligence"* — `#C8A951` gold ceiling 3–4%, `#FAFAF8` / `#121214` canvas, `Inter` + `JetBrains Mono`, semantic `#10B981` profit / `#F43F5E` loss / `#EA580C` warning) so the look and feel matches your other Trading Journal apps.
- **Portable Modules:** Clean, self-contained modules so any non-F&O UI/utility patterns can be copied cleanly later if desired.

---

## 2. Target Architecture (Local Laptop + Mobile via Tailscale)
- **Backend:** Local **Python FastAPI** (`0.0.0.0:8000`) + SQLite (`data/option_selling.db`) + Zerodha `kiteconnect` SDK.
- **Frontend:** **Next.js (App Router) + Tailwind CSS v4** (`0.0.0.0:3000`), mobile-first responsive layout (bottom navigation bar, `44px–48px` touch targets, PWA-friendly viewport) so you can control everything from your **phone over Tailscale** while your laptop runs at home.
- **One-Command Launcher:** `start.ps1` / `start.bat` to boot both backend and frontend together for Tailscale access.

---

## 3. Core Workflow: After-Market Analysis + Manual Control First
All trading decisions are made **after market hours** (zero intraday impulsive clicking), with **Manual Mode First** for several months before considering any autopilot:

1. **Daily Beaten-Down ("Dhool Chaat") Scanner (After-Market):**
   - Scans **F40**, **E40**, and **All NSE F&O** stocks (strictly no `S200`, with Large/Mid/Small Cap slicers) against ATH drop thresholds (Large Cap `-25%` to `-30%`, Mid `-30%` to `-40%`, Small `-35%` to `-40%`), 70% institutional holding, Median PE, `SMA(200) * 0.86` Lower Blue Line envelope proximity, and High-Volatility/IV Theta Opportunity ranking.
2. **After-Market ATO / GTT Staging (Manual Approval):**
   - When a beaten-down stock sets up, you review the **Red Candle + High IV** setup, **5% Bid-Ask liquidity check**, **PPM tier** (`<3%`, `3–6%`, `>6%`), and **₹25L Aukaat Lot Cap** (max 4 naked / 6 hedged).
   - You explicitly approve staging a **Limit-Only Alert Trigger Order (ATO) / GTT** on Kite for the next market session.
3. **Position Monitor & Emotion Guardrails (Mobile + Desktop):**
   - Tracks live Kite positions, MTM, and exact **Decay %** against your Profit Booking Rules (`30%` 1-day, `40–50%` 2–3 days, `50%` 15-day, `70–80%` expiry week).
   - **Decay Lock:** Blocks/warns against early profit booking out of impatience.
   - **Same-Strike Rollover Assistant:** Stages exact same-strike next-month rollovers (or Far-Month Future pivot if illiquid), preventing rolling down.
   - **Kill Switch:** Instant button to cancel pending GTTs/open orders from desktop or phone.
4. **Built-in Paper / Strategy Lab (Isolated Sandbox):**
   - Separate app section **completely disconnected from live Kite order placement**.
   - Uses live/after-market Kite quotes to test new ATO trigger conditions, decay rules, and rollover ideas safely.
5. **Lessons Learnt Continuous Loop:**
   - Every mistake logged in `docs/LESSONS_LEARNT.md` translates into a concrete guardrail in the scanner or order-staging checklist.

---

## 4. Explicit Non-Goals (Phase 1)
- No fully autonomous/unattended live order execution (strictly manual approval after market hours).
- No naked Call selling, no Market orders, no intraday scalping/OI-chasing.
- No direct integration or database sharing with `hify-tracker`.
