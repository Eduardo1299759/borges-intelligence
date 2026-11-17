"""Cálculo do próximo horário de uma rotina, no fuso do cliente (funções puras).

O horário é de parede (ex.: 08:00 em São Paulo). A conversão para UTC usa zoneinfo, então mudanças de horário
de verão são respeitadas. Um horário que não existe no dia (pulado pelo horário de verão) é ajustado para
frente pelo próprio fuso.
"""
from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

DEFAULTS = {
    # tipo: (agendamento, horário, dia da semana, dia do mês, intervalo)
    "daily_audit": ("daily", "08:00", None, None, None),
    "competitive_review": ("daily", "09:00", None, None, None),
    "weekly_report": ("weekly", "12:00", 0, None, None),
    "monthly_report": ("monthly", "10:00", None, 1, None),
    "creative_review": ("every_n_days", "10:00", None, None, 3),
}
LABELS = {
    "daily_audit": "Auditoria diária",
    "competitive_review": "Revisão competitiva",
    "weekly_report": "Relatório semanal",
    "monthly_report": "Relatório mensal",
    "creative_review": "Revisão de criativos",
}


@dataclass(frozen=True)
class Schedule:
    type: str
    time: str
    weekday: int | None = None
    day_of_month: int | None = None
    interval_days: int | None = None


def _at(day: date, hhmm: str, tz: ZoneInfo) -> datetime:
    h, m = (int(x) for x in hhmm.split(":"))
    local = datetime.combine(day, time(h, m), tzinfo=tz)
    # Normaliza horários inexistentes (horário de verão) indo e voltando do UTC.
    return local.astimezone(UTC)


def next_run(s: Schedule, tz_name: str, after: datetime, last_run: datetime | None = None) -> datetime:
    """Primeiro horário estritamente depois de `after` (UTC aware)."""
    tz = ZoneInfo(tz_name)
    if last_run is not None and last_run.tzinfo is None:  # SQLite devolve datas sem fuso (gravadas em UTC)
        last_run = last_run.replace(tzinfo=UTC)
    local_today = after.astimezone(tz).date()
    if s.type == "every_n_days":
        # Sem execução anterior: o primeiro horário disponível; depois, a cada `interval_days`.
        step = max(1, s.interval_days or 1) if last_run else 1
        day = last_run.astimezone(tz).date() + timedelta(days=step) if last_run else local_today
        while _at(day, s.time, tz) <= after:
            day += timedelta(days=step)
        return _at(day, s.time, tz)
    for offset in range(0, 400):
        day = local_today + timedelta(days=offset)
        if s.type == "weekly" and day.weekday() != (s.weekday or 0):
            continue
        if s.type == "monthly":
            wanted = min(s.day_of_month or 1, calendar.monthrange(day.year, day.month)[1])
            if day.day != wanted:
                continue
        candidate = _at(day, s.time, tz)
        if candidate > after:
            return candidate
    raise ValueError("Agendamento sem próxima execução.")
