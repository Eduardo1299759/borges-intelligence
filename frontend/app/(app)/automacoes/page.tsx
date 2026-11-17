"use client";

import { useState } from "react";
import { useApp } from "@/components/app-context";
import { AlertItem, AlertList } from "@/components/alert-list";
import { NoClient } from "@/components/no-client";
import { Badge, Button, Card, CardHeader, Loading, Notice, PageTitle, inputClass } from "@/components/ui";
import { api, useApi } from "@/lib/api";
import { dateTime } from "@/lib/format";

interface Routine { id: number; kind: string; label: string; enabled: boolean; schedule_type: string; time: string; weekday: number | null; day_of_month: number | null; interval_days: number | null; next_run_at: string | null; last_run_at: string | null; last_status: string | null; last_error: string | null }
interface Run { id: number; kind: string; label: string; status: string; triggered_by: string; summary: Record<string, unknown> | null; error: string | null; started_at: string; finished_at: string | null }

const WEEKDAYS = ["segunda", "terça", "quarta", "quinta", "sexta", "sábado", "domingo"];
const RUN_TONE: Record<string, "green" | "red" | "blue"> = { completed: "green", failed: "red", running: "blue" };
const RUN_LABEL: Record<string, string> = { completed: "Concluída", failed: "Falhou", running: "Executando" };

function when(r: Routine) {
  if (r.schedule_type === "daily") return `Todo dia às ${r.time}`;
  if (r.schedule_type === "weekly") return `Toda ${WEEKDAYS[r.weekday ?? 0]} às ${r.time}`;
  if (r.schedule_type === "monthly") return `Dia ${r.day_of_month} de cada mês às ${r.time}`;
  return `A cada ${r.interval_days} dias às ${r.time}`;
}

function summarize(s: Record<string, unknown> | null): string {
  if (!s) return "";
  const parts: string[] = [];
  if (typeof s.skipped === "string") parts.push(s.skipped);
  if (typeof s.new_recommendations === "number") parts.push(`${s.new_recommendations} recomendação(ões)`);
  if (Array.isArray(s.alerts)) parts.push(`${s.alerts.length} alerta(s) novo(s)`);
  if (Array.isArray(s.flagged)) parts.push(`${s.flagged.length} criativo(s) para revisar`);
  if (Array.isArray(s.learnings) && s.learnings.length) parts.push(`${s.learnings.length} aprendizado(s)`);
  if (s.report_id) parts.push("relatório gerado");
  const sync = s.sync as { status?: string; reason?: string } | undefined;
  if (sync) parts.push(`sincronização: ${sync.status === "completed" ? "ok" : sync.reason ?? sync.status}`);
  return parts.join(" · ");
}

export default function AutomacoesPage() {
  const { client, canManage, canAnalyze } = useApp();
  const base = client ? `/clients/${client.id}` : null;
  const routines = useApi<{ timezone: string; routines: Routine[] }>(base && `${base}/routines`);
  const runs = useApi<Run[]>(base && `${base}/routine-runs`);
  const alerts = useApi<AlertItem[]>(base && `${base}/alerts`);
  const [busy, setBusy] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  if (!client) return <NoClient />;
  const tz = routines.data?.timezone ?? client.timezone;

  async function act(id: number, fn: () => Promise<unknown>) {
    setBusy(id); setError(null);
    try { await fn(); routines.reload(); runs.reload(); alerts.reload(); } catch (e) { setError((e as Error).message); } finally { setBusy(null); }
  }
  const patch = (r: Routine, body: Record<string, unknown>) => act(r.id, () => api(`${base}/routines/${r.id}`, { method: "PATCH", body }));
  const runNow = (r: Routine) => act(r.id, () => api(`${base}/routines/${r.id}/run`, { method: "POST" }));
  const setAlert = (id: number, status: string) => act(-id, () => api(`${base}/alerts/${id}/status`, { method: "POST", body: { status } }));

  return (
    <>
      <PageTitle title="Automações" subtitle={`Rotinas por cliente; horários no fuso do cliente (${tz}). Elas leem dados, analisam e geram relatórios e alertas — nunca alteram campanhas.`} />
      <div className="mb-4"><Notice>
        As rotinas rodam pelo processo de automações (janela “Borges Automações” no Windows ou o serviço <code>worker</code> no Docker).
        Com ele desligado, nada roda sozinho; “Rodar agora” funciona sempre. Recomendações geradas continuam aguardando sua aprovação.
      </Notice></div>
      {error && <div className="mb-4"><Notice tone="error">{error}</Notice></div>}
      <div className="grid grid-cols-1 gap-6 xl:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]">
        <div className="min-w-0 space-y-6">
          <Card>
            <CardHeader title="Rotinas" />
            {routines.loading ? <Loading /> : (
              <ul className="divide-y divide-line">
                {routines.data?.routines.map((r) => (
                  <li key={r.id} className="flex flex-col gap-2 px-5 py-3 text-sm md:flex-row md:items-center md:justify-between">
                    <div className="min-w-0">
                      <div className="flex flex-wrap items-center gap-1.5">
                        <span className="font-medium text-navy-900">{r.label}</span>
                        {!r.enabled && <Badge>Desligada</Badge>}
                        {r.last_status && <Badge tone={RUN_TONE[r.last_status]}>{RUN_LABEL[r.last_status]}</Badge>}
                      </div>
                      <p className="text-xs text-muted">{when(r)} · próxima: {r.enabled && r.next_run_at ? dateTime(r.next_run_at, tz) : "—"} · última: {r.last_run_at ? dateTime(r.last_run_at, tz) : "nunca"}</p>
                      {r.last_error && <p className="text-xs text-rose-700">{r.last_error}</p>}
                    </div>
                    <div className="flex flex-wrap items-center gap-2">
                      {canManage && <input aria-label={`Horário de ${r.label}`} type="time" defaultValue={r.time} onBlur={(e) => e.target.value && e.target.value !== r.time && patch(r, { time: e.target.value })} className={`${inputClass} w-28`} />}
                      {canManage && <Button variant="secondary" disabled={busy === r.id} onClick={() => patch(r, { enabled: !r.enabled })}>{r.enabled ? "Desligar" : "Ligar"}</Button>}
                      {canAnalyze && <Button disabled={busy === r.id} onClick={() => runNow(r)}>{busy === r.id ? "Rodando…" : "Rodar agora"}</Button>}
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </Card>
          <Card>
            <CardHeader title="Últimas execuções" />
            {(runs.data?.length ?? 0) === 0 ? <p className="p-5 text-sm text-muted">Nenhuma execução ainda.</p> : (
              <ul className="divide-y divide-line">
                {runs.data!.map((r) => (
                  <li key={r.id} className="px-5 py-2.5 text-sm">
                    <div className="flex flex-wrap items-center gap-1.5"><Badge tone={RUN_TONE[r.status]}>{RUN_LABEL[r.status] ?? r.status}</Badge><span className="font-medium text-navy-900">{r.label}</span><span className="text-xs text-muted">{dateTime(r.started_at)} · {r.triggered_by}</span></div>
                    {r.error ? <p className="text-xs text-rose-700">{r.error}</p> : <p className="text-xs text-muted">{summarize(r.summary)}</p>}
                  </li>
                ))}
              </ul>
            )}
          </Card>
        </div>
        <Card className="h-fit min-w-0">
          <CardHeader title="Alertas" hint="Anomalias de gasto, entrega, custo por lead, ritmo do orçamento, experimentos prontos e criativos para revisar" />
          {alerts.loading ? <Loading /> : <AlertList alerts={alerts.data ?? []} canAct={canAnalyze} onChange={setAlert} />}
        </Card>
      </div>
    </>
  );
}
