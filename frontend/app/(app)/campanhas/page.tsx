"use client";

import { Fragment, useState } from "react";
import { useApp } from "@/components/app-context";
import { NoClient } from "@/components/no-client";
import { Badge, Card, DemoBadge, Loading, Notice, PageTitle } from "@/components/ui";
import { useApi } from "@/lib/api";
import { dateTime, day, dec, int, money, pct } from "@/lib/format";
import type { Breakdown, BreakdownNode, CampaignRow } from "@/lib/types";

interface Resp { is_demo: boolean; currency: string; period: { start: string; end: string }; campaigns: CampaignRow[] }

const PLATFORM = { meta: "Meta Ads", google: "Google Ads" } as Record<string, string>;

function BreakdownRow({ node, cur, indent }: { node: BreakdownNode; cur: string; indent: boolean }) {
  const k = node.kpis;
  return (
    <tr className="border-t border-line">
      <td className={`py-2 pr-3 ${indent ? "pl-8 text-muted" : "pl-3 font-medium text-navy-900"}`}>{node.name}</td>
      <td className="px-3 py-2 text-right">{money(k.spend, cur)}</td>
      <td className="px-3 py-2 text-right">{int(k.impressions)}</td>
      <td className="px-3 py-2 text-right">{pct(k.ctr, 2)}</td>
      <td className="px-3 py-2 text-right">{money(k.cpc, cur)}</td>
      <td className="px-3 py-2 text-right">{int(k.leads)}</td>
      <td className="px-3 py-2 text-right">{money(k.cpl, cur)}</td>
      <td className="px-3 py-2 text-right">{k.attributed_roas == null ? "—" : `${dec(k.attributed_roas)}x`}</td>
    </tr>
  );
}

function BreakdownTable({ clientId, campaignId, days, cur }: { clientId: number; campaignId: number; days: number; cur: string }) {
  const { data, error, loading } = useApi<Breakdown>(`/clients/${clientId}/campaigns/${campaignId}/breakdown?days=${days}`);
  if (loading) return <p className="mt-2 text-muted">Carregando detalhamento…</p>;
  if (error) return <p className="mt-2 text-rose-700">{error}</p>;
  if (!data || data.ad_sets.length === 0) return <p className="mt-1 text-muted">A fonte não entrega detalhamento para esta campanha no período.</p>;
  const setLabel = data.platform === "google" ? "Grupo de anúncios" : "Conjunto / anúncio";
  return (
    <div className="mt-2 overflow-x-auto rounded-lg border border-line bg-white">
      <table className="w-full min-w-[720px] text-sm">
        <thead className="bg-canvas text-xs text-muted">
          <tr>{[setLabel, "Investimento", "Impressões", "CTR", "CPC", "Leads", "CPL", "ROAS atrib."].map((h, i) => <th key={h} className={`px-3 py-2 font-medium ${i === 0 ? "text-left" : "text-right"}`}>{h}</th>)}</tr>
        </thead>
        <tbody>
          {data.ad_sets.map((s) => (
            <Fragment key={s.id}>
              <BreakdownRow node={s} cur={cur} indent={false} />
              {s.ads.map((a) => <BreakdownRow key={a.id} node={a} cur={cur} indent />)}
            </Fragment>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default function CampaignsPage() {
  const { client } = useApp();
  const [days, setDays] = useState(30);
  const [open, setOpen] = useState<number | null>(null);
  const { data, error, loading } = useApi<Resp>(client ? `/clients/${client.id}/campaigns?days=${days}` : null);
  if (!client) return <NoClient />;
  const cur = data?.currency ?? "BRL";
  const head = ["Campanha", "Orçam./dia", "Investimento", "Leads", "CPL", "Vendas conf.", "CAC real", "ROAS conf.", "ROAS atrib.", "CTR", "Freq. diária"];

  return (
    <>
      <PageTitle title="Gestor de campanhas" subtitle={data ? `${day(data.period.start)} a ${day(data.period.end)}` : undefined}
        action={
          <select aria-label="Período" value={days} onChange={(e) => setDays(Number(e.target.value))} className="rounded-lg border border-line bg-white px-3 py-2 text-sm">
            <option value={7}>Últimos 7 dias</option><option value={14}>Últimos 14 dias</option><option value={30}>Últimos 30 dias</option><option value={60}>Últimos 60 dias</option>
          </select>
        } />
      {error && <Notice tone="error">{error}</Notice>}
      {loading && <Loading />}
      {data && data.campaigns.length === 0 && <Notice tone="warn">Nenhuma campanha disponível. Conecte o Windsor.ai e sincronize em Configurações.</Notice>}
      {data && data.campaigns.length > 0 && (
        <Card>
          <div className="overflow-x-auto">
            <table className="w-full min-w-[1100px] text-sm">
              <thead className="border-b border-line bg-canvas text-xs text-muted">
                <tr>{head.map((h, i) => <th key={h} className={`px-4 py-3 font-medium ${i === 0 ? "text-left" : "text-right"}`}>{h}</th>)}</tr>
              </thead>
              <tbody>
                {data.campaigns.map((c) => {
                  const k = c.kpis;
                  return (
                    <Fragment key={c.id}>
                      <tr className="border-b border-line">
                        <td className="px-4 py-3">
                          <button onClick={() => setOpen(open === c.id ? null : c.id)} aria-expanded={open === c.id} className="text-left">
                            <span className="font-medium text-navy-900 hover:text-azure-700">{c.name}</span>
                            <span className="mt-1 flex flex-wrap gap-1.5">
                              <Badge tone={c.platform === "meta" ? "blue" : "neutral"}>{PLATFORM[c.platform] ?? c.platform}</Badge>
                              {c.is_demo && <DemoBadge />}
                              {c.changes.length > 0 && <Badge tone="green">{c.changes.length} alteração(ões)</Badge>}
                            </span>
                          </button>
                        </td>
                        <td className="px-4 py-3 text-right">{money(c.daily_budget, cur)}</td>
                        <td className="px-4 py-3 text-right">{money(k?.spend, cur)}</td>
                        <td className="px-4 py-3 text-right">{int(k?.leads)}</td>
                        <td className="px-4 py-3 text-right">{money(k?.cpl, cur)}</td>
                        <td className="px-4 py-3 text-right">{int(k?.confirmed_sales)}</td>
                        <td className="px-4 py-3 text-right font-medium">{money(k?.real_cac, cur)}</td>
                        <td className="px-4 py-3 text-right font-medium">{k?.confirmed_roas == null ? "—" : `${dec(k.confirmed_roas)}x`}</td>
                        <td className="px-4 py-3 text-right text-muted">{k?.attributed_roas == null ? "—" : `${dec(k.attributed_roas)}x`}</td>
                        <td className="px-4 py-3 text-right">{pct(k?.ctr, 2)}</td>
                        <td className="px-4 py-3 text-right">{dec(k?.avg_daily_frequency)}</td>
                      </tr>
                      {open === c.id && (
                        <tr className="border-b border-line bg-canvas">
                          <td colSpan={head.length} className="px-4 py-4 text-sm">
                            <p className="text-xs text-muted">Objetivo: {c.objective ?? "—"} · {k ? `${k.days} dia(s) com dados no período` : "sem dados no período"}</p>
                            <p className="mt-3 text-xs font-semibold uppercase tracking-wide text-muted">Conjuntos e anúncios</p>
                            <BreakdownTable clientId={client.id} campaignId={c.id} days={days} cur={cur} />
                            <p className="mt-4 text-xs font-semibold uppercase tracking-wide text-muted">Histórico de alterações</p>
                            {c.changes.length === 0 ? <p className="mt-1 text-muted">Nenhuma alteração registrada.</p> : (
                              <ul className="mt-1 space-y-1">
                                {c.changes.map((ch) => (
                                  <li key={ch.execution_id}>
                                    {dateTime(ch.finished_at)} — {ch.before && ch.after ? `orçamento diário ${money(ch.before.daily_budget, cur)} → ${money(ch.after.daily_budget, cur)}` : ch.title}{" "}
                                    <span className="text-muted">({ch.mode === "simulated" ? "simulada" : "real"}, {ch.status === "completed" ? "concluída" : "falhou"}{ch.verified ? ", verificada" : ""})</span>
                                  </li>
                                ))}
                              </ul>
                            )}
                          </td>
                        </tr>
                      )}
                    </Fragment>
                  );
                })}
              </tbody>
            </table>
          </div>
          <p className="border-t border-line px-4 py-3 text-xs text-muted">
            ROAS atribuído vem da plataforma; ROAS confirmado usa vendas registradas. Frequência é a média diária (alcance diário não é deduplicado entre dias).
            Clique em uma campanha para ver conjuntos e anúncios; vendas confirmadas só existem no nível da campanha.
          </p>
        </Card>
      )}
    </>
  );
}
