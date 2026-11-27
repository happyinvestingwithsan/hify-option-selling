# Multi-Agent Workflow & Roster

## 1. Agent Roster (Skills in `.agents/skills/`)

| Agent | Mode | Skill File | Primary Responsibility |
| :--- | :--- | :--- | :--- |
| **Product Owner** (`product-owner`) | **Mother Agent** (Main) | `.agents/skills/product-owner/SKILL.md` | Owns scope, splits tasks into small units, enforces the **90% confidence gate** with the user, delegates & accepts work. |
| **Prompt Agent** (`prompt-agent`) | **Always Subagent** | `.agents/skills/prompt-agent/SKILL.md` | Converts raw user thoughts, situations, or bug reports into crisp, token-efficient prompts for any agent. |
| **Planner Agent** (`planner-agent`) | Subagent | `.agents/skills/planner-agent/SKILL.md` | Breaks features into 1–3 file atomic units in `docs/IMPLEMENTATION_PLAN.md` with clear acceptance criteria. |
| **UI/UX Designer** (`ui-ux-designer`) | Subagent | `.agents/skills/ui-ux-designer/SKILL.md` | Runs **before `execution-agent`** on UI units to enforce clean space-efficient layouts, 3-tier disclosure, and graphics-only-in-Analysis. |
| **Execution Agent** (`execution-agent`) | Subagent | `.agents/skills/execution-agent/SKILL.md` | Writes backend (FastAPI/Kite/SQLite) and frontend (Next.js HIFY Gold UI) code one unit at a time. |
| **Testing & Validation** (`qa-validation-agent`) | Subagent | `.agents/skills/qa-validation-agent/SKILL.md` | Runs tests, verifies strategy math (PPM, 5% spread, Decay Lock, Same-Strike Rollover) & Paper Lab isolation. |
| **Security & Risk Auditor** (`security-auditor-agent`) | Subagent | `.agents/skills/security-auditor-agent/SKILL.md` | Audits Kite credentials, Tailscale CORS/auth, Limit-only/Aukaat hard blocks, and Kill Switch. |
| **Reconciliation Auditor** (`reconciliation-auditor`) | Subagent | `.agents/skills/reconciliation-auditor/SKILL.md` | Post-QA 3-way parity audit across Live Kite ↔ Local SQLite ↔ Zerodha Console `.xlsx` exports. |
| **Session Historian** (`session-historian`) | Subagent | `.agents/skills/session-historian/SKILL.md` | Maintains chat-independent daily continuity in `docs/PROGRESS_LOG.md` at session opening, milestones, and closing. |

### Optional Future Agent (Not Needed Yet)
- **Strategy & Lessons Analyst (`strategy-analyst`):** Can be added later if `docs/LESSONS_LEARNT.md` grows large and needs periodic rule mining or backtest analysis. For Phase 1, `qa-validation-agent` + `product-owner` cover rulebook checks to keep token usage lean.

---

## 2. Standard Execution Loop (Token-Efficient & High-Accuracy)
```text
[Raw User Thought / Situation]
       │
       ▼
  prompt-agent (Subagent) ──▶ Outputs minimal-token structured brief
       │
       ▼
  product-owner (Mother)  ──▶ Confidence >= 90%? ──(No)──▶ Ask User
       │ (Yes)
       ▼
  planner-agent (Subagent)──▶ Splits into 1–3 file Units (or asks Mother if <90%)
       │
       ▼
  ui-ux-designer (UI Units)─▶ Clean layout / space / 3-tier spec (graphics only in Analysis)
       │
       ▼
  execution-agent (Unit)  ──▶ Builds 1 Unit at a time (or asks Mother if <90%)
       │
       ▼
  qa-validation-agent     ──▶ Runs tests + rulebook checks
       │
       ▼
  security-auditor-agent + reconciliation-auditor ──▶ Post-QA safety & 3-way data parity
       │
       ▼
  product-owner (Mother)  ──▶ Reports verified result to User
```

## 3. Token-Saving Rules
1. **Unit-by-Unit Execution:** Never ask `execution-agent` to build the whole app in one turn; run one Unit (`U1`, `U2`, ...) per subagent call.
2. **Targeted Context Only:** Pass exact file paths and line ranges—never paste full markdown files into subagent prompts.
3. **90% Confidence Gate:** Any agent with `< 90%` certainty stops immediately and asks up the chain (`Subagent -> Mother Agent -> User`). Zero guessing.
