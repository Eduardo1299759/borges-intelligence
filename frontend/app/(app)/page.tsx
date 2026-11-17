"use client";

import Link from "next/link";
import { useState } from "react";
import { useApp } from "@/components/app-context";
import { NoClient } from "@/components/no-client";
import { TrendChart } from "@/components/trend-chart";
import { Badge, Card, CardHeader, Loading, Notice, PageTitle } from "@/components/ui";
import { useApi } from "@/lib/api";
import { dateTime, day, dec, int, money, pct } from "@/lib/format";
import type { Agent, Dashboard } from "@/lib/types";

type Direction = "up" | "down" | "neutral"; // qual sentido de variação é bom

function Delta({ value, good }: { value: number | null; good: Direction }) {
  if (value === null) return <span className="text-xs text-muted">sem base de comparação</span>;
  const positive = value >= 0;
  const isGood = good === "neutral" ? null : (good === "up") === positive;
  const color = isGood === null ? "text-muted" : isGood ? "text-emerald-700" : "text-rose-700";
  return <span className={`text-xs font-medium ${color}`}>{positive ? "▲" : "▼"} {pct(Math.abs(value))} <span className="font-normal text-muted">vs. período anterior</span></span>;
}

function Kpi({ label, value, change, good, note }: { label: string; value: string; change?: number | null; good?: Direction; note?: string }) {
  return (
    <Card className="p-5">
      <p className="text-xs font-medium text-muted">{label}</p>
      <p className="mt-2 text-xl font-semibold tracking-tight text-navy-900 sm:text-2xl" title={value === "—" ? "Dado indisponível" : undefined}>{value}</p>
      <div className="mt-1.5 min-h-4">{change !== undefined && good && <Delta value={change} good={good} />}</div>
      {note && <p className="mt-1 text-xs text-muted">{note}</p>}
    </Card>
  );
}

const AGENT_STATUS = { active: ["Ativo", "green"], partial: ["Parcial", "blue"], planned: ["Planejado", "neutral"] } as const;

export default function OverviewPage() {
  const { client } = useApp();
  const [days, setDays] = useState(30);
  const { data, error, loading } = useApi<Dashboard>(client ? `/clients/${client.id}/dashboard?days=${days}` : null);
  const agents = useApi<Agent[]>("/agents");

  if (!client) return <NoClient />;
  const k = data?.kpis;
  const cur = data?.currency ?? "BRL";

  return (
    <>
      <PageTitle
        title="Visão geral"
        subtitle={data ? `${day(data.period.start)} a ${day(data.period.end)} · comparado a ${day(data.previous_period.start)} – ${day(data.previous_period.end)}` : client.name}
        action={
          <select aria-label="Período" value={days} onChange={(e) => setDays(Number(e.target.value))} className="rounded-lg border border-line bg-white px-3 py-2 text-sm">
            <option value={7}>Últimos 7 dias</option><option value={14}>Últimos 14 dias</option><option value={30}>Últimos 30 dias</option><option value={45}>Últimos 45 dias</option>
          </select>
        }
      />
      {error && <Notice tone="error">{error}</Notice>}
      {loading && <Loading />}
      {data && !data.has_data && (
        <Notice tone="warn">
          Este cliente ainda não tem dados. <Link href="/configuracoes" className="font-medium underline">Conecte o Windsor.ai e sincronize</Link>{" "}
          em Configurações. Até lá os indicadores ficam indisponíveis — o sistema não preenche valores.
        </Notice>
      )}
      {data && k && data.has_data && (
        <div className="space-y-6">
          <div className="grid grid-cols-2 gap-4 xl:grid-cols-4">
            <Kpi label="Investimento" value={money(k.spend, cur)} change={data.changes.spend} good="neutral" />
            <Kpi label="Receita confirmada" value={money(k.confirmed_revenue, cur)} change={data.changes.confirmed_revenue} good="up" note={`Atribuída pelas plataformas: ${money(k.attributed_revenue, cur)}`} />
            <Kpi label="Leads / conversas" value={int(k.leads)} change={data.changes.leads} good="up" note={`Custo por lead: ${money(k.cpl, cur)}`} />
            <Kpi label="Vendas confirmadas" value={int(k.confirmed_sales)} change={data.changes.confirmed_sales} good="up" note={`Taxa lead→venda: ${pct(k.lead_to_sale_rate)}`} />
            <Kpi label="CAC real" value={money(k.real_cac, cur)} change={data.changes.real_cac} good="down" note={`Meta: ${money(data.targets.cac, cur)} · máx. sustentável: ${money(k.max_sustainable_cac, cur)}`} />
            <Kpi label="ROAS confirmado" value={k.confirmed_roas === null ? "—" : `${dec(k.confirmed_roas)}x`} change={data.changes.confirmed_roas} good="up" note={`Meta: ${dec(data.targets.roas)}x · equilíbrio: ${dec(k.breakeven_roas)}x`} />
            <Kpi label="Lucro de contribuição" value={money(k.contribution_profit, cur)} change={data.changes.contribution_profit} good="up" note="Receita confirmada × margem − mídia" />
            <Kpi label="CTR" value={pct(k.ctr, 2)} change={data.changes.ctr} good="neutral" note="Métrica de apoio, não de resultado" />
          </div>

          <div className="grid gap-6 xl:grid-cols-3">
            <Card className="xl:col-span-2">
              <CardHeader title="Investimento e receita confirmada por dia" hint={`Fontes: ${data.data_quality.sources.join(" + ")} · última sincronização ${dateTime(data.data_quality.last_synced_at)}`} />
              <div className="p-4"><TrendChart series={data.series} currency={cur} /></div>
            </Card>
            <Card>
              <CardHeader title="Alertas prioritários" hint="Recomendações aguardando decisão" action={<Link href="/aprovacoes" className="text-xs font-medium text-azure-600 hover:underline">Ver todas</Link>} />
              {data.alerts.length === 0 ? (
                <p className="px-5 py-8 text-sm text-muted">
                  Nenhuma pendência. <Link href="/inteligencia" className="font-medium text-azure-600 hover:underline">Solicite uma análise ao Borges Core</Link>.
                </p>
              ) : (
                <ul className="divide-y divide-line">
                  {data.alerts.map((a) => (
                    <li key={a.id} className="px-5 py-3">
                      <Link href="/aprovacoes" className="block hover:text-azure-700">
                        <div className="mb-1 flex gap-1.5"><Badge tone={a.priority === "alta" ? "red" : a.priority === "média" ? "amber" : "neutral"}>{a.priority}</Badge></div>
                        <p className="text-sm font-medium">{a.title}</p>
                      </Link>
                    </li>
                  ))}
                </ul>
              )}
            </Card>
          </div>

          {data.pacing.mtd_spend !== null && (
            <Card className="p-5">
              <div className="flex flex-wrap items-baseline justify-between gap-2">
                <h2 className="text-sm font-semibold text-navy-900">Ritmo de investimento em {data.pacing.month.slice(5)}/{data.pacing.month.slice(0, 4)}</h2>
                <p className="text-xs text-muted">Dia {data.pacing.days_elapsed} de {data.pacing.days_in_month} · projeção linear pela média diária do mês</p>
              </div>
              <dl className="mt-3 grid grid-cols-2 gap-4 text-sm md:grid-cols-4">
                <div><dt className="text-xs text-muted">Investido no mês</dt><dd className="font-semibold">{money(data.pacing.mtd_spend, cur)}</dd></div>
                <div><dt className="text-xs text-muted">Orçamento mensal</dt><dd className="font-semibold">{money(data.pacing.monthly_budget, cur)}</dd></div>
                <div><dt className="text-xs text-muted">Projeção de fechamento</dt><dd className="font-semibold">{money(data.pacing.projected_spend, cur)}</dd></div>
                <div>
                  <dt className="text-xs text-muted">Projeção vs. orçamento</dt>
                  <dd className={`font-semibold ${data.pacing.projected_vs_budget !== null && Math.abs(data.pacing.projected_vs_budget) > 0.1 ? "text-amber-700" : ""}`}>
                    {data.pacing.projected_vs_budget === null ? "—" : `${data.pacing.projected_vs_budget > 0 ? "+" : "−"}${pct(Math.abs(data.pacing.projected_vs_budget))}`}
                  </dd>
                </div>
              </dl>
            </Card>
          )}

          {data.data_quality.issues.length > 0 && (
            <Notice tone="warn">
              <strong>Qualidade dos dados</strong>
              <ul className="mt-1 list-disc space-y-0.5 pl-5">{data.data_quality.issues.map((i) => <li key={i}>{i}</li>)}</ul>
            </Notice>
          )}
        </div>
      )}

      <Card className="mt-6">
        <CardHeader title="Status dos agentes" hint="O que cada agente realmente faz nesta versão" />
        <ul className="grid sm:grid-cols-2 xl:grid-cols-3">
          {(agents.data ?? []).map((a) => (
            <li key={a.code} className="border-b border-line px-5 py-3 sm:border-r">
              <div className="flex items-center justify-between gap-2">
                <p className="text-sm font-medium text-navy-900"><span className="text-muted">{a.code}</span> {a.name}</p>
                <Badge tone={AGENT_STATUS[a.status][1]}>{AGENT_STATUS[a.status][0]}{a.status === "planned" ? ` · Fase ${a.phase}` : ""}</Badge>
              </div>
              <p className="mt-0.5 text-xs text-muted">{a.capability || a.role}</p>
            </li>
          ))}
        </ul>
      </Card>
    </>
  );
}
