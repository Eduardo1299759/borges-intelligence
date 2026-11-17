"use client";

import { useMemo, useState } from "react";
import { useApp } from "@/components/app-context";
import { NoClient } from "@/components/no-client";
import { Badge, Button, Card, CardHeader, Field, Notice, PageTitle, inputClass } from "@/components/ui";
import { api, useApi } from "@/lib/api";
import { day, int, money, pct } from "@/lib/format";

interface ArmOut { spend: number; clicks: number; leads: number; lead_rate: number | null; cpl: number | null; cpc: number | null; ctr: number | null }
interface Evaluation {
  window: { start: string; end: string | null; days_with_data: number; planned_end: string };
  control?: ArmOut; variant?: ArmOut; cpl_change?: number | null; notes?: string[];
  verdict: { status: string; label: string; p_value?: number | null; lift?: number | null; required_clicks_per_arm?: number | null; estimated_days_remaining?: number | null };
}
interface Experiment {
  id: number; name: string; problem: string; hypothesis: string; variable: string; primary_metric_label: string;
  guardrails: string[]; control_ads: string[]; variant_ads: string[]; campaign_name: string | null; relative_mde_pct: string;
  planned_days: number; start_date: string | null; status: string; outcome: string | null; learning: string | null;
  retroactive: boolean; evaluation: Evaluation | null;
}
interface Creative { ad_id: number; name: string; campaign: string; campaign_id: number }

const STATUS: Record<string, [string, "neutral" | "blue" | "green" | "red"]> = {
  draft: ["Rascunho", "neutral"], running: ["Em andamento", "blue"], concluded: ["Concluído", "green"], cancelled: ["Cancelado", "red"],
};
const VERDICT_TONE: Record<string, "green" | "red" | "amber" | "neutral"> = {
  significant_better: "green", significant_worse: "red", waiting_volume: "amber", no_difference: "neutral",
  trending_better: "amber", trending_worse: "amber",
};
const OUTCOME: Record<string, string> = { success: "Sucesso", failure: "Fracasso", inconclusive: "Inconclusivo" };

function ExperimentCard({ e, clientId, currency, canManage, onChanged }: { e: Experiment; clientId: number; currency: string; canManage: boolean; onChanged: () => void }) {
  const [startDate, setStartDate] = useState("");
  const [outcome, setOutcome] = useState("success");
  const [learning, setLearning] = useState("");
  const [error, setError] = useState<string | null>(null);
  const ev = e.evaluation;
  const base = `/clients/${clientId}/experiments/${e.id}`;
  async function act(path: string, body: unknown) {
    setError(null);
    try { await api(`${base}/${path}`, { method: "POST", body }); onChanged(); } catch (err) { setError((err as Error).message); }
  }
  return (
    <Card>
      <div className="flex flex-wrap items-start justify-between gap-3 border-b border-line px-5 py-4">
        <div>
          <div className="mb-1 flex flex-wrap gap-1.5">
            <Badge tone={STATUS[e.status][1]}>{STATUS[e.status][0]}</Badge>
            {e.outcome && <Badge tone="blue">{OUTCOME[e.outcome]}</Badge>}
            {e.retroactive && <Badge tone="cyan">Análise retroativa</Badge>}
          </div>
          <h3 className="text-sm font-semibold text-navy-900">{e.name}</h3>
          <p className="text-xs text-muted">{e.campaign_name} · variável: {e.variable} · métrica principal: {e.primary_metric_label}</p>
        </div>
        {ev && <Badge tone={VERDICT_TONE[ev.verdict.status] ?? "neutral"}>{ev.verdict.label}</Badge>}
      </div>
      <div className="space-y-4 px-5 py-4 text-sm">
        {error && <Notice tone="error">{error}</Notice>}
        <dl className="grid gap-3 md:grid-cols-2">
          <div><dt className="text-[11px] font-semibold uppercase tracking-wide text-muted">Problema</dt><dd>{e.problem}</dd></div>
          <div><dt className="text-[11px] font-semibold uppercase tracking-wide text-muted">Hipótese</dt><dd>{e.hypothesis}</dd></div>
          <div><dt className="text-[11px] font-semibold uppercase tracking-wide text-muted">Controle</dt><dd>{e.control_ads.join(", ")}</dd></div>
          <div><dt className="text-[11px] font-semibold uppercase tracking-wide text-muted">Variante</dt><dd>{e.variant_ads.join(", ")}</dd></div>
          <div><dt className="text-[11px] font-semibold uppercase tracking-wide text-muted">Critério</dt><dd>Detectar variação de {Number(e.relative_mde_pct)}% na taxa clique → lead; duração planejada {e.planned_days} dias</dd></div>
          <div><dt className="text-[11px] font-semibold uppercase tracking-wide text-muted">Métricas de proteção</dt><dd>{e.guardrails.join(", ")}</dd></div>
        </dl>
        {ev?.control && ev.variant && (
          <div className="overflow-x-auto rounded-lg border border-line">
            <table className="w-full min-w-[560px] text-sm">
              <thead className="bg-canvas text-xs text-muted"><tr>{["", "Investimento", "Cliques", "Leads", "Clique → lead", "CPL", "CPC", "CTR"].map((h, i) => <th key={i} className={`px-3 py-2 font-medium ${i ? "text-right" : "text-left"}`}>{h}</th>)}</tr></thead>
              <tbody>
                {([["Controle", ev.control], ["Variante", ev.variant]] as const).map(([label, a]) => (
                  <tr key={label} className="border-t border-line">
                    <td className="px-3 py-2 font-medium">{label}</td>
                    <td className="px-3 py-2 text-right">{money(a.spend, currency)}</td>
                    <td className="px-3 py-2 text-right">{int(a.clicks)}</td>
                    <td className="px-3 py-2 text-right">{int(a.leads)}</td>
                    <td className="px-3 py-2 text-right">{pct(a.lead_rate, 2)}</td>
                    <td className="px-3 py-2 text-right">{money(a.cpl, currency)}</td>
                    <td className="px-3 py-2 text-right">{money(a.cpc, currency)}</td>
                    <td className="px-3 py-2 text-right">{pct(a.ctr, 2)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {ev && (
          <p className="text-xs text-muted">
            {ev.window.end ? `Período ${day(ev.window.start)} a ${day(ev.window.end)} (${ev.window.days_with_data} dias com dados)` : `Início em ${day(ev.window.start)}`}
            {ev.verdict.lift != null && ` · variação na taxa clique → lead: ${ev.verdict.lift >= 0 ? "+" : ""}${pct(ev.verdict.lift)}`}
            {ev.verdict.p_value != null && ` · p-valor ${ev.verdict.p_value.toFixed(4).replace(".", ",")}`}
            {ev.verdict.required_clicks_per_arm != null && ` · volume necessário: ${int(ev.verdict.required_clicks_per_arm)} cliques por braço`}
            {ev.verdict.estimated_days_remaining != null && ` · estimativa: mais ${ev.verdict.estimated_days_remaining} dia(s)`}
          </p>
        )}
        {ev?.notes && <ul className="list-disc space-y-0.5 pl-5 text-xs text-muted">{ev.notes.map((n) => <li key={n}>{n}</li>)}</ul>}
        {e.learning && <Notice><strong>Aprendizado registrado:</strong> {e.learning}</Notice>}
        {canManage && e.status === "draft" && (
          <div className="flex flex-wrap items-end gap-2 border-t border-line pt-4">
            <Field label="Início (vazio = hoje; data passada = análise retroativa)">
              <input type="date" value={startDate} onChange={(x) => setStartDate(x.target.value)} className={inputClass} />
            </Field>
            <Button onClick={() => act("start", { start_date: startDate || null })}>Iniciar</Button>
            <Button variant="danger" onClick={() => act("cancel", {})}>Cancelar</Button>
          </div>
        )}
        {canManage && e.status === "running" && (
          <div className="space-y-2 border-t border-line pt-4">
            <div className="grid gap-3 md:grid-cols-[200px_1fr]">
              <Field label="Resultado">
                <select value={outcome} onChange={(x) => setOutcome(x.target.value)} className={inputClass}>
                  <option value="success">Sucesso</option><option value="failure">Fracasso</option><option value="inconclusive">Inconclusivo</option>
                </select>
              </Field>
              <Field label="Aprendizado (mínimo 10 caracteres)">
                <input value={learning} onChange={(x) => setLearning(x.target.value)} placeholder="O que este teste ensinou sobre o público, a oferta ou o criativo?" className={inputClass} />
              </Field>
            </div>
            <div className="flex gap-2">
              <Button disabled={learning.trim().length < 10} onClick={() => act("conclude", { outcome, learning })}>Concluir e registrar</Button>
              <Button variant="danger" onClick={() => act("cancel", {})}>Cancelar</Button>
            </div>
          </div>
        )}
      </div>
    </Card>
  );
}

export default function ExperimentsPage() {
  const { client, canManage, canAnalyze } = useApp();
  const list = useApi<Experiment[]>(client ? `/clients/${client.id}/experiments` : null);
  const lib = useApi<{ creatives: Creative[] }>(client ? `/clients/${client.id}/creatives?days=30` : null);
  const [form, setForm] = useState({ name: "", problem: "", hypothesis: "", variable: "Criativo", campaign: "", control: [] as number[], variant: [] as number[], mde: "20", days: "14" });
  const [error, setError] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const campaigns = useMemo(() => {
    const m = new Map<number, string>();
    lib.data?.creatives.forEach((c) => m.set(c.campaign_id, c.campaign));
    return [...m.entries()];
  }, [lib.data]);
  if (!client) return <NoClient />;
  const ads = (lib.data?.creatives ?? []).filter((c) => String(c.campaign_id) === form.campaign);
  const toggle = (k: "control" | "variant", id: number) => setForm((f) => ({ ...f, [k]: f[k].includes(id) ? f[k].filter((x) => x !== id) : [...f[k], id] }));

  async function create(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      await api(`/clients/${client!.id}/experiments`, { method: "POST", body: {
        name: form.name, problem: form.problem, hypothesis: form.hypothesis, variable: form.variable,
        control_ad_ids: form.control, variant_ad_ids: form.variant, relative_mde_pct: Number(form.mde), planned_days: Number(form.days) } });
      setCreating(false);
      setForm({ ...form, name: "", problem: "", hypothesis: "", control: [], variant: [] });
      list.reload();
    } catch (err) { setError((err as Error).message); }
  }
  const set = (k: "name" | "problem" | "hypothesis" | "variable" | "mde" | "days") => (e: React.ChangeEvent<HTMLInputElement>) => setForm({ ...form, [k]: e.target.value });

  return (
    <>
      <PageTitle title="Experimentos" subtitle="Testes entre anúncios: hipótese, volume necessário, resultado estatístico e aprendizado registrado."
        action={canAnalyze && <Button onClick={() => setCreating(!creating)}>{creating ? "Fechar" : "Novo experimento"}</Button>} />
      {creating && (
        <Card className="mb-6">
          <CardHeader title="Novo experimento" hint="Controle e variante são anúncios da mesma campanha." />
          <form onSubmit={create} className="grid gap-4 p-5 md:grid-cols-2">
            {error && <div className="md:col-span-2"><Notice tone="error">{error}</Notice></div>}
            <Field label="Nome"><input required minLength={3} value={form.name} onChange={set("name")} className={inputClass} /></Field>
            <Field label="Variável testada"><input required minLength={2} value={form.variable} onChange={set("variable")} className={inputClass} /></Field>
            <Field label="Problema"><input required minLength={3} value={form.problem} onChange={set("problem")} className={inputClass} /></Field>
            <Field label="Hipótese"><input required minLength={3} value={form.hypothesis} onChange={set("hypothesis")} className={inputClass} /></Field>
            <Field label="Campanha">
              <select required value={form.campaign} onChange={(e) => setForm({ ...form, campaign: e.target.value, control: [], variant: [] })} className={inputClass}>
                <option value="">Escolha</option>
                {campaigns.map(([id, name]) => <option key={id} value={id}>{name}</option>)}
              </select>
            </Field>
            <div className="grid grid-cols-2 gap-3">
              <Field label="Variação mínima a detectar (%)"><input type="number" min="5" max="100" value={form.mde} onChange={set("mde")} className={inputClass} /></Field>
              <Field label="Duração planejada (dias)"><input type="number" min="3" max="90" value={form.days} onChange={set("days")} className={inputClass} /></Field>
            </div>
            {form.campaign && (["control", "variant"] as const).map((k) => (
              <fieldset key={k} className="rounded-lg border border-line p-3">
                <legend className="px-1 text-xs font-medium text-navy-800">{k === "control" ? "Controle" : "Variante"}</legend>
                {ads.map((a) => (
                  <label key={a.ad_id} className="flex items-center gap-2 py-0.5 text-sm">
                    <input type="checkbox" checked={form[k].includes(a.ad_id)} onChange={() => toggle(k, a.ad_id)} /> {a.name}
                  </label>
                ))}
              </fieldset>
            ))}
            <div className="md:col-span-2"><Button type="submit" disabled={!form.control.length || !form.variant.length}>Criar rascunho</Button></div>
          </form>
        </Card>
      )}
      {(list.data ?? []).length === 0 && !list.loading && <Card className="p-10 text-center text-sm text-muted">Nenhum experimento ainda.</Card>}
      <div className="space-y-4">
        {list.data?.map((e) => <ExperimentCard key={`${e.id}-${e.status}`} e={e} clientId={client.id} currency={client.currency} canManage={canManage} onChanged={list.reload} />)}
      </div>
    </>
  );
}
