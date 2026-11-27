# Zerodha Kite Connect & After-Market ATO / GTT Plan

## 1. Execution Philosophy: After-Market Decisions, Manual First
- All scanning, strike selection, PPM calculation, and order staging happen **after market hours** in a calm, emotion-free review.
- Orders are **never** fired automatically in Phase 1; every entry, exit GTT, or rollover requires your explicit approval.
- Accessible from your **mobile browser via Tailscale** (`http://<home-laptop-tailscale-ip>:3011`) so you can monitor decay, approve staged orders, or trigger the Kill Switch from the office.

## 2. Kite Connect Capabilities Used
Using the official `kiteconnect` Python SDK:
- **After-Market & Live Market Data:** Fetch OHLC, historical candles (ATH drop %, Lower Blue Line envelope), option chain quotes, and Bid/Ask depth (enforcing the **≤ 5% Bid-Ask spread** rule).
- **Account & Portfolio Sync:** Read live Margins (available vs. pledged), Positions (open PEs/CEs/Futures), Holdings, and active GTTs/Orders.
- **Limit-Only Order & GTT Staging:**
  - **Entry ATO / GTT:** Stage a GTT trigger at your chosen panic/envelope price level that submits a **Limit Sell** (`NRML` on `NFO`)—never `MARKET`.
  - **Exit GTT:** Stage the **50%–60% decay** Buy Limit GTT right alongside or immediately after entry fill.
- **Paper / Strategy Lab Isolation:** The Paper Lab page reads quotes from Kite (read-only) and writes simulated trades strictly to local SQLite (`data/option_selling.db`), with **zero calls** to Kite order/GTT endpoints.

## 3. Daily Auth & Safety Guardrails
- **Morning 1-Click Login:** Zerodha requires a daily OAuth handshake (`request_token` → `access_token` valid until 6:00 AM next day).
- **Aukaat Hard Block (₹25L Tier):** Backend refuses to stage any live order exceeding **4 naked positions** (or **6 hedged positions**).
- **Kill Switch:** Single mobile/desktop button to cancel all pending GTTs/open orders immediately.
