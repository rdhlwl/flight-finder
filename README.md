# Flight Finder

Finds cheap round-trip flights between the Bay Area + Sacramento (SFO, OAK, SJC, SMF)
and New York City (JFK, EWR, LGA), by scraping Google Flights via the
[`fast-flights`](https://pypi.org/project/fast-flights/) library. No API key required.

## Setup

```bash
source myenv/bin/activate
pip install -r requirements.txt
```

## Run

```bash
./run.sh
```

Then open http://127.0.0.1:5050

## Features

- **Day-of-week range search** — e.g. "depart Thursday, return Sunday" scanned across the
  next N months (configurable), sorted by price.
- **Near-day matches** — optional checkbox to also surface fares ~1 day off your preferred
  depart/return weekday (shown in a lighter row with a "near" badge).
- **Specific date search** — enter one or more exact depart/return date pairs.
- **Pick the departing side** — toggle whether you're flying out from the Bay Area side or
  NYC side, and choose specific airports within each side.
- **Best Deals page** (`/deals`) — every previously scanned route/date combo this tool has
  found, deduped and sorted by price, filterable by departing side.

## How it works

- Each search starts a background scan thread; the job page polls `/api/jobs/<id>` every 2s
  and fills in results live as they come in.
- Every priced result is written to `flights.db` (SQLite) immediately, so the Best Deals page
  stays useful even if you close the search mid-scan.
- Repeated identical route/date lookups are cached for 12 hours (`scanner.CACHE_HOURS`) to
  avoid re-hitting Google Flights unnecessarily.
- A scan request fans out across **every selected origin airport x every selected destination
  airport x every matching date**. Narrow your airport selection or date range if a scan is
  taking too long — Google Flights is queried live and a delay (`scanner.REQUEST_DELAY_SECONDS`,
  default 1.5s) is added between requests to avoid getting rate-limited/blocked.

## Known limitations

- Price is the **round-trip total** for the cheapest itinerary on that date pair. The
  departure/arrival times reflect the outbound leg's times for the cheapest option;
  Google Flights' round-trip search doesn't expose the return leg's time until after the
  outbound flight is selected, so the return-time isn't independently filterable.
- This relies on scraping Google Flights' internal endpoints (no official API). It can break
  if Google changes their page, and aggressive scanning may get temporarily blocked.

## GitHub Pages version (static, no server)

There's also a static deployment under `docs/` that doesn't need you to run anything
locally: a scheduled GitHub Action does the scanning and commits results as JSON, and
GitHub Pages serves a read-only "Best Deals" table from that JSON.

**One-time setup, once this is pushed to a GitHub repo:**

1. Repo Settings → Pages → Source: "Deploy from a branch" → Branch: `main`, folder: `/docs`.
2. That's it — the page is live at `https://<you>.github.io/<repo>/`.

**How it stays updated:**

- `.github/workflows/scan.yml` runs on a schedule (weekly by default — edit the cron in that
  file) and on manual trigger.
- To run an ad-hoc scan (custom dates, different weekdays, narrower airport list): repo's
  **Actions** tab → `scan` workflow → **Run workflow**, fill in the inputs, run it.
- The workflow runs `scripts/scan_cli.py`, which merges new results into
  `docs/data/scans.json` (keeping the cheapest price ever seen per route/date combo) and
  commits/pushes the file. Pages redeploys automatically a minute or two later.
- The static page (`docs/index.html` + `docs/app.js`) has no live "search" form — it just
  renders whatever is in `scans.json`, with client-side sort/filter (price, departing side,
  near-match toggle, max price).

**Tradeoffs vs. the local Flask app:**

- No on-page live search — triggering a new scan means using the Actions tab, and waiting
  for the workflow + Pages redeploy (a few minutes), not instant results.
- Scans run from GitHub's shared runner IPs, which are more likely to get rate-limited by
  Google Flights than your home IP. If a scheduled run comes back empty, that's likely why.
- If the repo is public, scan history (routes, prices, timestamps) is publicly visible on
  the Pages site and in the committed JSON.
