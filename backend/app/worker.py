"""Processo de automações: `python -m app.worker` (a cada minuto roda as rotinas vencidas).

`python -m app.worker --once` roda um ciclo e sai (útil para agendadores externos e testes).
"""
from __future__ import annotations

import argparse
import logging
import signal
import time

from app.automation import routines
from app.core import db as db_module

log = logging.getLogger("borges.worker")
_stop = False


def _handle(*_):
    global _stop
    _stop = True


def cycle() -> int:
    with db_module.SessionLocal() as db:
        runs = routines.tick(db)
    for r in runs:
        log.info("rotina %s cliente %s: %s", r.routine_id, r.client_id, r.status)
    return len(runs)


def main() -> None:
    parser = argparse.ArgumentParser(description="Worker de automações do Borges Intelligence")
    parser.add_argument("--once", action="store_true", help="roda um ciclo e sai")
    parser.add_argument("--interval", type=int, default=60, help="segundos entre ciclos")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    if args.once:
        cycle()
        return
    signal.signal(signal.SIGINT, _handle)
    signal.signal(signal.SIGTERM, _handle)
    log.info("Worker iniciado (ciclo de %ss). Rotinas não alteram campanhas.", args.interval)
    while not _stop:
        try:
            cycle()
        except Exception:  # noqa: BLE001 — o worker continua no próximo ciclo
            log.exception("Falha no ciclo do worker")
        for _ in range(args.interval):
            if _stop:
                break
            time.sleep(1)
    log.info("Worker encerrado.")


if __name__ == "__main__":
    main()
