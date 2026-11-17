"use client";

import { useState } from "react";
import { useApp } from "@/components/app-context";
import { NoClient } from "@/components/no-client";
import { Badge, Button, Card, CardHeader, Field, Loading, Notice, PageTitle, inputClass } from "@/components/ui";
import { api, useApi } from "@/lib/api";
import { dateTime, money, pct } from "@/lib/format";

interface Learning { id: number; title: string; statement: string; context: string | null; source_type: string; source_ref: string | null; status: "hypothesis" | "validated" | "refuted"; reliability: string; evidence: Record<string, unknown>; created_by: string; created_at: string; validated_at: string | null }
interface Exp { id: number; name: string; status: string; evaluation: { verdict?: { status: string; label: string } } | null }
interface Impact { execution_id: number; pending?: boolean; note?: string; campaign?: string; action?: string; metric?: string; metric_change?: number | null; spend_change?: number | null; before?: Record<string, number | null>; after?: Record<string, number | null>; window?: { before: string[]; after: string[] } }

const STATUS = { hypothesis: { label: "Hipótese", tone: "amber" }, validated: { label: "Validado", tone: "green" }, refuted: { label: "Refutado", tone: "red" } } as const;
const SOURCE: Record<string, string> = { experiment: "Experimento", execution_impact: "Antes x depois de uma execução", manual: "Registro manual", platform_doc: "Documentação da plataforma" };
const SIGNIFICANT = new Set(["significant_better", "significant_worse"]);

export default function AprendizadosPage() {
  const { client, canAnalyze, canManage } = useApp();
  const base = client ? `/clients/${client.id}` : null;
  const [q, setQ] = useState("");
  const [query, setQuery] = useState("");
  const [status, setStatus] = useState("");
  const params = new URLSearchParams({ ...(query && { q: query }), ...(status && { status }) }).toString();
  const list = useApi<Learning[]>(base && `${base}/learnings${params ? `?${params}` : ""}`);
  const exps = useApi<Exp[]>(base && `${base}/experiments`);
  const impact = useApi<Impact[]>(base && `${base}/impact`);
  const [form, setForm] = useState({ title: "", statement: "", context: "" });
  const [validating, setValidating] = useState<Record<number, string>>({});
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  if (!client) return <NoClient />;
  const validators = (exps.data ?? []).filter((e) => e.status === "concluded" && SIGNIFICANT.has(e.evaluation?.verdict?.status ?? ""));

  async function run(fn: () => Promise<unknown>) {
    setBusy(true); setError(null);
    try { await fn(); list.reload(); } catch (e) { setError((e as Error).message); } finally { setBusy(false); }
  }
  const add = (e: React.FormEvent) => { e.preventDefault(); return run(async () => {
    await api(`${base}/learnings`, { method: "POST", body: { title: form.title, statement: form.statement, context: form.context || null } });
    setForm({ title: "", statement: "", context: "" });
  }); };
  const validate = (l: Learning) => run(() => api(`${base}/learnings/${l.id}/validate`, { method: "POST", body: { experiment_id: Number(validating[l.id]) } }));
  const refute = (l: Learning) => {
    const reason = window.prompt("Por que este aprendizado foi refutado? (mín. 10 caracteres)");
    if (reason) run(() => api(`${base}/learnings/${l.id}/refute`, { method: "POST", body: { reason } }));
  };

  return (
    <>
      <PageTitle title="Aprendizados" subtitle="Memória do que funcionou e do que não funcionou neste cliente. Só vira “validado” com evidência de experimento." />
      <div className="mb-4"><Notice>
        Experimentos concluídos viram aprendizados automaticamente (validados só se o resultado for estatisticamente significativo).
        Comparações antes x depois de execuções e anotações manuais entram como hipótese de baixa confiabilidade — correlação não é causalidade.
      </Notice></div>
      {error && <div className="mb-4"><Notice tone="error">{error}</Notice></div>}
      <div className="grid grid-cols-1 gap-6 xl:grid-cols-[minmax(0,1fr)_360px]">
        <div className="min-w-0 space-y-6">
          <Card>
            <form onSubmit={(e) => { e.preventDefault(); setQuery(q.trim()); }} className="flex flex-wrap items-end gap-2 border-b border-line p-4">
              <div className="min-w-0 flex-1"><Field label="Buscar"><input value={q} onChange={(e) => setQ(e.target.value)} placeholder="ex.: vídeo depoimento, horário, oferta" className={inputClass} /></Field></div>
              <Field label="Status">
                <select value={status} onChange={(e) => setStatus(e.target.value)} className={inputClass}>
                  <option value="">Todos</option><option value="validated">Validados</option><option value="hypothesis">Hipóteses</option><option value="refuted">Refutados</option>
                </select>
              </Field>
              <Button type="submit" variant="secondary">Buscar</Button>
            </form>
            {list.loading ? <Loading /> : (list.data?.length ?? 0) === 0 ? <p className="p-5 text-sm text-muted">Nenhum aprendizado {query ? "encontrado" : "registrado ainda"}.</p> : (
              <ul className="divide-y divide-line">
                {list.data!.map((l) => (
                  <li key={l.id} className="px-5 py-3 text-sm">
                    <div className="flex flex-wrap items-center gap-1.5">
                      <Badge tone={STATUS[l.status].tone}>{STATUS[l.status].label}</Badge>
                      <Badge>confiabilidade {l.reliability}</Badge>
                      <span className="font-medium text-navy-900">{l.title}</span>
                    </div>
                    <p className="mt-1">{l.statement}</p>
                    {l.context && <p className="text-xs text-muted">{l.context}</p>}
                    {typeof l.evidence?.refuted_reason === "string" && <p className="text-xs text-rose-700">Refutado: {l.evidence.refuted_reason}</p>}
                    <p className="mt-1 text-xs text-muted">{SOURCE[l.source_type] ?? l.source_type} · {l.created_by} · {dateTime(l.created_at)}{l.validated_at && <> · validado em {dateTime(l.validated_at)}</>}</p>
                    {canManage && l.status === "hypothesis" && (
                      <div className="mt-2 flex flex-wrap items-center gap-2">
                        {validators.length > 0 && <>
                          <select aria-label="Experimento que valida" value={validating[l.id] ?? ""} onChange={(e) => setValidating({ ...validating, [l.id]: e.target.value })} className={`${inputClass} w-auto`}>
                            <option value="">Validar com experimento…</option>
                            {validators.map((e) => <option key={e.id} value={e.id}>{e.name}</option>)}
                          </select>
                          <Button variant="secondary" disabled={busy || !validating[l.id]} onClick={() => validate(l)}>Validar</Button>
                        </>}
                        <Button variant="secondary" disabled={busy} onClick={() => refute(l)}>Refutar</Button>
                      </div>
                    )}
                  </li>
                ))}
              </ul>
            )}
          </Card>
          <Card>
            <CardHeader title="Impacto das execuções" hint="7 dias antes x 7 dias depois de cada mudança concluída. Indica, não prova." />
            {(impact.data?.length ?? 0) === 0 ? <p className="p-5 text-sm text-muted">Nenhuma execução concluída ainda.</p> : (
              <ul className="divide-y divide-line">
                {impact.data!.map((m) => (
                  <li key={m.execution_id} className="px-5 py-2.5 text-sm">
                    {m.pending ? <span className="text-muted">Execução #{m.execution_id}: {m.note}</span> : (
                      <>
                        <span className="font-medium text-navy-900">{m.campaign}</span> <span className="text-xs text-muted">({m.action})</span>
                        <p className="text-xs text-muted">
                          {m.metric === "real_cac" ? "CAC real" : "Custo por lead"}: {money(m.before?.[m.metric!])} → {money(m.after?.[m.metric!])} ({m.metric_change != null ? pct(m.metric_change, 0) : "—"}) ·
                          investimento {m.spend_change != null ? pct(m.spend_change, 0) : "—"} · {m.window?.before[0]} a {m.window?.after[1]}
                        </p>
                      </>
                    )}
                  </li>
                ))}
              </ul>
            )}
          </Card>
        </div>
        {canAnalyze && (
          <Card className="h-fit">
            <CardHeader title="Registrar aprendizado" hint="Entra como hipótese" />
            <form onSubmit={add} className="space-y-2 p-5">
              <Field label="Título"><input required minLength={3} value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} className={inputClass} /></Field>
              <Field label="O que foi observado"><textarea required minLength={10} rows={4} value={form.statement} onChange={(e) => setForm({ ...form, statement: e.target.value })} className={inputClass} /></Field>
              <Field label="Contexto (opcional)" hint="Campanha, público, período"><input value={form.context} onChange={(e) => setForm({ ...form, context: e.target.value })} className={inputClass} /></Field>
              <Button type="submit" disabled={busy}>Registrar</Button>
            </form>
          </Card>
        )}
      </div>
    </>
  );
}
