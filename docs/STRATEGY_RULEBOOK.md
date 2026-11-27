# Option Selling Strategy Rulebook

Synthesized from `D:\AI Projects\FNO KBase\Handmade_Notes_with_AI` (`Oct_Batch_Class_1` through `Oct_Batch_Class_10`).

---

## 1. Core Philosophy ("Chill as a Robot")
- **The Wheel ("Dhool Chaat") Cycle:**
  1. **Sell Cash-Secured Puts (CSP)** on great companies that have crashed to collect premium or acquire at a discount.
  2. **Take Delivery / Roll** via Futures or next-month same-strike Puts if assigned—never panic-close fundamentally sound stocks.
  3. **Sell Covered Calls** against long stock/Future holdings to earn rent during recovery. (Always open/close Future + Call pairs **together**; never leave a naked Call).
- **Positive Greeks Only:** Always maintain **Positive Theta** (daily rent) and **Positive Delta** (profit on recovery). No naked Call selling.
- **No Stop-Losses on Great Stocks:** Risk is controlled via **Leverage Control ("Aukaat")** and **Eternal Rolling**, not panic stop-losses.

---

## 2. Stock Universe & Selection Criteria
- **Universe (Strictly 3 Lists — NO S200):**
  1. **F40 (Flagship 40):** Curated core 40 quality leaders (with In/Out changelog).
  2. **E40 (Emerging 40):** Curated 40 emerging leaders (with In/Out changelog).
  3. **All NSE F&O:** Dynamically synced daily from Kite `NFO` instruments (tracking newly added & excluded F&O stocks).
  - **Market-Cap Slicers:** Filter any universe by **Large Cap**, **Mid Cap**, or **Small Cap**.
- **Fundamental Filters:**
  1. Sales & Profits at or near **All-Time Highs (ATH)**.
  2. Trading **below Median PE**.
  3. **70% Institutional Rule:** `FII + DII + Promoter >= 70%`. Avoid PSU/Govt companies unless hedged.
  4. **Business Conviction:** Only trade sectors you understand; skip opaque sectors even if numbers match.
- **Beaten-Down ("Dhool Chaat") Drop from ATH:**
  - **Large Caps:** `-25%` to `-30%` from ATH (`-20%` in rare defensive cases like Dabur/HUL).
  - **Mid Caps:** `-30%` to `-40%` from ATH.
  - **Small Caps:** `-35%` to `-40%` from ATH.
  - **Special Situation:** `67% Funda` (great companies down ~67%) for long-term rolling.

---

## 3. Entry Triggers & Execution Rules
- **Red Candle + High IV:** Enter only on a day the stock is forming a **Red Candle** (intraday panic spikes Put IV/premiums).
- **Technical Envelope:** Target entries near the **Lower Blue Line** of the envelope:
  - *At Lower Blue Line:* **ATM Put** (Delta ~0.50, max Theta, ~60% win rate).
  - *Slightly Above:* **OTM Put** (Delta < 0.50, ~80% win rate, fast 2–3 day decay).
  - *Below Lower Blue Line:* **ITM Put** (Delta > 0.50, ~50% immediate win rate, higher reward on recovery).
- **Liquidity Check (5% Rule):**
  - Options: Reject if `Bid-Ask Spread > 5%` of option price.
  - Stocks/Futures: Reject if `Bid-Ask Spread > 1–2%`.
- **Limit Orders Only:** Never use market orders / never cross the spread.
- **Secondary Positioning (Sensible FII/DII & PCR):**
  - `PCR > 0.7`: Bullish (normal/aggressive sizing). `PCR < 0.3`: Bearish (conservative, OTM Puts, fewer lots).

---

## 4. Strike Selection, PPM & Capital Sizing ("Aukaat")
- **PPM (Percentage Gain per Margin):**
  $$\text{PPM} = \left(\frac{\text{Premium Received} \times \text{Lot Size}}{\text{Margin Blocked}}\right) \times 100$$
  - **Aggressive:** `PPM > 6%` (ATM Puts)
  - **Normal:** `PPM = 3% – 6%`
  - **Conservative:** `PPM < 3%` (deep OTM Puts)
- **Strict Lot Counter:**
  - **₹12L Capital:** Max **2 Lots** (Great Large Caps only).
  - **₹25L Capital:** Max **4 Lots / 4 Naked Positions** in 4 different stocks (or **6 Hedged Positions**).
  - **₹1Cr Capital:** Max **16 Lots**.
  - **₹2.5Cr Capital:** ~32–40 Positions (cut by **50%** when Nifty is at All-Time High).
- **Zero-Interest Margin Pledging:** Pledge Swing Stocks + Liquid Funds for 0% interest margin (never use MTF at 12–18%), keeping a cash buffer for MTM swings.

---

## 5. Profit Booking Rules ("Muh Meetha Karo")
Wait strictly for these decay targets—**never book early out of boredom/impatience**:
1. **Intraday Gift:** **30% decay** in 1 day → Square off immediately.
2. **Fast Move:** **40% – 50% decay** in 2–3 days → Square off immediately.
3. **Mid-Month Rule:** **50% – 60% decay** in ~15 days → Automate via **GTT**.
4. **Expiry Week Rule:** **70% – 80% decay** in the final week → Square off or roll.
5. **Never Wait for 100% Decay:** Close at 70–80% to avoid Gamma spikes and physical delivery penalties.

---

## 6. Rollover & Hedging Rules
- **Same-Strike Eternal Rolling:** If stock falls below strike near expiry, buy back current month Put and sell next month's **exact same strike** Put. **Never roll down to a lower strike** (locks in loss).
- **Deep ITM / Illiquid Pivot:** If next-month Put is illiquid, exit Put and **Buy Far-Month Futures** (saves STT: 0.02% vs 0.12% on ITM options). Hold Future for higher recovery targets rather than exiting for tiny profit.
- **Physical Delivery Guard:** Always square off or roll before final hours of Last Thursday unless taking delivery.
- **Position Hedge (High-Beta/PSU/Small Cap):** Bull Put Spread — sell ATM Put, buy OTM Put ~**10% lower**.
- **Portfolio Hedge:** Buy **Yearly/Far-Month ATM Nifty Puts** (~2% annual cost) sized to `Total Notional Exposure / (Nifty * Lot Size)`. Shift hedge only on an **8–10% Nifty crash**.
