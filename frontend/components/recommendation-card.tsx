"use client";

import { useState } from "react";
import { api } from "@/lib/api";
import { dateTime, money } from "@/lib/format";
import type { Recommendation } from "@/lib/types";
import { Badge, Button, DemoBadge, Notice, StatusBadge, inputClass } from "./ui";

const PRIORITY_TONE = { alta: "red", média: "amber", baixa: "neutral" } as const;
const DECISION_LABEL: Record<string, string> = {
  approved: "Aprovou", rejected: "Rejeitou", adjustment_requested: "Solicitou ajuste",
};

function Block({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <dt className="text-[11px] font-semibold uppercase tracking-wide text-muted">{label}</dt>
      <dd className="mt-1 text-sm leading-relaxed text-ink">{children}</dd>
    </div>
  );
}

export function RecommendationCard({
  rec, clientId, currency = "BRL", canDecide = false, highlighted = false, defaultOpen = false, onChanged,
}: {
  rec: Recommendation; clientId: number; currency?: string; canDecide?: boolean; highlighted?: boolean;
  defaultOpen?: boolean; onChanged?: () => void;
}) {
  const [open, setOpen] = useState(defaultOpen);
  const [comment, setComment] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const pending = rec.status === "awaiting_approval" || rec.status === "adjustment_requested";
  const p = rec.action_payload;
  const isBudget = rec.action_type === "adjust_budget" && p.from !== undefined && p.to !== undefined;

  async function decide(decision: "approve" | "reject" | "request_adjustment") {
    setBusy(true);
    setError(null);
    try {
      await api(`/clients/${clientId}/recommendations/${rec.id}/decision`, { method: "POST", body: { decision, comment: comment || null } });
      setComment("");
      onChanged?.();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <article className={`rounded-xl border bg-white ${highlighted ? "border-azure-500 ring-2 ring-azure-100" : "border-line"}`}>
      <button type="button" onClick={() => setOpen(!open)} aria-expanded={open} className="flex w-full items-start justify-between gap-4 px-5 py-4 text-left">
        <div className="min-w-0">
          <div className="mb-1.5 flex flex-wrap items-center gap-1.5">
            <StatusBadge status={rec.status} />
            {rec.requires_approval && <Badge tone={PRIORITY_TONE[rec.priority]}>Prioridade {rec.priority}</Badge>}
            <Badge>Confiança {rec.confidence}</Badge>
            {rec.is_demo && <DemoBadge />}
            {highlighted && <Badge tone="blue">Relacionada à pergunta</Badge>}
          </div>
          <h3 className="text-sm font-semibold text-navy-900">{rec.title}</h3>
          <p className="mt-0.5 text-xs text-muted">
            {rec.agent} · {rec.platform === "meta" ? "Meta Ads" : rec.platform === "google" ? "Google Ads" : "Conta"} · #{rec.id}
          </p>
        </div>
        <span aria-hidden className="mt-1 text-muted">{open ? "−" : "+"}</span>
      </button>

      {open && (
        <div className="space-y-5 border-t border-line px-5 py-5">
          <dl className="grid gap-5 md:grid-cols-2">
            <Block label="Problema">{rec.problem}</Block>
            <Block label="Causa provável">{rec.probable_cause}</Block>
            <Block label="Hipótese">{rec.hypothesis}</Block>
            <Block label="Ação recomendada">{rec.recommended_action}</Block>
            <Block label="Impacto esperado e incertezas">{rec.expected_impact}</Block>
            <Block label="Riscos">{rec.risks}</Block>
            <Block label="Métrica de validação">{rec.validation_metric}</Block>
            {rec.alternatives.length > 0 && (
              <Block label="Explicações alternativas">
                <ul className="list-disc space-y-1 pl-4">{rec.alternatives.map((a) => <li key={a}>{a}</li>)}</ul>
              </Block>
            )}
          </dl>

          <div>
            <p className="mb-2 text-[11px] font-semibold uppercase tracking-wide text-muted">Evidências</p>
            <div className="overflow-x-auto rounded-lg border border-line">
              <table className="w-full min-w-[520px] text-sm">
                <thead className="bg-canvas text-left text-xs text-muted">
                  <tr><th className="px-3 py-2 font-medium">Indicador</th><th className="px-3 py-2 font-medium">Valor</th><th className="px-3 py-2 font-medium">Referência</th><th className="px-3 py-2 font-medium">Período · fonte</th></tr>
                </thead>
                <tbody>
                  {rec.evidence.map((e, i) => (
                    <tr key={i} className="border-t border-line">
                      <td className="px-3 py-2">{e.metric}</td>
                      <td className="px-3 py-2 font-medium">{e.value}</td>
                      <td className="px-3 py-2 text-muted">{e.benchmark || "—"}</td>
                      <td className="px-3 py-2 text-xs text-muted">{e.period} · {e.source}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          {isBudget && (
            <div className="rounded-lg border border-azure-100 bg-azure-50 px-4 py-3 text-sm">
              <p className="text-[11px] font-semibold uppercase tracking-wide text-azure-700">Prévia da mudança</p>
              <p className="mt-1 text-navy-900">
                Orçamento diário: <strong>{money(p.from, currency)}</strong> → <strong>{money(p.to, currency)}</strong>{" "}
                ({p.change_pct! > 0 ? "+" : ""}{p.change_pct}%)
              </p>
              <p className="mt-1 text-xs text-muted">
                {rec.is_demo ? "Execução simulada: altera apenas a campanha demonstrativa dentro do Borges." : "Cliente real: não há conector de escrita autorizado; a execução será bloqueada."}
              </p>
            </div>
          )}

          {rec.executions.map((ex) => (
            <div key={ex.id} className="rounded-lg border border-line px-4 py-3 text-sm">
              <p className="font-medium text-navy-900">
                Execução #{ex.id} · {ex.mode === "simulated" ? "simulada" : "real"} · {ex.status === "completed" ? "concluída" : "falhou"}
                {ex.verified && " · verificada por releitura"}
              </p>
              {ex.before_state && ex.after_state && (
                <p className="mt-1 text-muted">Orçamento diário: {money(ex.before_state.daily_budget, currency)} → {money(ex.after_state.daily_budget, currency)}</p>
              )}
              {ex.error && <p className="mt-1 text-rose-700">{ex.error}</p>}
              <ul className="mt-2 space-y-0.5 text-xs">
                {ex.checks.map((c) => (
                  <li key={c.check} className={c.passed ? "text-emerald-700" : "text-rose-700"}>{c.passed ? "✓" : "✕"} {c.check} — <span className="text-muted">{c.detail}</span></li>
                ))}
              </ul>
            </div>
          ))}

          {rec.decisions.length > 0 && (
            <ul className="space-y-1 text-sm">
              {rec.decisions.map((d, i) => (
                <li key={i} className="text-muted">
                  <span className="font-medium text-ink">{d.user ?? "Usuário removido"}</span> · {DECISION_LABEL[d.decision] ?? d.decision} em {dateTime(d.created_at)}
                  {d.comment && <> — “{d.comment}”</>}
                </li>
              ))}
            </ul>
          )}

          {pending && canDecide && (
            <div className="space-y-3 border-t border-line pt-4">
              {error && <Notice tone="error">{error}</Notice>}
              <textarea value={comment} onChange={(e) => setComment(e.target.value)} rows={2} maxLength={2000} placeholder="Comentário (obrigatório ao solicitar ajuste)" aria-label="Comentário da decisão" className={inputClass} />
              <div className="flex flex-wrap gap-2">
                <Button disabled={busy} onClick={() => decide("approve")}>{isBudget ? "Aprovar e executar" : "Aprovar"}</Button>
                <Button variant="secondary" disabled={busy || !comment.trim()} onClick={() => decide("request_adjustment")}>Solicitar ajuste</Button>
                <Button variant="danger" disabled={busy} onClick={() => decide("reject")}>Rejeitar</Button>
              </div>
            </div>
          )}
        </div>
      )}
    </article>
  );
}
