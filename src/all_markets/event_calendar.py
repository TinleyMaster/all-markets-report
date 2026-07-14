from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta


@dataclass
class CalendarEvent:
    date_label: str
    label: str
    impact: str
    source: str

    def to_payload(self) -> dict:
        return {
            "date": self.date_label,
            "label": self.label,
            "impact": self.impact,
            "source": self.source,
        }


@dataclass
class EventCalendar:
    as_of: str
    upcoming: list[CalendarEvent]

    def to_payload(self) -> dict:
        return {
            "as_of": self.as_of,
            "upcoming": [item.to_payload() for item in self.upcoming],
        }


def _resolve_event_date(event: dict, today: date) -> date | None:
    raw_date = event.get("date")
    if raw_date:
        return datetime.strptime(str(raw_date), "%Y-%m-%d").date()

    month_day = event.get("month_day")
    if month_day:
        return datetime.strptime(f"{today.year}-{month_day}", "%Y-%m-%d").date()

    days_from_now = event.get("days_from_now")
    if days_from_now is not None:
        return today + timedelta(days=int(days_from_now))

    return None


def build_event_calendar(
    config_data: dict | None, today: date | None = None
) -> EventCalendar | None:
    if not config_data or not config_data.get("events"):
        return None

    today = today or date.today()
    lookahead_days = int(config_data.get("lookahead_days", 7))
    end_date = today + timedelta(days=lookahead_days)

    upcoming: list[CalendarEvent] = []
    for event in config_data.get("events", []):
        event_date = _resolve_event_date(event, today)
        if event_date is None or event_date < today or event_date > end_date:
            continue

        upcoming.append(
            CalendarEvent(
                date_label=event_date.strftime("%m-%d"),
                label=str(event.get("label", "未命名事件")),
                impact=str(event.get("impact", "关注对跨资产风险偏好的影响。")),
                source=str(event.get("source", "维护型关注清单")),
            )
        )

    upcoming.sort(key=lambda item: item.date_label)
    return EventCalendar(as_of=today.isoformat(), upcoming=upcoming)
