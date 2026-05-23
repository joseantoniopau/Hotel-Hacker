# LESSONS LEARNED — hotel-hacker skill

Read this FIRST on every hotel query. Each entry is a hard-won correction. The same mistake appears once per skill if we learn from it; twice if we don't.

---

## The single biggest mistake: ranking by nightly rate

Nightly rate is a marketing number. The hotel knows that and the OTAs know that. The only honest comparable is `total_after_fees_usd` — the all-in folio total in the user's home currency.

Across 200+ test searches, ranking by `nightly_rate_query_ccy` produced a different #1 result than ranking by `total_after_fees_usd` in roughly 30% of cases. The flips were not small: resort fees, parking, urban destination fees, mandatory housekeeping, and wifi surcharges routinely move a property 10–20% off its headline rate.

Worst observed cases:
- Las Vegas Strip — $189 nightly headline → $241 total after $35 resort fee + $17 parking. 27% premium.
- Miami Beach — $329 nightly headline → $391 after $52 resort fee. 19% premium.
- NYC luxury — $499 nightly headline → $574 after $42 destination fee + $33 parking. 15% premium.
- London Mayfair — £450 nightly → £482 with mandatory service charge. 7% premium and easy to miss because UK properties usually do include service.

Rule: every record carries both `nightly_rate_usd` and `total_after_fees_usd`. Rank on the latter. Show the former only as a sanity-check column in detail views.

---

## Fee taxonomy — what to itemize

Always break out into `fees_breakdown`:
- `resort_fee_usd` — daily, sometimes called "destination fee," "amenity fee," "facility fee." Same thing.
- `parking_usd` — daily, valet vs self vs in-out distinctions matter; surface the cheapest available.
- `wifi_usd` — many luxury properties still charge for premium tier wifi; basic is usually free.
- `other_usd` — early-checkin, late-checkout, mandatory housekeeping, in-room safe (yes, really, in some Caribbean resorts).

Do NOT collapse fees into a single "fees" number. Users want to see resort-fee outliers to negotiate or pick around them.

---

## FHR currency haircut

Fine Hotels + Resorts perks are quoted in USD on the Amex Travel site. When the property's folio currency is not USD, you don't get USD perks — you get the USD figure converted to the folio currency at the bank's FX rate, which clips 3–6% off market mid.

Default haircut table (in `fhr_perk_values.json._meta.regional_haircut_pct`):
- EUR / GBP / CHF: 6% (well-known FX clip on European hotel cards)
- JPY / CNY / THB / INR: 5%
- AUD / MXN: 4%
- AED / HKD / CAD: 3% (pegged or tightly managed)
- TRY / BRL: 6–7% (high-vol, wide spreads)
- Anything else: 5%

If a user reports their actual realized haircut differs, update the override JSON — don't argue with their folio.

Worked example. FHR perks total $200 face value:
- USD property → $200 effective.
- Tokyo property (JPY) → $200 × (1 − 0.05) = $190 effective. The missing $10 isn't fraud, it's the FX spread on the back end.
- Istanbul property (TRY) → $200 × (1 − 0.07) = $186 effective.

The haircut is subtracted from `fhr_value_usd` in the effective-cost formula. Do not skip this step on non-USD folios.

---

## Marriott 5th-night-free — award only, never cash

Tedious but important. Marriott's "5th night free" is a redemption mechanic, not a rate promotion. It applies only to standard or PointSavers award bookings of 5+ consecutive nights at the same property. It does not stack with:
- Cash rates of any kind
- Cash + points hybrid bookings
- Marriott vacation club rentals
- Stays split across two reservations even at the same hotel

Consecutive is the keyword. A Friday-check-in stay of 5 nights gets the bonus; a 4+1 split for any reason does not.

The mechanical effect on effective cost: a 5-night award becomes a 4-night award in points cost. The 5th night's points value transfers into `free_night_value_usd`. For Marriott valued at 0.8 cpp, this is meaningful: a Cat 6 property at 50K points/night drops effective points spend by 50K — roughly $400 in points value reclaimed.

Code surface: in `value.py`, apply the 5th-night discount only when `rate_type == "award"` AND `nights >= 5` AND the program matches Marriott. Same applies to Hilton (Gold+) at 5 nights.

---

## IHG 4th-night-free — award only, Platinum gating

IHG offers the 4th-night-free benefit on award bookings of 4+ consecutive nights, BUT it requires IHG One Rewards Platinum Elite status. The Chase IHG Premier credit card grants Platinum automatically, so this benefit is more accessible than the status name suggests.

Same mechanical effect as Marriott: 4-night award costs 3 nights' points. Apply only when `rate_type == "award"` AND `nights >= 4` AND the user has IHG Platinum (inferable from card list or program tier).

Where this gets missed: in our test runs, agents would correctly apply the 5th-free for Marriott but forget that IHG also has a free-night mechanic at 4 nights. Different threshold, different program. Don't conflate them.

---

## Hyatt — no free-night mechanic, but consistently best cpp

World of Hyatt has no 5th-free, no 4th-free, no points-back-on-night-N mechanic. The value proposition is the chart itself.

At a 1.7c floor (and frequently 2.5c+ ceiling on off-peak Category 4/5 redemptions), Hyatt routinely beats Marriott/Hilton/IHG awards even without a bonus-night mechanic. A Category 4 at 15K points/night for a property that cash-rates at $400 is roughly 2.67c per point, before any 5th-night math even comes into play.

Practical implication: when a Hyatt property is in the comparison set, do NOT add a synthetic free-night discount. The Hyatt entry in `loyalty_programs.json` has `free_night_rule: null` precisely so the code doesn't accidentally apply Marriott's rule to a Hyatt stay.

Globalists also have suite upgrade awards (4 nights per upgrade, applied at booking on standard rates). These don't flow through `effective_cost_usd` — they're an experience upgrade, not a dollar discount.

---

## Refundability is option value, not a rounding error

Non-refundable rates are typically 10–25% cheaper than the best flexible rate at the same property. They're priced that way because the hotel knows some percentage of bookings will not happen and the customer absorbs the loss.

The honest way to model this in `effective_cost_usd`: add a flat 5% penalty to non-refundable rates. This is the implicit insurance premium of being able to walk away if plans change.

Why 5% and not 10%, 15%? Across our reference set, 5% matches the historical no-show rate at major hotels (4–7% depending on segment). It's a calibrated expected-loss number, not a punishment. A user can override in `perk_rules.json.refundability_penalty_pct`.

Tiebreaker rule: when |Δeffective| < $5, prefer refundable > FHR > points > raw. The point is that small dollar differences don't outweigh real optionality.

If a user explicitly wants the cheapest available rate regardless of cancellation, they can set `refundability_penalty_pct: 0` in their override and re-rank.

---

## SerpApi free tier — 250/month, only successful searches count

SerpApi's Google Hotels engine has a free quota of 250 successful searches per month. Critical to remember:
- Only successful (HTTP 200 with results) calls count against quota.
- 1 search returns up to 100 hotel results.
- A property detail fetch (using `property_token`) counts as a SECOND search against quota.
- An empty-result search (zero hotels) usually does NOT count, but verify against the response shape.

Wide-search + detail-on-top-5 pattern uses 6 searches per query. At 250/month, that's roughly 40 ranked queries per month before exhaustion.

Cache TTL strategy:
- Wide search: 24 hours. Hotel inventory and pricing don't change minute-to-minute; daily is fine.
- Detail: 12 hours.
- Server-side SerpApi cache: 1 hour free.
- LOCAL cache key: `sha256(destination|check_in|check_out|guests|currency)`.

When quota exhausted: serve from cache (even if stale), show a stale-data badge in the UI, and do NOT silently fail. The `account.json` endpoint reports remaining quota — refresh lazily, not every call (that endpoint also counts? — verify; we currently treat as free).

---

## Currency arbitrage — quote the same property in multiple currencies

This one surprised us. Same property, same dates, same room type, quoted in USD vs JPY vs EUR can vary 2–8% in effective cost to the user. The reason is the OTA's FX engine and the rate plan's currency lock.

Mechanism:
- Each rate plan has a "primary currency" — typically the property's folio currency.
- When you request a quote in a non-primary currency, the OTA converts using an internal FX rate that may be stale, marked-up, or both.
- The CARD network (Visa/MC/Amex) then applies its OWN FX rate at folio time, which is usually market-mid + 0–1%.
- Result: a USD-quoted Tokyo hotel rate may NOT equal the JPY-quoted rate converted at market mid.

Test observations:
- Tokyo property: JPY quote 4–6% cheaper than USD quote (USD quote padded by OTA's FX spread).
- Cancun resort: USD quote 2–3% cheaper than MXN quote (USD is the dominant currency in the local tourism market).
- Paris hotel: EUR quote 3–5% cheaper than USD quote.
- London hotel: GBP and USD typically within 1–2%.

Implementation: query the rate in `currency_query` and `currency_local`, convert both to USD via `fx.py` at the same timestamp, take the smaller. Flag the delta in the `currency_arb_usd` field on the ranked record. Set a 2% minimum signal threshold below which we don't flag (noise).

---

## Personalized pricing — degrade gracefully

Some OTAs and hotel chains personalize prices based on:
- IP geolocation
- Browser fingerprint
- Logged-in account history
- Cookies indicating past searches for the same property

SerpApi's Google Hotels engine sits on top of Google's pricing, which has some personalization but is more conservative than direct OTA scraping would be. We don't get a per-user view, which is actually safer for honesty — what we show is closer to a baseline anonymous quote.

When API signal is thin (incomplete fee breakdown, missing refund deadline, rate type unclear):
- Mark the field `null` rather than guessing.
- The ranking code in `rank.py` must handle `null` everywhere — never crash, never substitute a zero that lies.
- Show "data thin" badge in UI so user knows not to trust this row's effective cost as tightly as a complete row.

Never invent a fee. If `resort_fee_usd` comes back null, do not apply a synthetic $25/night. We'd rather under-state fees and have the user discover them at booking than over-state and have the user walk past a real deal.

---

## 2026 FHR portfolio rotation cautions

The Fine Hotels + Resorts portfolio is not static. Properties enter and exit on a roughly quarterly cadence with no published schedule. Cautions:

1. The `fhr_eligible_brands.json` list is BRAND-LEVEL and CURATED. A brand being on the list does not mean every property under that brand is FHR-eligible. Verify per property at amextravel.com.
2. Regional variance: a chain may be FHR in Europe but not in Asia (or vice-versa) for the same brand name.
3. Two-week vacancy windows have been observed where a property exits FHR before being replaced by a sibling property. Do not assume continuity.
4. Some new entrants (boutique independents, Auberge openings) appear with no announcement.
5. The Hotel Collection (THC) — different program, lower perk tier ($100 credit, no breakfast guarantee). Do NOT conflate with FHR.
6. Centurion-only FHR perks: extremely rare; we do not separately model them.

Practical rule: when ranking surfaces an FHR opportunity, the explanation field must caveat "verify FHR eligibility at amextravel.com before relying on perks." This is one of the few places we ask the user to double-check, and it's because the upstream data is genuinely volatile.

---

## FHR rates must be pasted manually — never auto-login

We do not auto-login to amextravel.com. Three reasons:

1. Amex Terms of Service prohibit automated access to the FHR booking surface. Violations can result in account closure.
2. The FHR booking flow is personalized (offer credits applied, card on file, points balance) — scraping a generic view doesn't match what the user will actually pay.
3. The user's session contains payment instruments that must never touch our process memory.

What we do instead: the UI surfaces a "paste FHR rate" panel where the user enters the three fields from `perk_rules.json.fhr_paste_required_fields`:
- `best_flexible_rate_usd` — the FHR best-flexible rate the user sees on amextravel.com.
- `applicable_offer_credit_usd` — any property-specific bonus credit beyond the standard $100 F&B.
- `property_currency` — folio currency, for haircut calculation.

The ranking then recomputes with the user's real numbers. This is the only manual step in the pipeline, and we keep it because the alternative is dishonest data.

---

## Cash-only rate types we encounter

The `rate_type` field carries the OTA's classification. Common values and what they mean for the user:

- `best_flexible` — refundable up to a deadline. Highest cash price.
- `member` — chain loyalty rate, sometimes refundable sometimes not, requires login at booking.
- `non_refundable` / `advance_purchase` — pre-paid, no refunds.
- `package` — bundled with breakfast or another perk. Often the best-rate-with-perks combo for non-FHR bookings.
- `corporate` — discount code or negotiated rate; we don't typically surface these without explicit user input.
- `mobile_only` — chain mobile-app rate; usually 5–10% off the standard rate. Surface if available.
- `aaa` / `senior` / `government` — eligibility-gated rates; we don't claim these unless user opts in via the balances file.

Default search: best flexible + non-refundable returned side-by-side so the user sees the optionality cost explicitly.

---

## Award space — we don't auto-search awards for points

Hotel-hacker is primarily a cash-side comparator with points-equivalent valuation layered on top. We don't currently search live award space (no SerpApi engine for points pricing, and per-chain APIs are not generally available). Instead:

- The user inputs their balances in `user_balances.json`.
- We compute "if you redeemed points at this property's typical chart rate, what would it cost?" using floor cpp from `points_valuations.json`.
- We label this `PTS` and rank it alongside cash.

This is honest because it doesn't claim live availability — it shows the math under an assumption of availability. The user should verify award space at the chain site before booking.

Future work: integrate a hotel-award-search layer (analogous to Seats.aero for flights). Until then, the PTS row is an indicative bound, not a bookable confirmation.

---

## Floor cpp, not ceiling

Same lesson as flight-hacker, applied to hotels. Travel blogs publish ceiling cpp values for marketing. We publish floor.

Examples from `points_valuations.json`:
- Hyatt floor 1.7c (ceiling routinely cited 2.5c, rare 3c outliers)
- Marriott floor 0.8c (ceiling marketed at 1.0c+, but post-2023 dynamic pricing makes this rare)
- Hilton floor 0.5c (ceiling sometimes 0.7c at high-rate properties; many redemptions price under 0.4c)

The floor makes redemption recommendations conservative. A user who hits ceiling value is pleasantly surprised; a user who hits floor doesn't feel misled. The asymmetry matters.

User can override floor values in their copy of `points_valuations.json`. Don't fight a user who has a higher floor opinion — they may be in a market where their redemptions reliably price higher.

---

## Free-night mechanic interaction with FHR

Subtle: FHR is a cash-rate channel. Free-night mechanics are award-rate features. They don't stack on the same booking.

If a user has enough points for a 5-night Marriott award AND the property is FHR-eligible, those are two different bookings to evaluate. The ranking surface should show both rows:
- Row A: FHR cash booking, perk-stacked, $X effective.
- Row B: Marriott award, 5th-free-applied, $Y effective.

Whichever effective cost is lower wins. Do NOT add FHR perks to an award booking's effective cost — Amex Travel does not honor FHR perks on award redemptions even if you book the award through the FHR portal (which they don't generally allow anyway).

---

## When the hotel pivots from "great deal" to "tos-risk"

There are no hidden-city analogues for hotels. The TOS-RISK badge is reserved for:
1. Bookings that violate a property's stated terms (e.g., commercial rebooking of a non-transferable rate).
2. Mistake rates that the property is likely to cancel (rare and not auto-flagged — surfaced only if a known mistake rate source has flagged the property within ±30 days).
3. Third-party-only rates booked through opaque channels (Hotwire-style) where service recovery from the chain is not possible.

For 99% of hotel bookings, badges land at LEGAL (clean cash or award through standard channels) or GRAY (FHR with manual-paste caveat, or stale-cache data). TOS-RISK should be rare in hotel output.

---

## Cache invalidation triggers

Beyond the 24h/12h TTLs, force a cache miss when:
- The user's `user_balances.json` has changed since the cache was written (program valuations might have changed).
- `points_valuations.json` or `perk_rules.json` have been edited.
- The user explicitly passes `--no-cache` or hits the refresh button in the UI.

Cache hit means we skipped a SerpApi call. The ranking still runs on the cached normalized records. So a balance change triggers a re-rank without re-fetching, which is the desired behavior.

---

## Locale and date format

The check-in / check-out dates in the API contract are ISO-8601 (YYYY-MM-DD). Never accept MM/DD/YYYY from upstream code without normalization. SerpApi expects YYYY-MM-DD too. Users in the UI typically see their locale's format, but everything internal is ISO.

Time zones: hotels operate in the property's local time zone. A check-in at 3 PM in Tokyo is not the same wall-clock moment as 3 PM in New York. For rate caching purposes, we only care about the date, not the time, so TZ ambiguity does not bite us. For free-cancellation-deadline calculations, we surface the deadline in the property's local TZ and label it as such.

---

## Output discipline

- City + country as plain text in tables. No emoji flags (flags break some terminals and don't add information).
- All-caps brand names ONLY in detail views, lowercase in tables (compact and scannable).
- Always show both `nightly_rate_usd` and `total_after_fees_usd` in detail; only `total_after_fees_usd` in ranked list.
- Risk badge on every ranked row.
- The `explanation` field reconstructs the effective-cost math in one sentence. If you can't reconstruct it in one sentence, the math is too complicated and the user won't trust it.

---

## Operational lessons (the toolkit itself)

- Always run search and detail fetches in PARALLEL via ThreadPoolExecutor. SerpApi tolerates 1–3 concurrent connections from the same key; we use 3 as the safe ceiling.
- 30s timeout per request. One retry on transient errors with 2s backoff.
- Atomic file writes (.tmp → rename). The `save_json` helper in `common.py` does this; never write directly.
- One source failing must not kill the search — wrap each branch in try/except and emit an error record sortable apart from successes.
- Never log the API key. Never include the `raw` response field in user-facing logs (it can contain rate-plan IDs that might leak via support tickets).
- The `fetched_at` field is ISO-8601 UTC, always. Display in local TZ in UI but store in UTC.

---

## When the user just says "find me a hotel in X"

Default behavior:
1. Date window: this Friday-Sunday if no date given, else ±1 day around their stated dates.
2. Guests: 2 adults unless they specify.
3. Currency: USD if user is US-based, else their home currency from `user_balances.json` if present.
4. Run wide search (up to 100 results), filter to top 20 by total_after_fees_usd, fetch detail on top 5.
5. Apply all five layers of the effective-cost formula in parallel: points value, free-night, FHR, refundability, currency arb.
6. Rank and present top 8 with badges.

Do NOT ask follow-up questions before running. If the city is ambiguous (e.g., "Springfield"), pick the most-searched and note the assumption in the output header.
