# HOTEL-HACKER PLAYBOOK — Strategies by Trip Archetype

Loaded after `lessons.md` on every search. This document is a strategy index, not exhaustive prose. Each archetype tells you what to weight, where to look, and what to verify manually.

The five canonical archetypes:

| ID | Archetype | Nights | Channel default | Free-night relevance | FHR fit | Currency-arb attention |
|----|-----------|--------|-----------------|----------------------|---------|------------------------|
| A  | Weekend city break | 1–2 | OTA / chain direct | Low | Medium | Low |
| B  | 4+ night resort | 4–6 | Chain points + FHR | High (Marriott/IHG/Hilton) | High | Medium |
| C  | 5+ night luxury | 5–10 | FHR + Hyatt cash | High (5th-free properties) | Very high | High |
| D  | Conference (locked dates) | 2–4 | Chain direct + corp rate | Low | Low | Low |
| E  | Long international stay | 7+ | Mixed cash + FHR + arb | Medium | Medium | Very high |

---

## A. WEEKEND CITY BREAK (1–2 nights)

Common case: Friday/Saturday domestic, 1–2 guests, locked dates.

Priority weights (sum to 1.0):
- `total_after_fees_usd`: 0.55
- `refundability`: 0.20
- `points_value_usd`: 0.10
- `fhr_value_usd`: 0.10
- `currency_arb_usd`: 0.05

Recommended channel: OTA (Booking.com, Expedia) for breadth; chain direct if user has status. Most chain best-rate guarantees apply on short stays — worth checking but rarely fires.

Free-night opportunities: Low relevance. None of the bonus-night mechanics trigger at 1–2 nights. Don't even surface them in the row badges for these stays.

FHR fit: Medium. The $100 F&B credit is valuable on a 2-night stay because it amortizes well per night. Late-checkout (a Sunday afternoon perk) is genuinely useful here. But many short-stay travelers won't be at luxury properties anyway.

Refundability emphasis: HIGH. Plans change on short trips more often than they do on planned long stays. Default-display refundable rate; surface non-refundable as a side-by-side comparison.

Currency arbitrage attention: LOW. For domestic stays, none. For short international hops, the cash spread is small enough that the 2% noise threshold often suppresses the signal anyway.

What to check manually:
- Resort fees in the destination city (Vegas, Miami, Honolulu — always).
- Sunday late checkout — call the property; many will extend free.

---

## B. 4+ NIGHT RESORT (4–6 nights)

Common case: vacation week at a beach / lake / mountain property. Often family-of-4. Date-flexible by ±2 days.

Priority weights:
- `total_after_fees_usd`: 0.35
- `free_night_value_usd`: 0.25 (this is the headline lever)
- `fhr_value_usd`: 0.15
- `points_value_usd`: 0.10
- `refundability`: 0.10
- `currency_arb_usd`: 0.05

Recommended channel: Chain direct with award points if available. Marriott 5-night award triggers the 5th-free at any qualifying property in the portfolio. IHG 4-night award triggers 4th-free with Platinum. Hilton 5-night award triggers 5th-free at Gold+.

Free-night opportunities: VERY HIGH relevance. Surface as a top-badge `5TH-FREE` or `4TH-FREE` on every ranked row that qualifies. The math is large:
- Marriott Cat 6 at 50K/night, 5-night stay: 200K points instead of 250K. At 0.8c floor, that's $400 reclaimed.
- IHG 35K/night property, 4-night stay: 105K instead of 140K. At 0.5c floor, that's $175.
- Hilton 80K/night property (Gold+), 5-night: 320K instead of 400K. At 0.5c, that's $400.

FHR fit: HIGH. Resort properties heavily represented in FHR. The $100 F&B credit + breakfast + late checkout on a 5-night stay is roughly $400–500 of perk value, before haircut. Compare against the points path explicitly.

Refundability emphasis: MEDIUM. Vacation dates are usually firmer than weekend dates. Some users will accept non-refundable to save 15–20%; surface the choice.

Currency arbitrage attention: MEDIUM. Beach resorts in MX, CR, DR, Caribbean often dual-quote in USD and local currency. USD is usually cheaper at Caribbean and Mexican resorts; local-currency cheaper at European resorts.

What to check manually:
- FHR perk applicability per property (`fhr_eligible_brands.json` is brand-level, not property-level).
- Holiday surcharges — many resorts inflate over Christmas/Thanksgiving/Easter with mandatory minimum stays.
- Whether the property's award chart is in standard or off-peak pricing for the date window.

---

## C. 5+ NIGHT LUXURY (5–10 nights)

Common case: anniversary, honeymoon, milestone trip. Single luxury property or two adjacent properties. Date flex modest.

Priority weights:
- `fhr_value_usd`: 0.30 (the highest weighting of any archetype)
- `total_after_fees_usd`: 0.25
- `free_night_value_usd`: 0.15
- `points_value_usd`: 0.10
- `refundability`: 0.10
- `currency_arb_usd`: 0.10

Recommended channel: FHR via Amex Platinum (manual paste). Hyatt cash with Globalist perks is the FHR-rival on Park Hyatt / Andaz / Thompson properties. Compare both.

Free-night opportunities: HIGH at Marriott Luxury / Ritz / St. Regis (5-night) and at Hilton Waldorf Astoria / Conrad (5-night with Gold+). 5th-free is most impactful here because nightly rates are highest.

FHR fit: VERY HIGH. This is FHR's sweet spot. Every perk in the table is meaningful at luxury price points:
- $100 F&B credit at a $1000/night property is real money.
- Late checkout to 4 PM on a luxury property is often a $200+ commercial value.
- Room upgrade (subject to availability) at a Four Seasons can be $300–500 of upgrade value.
- Daily breakfast for 2 at a high-end European property is genuinely $80–100/day.

Total realized FHR perk value on a 5-night luxury stay frequently hits $400–600 face. After haircut (5–6% for EUR/CHF properties), realized $375–565.

Refundability emphasis: MEDIUM-HIGH. Luxury cancellation windows are often longer (some properties have 14–21 day cancellation), which IS the refundability — so it may already be priced in. Verify the deadline in the booking confirmation.

Currency arbitrage attention: HIGH. Luxury properties in EUR/GBP/CHF/JPY are the ones where the OTA's FX engine clips most. Always query in both folio currency and USD; take the cheaper.

What to check manually:
- FHR vs Hyatt Globalist: at Park Hyatt properties, Globalist breakfast can be richer than FHR breakfast credit. Math both paths.
- Whether the property's FHR rate is the same as the best-flexible (it usually is) or marked up (occasionally happens).
- Upgrade likelihood — read recent FlyerTalk / Reddit r/amex threads for the specific property.

---

## D. CONFERENCE (locked dates, 2–4 nights)

Common case: business travel with fixed conference dates. Often the conference has a "group rate" code. Single guest typical.

Priority weights:
- `total_after_fees_usd`: 0.50
- `refundability`: 0.25
- `points_value_usd`: 0.10
- `fhr_value_usd`: 0.05
- `currency_arb_usd`: 0.05
- `free_night_value_usd`: 0.05 (low relevance, 2–4 nights rarely triggers)

Recommended channel: Conference group rate FIRST (compare against open-market). Then chain direct with corporate or business rate if user has one. OTA last — many corporate cards earn 3-5x on hotel direct bookings and 1x on OTA.

Free-night opportunities: LOW. Conferences are typically 3–4 nights; IHG 4-night triggers occasionally if dates line up. Don't optimize for free-night on a 2-night stay.

FHR fit: LOW. Conference hotels are typically not in the FHR portfolio (FHR skews luxury leisure). Don't weight this heavily; surface only if the conference happens to be at a Four Seasons / Ritz.

Refundability emphasis: VERY HIGH. Conference attendance gets cancelled (travel ban, project conflict, family emergency). The refundable rate is usually 10–15% more expensive than non-refundable; pay it.

Currency arbitrage attention: LOW. The conference fixes the city; user has no flexibility to shift to a different market. Quote in USD and home currency; flag if delta is >3%, otherwise ignore.

What to check manually:
- Group rate code — these are usually published on the conference website and not surfaced by SerpApi at all.
- Corporate negotiated rate — check via the user's company travel portal if they have one.
- Whether the conference offers a "host hotel" with shuttle service — proximity sometimes outweighs $50 nightly savings at a competitor 10 minutes away.

---

## E. LONG INTERNATIONAL STAY (7+ nights, currency-volatile)

Common case: extended international stay — sabbatical week, slow travel, family visit in a market with volatile or weak local currency.

Priority weights:
- `total_after_fees_usd`: 0.30
- `currency_arb_usd`: 0.25 (highest weighting of any archetype)
- `fhr_value_usd`: 0.15
- `free_night_value_usd`: 0.15
- `points_value_usd`: 0.10
- `refundability`: 0.05

Recommended channel: MIXED. Often the optimal play is: book first night refundable through any channel, lock in arrival certainty, then optimize subsequent nights as the date approaches and cash rates settle.

Free-night opportunities: MEDIUM. On 7+ night stays the 5th-free / 4th-free mechanics fire reliably. But the savings are smaller as a percentage of total spend because the points cost spreads over more nights.

FHR fit: MEDIUM. FHR perks like F&B credit and breakfast are per-stay, not per-night, so the perk-per-night amortization is worst on long stays. The breakfast credit is exception (per-day, so scales). For 10-night stays, FHR still adds $200–400 realized value but other levers matter more.

Refundability emphasis: LOW. Long international stays are usually firmer plans (visas, flights booked, lodging logistics). Refundability is less critical; surface non-refundable rates with the standard 5% penalty and trust the user to choose.

Currency arbitrage attention: VERY HIGH. This is the archetype where the dual-quote check has the biggest payoff. On a 10-night Tokyo stay:
- USD quote total: $4,200
- JPY quote converted at market mid: $3,990
- Delta: $210 (5%)
- That's real money. Always run both quotes.

For Tokyo, Buenos Aires, Istanbul, Cairo, Mexico City, Bangkok — query in both USD and local; take the cheaper.

What to check manually:
- Card network for the booking: Visa and Mastercard have different FX rates than Amex; check the user's card list and pick the booking currency that minimizes their network's FX clip.
- Property's billing currency: sometimes the OTA's display currency differs from the folio currency; the folio is what hits the card.
- Whether the user can pay a deposit in local currency and balance on arrival (some Asian properties allow this — interesting if local currency is depreciating).

---

## SUPPLEMENTARY ARCHETYPES

These are not the five canonical archetypes but they come up enough to document.

### F. Award-stay only (user wants to use points regardless of cash math)

Don't fight the user. They want points. Rank by `points_value_usd` recovered and let them pick. Still surface `total_after_fees_usd` so they see the cash-equivalent comparison, but don't add a 5% penalty to award rates (awards are typically non-refundable but the user explicitly asked for points).

### G. Mistake rates / hot deals

Hotel-hacker does not currently ingest mistake-rate feeds (this is on the roadmap). If the user reports a mistake rate at a property, surface it as a single-row recommendation with caveats:
- Book and screenshot the confirmation immediately.
- Do not call to confirm — calling triggers a review that often results in cancellation.
- Have a backup booking for the same dates that you can cancel if the mistake holds.

### H. Status-run / nights-credit hunting

User is targeting Hilton Diamond / Marriott Platinum / IHG Diamond and needs N more qualifying nights. Optimize for:
- Lowest-cost qualifying nights at any property in the chain.
- Mattress runs (single-night stays at low-cost chain properties) acceptable if needed.
- Earn promotions stacked (current Q-promos in the chain) before booking.

This is its own optimization problem and not the default flow.

### I. Multi-property trip (one trip, two cities)

Surface each city independently and rank within each. If both cities have FHR-eligible properties, weight FHR slightly higher since the user is willing to manage two FHR pastes. If one city is conference (locked) and another is leisure (flex), don't average — show them as two separate ranked tables.

---

## CHANNEL DECISION TREE (when archetype is ambiguous)

```
Is the user's stay primarily for business with fixed dates?
  YES → Archetype D (conference). Prefer corporate / group rate.
  NO  → Continue.

Is the stay 7+ nights AND in a market with non-USD folio?
  YES → Archetype E (long international). Prioritize currency arb.
  NO  → Continue.

Is the property luxury-tier (Four Seasons, Ritz, St. Regis, Aman, Rosewood, etc.) AND stay >= 4 nights?
  YES → Archetype C (5+ night luxury). Prioritize FHR.
  NO  → Continue.

Is the stay 4–6 nights at a resort property?
  YES → Archetype B (4+ night resort). Prioritize free-night mechanic.
  NO  → Continue.

Default → Archetype A (weekend city break). Prioritize refundability + total cost.
```

---

## SEARCH-FANOUT TEMPLATE (for subagents)

When fanning out to subagents per destination, use this template:

```
Destination: <city, country>
Date window: <YYYY-MM-DD to YYYY-MM-DD, with ±N day flex>
Guests: <n>
Currencies to query: [<query_currency>, <folio_currency_if_different>]
Archetype: <A|B|C|D|E>

Run in this order:
1. search_hotels.py with widest acceptable parameters — parallel by currency
2. Filter top 20 by total_after_fees_query_ccy
3. search_details.py on top 5 — parallel
4. rank.py with archetype-specific weights

Aggregate JSON into one list. Pipe to rank.py.
Return top-8 rows in compact ASCII table. No raw JSON.
```

---

## WHEN TO PRESENT A NON-OBVIOUS RECOMMENDATION

If the ranked #1 is FHR but #2 is a Hyatt cash booking that's only $30 more, lead with the Hyatt and explain why:
- Hyatt earns elite-qualifying nights toward Globalist.
- Hyatt cash earns base + bonus points that have ongoing value.
- FHR perks are stay-specific; Hyatt status compounds across the year.

The "lower effective cost" winner is not always the best recommendation when the user is on a status track. The ranking output exposes the dollar delta; the playbook helps interpret it.

---

## WHEN TO TELL THE USER TO STOP AND VERIFY

Verify manually before booking when:
- The FHR perk stack is the headline savings (verify property is currently FHR at amextravel.com — portfolio rotates).
- The currency arb signal is >5% (rare; usually a stale-cache artifact, not a real opportunity).
- A free-night mechanic would change the ranking AND the user's program tier is unclear (check status with the chain before assuming benefit).
- The property's award chart is rumored to be devaluing (check the chain's official chart page directly).

For everything else, the ranking output is bookable.

---

## CALIBRATION NOTES

These weights are starting points. After a user has run 10+ searches, we should be able to calibrate:
- Whether they actually book the top-ranked option (if not, why not — gather the signal).
- Whether the FHR weight is too high or too low for their typical bookings.
- Whether the refundability penalty matches their actual cancellation behavior.

User-level overrides go in `user_balances.json` or a future `user_preferences.json`. We do NOT calibrate weights silently — the user should be able to see and edit them.
