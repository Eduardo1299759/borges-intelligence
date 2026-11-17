"use client";

import { Badge, DemoBadge } from "@/components/ui";
import { day, money, pct } from "@/lib/format";

export interface Kpi { key: string; label: string; good: "up" | "down" | "neutral"; current: number | null; previous: number | null; change: number | null }
export interface ReportContent {
  kind: string; label: string; client: string; is_demo: boolean; currency?: string;
  period: { start: string; end: string }; compare?: { start: string; end: string }; sources?: string[];
  executive_summary?: string; kpis?: Kpi[]; highlights?: string[];
  campaigns?: { name: string; platform: string | null; spend: number | null; spend_change: number | null; leads: number | null; cpl: number | null; cpl_change: number | null; sales: number | null; cac: number | null; cac_change: number | null; roas: number | null }[];
  why?: { title: string; problem: string; probable_cause: string | null; hypothesis: string | null; priority: string; confidence: string }[];
  next_steps?: { title: string; action: string; validation: string | null }[];
  actions_done?: { title: string; decision: string; comment: string | null; at: string }[];
  executions?: { title: string; mode: string; status: string; verified: boolean }[];
  experiments?: { name: string; status: string; hypothesis: string; outcome: string | null; learning: string | null; verdict: string | null }[];
  learnings?: { title: string; status: string; reliability: string }[];
  alerts?: { title: string; severity: string; detail: string }[];
  data_quality?: string[]; notes?: string[];
  insights?: { source: string; note?: string; angles?: { angle: string; competitors: string[]; example: string }[]; offers?: string[]; opportunities?: { idea: string; rationale: string }[]; long_running?: { competitor: string; days_running: number; ad_text: string }[] };
}

const MONEY_KEYS = new Set(["spend", "confirmed_revenue", "real_cac", "cpl", "contribution_profit"]);
const DECISION: Record<string, string> = { approved: "Aprovada", rejected: "Rejeitada", adjustment_requested: "Ajuste pedido" };
const LEARNING: Record<string, string> = { hypothesis: "Hipótese", validated: "Validado", refuted: "Refutado" };

function fmt(k: Kpi, v: number | null, currency: string) {
  if (v == null) return "—";
  if (MONEY_KEYS.has(k.key)) return money(v, currency);
  if (k.key === "confirmed_roas") return `${v.toFixed(2).replace(".", ",")}x`;
  return Math.round(v).toLocaleString("pt-BR");
}

function Change({ v, good }: { v: number | null; good: "up" | "down" | "neutral" }) {
  if (v == null) return <span className="text-muted">—</span>;
  const better = good === "neutral" ? null : (good === "up") === v > 0;
  const tone = better == null || Math.abs(v) < 0.005 ? "text-muted" : better ? "text-emerald-700" : "text-rose-700";
  return <span className={tone}>{v > 0 ? "+" : ""}{pct(v, 0)}</span>;
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="break-inside-avoid border-t border-line px-5 py-4 sm:px-8">
      <h3 className="mb-2 text-sm font-semibold uppercase tracking-wide text-navy-900">{title}</h3>
      <div className="text-sm">{children}</div>
    </section>
  );
}

export function ReportView({ c }: { c: ReportContent }) {
  const cur = c.currency ?? "BRL";
  return (
    <article className="min-w-0 rounded-xl border border-line bg-white print:border-0">
      <header className="px-5 py-5 sm:px-8">
        <div className="flex flex-wrap items-center gap-2">
          <h2 className="text-lg font-semibold text-navy-900">{c.label} — {c.client}</h2>
          {c.is_demo && <DemoBadge />}
        </div>
        <p className="mt-1 text-sm text-muted">
          Período {day(c.period.start)}{c.period.end !== c.period.start && <> a {day(c.period.end)}</>}
          {c.compare && <> · comparado com {day(c.compare.start)}{c.compare.end !== c.compare.start && <> a {day(c.compare.end)}</>}</>}
          {c.sources && c.sources.length > 0 && <> · Fontes: {c.sources.join(" + ")}</>}
        </p>
        {c.is_demo && <p className="mt-2 text-xs text-cyan-900">Dados simulados de demonstração — não representam resultados reais.</p>}
      </header>

      {c.executive_summary && <Section title="Resumo executivo"><p>{c.executive_summary}</p></Section>}

      {c.kpis && (
        <Section title="Indicadores">
          <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
            {c.kpis.map((k) => (
              <div key={k.key} className="min-w-0 rounded-lg border border-line p-3">
                <p className="truncate text-xs text-muted">{k.label}</p>
                <p className="text-base font-semibold text-navy-900">{fmt(k, k.current, cur)}</p>
                <p className="text-xs">antes {fmt(k, k.previous, cur)} · <Change v={k.change} good={k.good} /></p>
              </div>
            ))}
          </div>
        </Section>
      )}

      {c.campaigns && c.campaigns.length > 0 && (
        <Section title="O que aconteceu por campanha">
          <div className="overflow-x-auto">
            <table className="w-full min-w-[640px] text-left text-sm">
              <thead className="text-xs text-muted"><tr><th className="py-1 pr-3">Campanha</th><th className="pr-3">Investimento</th><th className="pr-3">Leads</th><th className="pr-3">CPL</th><th className="pr-3">Vendas</th><th className="pr-3">CAC real</th><th>ROAS conf.</th></tr></thead>
              <tbody className="divide-y divide-line">
                {c.campaigns.map((r) => (
                  <tr key={r.name}>
                    <td className="py-1.5 pr-3">{r.name}</td>
                    <td className="pr-3">{money(r.spend, cur)} <Change v={r.spend_change} good="neutral" /></td>
                    <td className="pr-3">{r.leads ?? "—"}</td>
                    <td className="pr-3">{money(r.cpl, cur)} <Change v={r.cpl_change} good="down" /></td>
                    <td className="pr-3">{r.sales ?? "—"}</td>
                    <td className="pr-3">{money(r.cac, cur)} <Change v={r.cac_change} good="down" /></td>
                    <td>{r.roas != null ? `${r.roas.toFixed(2).replace(".", ",")}x` : "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {c.highlights && c.highlights.length > 0 && <ul className="mt-3 list-disc pl-5">{c.highlights.map((h, i) => <li key={i}>{h}</li>)}</ul>}
        </Section>
      )}

      {c.why && c.why.length > 0 && (
        <Section title="Por que pode ter acontecido (hipóteses)">
          <ul className="space-y-2">{c.why.map((w, i) => (
            <li key={i}><strong>{w.title}</strong> <Badge tone={w.priority === "alta" ? "red" : "amber"}>prioridade {w.priority}</Badge> <Badge>confiança {w.confidence}</Badge>
              <p className="text-muted">{w.problem}{w.probable_cause && <> Causa provável: {w.probable_cause}</>}</p></li>
          ))}</ul>
        </Section>
      )}

      <Section title="O que foi feito">
        {(c.actions_done?.length ?? 0) + (c.executions?.length ?? 0) === 0 ? <p className="text-muted">Nenhuma decisão ou execução registrada no período.</p> : (
          <ul className="list-disc space-y-1 pl-5">
            {c.actions_done?.map((a, i) => <li key={`d${i}`}>{DECISION[a.decision] ?? a.decision}: {a.title}{a.comment && <span className="text-muted"> — {a.comment}</span>}</li>)}
            {c.executions?.map((e, i) => <li key={`e${i}`}>Execução {e.mode === "live" ? "real" : "simulada"} ({e.status}{e.verified ? ", verificada" : ""}): {e.title}</li>)}
          </ul>
        )}
      </Section>

      {c.experiments && c.experiments.length > 0 && (
        <Section title="O que está sendo testado">
          <ul className="space-y-1">{c.experiments.map((e, i) => (
            <li key={i}><strong>{e.name}</strong> — {e.hypothesis} <Badge tone={e.status === "running" ? "blue" : "green"}>{e.status === "running" ? "Em andamento" : "Concluído"}</Badge>
              {e.verdict && <span className="text-muted"> · {e.verdict}</span>}{e.learning && <p className="text-muted">Aprendizado: {e.learning}</p>}</li>
          ))}</ul>
        </Section>
      )}

      {c.next_steps && c.next_steps.length > 0 && (
        <Section title="Próximos passos (aguardando aprovação)">
          <ol className="list-decimal space-y-1 pl-5">{c.next_steps.map((n, i) => <li key={i}><strong>{n.title}</strong> — {n.action}{n.validation && <span className="text-muted"> Validar por: {n.validation}</span>}</li>)}</ol>
        </Section>
      )}

      {c.learnings && c.learnings.length > 0 && (
        <Section title="Aprendizados registrados">
          <ul className="space-y-1">{c.learnings.map((l, i) => <li key={i}>{l.title} <Badge tone={l.status === "validated" ? "green" : l.status === "refuted" ? "red" : "amber"}>{LEARNING[l.status]}</Badge> <span className="text-xs text-muted">confiabilidade {l.reliability}</span></li>)}</ul>
        </Section>
      )}

      {c.alerts && c.alerts.length > 0 && (
        <Section title="Alertas abertos">
          <ul className="space-y-1">{c.alerts.map((a, i) => <li key={i}><Badge tone={a.severity === "alta" ? "red" : "amber"}>{a.severity}</Badge> <strong>{a.title}</strong> <span className="text-muted">— {a.detail}</span></li>)}</ul>
        </Section>
      )}

      {c.insights && (
        <Section title="Concorrência">
          {c.insights.note && <p className="mb-2 text-muted">{c.insights.note}</p>}
          {c.insights.angles?.map((a, i) => <p key={i}><strong>{a.angle}</strong> ({a.competitors.join(", ")}) — “{a.example}”</p>)}
          {c.insights.offers && c.insights.offers.length > 0 && <ul className="list-disc pl-5">{c.insights.offers.map((o, i) => <li key={i}>{o}</li>)}</ul>}
          {c.insights.opportunities?.map((o, i) => <p key={i}><strong>{o.idea}</strong> — {o.rationale}</p>)}
          {c.insights.long_running?.map((a, i) => <p key={i}>{a.competitor}: {a.days_running} dias no ar — <span className="text-muted">{a.ad_text}</span></p>)}
        </Section>
      )}

      {((c.data_quality?.length ?? 0) > 0 || (c.notes?.length ?? 0) > 0) && (
        <Section title="Qualidade dos dados e observações">
          <ul className="list-disc space-y-1 pl-5 text-muted">{[...(c.data_quality ?? []), ...(c.notes ?? [])].map((n, i) => <li key={i}>{n}</li>)}</ul>
        </Section>
      )}
    </article>
  );
}
