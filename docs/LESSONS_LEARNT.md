# Lessons Learnt & Continuous Improvement Log

> Every mistake or emotional slip (greed, fear, impatience) is documented here and converted into an **automated system guardrail** so it cannot happen again.

---

## Core Emotional Guardrails (Initial Baseline)

| ID | Emotion / Mistake | What Happened | System Guardrail to Enforce | Status |
| :--- | :--- | :--- | :--- | :--- |
| **LL-001** | **Impatience / Early Profit Booking** | Booked Put profit early during a long wait instead of waiting for the decay rule. | **Decay Lock:** Dashboard hides/locks "Close Trade" CTA behind a warning modal unless Decay >= Rule Target (30% 1d / 40-50% 2-3d / 50% 15d / 70-80% expiry week). | `Planned` |
| **LL-002** | **Fear of MTM Drawdown** | Felt urge to panic-close a fundamentally sound stock during temporary red MTM. | **Chill-as-a-Robot Panel:** Show Fundamental Check (ATH Sales/Profits, <Median PE, >=70% Inst. Holding) + Rollover Math alongside MTM red to reinforce holding/rolling. | `Planned` |
| **LL-003** | **Rolling Down Strike** | Risk of rolling a Put down to a lower strike, locking in permanent loss. | **Same-Strike Validator:** Rollover staging tool locks the next-month strike to `== current_strike` (or pivots to Far-Month Future if illiquid). | `Planned` |
| **LL-004** | **Market Orders / Crossing Spread** | Slippage from market orders or illiquid options. | **Limit-Only + 5% Liquidity Gate:** Rejects order staging if `(Ask - Bid) / Mid > 5%` and pre-fills Limit price only. | `Planned` |

---

## Template for New Lessons
```markdown
### LL-XXX: [Short Title]
- **Date:** YYYY-MM-DD
- **Stock / Contract:** e.g., DABUR 510 PE
- **Trigger (Greed / Fear / Process Gap):**
- **What Happened:**
- **Rule Violated:**
- **New System Guardrail / Code Change:**
```
