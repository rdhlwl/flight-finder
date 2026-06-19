GROUPS = {
    "bay_area": {
        "label": "Bay Area + Sacramento",
        "airports": {
            "SFO": "San Francisco (SFO)",
            "OAK": "Oakland (OAK)",
            "SJC": "San Jose (SJC)",
            "SMF": "Sacramento (SMF)",
        },
    },
    "nyc": {
        "label": "New York City",
        "airports": {
            "JFK": "JFK",
            "EWR": "Newark (EWR)",
            "LGA": "LaGuardia (LGA)",
        },
    },
}


TIMEZONES = {
    "SFO": "America/Los_Angeles",
    "OAK": "America/Los_Angeles",
    "SJC": "America/Los_Angeles",
    "SMF": "America/Los_Angeles",
    "JFK": "America/New_York",
    "EWR": "America/New_York",
    "LGA": "America/New_York",
}


def other_group(group_key: str) -> str:
    return "nyc" if group_key == "bay_area" else "bay_area"


def all_airport_codes() -> set[str]:
    codes = set()
    for g in GROUPS.values():
        codes.update(g["airports"].keys())
    return codes


WEEKDAYS = [
    (0, "Monday"),
    (1, "Tuesday"),
    (2, "Wednesday"),
    (3, "Thursday"),
    (4, "Friday"),
    (5, "Saturday"),
    (6, "Sunday"),
]
