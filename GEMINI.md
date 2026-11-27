# GEMINI.md — HIFY Option Selling System Context & Guardrails

> **Read this file first** at the start of any task in `D:\AI Projects\Trading Log\OptionSelling`.

---

## 1. Project Identity & Boundaries
- **Project:** HIFY Option Selling System ("Dhool Chaat" / Wheel Discipline Engine).
- **Standalone Workspace:** `D:\AI Projects\Trading Log\OptionSelling` is **completely standalone** from `D:\AI Projects\hify-tracker` (no shared database, no shared deployment, no coupling).
- **Brand Alignment:** Follow the universal **HIFY Gold Identity + Neutral Intelligence** color palette defined in `D:\AI Projects\Trading Log\HIFY_COLOR_PALETTE.md` (and `docs/BRAND_TOKENS.md` — `#C8A951` HIFY Gold, `#8E6C20` Light-Mode Deep Gold text, `#FAFAF8` / `#121214` canvas, `#FFFFFF` / `#18181B` surfaces, `Inter` + `JetBrains Mono`, semantic `#10B981` profit / `#F43F5E` loss / `#EA580C` warning). Legacy Teal tokens are deprecated.
- **Access & Deployment Model:** Runs locally on the user's home laptop (**Python FastAPI** + **Next.js**) and streams over **Tailscale** to the user's mobile phone at the office. All UI screens must be mobile-first responsive (`44px–48px` touch targets).

---

## 2. Authoritative Reference Documents
Always consult these files before making architectural, strategy, UI, or broker-integration decisions:
1. **Scope & Architecture:** `docs/PROJECT_SCOPE.md`
2. **Implementation Plan (Units U1–U9):** `docs/IMPLEMENTATION_PLAN.md`
3. **Option Selling Rules (`D:\AI Projects\FNO KBase\Handmade_Notes_with_AI`):** `docs/STRATEGY_RULEBOOK.md`
4. **Configurable Parameters (₹25L Tier):** `config/rules.example.yaml`
5. **Universal HIFY Color Palette & Brand Tokens:** `D:\AI Projects\Trading Log\HIFY_COLOR_PALETTE.md` (and `docs/BRAND_TOKENS.md`)
6. **Zerodha Kite Connect & ATO/GTT Plan:** `docs/KITE_INTEGRATION_PLAN.md`
7. **Mistakes & Emotional Guardrails:** `docs/LESSONS_LEARNT.md`
8. **Multi-Agent Workflow:** `agents/WORKFLOW.md`
9. **Daily Progress & Session Handoff Log:** `docs/PROGRESS_LOG.md`

---

## 3. Role-Based Agent System & Workflow
All work in this project is orchestrated by the **Product Owner (Mother Agent)** using specialized skills in `.agents/skills/`:

| Role | Skill Path | Task Ownership |
| :--- | :--- | :--- |
| **Product Owner (Mother Agent)** | `.agents/skills/product-owner/SKILL.md` | Orchestrates workflow, splits tasks into atomic units, enforces 90% confidence gate with User. |
| **Prompt Agent (Always Subagent)** | `.agents/skills/prompt-agent/SKILL.md` | Converts raw user thoughts/situations into crisp, token-efficient prompts for any agent. |
| **Planner Agent** | `.agents/skills/planner-agent/SKILL.md` | Breaks features into 1–3 file units in `docs/IMPLEMENTATION_PLAN.md`. |
| **UI/UX Designer** | `.agents/skills/ui-ux-designer/SKILL.md` | Pre-execution design spec for UI units (uncluttered space-efficient UI; graphics only in Analysis). |
| **Execution Agent** | `.agents/skills/execution-agent/SKILL.md` | Implements one unit at a time (FastAPI, Kite, SQLite, Next.js HIFY Gold UI). |
| **Testing & Validation Agent** | `.agents/skills/qa-validation-agent/SKILL.md` | Runs tests, verifies strategy formulas, Decay Lock, Same-Strike Rollover, Paper Lab isolation. |
| **Security & Risk Auditor** | `.agents/skills/security-auditor-agent/SKILL.md` | Audits Kite credentials, Tailscale CORS/auth, Limit-only/Aukaat hard blocks, Kill Switch. |
| **Reconciliation Auditor** | `.agents/skills/reconciliation-auditor/SKILL.md` | Post-QA 3-way parity audit (Live Kite ↔ SQLite ↔ Console `.xlsx`). |
| **Session Historian** | `.agents/skills/session-historian/SKILL.md` | Runs at session opening & closing to maintain chat-independent continuity in `docs/PROGRESS_LOG.md` with IST timestamps. |

### Mandatory Agent Operating Rules
1. **90% Confidence Gate (Zero Assumptions):**
   - Any subagent with **< 90% certainty** must stop and ask the **Mother Agent (`product-owner`)**.
   - The **Mother Agent** with **< 90% certainty** must stop and ask the **User** before proceeding.
2. **Token-Efficient Unit Execution:**
   - Split every new task into small, manageable atomic units (`1–3` files per unit).
   - Pass only exact file paths and line ranges to subagents—never dump entire documents.
   - Use `prompt-agent` in subagent mode whenever converting raw user thoughts or complex situations into agent tasks.

---

## 4. Non-Negotiable Trading Guardrails
1. **After-Market Decisions & Manual Mode First:**
   - All opportunity scanning, strike selection, and ATO/GTT staging happen **after market hours**.
   - **Never** auto-fire live orders without explicit user approval in Phase 1.
2. **Strict Isolation of Paper / Strategy Lab:**
   - The **Paper / Strategy Lab** page must remain **100% disconnected** from Kite order/GTT placement endpoints (read-only quotes + local SQLite only).
3. **Hard Strategy Guardrails (Never Violate in Code):**
   - **Capital Tier ("Aukaat"):** ₹25L tier → max **4 naked positions** (or **6 hedged positions**).
   - **Limit Orders Only:** Never generate `MARKET` orders; reject options with `Bid-Ask Spread > 5%`.
   - **Decay Lock:** Enforce profit-booking targets (`30%` 1-day, `40–50%` 2–3 days, `50–60%` 15-day GTT, `70–80%` expiry week) and block impulsive early exits without a logged override reason.
   - **Same-Strike Rollover:** Never allow rolling a Put down to a lower strike; keep exact same strike or pivot to Far-Month Futures if illiquid.
   - **No Naked Calls:** Calls may only be sold as Covered Calls paired with a long stock/Future.
4. **Continuous Learning Loop:**
   - Whenever the user logs a new mistake or lesson in `docs/LESSONS_LEARNT.md`, translate it into a concrete validation check or UI guardrail.

---

## 5. Git Polyrepo Isolation & Tailscale One-Link Contract

- **Strict Polyrepo Isolation:** Never run `git init` at `D:\AI Projects\Trading Log\`. Each segment (`OptionSelling` -> `hify-option-selling`, `US Stocks` -> `hify-us-stocks`, future `Indian Swing` -> `hify-swing-india`, `HIFY-Hub` -> `hify-trading-hub`) is an independent Private Git repository.
- **Zero-Blast-Radius Commit Rule:** Never stage, modify, or commit files across sibling segment folders in a single commit. Use `.agents/skills/git-safe-commit/SKILL.md` before any commit.
- **Zero-Secret Gate:** Never commit `.env*`, `*.db`, `*.sqlite*`, `config/rules.yaml`, `logs/`, `Console_Reports/`, `Reports/`, `node_modules/`, `.next/`, `.venv/`.
- **Tailscale One-Link Port & Path Contract (`127.0.0.1` only):**
  - `HIFY-Hub`: `127.0.0.1:3099` -> `/`
  - `OptionSelling` UI: `127.0.0.1:3000` -> `/options` (API: `127.0.0.1:8000` -> `/options/api`)
  - `US Stocks`: `127.0.0.1:3010` -> `/us`
  - `Indian Swing` (future): `127.0.0.1:3020` -> `/swing`
