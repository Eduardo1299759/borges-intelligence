"""Importação de pedidos e leads exportados do CRM / sistema de pedidos (CSV).

LGPD: colunas com dados pessoais (nome, e-mail, telefone, documento, endereço) são descartadas na leitura e
nunca gravadas. O identificador do lead é guardado só como hash (para não duplicar numa reimportação).

Pedidos: somados por campanha e dia em vendas confirmadas (fonte "crm_import"). A importação SUBSTITUI os
totais dos dias e campanhas presentes no arquivo: envie sempre o período completo desses dias.
Associação à campanha, nesta ordem: ID da campanha; nome da campanha; utm_campaign (nome em formato slug).
"""
from __future__ import annotations

import csv
import hashlib
import io
import re
import unicodedata
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Campaign, Client, LeadRecord, SalesDaily

SOURCE = "crm_import"
MAX_ROWS = 50_000


def norm(text: str) -> str:
    """Minúsculas, sem acentos, só letras/números separados por hífen: 'Público — Aberto' -> 'publico-aberto'."""
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "-", text).strip("-")


def utm_slug(campaign_name: str) -> str:
    return norm(campaign_name)


ALIASES = {
    "date": {"data", "date", "data-pedido", "data-venda", "data-criacao", "created-at", "criado-em", "data-do-pedido"},
    "value": {"valor", "value", "receita", "total", "valor-total", "revenue", "amount", "valor-do-pedido"},
    "campaign": {"campanha", "campaign", "utm-campaign", "campaign-name", "nome-campanha", "origem-campanha"},
    "campaign_id": {"campaign-id", "id-campanha", "campanha-id"},
    "status": {"status", "situacao", "status-pedido", "status-do-pedido"},
    "order": {"pedido", "order-id", "id-pedido", "numero-pedido", "order", "n-pedido"},
    "stage": {"etapa", "estagio", "stage", "fase", "status-lead", "etapa-funil"},
    "response": {"tempo-resposta-min", "tempo-resposta", "response-minutes", "primeira-resposta-min",
                 "tempo-primeira-resposta"},
    "lost_reason": {"motivo-perda", "motivo", "lost-reason", "motivo-de-perda"},
    "lead_id": {"lead-id", "id-lead", "id"},
}
PERSONAL = {"nome", "name", "email", "e-mail", "telefone", "phone", "celular", "whatsapp", "cpf", "cnpj", "rg",
            "documento", "endereco", "address", "cep", "nome-cliente", "cliente", "customer", "first-name",
            "last-name", "sobrenome", "ip"}

PAID = {"pago", "aprovado", "concluido", "entregue", "faturado", "paid", "approved", "completed", "completo",
        "finalizado", "confirmado", "venda"}
NOT_SALE = {"cancelado", "estornado", "reembolsado", "recusado", "cancelled", "canceled", "refunded", "pendente",
            "pending", "aguardando", "aguardando-pagamento", "expirado"}
STAGES = {
    "novo": {"novo", "new", "lead", "entrada", "nao-atendido"},
    "contato": {"contato", "contatado", "em-atendimento", "contacted", "atendimento", "em-contato"},
    "qualificado": {"qualificado", "qualified", "mql", "sql", "interessado"},
    "proposta": {"proposta", "orcamento", "negociacao", "proposal", "orcamento-enviado"},
    "venda": {"venda", "ganho", "fechado", "won", "cliente", "convertido", "vendido"},
    "perdido": {"perdido", "lost", "descartado", "desqualificado", "sem-interesse"},
}
STAGE_OF = {alias: stage for stage, aliases in STAGES.items() for alias in aliases}


class ImportError_(ValueError):
    pass


def parse_date(raw: str) -> date | None:
    raw = raw.strip()
    if not raw:
        return None
    head = raw.split()[0].split("T")[0]
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d/%m/%y", "%d-%m-%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(head, fmt).date()
        except ValueError:
            continue
    return None


def parse_money(raw: str) -> Decimal | None:
    s = re.sub(r"[^\d,.\-]", "", raw.strip())
    if not s:
        return None
    if "," in s and "." in s:
        s = s.replace(".", "").replace(",", ".") if s.rfind(",") > s.rfind(".") else s.replace(",", "")
    elif "," in s:
        s = s.replace(".", "").replace(",", ".")
    try:
        return Decimal(s).quantize(Decimal("0.01"))
    except InvalidOperation:
        return None


@dataclass
class Parsed:
    rows: list[dict[str, str]]
    columns: dict[str, str]  # campo canônico -> coluna do arquivo
    ignored_personal: list[str]
    ignored_other: list[str]


def read_csv(text: str) -> Parsed:
    text = text.lstrip("﻿")
    if not text.strip():
        raise ImportError_("Arquivo vazio.")
    sample = text[:5000]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=";,\t")
    except csv.Error:
        dialect = csv.excel
    reader = csv.DictReader(io.StringIO(text), dialect=dialect)
    if not reader.fieldnames:
        raise ImportError_("Cabeçalho não encontrado.")
    columns: dict[str, str] = {}
    personal, other = [], []
    for col in reader.fieldnames:
        key = norm(col or "")
        if key in PERSONAL:
            personal.append(col)
            continue
        canon = next((c for c, names in ALIASES.items() if key in names and c not in columns), None)
        if canon:
            columns[canon] = col
        else:
            other.append(col)
    rows = []
    for i, row in enumerate(reader):
        if i >= MAX_ROWS:
            raise ImportError_(f"Arquivo com mais de {MAX_ROWS} linhas; divida em partes.")
        # descarta já na leitura qualquer coluna pessoal
        rows.append({c: (row.get(col) or "").strip() for c, col in columns.items()})
    return Parsed(rows, columns, personal, other)


class CampaignMatcher:
    def __init__(self, db: Session, client: Client):
        self.by_id: dict[str, Campaign] = {}
        self.by_name: dict[str, Campaign] = {}
        for c in db.scalars(select(Campaign).where(Campaign.client_id == client.id)):
            self.by_id[c.external_id] = c
            self.by_name[norm(c.name)] = c

    def match(self, row: dict[str, str]) -> Campaign | None:
        if row.get("campaign_id") and row["campaign_id"] in self.by_id:
            return self.by_id[row["campaign_id"]]
        if row.get("campaign"):
            value = row["campaign"]
            # utm_campaign pode trazer o nome (Meta: {{campaign.name}}) ou o ID (Google: {campaignid})
            return self.by_name.get(norm(value)) or self.by_id.get(value.strip())
        return None


@dataclass
class Result:
    kind: str
    rows_read: int = 0
    imported: int = 0
    skipped: Counter = field(default_factory=Counter)
    unmatched: Counter = field(default_factory=Counter)
    columns: dict[str, str] = field(default_factory=dict)
    ignored_personal: list[str] = field(default_factory=list)
    ignored_other: list[str] = field(default_factory=list)
    totals: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {"kind": self.kind, "rows_read": self.rows_read, "imported": self.imported,
                "skipped": dict(self.skipped), "unmatched_campaigns": self.unmatched.most_common(15),
                "columns": self.columns, "ignored_personal_columns": self.ignored_personal,
                "ignored_other_columns": self.ignored_other, "totals": self.totals}


def import_orders(db: Session, client: Client, text: str, commit: bool) -> Result:
    parsed = read_csv(text)
    res = Result("orders", columns=parsed.columns, ignored_personal=parsed.ignored_personal,
                 ignored_other=parsed.ignored_other)
    missing = [c for c in ("date", "value") if c not in parsed.columns]
    if missing:
        raise ImportError_("Colunas obrigatórias não encontradas: " + ", ".join(
            {"date": "data", "value": "valor"}[m] for m in missing) + ".")
    if "campaign" not in parsed.columns and "campaign_id" not in parsed.columns:
        raise ImportError_("Inclua uma coluna de campanha (campanha, utm_campaign ou campaign_id).")
    matcher = CampaignMatcher(db, client)
    seen_orders: set[str] = set()
    agg: dict[tuple[int, date], list] = defaultdict(lambda: [0, Decimal("0")])
    unmatched_revenue = Decimal("0")
    for row in parsed.rows:
        res.rows_read += 1
        order_key = row.get("order") or row.get("lead_id")  # uma coluna "id" num arquivo de pedidos é o pedido
        if order_key:
            if order_key in seen_orders:
                res.skipped["pedido repetido no arquivo"] += 1
                continue
            seen_orders.add(order_key)
        status = norm(row.get("status", ""))
        if status and status not in PAID:
            res.skipped["status não pago" if status in NOT_SALE else f"status desconhecido: {status}"] += 1
            continue
        day, value = parse_date(row.get("date", "")), parse_money(row.get("value", ""))
        if day is None:
            res.skipped["data inválida"] += 1
            continue
        if value is None or value < 0:
            res.skipped["valor inválido"] += 1
            continue
        camp = matcher.match(row)
        if camp is None:
            res.unmatched[row.get("campaign") or row.get("campaign_id") or "(sem campanha)"] += 1
            unmatched_revenue += value
            continue
        agg[(camp.id, day)][0] += 1
        agg[(camp.id, day)][1] += value
        res.imported += 1
    res.totals = {"sales": sum(v[0] for v in agg.values()), "revenue": float(sum(v[1] for v in agg.values())),
                  "unmatched_revenue": float(unmatched_revenue), "days": len({d for _, d in agg}),
                  "campaigns": len({c for c, _ in agg})}
    if commit and agg:
        existing = {(s.campaign_id, s.date): s for s in db.scalars(select(SalesDaily).where(
            SalesDaily.client_id == client.id, SalesDaily.source == SOURCE,
            SalesDaily.date.in_({d for _, d in agg})))}
        for (cid, day), (count, revenue) in agg.items():
            row = existing.get((cid, day))
            if row is None:
                row = SalesDaily(client_id=client.id, campaign_id=cid, date=day, source=SOURCE, is_demo=False,
                                 confirmed_sales=0, confirmed_revenue=0)
                db.add(row)
            row.confirmed_sales, row.confirmed_revenue = count, revenue
        db.flush()
    return res


def _ref_hash(client: Client, row: dict[str, str], index: int) -> str:
    basis = row.get("lead_id") or f"linha:{index}:{row.get('date')}:{row.get('campaign')}:{row.get('stage')}"
    return hashlib.sha256(f"{client.id}:{basis}".encode()).hexdigest()


def import_leads(db: Session, client: Client, text: str, commit: bool) -> Result:
    parsed = read_csv(text)
    res = Result("leads", columns=parsed.columns, ignored_personal=parsed.ignored_personal,
                 ignored_other=parsed.ignored_other)
    # Em exportações de CRM a etapa costuma vir numa coluna "status".
    if "stage" not in parsed.columns and "status" in parsed.columns:
        parsed.columns["stage"] = parsed.columns["status"]
        for row in parsed.rows:
            row["stage"] = row.get("status", "")
    missing = [c for c in ("date", "stage") if c not in parsed.columns]
    if missing:
        raise ImportError_("Colunas obrigatórias não encontradas: " + ", ".join(
            {"date": "data", "stage": "etapa"}[m] for m in missing) + ".")
    matcher = CampaignMatcher(db, client)
    existing = {r.ref_hash: r for r in db.scalars(select(LeadRecord).where(LeadRecord.client_id == client.id))}
    stages: Counter = Counter()
    seen: set[str] = set()
    for index, row in enumerate(parsed.rows):
        res.rows_read += 1
        day = parse_date(row.get("date", ""))
        stage = STAGE_OF.get(norm(row.get("stage", "")))
        if day is None:
            res.skipped["data inválida"] += 1
            continue
        if stage is None:
            res.skipped[f"etapa desconhecida: {norm(row.get('stage', '')) or '(vazia)'}"] += 1
            continue
        ref = _ref_hash(client, row, index)
        if ref in seen:
            res.skipped["lead repetido no arquivo"] += 1
            continue
        seen.add(ref)
        camp = matcher.match(row)
        if camp is None and (row.get("campaign") or row.get("campaign_id")):
            res.unmatched[row.get("campaign") or row.get("campaign_id")] += 1
        minutes = None
        if row.get("response"):
            try:
                minutes = max(0, int(float(row["response"].replace(",", "."))))
            except ValueError:
                res.skipped["tempo de resposta inválido (lead mantido)"] += 1
        stages[stage] += 1
        res.imported += 1
        if commit:
            rec = existing.get(ref) or LeadRecord(client_id=client.id, ref_hash=ref)
            if rec.id is None:
                db.add(rec)
                existing[ref] = rec
            rec.campaign_id = camp.id if camp else None
            rec.date, rec.stage, rec.response_minutes = day, stage, minutes
            rec.lost_reason = (row.get("lost_reason") or None) if stage == "perdido" else None
            rec.value = parse_money(row.get("value", "")) if row.get("value") else None
    if commit:
        db.flush()
    res.totals = {"by_stage": dict(stages)}
    return res
