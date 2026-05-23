# hotel-hacker

**Find the TRUE cheapest hotel stay — the one Google's price tag doesn't tell you.**

When you search a hotel on Google, you see a sticker price. That's it. This tool layers in everything that actually moves the needle — the points you already have, free-night mechanics most travelers don't realize they're owed, and the Amex Fine Hotels & Resorts perks that often net cheaper than booking direct. Then it ranks every option side-by-side in one table.

**Free, runs on your own computer.** Your balances and your Amex info never leave your machine.

```
┌──────────────────────────────────────────┐
│             hotel-hacker                 │
│  cash + points + Amex perks · ranked     │
│  refundable · risk-badged · local-only   │
└──────────────────────────────────────────┘
```

Live page: https://joseantoniopau.github.io/Hotel-Hacker/
Sibling project (flights): https://github.com/joseantoniopau/flight_hacker

---

## What it does (in plain English)

When you check a hotel on Google, you see one number. This tool adds **everything Google leaves out** and shows you the real cost of every option in the same table.

- 💰 **True total cost**: Resort fees, parking, wifi — folded into the headline number, not buried in a footnote three clicks later.
- 🎫 **Loyalty-point and free-night smarts**: Checks if your Hyatt, Marriott, Hilton, IHG, or Accor points actually reach the stay — and applies Marriott's fifth-night-free award, IHG's fourth-night-free, and Hilton's fifth-free automatically when you have a positive balance.
- 💳 **Amex Fine Hotels & Resorts perks valued in dollars**: For the right luxury stays, the Amex channel ($100 property credit + daily breakfast + 4 PM late checkout + room upgrade when available) often nets cheaper than the public best-flexible rate. The tool does the math you'd otherwise have to do on a napkin — but only when you've ticked at least one qualifying Amex card in the BALANCES tab.
- 🌍 **Currency haircut on non-US-dollar folios**: When a hotel charges in a volatile local currency, the Amex statement credit converts at a rate that typically clips 3–6%. The tool subtracts that haircut from the effective Amex credit so the comparison stays honest.
- ⚠️ **Risk labels on every row**: Each result is tagged *Verified rate*, *Unverified* (cache stale or rate not confirmed), or *Booking risk* (an aggressive tactic we explain but never auto-execute). No surprises.
- 🧮 **Self-explaining math**: Every row's notes column shows the one-sentence reason citing the exact line items applied. Click any row to expand the full breakdown grid.
- 🔒 **Local-only**: Your points balances, your Amex card list, your trip plans — none of it leaves your computer.

---

## What the tool actually computes per row

The ranking formula in plain English:

```
  raw nightly rate × nights                       (Google's number)
+ resort fees, parking, wifi (when known)         (the fees Google hides)
─ loyalty-point value                             (only when you have the balance to book)
─ free-night value                                (Marriott 5-for-4, IHG 4th-free, Hilton 5th-free)
─ Amex Fine Hotels & Resorts perks                (only when an eligible Amex card is in your wallet)
+ currency haircut on non-USD folio               (3-6%, eats the Amex credit's real value)
+ 5% flexibility penalty                          (non-refundable rates only)
─────────────────────────────────────────────
= effective cost                                  (what you'd actually pay)
```

Every line is shown in the breakdown grid when you click a row. If a discount can't be honestly applied (no balance, no eligible card, brand not enrolled), that line is zero — the tool never invents a discount you wouldn't actually receive.

---

## Who is this for?

You'll get the most out of this if:

- ✅ You stay in hotels at least twice a year
- ✅ You have a points-earning credit card already, OR you're starting to think about getting one
- ✅ You're willing to spend ~10 minutes on a one-time setup
- ✅ You're comfortable copy-pasting a few commands into your computer's Terminal app

You don't need to be a programmer. You don't need to be an Amex Platinum holder either — most features work without one. But if you have one, the Amex Fine Hotels & Resorts math is where this tool earns its keep on luxury stays.

---

## What you need before you start

1. **A Mac or Linux computer** (Windows works through WSL — see Troubleshooting)
2. **About 10 minutes** for the one-time setup
3. **A free SerpApi account** at https://serpapi.com/ — this is the connection to Google Hotels that powers all the searches.

   **This is the big difference from our sibling project.** Unlike [flight_hacker](https://github.com/joseantoniopau/flight_hacker) which needs a **$99/year Seats.aero subscription**, hotel-hacker only needs a **free SerpApi account**. The free tier gives you 250 searches per month, which covers casual use — a typical trip-planning session uses 1 wide search plus a handful of detail lookups, so you can comfortably plan many trips per month without ever paying.

4. **(Optional)** A free **Google Maps API key**. Without one, the map at the top of the results page shows a faded "For development purposes only" watermark from Google. It still works — just looks unfinished. Getting a key takes ~3 minutes at [console.cloud.google.com/google/maps-apis/start](https://console.cloud.google.com/google/maps-apis/start): create a project, enable the Maps JavaScript / Maps Embed / Street View Static APIs, generate a key, paste it in when `setup-keys.sh` asks. Google's free tier covers ~28,000 map loads per month — way more than you'll ever use locally.
5. **(Optional)** An Amex Platinum, Centurion, or Business Platinum card if you want to use the Amex Fine Hotels & Resorts features. Everything else works without it.

---

## How to install (step by step)

The whole setup takes about 10 minutes. You only do it once.

### Step 1: Open Terminal

This is just a black window where you type commands. On a Mac: press `Cmd + Space`, type "Terminal", press Enter. Don't worry if you've never opened it before — you're not breaking anything by being here.

You'll see a small prompt waiting for you. That's all the next steps need.

### Step 2: Check you have Python

Python is the language this tool is built in. Most Macs already have it.

Copy this line, paste it into Terminal, press Enter:

```bash
python3 --version
```

You should see something like `Python 3.10.6` or higher. If you see that, you're good — skip to Step 3.

If you see "command not found" or a version below 3.10, install Python from https://www.python.org/downloads/ first. Download the latest version, run the installer like any other Mac app, then come back here.

### Step 3: Download the tool

This is just copying the tool to your Desktop. It takes about 10 seconds.

Paste this into Terminal and press Enter:

```bash
git clone https://github.com/joseantoniopau/Hotel-Hacker ~/Desktop/hotel-hacker
cd ~/Desktop/hotel-hacker
```

You'll see a bunch of lines scroll past — that's good, it means the download worked. When you see the prompt again, you're done with this step.

### Step 4: Run the installer

This downloads the small helper files the tool needs to run. Takes about 30 seconds.

```bash
./install.sh
```

You'll see a long list of words scrolling by — that's the installer fetching what it needs. When it finishes you'll see something like "Setup complete." Don't worry about most of what scrolled past; the installer is just being honest about its work.

### Step 5: Get your free SerpApi key

This is the connection to the hotel search service. It's free.

1. Open https://serpapi.com/users/sign_up in your browser
2. Sign up with email or Google (takes 30 seconds, no credit card needed)
3. Once logged in, go to https://serpapi.com/manage-api-key
4. Copy the long string they show you — that's your key

### Step 6: Tell the tool your key

Back in Terminal, run:

```bash
./setup-keys.sh
```

When it asks for your SerpApi key, paste it in and press Enter. The screen won't show what you pasted — that's normal, it's hiding it for security. Press Enter again to confirm.

### Step 7: Tell it about your points (optional but recommended)

This is what makes the tool know which loyalty programs you can actually use. If you skip this, you'll still get cash prices — just no points recommendations.

Open this file in any text editor (TextEdit on Mac works fine, or VS Code, or whatever you have):

```
~/Desktop/hotel-hacker/data/user_balances.json
```

You'll see a template that looks like this:

```json
{
  "currencies": {
    "Amex Membership Rewards": 0,
    "Chase Ultimate Rewards": 0,
    "Citi ThankYou": 0,
    "Capital One Miles": 0,
    "Bilt Rewards": 0
  },
  "programs": {
    "World of Hyatt": 0,
    "Marriott Bonvoy": 0,
    "Hilton Honors": 0,
    "IHG One Rewards": 0,
    "Accor Live Limitless": 0
  },
  "cards": ["Amex Platinum"]
}
```

Replace each `0` with the actual point balance you have. If you don't know yours, log into your credit card and hotel program accounts and check. If you don't carry the Amex Platinum, change the `"cards"` line to `[]` (empty brackets). Save the file when you're done.

This file stays on your computer. It never gets uploaded anywhere.

### Step 8: Launch the tool

```bash
python3 ui/server.py
```

You'll see a message like `Uvicorn running on http://127.0.0.1:8788`. Leave this Terminal window open — that's the tool running.

Open your web browser and go to: **http://127.0.0.1:8788**

That's it. The tool is up.

---

## How to use it

1. **Click SEARCH in the sidebar** (it's the first thing on the left).
2. Type your destination — a city name, a neighborhood, or a specific hotel ("Park Hyatt Tokyo").
3. Pick your check-in and check-out dates.
4. Set the number of guests (defaults to 2).
5. Click **Search hotels**.
6. Wait about 10 seconds. You'll see a ranked table with both **RAW $** (the sticker price after taxes and fees) and **EFFECTIVE $** (the true out-the-door cost after loyalty points, free-night perks, Amex Fine Hotels & Resorts credits, currency haircuts, and the non-refundable penalty). Above the table is a Google Map with a pin for every result — click a pin to see Street View and the full breakdown for that property in a side panel. The BOOK column on each row carries up to three working links: the hotel's own website, the rate's source (Google Hotels deep link), and a Google Maps lookup.

Look for the **EFFECTIVE $ column** — that's the true cost. The **NOTES** column at the right shows the math in plain English so you can sanity-check it before booking.

### Other things to try

- **Paste an Amex Fine Hotels & Resorts rate**: For any luxury stay you're considering through Amex Travel, expand the "ADD AMEX FINE HOTELS & RESORTS DETAILS" panel on the SEARCH tab and drop in the best-flexible rate from amextravel.com plus the offer credit you'd receive. Tick the perks you'll actually use, pick the matching property after the search, and click Re-rank. The tool layers in the math (breakfast, late checkout, $100 property credit, room upgrade) and tells you whether the Amex channel actually nets cheaper than booking direct.
- **Click a pin on the map**: Every result is plotted on a brutalist amber-on-midnight map at the top of the RESULTS tab. Click any pin to slide out a panel showing Street View of the front door, the full breakdown grid, and direct booking links.
- **Draft an upgrade email**: Click "Draft upgrade email" on any row's detail panel. The tool drafts a polite pre-arrival note mentioning your elite status (if any) and any special occasion. You review and send it yourself — the tool never sends anything on your behalf.
- **Update your balances anytime**: Click the BALANCES tab in the sidebar to edit your card-currency points, hotel-program points, and the Amex cards you carry. The next search uses the fresh numbers immediately. (The same file lives at `~/Desktop/hotel-hacker/data/user_balances.json` if you'd rather edit it by hand.)

---

## How to use it tomorrow (and every day after)

You only install it once. After that, every time you want to use it:

1. Open Terminal
2. Run:
   ```bash
   cd ~/Desktop/hotel-hacker && python3 ui/server.py
   ```
3. Open http://127.0.0.1:8788 in your browser

To stop it: in the Terminal window, press `Ctrl + C`.

---

## Why this is better than searching on Google

Google Hotels shows you a sticker price. That's a starting point, not an answer.

This tool shows you:

- The full cost including resort fees, parking, and wifi (which Google often buries)
- Whether your loyalty points actually reach the stay — gated by your real balance, not by what *would* be possible if you had more points
- Whether Marriott's fifth-night-free or IHG's fourth-night-free flips the math for stays long enough to trigger them
- Whether the Amex Fine Hotels & Resorts channel nets cheaper than the public best-flexible rate — only when you've ticked a qualifying Amex card in the BALANCES tab
- Whether paying on a non-US-dollar folio is going to quietly eat 3–6% of your Amex credit value

The ranking formula is shown in the previous section so you can audit it. There are no invented savings on this page — every dollar amount you see in the actual tool comes from a real Google Hotels search routed through the formula above.

---

## Troubleshooting

**"I get an error when I run ./install.sh"**
Make sure you have Python 3.10 or newer. In Terminal, type `python3 --version` to check. If it's older, install the latest from https://www.python.org/downloads/.

**"The website doesn't load when I go to localhost:8788"**
Make sure the Terminal window where you ran `python3 ui/server.py` is still open and shows "Uvicorn running...". If you closed it, run that command again.

**"It says I'm out of searches"**
SerpApi's free tier gives you 250 searches per month, refreshed on the 1st. The tool tracks usage and warns you at 20 remaining. If you've hit zero, you can either wait, fall back to cached results (the tool will tag them *Unverified* since the cached rate might be stale), or upgrade your SerpApi plan.

**"My points balances aren't being used"**
Open `~/Desktop/hotel-hacker/data/user_balances.json` and make sure the numbers are saved and the JSON brackets are intact (no missing commas). If a program shows balance 0, the tool won't recommend it.

**"The Amex Fine Hotels & Resorts perks aren't showing on my rows"**
The Amex Fine Hotels & Resorts perks are only credited when you've ticked at least one qualifying card (Amex Platinum, Centurion, or Business Platinum) in the BALANCES tab. If you don't carry one of those, the tool deliberately won't subtract perks you couldn't actually claim. If you do carry one but it's not ticked, open the BALANCES tab and tick it.

**"I'm on Windows"**
Use WSL (Windows Subsystem for Linux) — https://learn.microsoft.com/en-us/windows/wsl/install — then follow the Mac/Linux steps above.

**"I clicked Book and the external site threw an error (e.g. 'Could not connect to MySQL server')"**
That error came from the **booking site you were sent to**, not from Hotel Hacker. Hotel Hacker has no database, no MySQL, no backend booking system — it's a pure-Python local server. When you click a booking link, you leave the tool entirely and load whichever site the rate came from. Try a different link in the same BOOK cell: "Hotel website" goes to the property's own site (usually the most reliable), "Maps" always works for finding it manually. If the rate source is an aggregator that's having backend trouble, search for the hotel directly on its own brand website — the rate is usually within a dollar or two of what the aggregator quoted.

---

## Privacy + safety

- ✅ Everything runs on **your own computer**. Nothing is uploaded.
- ✅ Your points balances and Amex card list stay in a file on your computer (`user_balances.json`).
- ✅ **We never see your Amex card.** Amex Fine Hotels & Resorts perks are valued from a rate YOU paste in from amextravel.com — we never log in for you, never store your card, never see your statement credits.
- ✅ **We draft, you send.** Pre-arrival upgrade emails are drafted in the UI for you to review and send yourself. The tool never sends anything on your behalf and never asks for your email password.
- ✅ No tracking, no ads, no Google account tied to your hotel searches. When you book, you book directly on the hotel's website (or amextravel.com for Fine Hotels & Resorts bookings).

---

## Advanced (for the curious)

<details>
<summary>Click to expand</summary>

The tool can also be used through:

- **Command line** for power users:
  ```bash
  python3 scripts/search_hotels.py --q "Tokyo" --check-in 2026-08-10 --check-out 2026-08-13 --adults 2 --currency USD
  ```
  Returns normalized JSON to stdout. Pipe through `scripts/rank.py` to get a ranked table.

- **REST API** at `http://127.0.0.1:8788/api/search` for building your own front-end. Accepts `POST` with `{q, check_in, check_out, adults, currency}` and returns normalized hotel records. `POST /api/rank` accepts `{hotels, balances, fhr_inputs}` and returns the ranked table the UI shows.

- **Claude Code** (an AI coding assistant): The skill auto-loads when you mention hotels. Just say "find me a 4-night stay in Tokyo next month" — the skill runs the search with sensible defaults, applies your balances, and returns the ranked table without asking 12 follow-up questions.

</details>

---

## What this does NOT do

- ❌ It doesn't book the stay for you. It shows you the cheapest path and links you to the hotel's own website (or amextravel.com for Amex Fine Hotels & Resorts bookings) to complete the booking.
- ❌ It doesn't see your real credit card. Amex Fine Hotels & Resorts perks are valued from a rate **you** paste in, not by logging into your Amex account.
- ❌ It doesn't track you. Everything is local.
- ❌ **It does not help with flights.** For flights, use our sibling project: **[flight_hacker](https://github.com/joseantoniopau/flight_hacker)** (live site: https://joseantoniopau.github.io/flight_hacker/). Same philosophy, same brutalist UI, built for cash + award flights.

---

## Technical architecture (for developers)

<details>
<summary>Click to expand</summary>

```
hotel-hacker/
├── SKILL.md                    Claude orchestration prompt (PRE-OUTPUT GATE, etc.)
├── lessons.md                  Hard-won corrections. Loaded first every query.
├── playbook.md                 Strategy table by trip archetype.
├── install.sh                  One-shot installer
├── setup-keys.sh               Interactive secrets setup
├── .env                        Gitignored secrets (SERPAPI_KEY)
│
├── data/                       Reference data — all 2026-accurate
│   ├── points_valuations.json  Floor cents-per-point per program (TPG/UP/OMAAT/VFTW)
│   ├── loyalty_programs.json   Free-night mechanics, stack rules, tier requirements
│   ├── fhr_perk_values.json    Amex Fine Hotels & Resorts perk USD values + regional haircut table
│   ├── perk_rules.json         Card requirements, paste-required fields
│   ├── fhr_eligible_brands.json   Curated Fine Hotels & Resorts brand shortlist
│   ├── user_balances.example.json
│   └── account.json            SerpApi search budget tracker
│
├── scripts/
│   ├── common.py               Shared utilities: cache, log, schema
│   ├── fx.py                   USD ↔ local conversion
│   ├── value.py                Pure scoring functions (unit-tested)
│   ├── search_hotels.py        SerpApi google_hotels engine, wide pass
│   ├── search_details.py       Property-token detail lookups
│   ├── rank.py                 Unified ranker (raw + points + Amex perks + currency)
│   ├── smoke_test.py           End-to-end golden tests
│   └── tests/                  Pinned fixtures + unit tests
│
├── ui/
│   ├── index.html · styles.css · app.js     Brutalist amber-on-navy UI
│   └── server.py                            FastAPI backend, port 8788
│
└── docs/
    └── index.html              GitHub Pages landing
```

Design principles:

1. **Cash, points, and Amex Fine Hotels & Resorts in one ranked table.** No silos.
2. **Floor cents-per-point, not ceiling.** Honest math. User overrides allowed; defaults are conservative.
3. **Strict balance gating.** A points discount is only applied when the user actually has the balance to book the award. A Fine Hotels & Resorts credit is only applied when the user has a qualifying Amex card ticked in the BALANCES tab.
4. **Refundability as flexibility insurance.** Non-refundable rates pay a 5% penalty in the ranker, because they are not the same product.
5. **Assisted-manual Amex Fine Hotels & Resorts.** No public Amex API exists. We make it three clicks to paste a rate and get honest math.
6. **Parallel by default.** Multi-destination queries fan out to subagents.
7. **Risk labels everywhere.** Each row gets a *Verified rate* / *Unverified* / *Booking risk* label. No silent gray-area moves.
8. **PRE-OUTPUT GATE.** The skill refuses to ask the user 12 questions before running a search. Defaults first, refine after.
9. **Pure-function scoring with pinned fixtures.** `value.py` and `rank.py` are I/O-free and unit-testable. Fixtures in `scripts/tests/fixtures/` lock golden behavior.

</details>

---

## License

MIT. Free for any use, including commercial.

---

Made with care for travel-hacking enthusiasts who care about hotels too. Sibling project for the other half of your trip: [flight_hacker](https://github.com/joseantoniopau/flight_hacker).
