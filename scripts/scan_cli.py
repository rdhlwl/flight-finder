"""Headless scan entry point for CI (GitHub Actions). Runs a scan with fast-flights and
merges the results into docs/data/scans.json, keeping the cheapest price ever seen per
origin/destination/depart_date/return_date combo. Designed to be driven entirely by
environment variables so it can run unattended in a workflow.

Env vars:
  ORIGIN_GROUP        "bay_area" or "nyc"            (default: bay_area)
  MODE                "range" or "dates"             (default: range)
  DEPART_WEEKDAY      0=Mon .. 6=Sun                 (default: 3, Thursday)   [range mode]
  RETURN_WEEKDAY      0=Mon .. 6=Sun                 (default: 6, Sunday)     [range mode]
  MONTHS_AHEAD        integer                        (default: 3)              [range mode]
  INCLUDE_NEAR        "true"/"false"                 (default: true)           [range mode]
  DATE_PAIRS          "YYYY-MM-DD:YYYY-MM-DD,..."    (required in dates mode)  [dates mode]
  ORIGIN_AIRPORTS     comma list, e.g. "SFO,OAK"     (default: all in group)
  DESTINATION_AIRPORTS comma list                    (default: all in group)
"""

import json
import os
import sys
from datetime import date, datetime, UTC
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from flightfinder import airports, scanner

OUTPUT_PATH = Path(__file__).resolve().parent.parent / "docs" / "data" / "scans.json"


def _env_bool(name, default):
    return os.environ.get(name, str(default)).strip().lower() in ("1", "true", "yes", "on")


def _airport_list(env_name, group):
    raw = os.environ.get(env_name, "").strip()
    if raw:
        return [code.strip().upper() for code in raw.split(",") if code.strip()]
    return list(airports.GROUPS[group]["airports"].keys())


def build_combos():
    origin_group = os.environ.get("ORIGIN_GROUP", "bay_area").strip()
    destination_group = airports.other_group(origin_group)

    origins = _airport_list("ORIGIN_AIRPORTS", origin_group)
    destinations = _airport_list("DESTINATION_AIRPORTS", destination_group)

    mode = os.environ.get("MODE", "range").strip()

    if mode == "dates":
        raw_pairs = os.environ.get("DATE_PAIRS", "").strip()
        if not raw_pairs:
            raise SystemExit("MODE=dates requires DATE_PAIRS, e.g. '2026-08-06:2026-08-09,2026-08-13:2026-08-16'")
        date_pairs = []
        for chunk in raw_pairs.split(","):
            depart_str, return_str = chunk.strip().split(":")
            date_pairs.append((date.fromisoformat(depart_str), date.fromisoformat(return_str)))
        combos = scanner.build_specific_date_combos(origins, destinations, date_pairs)
        search_label = "custom dates"
        return combos, search_label

    depart_weekday = int(os.environ.get("DEPART_WEEKDAY", "3"))
    return_weekday = int(os.environ.get("RETURN_WEEKDAY", "6"))
    months_ahead = int(os.environ.get("MONTHS_AHEAD", "3"))
    include_near = _env_bool("INCLUDE_NEAR", True)

    combos = scanner.build_range_combos(
        origins, destinations, depart_weekday, return_weekday, months_ahead, include_near
    )
    depart_name = dict(airports.WEEKDAYS)[depart_weekday]
    return_name = dict(airports.WEEKDAYS)[return_weekday]
    search_label = f"{depart_name} -> {return_name} (next {months_ahead}mo)"
    return combos, search_label


def merge_results(existing, new_results):
    by_key = {}
    for row in existing:
        key = (row["origin"], row["destination"], row["depart_date"], row["return_date"])
        by_key[key] = row

    for row in new_results:
        if row["price"] is None:
            continue
        key = (row["origin"], row["destination"], row["depart_date"], row["return_date"])
        prior = by_key.get(key)
        if prior is None or row["price"] <= prior["price"]:
            by_key[key] = {
                "origin": row["origin"],
                "destination": row["destination"],
                "depart_date": row["depart_date"],
                "return_date": row["return_date"],
                "price": row["price"],
                "outbound_departure_time": row["outbound_departure_time"],
                "outbound_arrival_time": row["outbound_arrival_time"],
                "duration_minutes": row["duration_minutes"],
                "duration_label": row["duration_label"],
                "match_type": row["match_type"],
                "search_label": row.get("search_label"),
                "scanned_at": datetime.now(UTC).isoformat(),
            }

    return sorted(by_key.values(), key=lambda r: r["price"])


def main():
    combos, search_label = build_combos()
    print(f"Scanning {len(combos)} route/date combos for '{search_label}'...")

    def progress(done, total, latest):
        price = latest["price"]
        print(f"[{done}/{total}] {latest['origin']}->{latest['destination']} "
              f"{latest['depart_date']}/{latest['return_date']}: {price if price is not None else 'n/a'}")

    new_results = scanner.run_scan(combos, search_label, progress_callback=progress)
    for r in new_results:
        r["search_label"] = search_label

    existing_payload = {"updated_at": None, "deals": []}
    if OUTPUT_PATH.exists():
        existing_payload = json.loads(OUTPUT_PATH.read_text())

    merged = merge_results(existing_payload.get("deals", []), new_results)

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps({
        "updated_at": datetime.now(UTC).isoformat(),
        "deals": merged,
    }, indent=2))

    print(f"Wrote {len(merged)} total deal rows to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
