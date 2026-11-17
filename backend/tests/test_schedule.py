"""Horários das rotinas: fuso do cliente, semanas, meses curtos e horário de verão."""
from datetime import UTC, datetime

from app.automation.schedule import Schedule, next_run

SP = "America/Sao_Paulo"  # UTC-3, sem horário de verão


def utc(*a):
    return datetime(*a, tzinfo=UTC)


def test_daily_in_client_timezone():
    s = Schedule("daily", "08:00")
    assert next_run(s, SP, utc(2026, 11, 17, 10, 0)) == utc(2026, 11, 17, 11, 0)  # 07:00 local -> 08:00 hoje
    assert next_run(s, SP, utc(2026, 11, 17, 11, 0)) == utc(2026, 11, 18, 11, 0)  # exatamente na hora: amanhã


def test_weekly_monday_noon():
    s = Schedule("weekly", "12:00", weekday=0)
    assert next_run(s, SP, utc(2026, 11, 17, 12, 0)) == utc(2026, 11, 23, 15, 0)  # terça -> segunda seguinte


def test_monthly_clamps_to_short_months():
    s = Schedule("monthly", "10:00", day_of_month=31)
    assert next_run(s, SP, utc(2027, 2, 1, 0, 0)) == utc(2027, 2, 28, 13, 0)


def test_every_three_days_from_last_run():
    s = Schedule("every_n_days", "10:00", interval_days=3)
    last = utc(2026, 11, 14, 13, 0)
    assert next_run(s, SP, utc(2026, 11, 15, 0, 0), last) == utc(2026, 11, 17, 13, 0)
    assert next_run(s, SP, utc(2026, 11, 15, 0, 0)) == utc(2026, 11, 15, 13, 0)  # nunca rodou: hoje


def test_daylight_saving_time_is_respected():
    s = Schedule("daily", "08:00")
    ny = "America/New_York"
    # antes da mudança (EDT, UTC-4) e depois (EST, UTC-5) em 1/11/2026
    assert next_run(s, ny, utc(2026, 10, 31, 13, 0)) == utc(2026, 11, 1, 13, 0)
    assert next_run(s, ny, utc(2026, 10, 30, 13, 0)) == utc(2026, 10, 31, 12, 0)
