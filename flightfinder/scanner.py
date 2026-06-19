"""Date logic + Google Flights querying (via fast-flights) with SQLite caching."""

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo
import sys
import time

import fast_flights as ff

from . import airports, db

CACHE_HOURS = 12
REQUEST_DELAY_SECONDS = 1.5


def weekday_dates_in_range(start_date: date, months_ahead: int, target_weekday: int):
    """Yield every date matching target_weekday from start_date through N months ahead."""
    end_date = _add_months(start_date, months_ahead)
    d = start_date
    while d.weekday() != target_weekday:
        d += timedelta(days=1)
    while d <= end_date:
        yield d
        d += timedelta(days=7)


def _add_months(d: date, months: int) -> date:
    month = d.month - 1 + months
    year = d.year + month // 12
    month = month % 12 + 1
    day = min(d.day, [31, 29 if year % 4 == 0 and (year % 100 != 0 or year % 400 == 0) else 28,
                       31, 30, 31, 30, 31, 31, 30, 31, 30, 31][month - 1])
    return date(year, month, day)


def day_of_week_pairs(start_date: date, months_ahead: int, depart_weekday: int, return_weekday: int):
    """Yield (depart_date, return_date) tuples for every week in range matching the weekday pair."""
    offset = (return_weekday - depart_weekday) % 7
    if offset == 0:
        offset = 7
    for depart in weekday_dates_in_range(start_date, months_ahead, depart_weekday):
        yield depart, depart + timedelta(days=offset)


def near_variants(depart: date, ret: date):
    """Yield (depart_date, return_date) pairs that are 1 day off the exact pair on a single leg."""
    for delta in (-1, 1):
        yield depart + timedelta(days=delta), ret
    for delta in (-1, 1):
        yield depart, ret + timedelta(days=delta)


def _localize(simple_datetime, tz_name: str) -> datetime:
    """Combine a fast_flights SimpleDatetime (date=[Y,M,D], time=[H] or [H,M]) with an IANA tz."""
    year, month, day = simple_datetime.date
    t = simple_datetime.time
    # fast_flights represents an hour of exactly midnight as None rather than 0.
    hour = t[0] if t[0] is not None else 0
    minute = (t[1] if len(t) > 1 else 0) or 0
    return datetime(year, month, day, hour, minute, tzinfo=ZoneInfo(tz_name))


def query_round_trip_price(origin: str, destination: str, depart_date: date, return_date: date,
                            force_refresh: bool = False):
    """Return a dict with price, departure/arrival times (each in their own airport's local
    timezone) and total trip duration in minutes, for the cheapest outbound itinerary. Uses the
    cache when fresh."""
    depart_str = depart_date.isoformat()
    return_str = return_date.isoformat()

    if not force_refresh:
        cached = db.get_cached(origin, destination, depart_str, return_str, CACHE_HOURS)
        if cached:
            return {
                "price": cached["price"],
                "outbound_departure_time": cached["outbound_departure_time"],
                "outbound_arrival_time": cached["outbound_arrival_time"],
                "duration_minutes": cached["duration_minutes"],
            }

    info = {"price": None, "outbound_departure_time": None,
            "outbound_arrival_time": None, "duration_minutes": None}
    try:
        q = ff.create_query(
            flights=[
                ff.FlightQuery(date=depart_str, from_airport=origin, to_airport=destination),
                ff.FlightQuery(date=return_str, from_airport=destination, to_airport=origin),
            ],
            trip="round-trip",
            seat="economy",
            passengers=ff.Passengers(adults=1),
        )
        result = ff.get_flights(q)
        if result:
            cheapest = min(result, key=lambda r: r.price)
            info["price"] = cheapest.price

            origin_tz = airports.TIMEZONES.get(origin, "UTC")
            dest_tz = airports.TIMEZONES.get(destination, "UTC")
            departure_dt = _localize(cheapest.flights[0].departure, origin_tz)
            arrival_dt = _localize(cheapest.flights[-1].arrival, dest_tz)

            info["outbound_departure_time"] = departure_dt.strftime("%H:%M %Z")
            info["outbound_arrival_time"] = arrival_dt.strftime("%H:%M %Z")
            info["duration_minutes"] = round((arrival_dt - departure_dt).total_seconds() / 60)
    except Exception as e:
        print(f"warning: failed to fetch {origin}->{destination} {depart_str}/{return_str}: {e}",
              file=sys.stderr)
    finally:
        time.sleep(REQUEST_DELAY_SECONDS)

    return info


def format_duration(minutes):
    if minutes is None:
        return ""
    sign = "-" if minutes < 0 else ""
    minutes = abs(minutes)
    return f"{sign}{minutes // 60}h {minutes % 60}m"


def run_scan(jobs_combos, search_label, progress_callback=None):
    """
    jobs_combos: iterable of (origin, destination, depart_date, return_date, match_type)
    Queries each, stores results in the db, calls progress_callback(done, total, latest_result) as it goes.
    Returns the list of result dicts.
    """
    combos = list(jobs_combos)
    total = len(combos)
    results = []
    for i, (origin, destination, depart_date, return_date, match_type) in enumerate(combos, start=1):
        info = query_round_trip_price(origin, destination, depart_date, return_date)
        db.insert_scan(origin, destination, depart_date.isoformat(), return_date.isoformat(),
                        info["price"], info["outbound_departure_time"], info["outbound_arrival_time"],
                        info["duration_minutes"], match_type, search_label)
        result = {
            "origin": origin,
            "destination": destination,
            "depart_date": depart_date.isoformat(),
            "return_date": return_date.isoformat(),
            "price": info["price"],
            "outbound_departure_time": info["outbound_departure_time"],
            "outbound_arrival_time": info["outbound_arrival_time"],
            "duration_minutes": info["duration_minutes"],
            "duration_label": format_duration(info["duration_minutes"]),
            "match_type": match_type,
        }
        results.append(result)
        if progress_callback:
            progress_callback(i, total, result)
    return results


def build_range_combos(origins, destinations, depart_weekday, return_weekday, months_ahead,
                        include_near, start_date=None):
    start_date = start_date or date.today()
    combos = []
    for depart, ret in day_of_week_pairs(start_date, months_ahead, depart_weekday, return_weekday):
        for origin in origins:
            for destination in destinations:
                combos.append((origin, destination, depart, ret, "exact"))
        if include_near:
            for near_depart, near_ret in near_variants(depart, ret):
                if near_depart < start_date:
                    continue
                for origin in origins:
                    for destination in destinations:
                        combos.append((origin, destination, near_depart, near_ret, "near"))
    return combos


def build_specific_date_combos(origins, destinations, date_pairs):
    combos = []
    for depart, ret in date_pairs:
        for origin in origins:
            for destination in destinations:
                combos.append((origin, destination, depart, ret, "exact"))
    return combos
