from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta


WEEKDAYS = {
    "monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3,
    "friday": 4, "saturday": 5, "sunday": 6,
}
MONTHS = {name.lower(): number for number, name in enumerate(
    ("", "January", "February", "March", "April", "May", "June",
     "July", "August", "September", "October", "November", "December")
    ) if name}


@dataclass(frozen=True)
class ParsedTask:
    title: str
    start: datetime
    duration_minutes: int = 60
    repeat: str = ""


def _parse_clock(text: str) -> tuple[time, tuple[int, int] | None]:
    match = re.search(r"\b(?:at\s+)?(\d{1,2})(?::(\d{2}))?\s*(am|pm)\b", text, re.I)
    if not match:
        match = re.search(r"\bat\s+(\d{1,2})(?::(\d{2}))?\b", text, re.I)
    if not match:
        return time(9), None
    hour, minute = int(match.group(1)), int(match.group(2) or 0)
    suffix = match.group(3).lower() if match.lastindex and match.lastindex >= 3 and match.group(3) else ""
    if suffix:
        hour = hour % 12 + (12 if suffix == "pm" else 0)
    if hour > 23 or minute > 59:
        raise ValueError("That time is not valid.")
    return time(hour, minute), match.span()


def parse_request(text: str, now: datetime | None = None) -> ParsedTask:
    """Parse one friendly-English schedule request without an internet service."""
    now = now or datetime.now()
    original = " ".join(text.strip().split())
    if not original:
        raise ValueError("Type something to schedule first.")
    lowered = original.lower()
    clock, clock_span = _parse_clock(original)
    selected = now.date()
    repeat = ""
    consumed: list[tuple[int, int]] = []

    if "tomorrow" in lowered:
        selected += timedelta(days=1)
        m = re.search(r"\btomorrow\b", original, re.I)
        consumed.append(m.span())
    elif "today" in lowered:
        m = re.search(r"\btoday\b", original, re.I)
        consumed.append(m.span())
    else:
        weekday = re.search(r"\b(?:(every|next)\s+)?(" + "|".join(WEEKDAYS) + r")\b", original, re.I)
        explicit = re.search(r"\b(" + "|".join(MONTHS) + r")\s+(\d{1,2})(?:st|nd|rd|th)?(?:,?\s+(\d{4}))?\b", original, re.I)
        numeric = re.search(r"\b(\d{1,2})[/-](\d{1,2})(?:[/-](\d{2,4}))?\b", original)
        if explicit:
            month = MONTHS[explicit.group(1).lower()]
            year = int(explicit.group(3) or now.year)
            selected = date(year, month, int(explicit.group(2)))
            if not explicit.group(3) and selected < now.date():
                selected = selected.replace(year=year + 1)
            consumed.append(explicit.span())
        elif numeric:
            year = int(numeric.group(3) or now.year)
            if year < 100:
                year += 2000
            selected = date(year, int(numeric.group(1)), int(numeric.group(2)))
            consumed.append(numeric.span())
        elif weekday:
            target = WEEKDAYS[weekday.group(2).lower()]
            distance = (target - now.weekday()) % 7
            if distance == 0 and (weekday.group(1) or datetime.combine(now.date(), clock) <= now):
                distance = 7
            selected += timedelta(days=distance)
            repeat = "weekly" if (weekday.group(1) or "").lower() == "every" else ""
            consumed.append(weekday.span())

    duration = 60
    duration_match = re.search(r"\bfor\s+(\d+(?:\.\d+)?)\s*(minutes?|mins?|hours?|hrs?)\b", original, re.I)
    if duration_match:
        amount = float(duration_match.group(1))
        duration = round(amount * (60 if duration_match.group(2).lower().startswith(("hour", "hr")) else 1))
        consumed.append(duration_match.span())
    if clock_span:
        consumed.append(clock_span)

    title = original
    for start, end in sorted(consumed, reverse=True):
        title = title[:start] + " " + title[end:]
    title = re.sub(r"\b(?:on|at)\b\s*$", "", " ".join(title.split()), flags=re.I).strip(" ,-:")
    title = re.sub(r"^(?:schedule|add|remind me to)\s+", "", title, flags=re.I).strip()
    if not title:
        title = "Scheduled task"
    return ParsedTask(title[0].upper() + title[1:], datetime.combine(selected, clock), duration, repeat)

