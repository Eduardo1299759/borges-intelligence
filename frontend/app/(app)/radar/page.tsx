"use client";

import { useState } from "react";
import { useApp } from "@/components/app-context";
import { NoClient } from "@/components/no-client";
import { Badge, Button, Card, CardHeader, Field, Notice, PageTitle, inputClass } from "@/components/ui";
import { api, useApi } from "@/lib/api";
import { dateTime } from "@/lib/format";

interface Radar {
  competitors: { id: number; name: string; website: string | null; facebook_page: string | null; notes: string | null; ads: number }[];
  ads: { id: number; competitor_id: number; source: string; url: string | null; ad_text: string; offer: string | null; format: string | null; first_seen: string | null; captured_at: string; days_running: number | null }[];
}
interface Insights {
  source: "ia" | "regras" | "nenhuma"; note?: string; model?: string; cost_usd?: number;
  angles?: { angle: string; competitors: string[]; example: string }[]; offers?: string[];
  opportunities?: { idea: string; rationale: string }[]; long_running?: { competitor: string; days_running: number; ad_text: string }[];
}

export default function RadarPage() {
  const { client, canAnalyze } = useApp();
  const radar = useApi<Radar>(client ? `/clients/${client.id}/radar` : null);
  const [comp, setComp] = useState({ name: "", website: "", facebook_page: "" });
  const [ad, setAd] = useState({ competitor: "", ad_text: "", url: "", offer: "", format: "", first_seen: "" });
  const [insights, setInsights] = useState<Insights | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  if (!client) return <NoClient />;
  const names = new Map(radar.data?.competitors.map((c) => [c.id, c.name]));
  const orNull = (v: string) => v.trim() || null;

  async function run(fn: () => Promise<void>) {
    setBusy(true); setError(null);
    try { await fn(); } catch (err) { setError((err as Error).message); } finally { setBusy(false); }
  }
  const addComp = (e: React.FormEvent) => { e.preventDefault(); return run(async () => {
    await api(`/clients/${client.id}/competitors`, { method: "POST", body: { name: comp.name, website: orNull(comp.website), facebook_page: orNull(comp.facebook_page) } });
    setComp({ name: "", website: "", facebook_page: "" }); radar.reload();
  }); };
  const addAd = (e: React.FormEvent) => { e.preventDefault(); return run(async () => {
    await api(`/clients/${client.id}/competitors/${ad.competitor}/ads`, { method: "POST", body: {
      ad_text: ad.ad_text, url: orNull(ad.url), offer: orNull(ad.offer), format: ad.format || null, first_seen: ad.first_seen || null } });
    setAd({ ...ad, ad_text: "", url: "", offer: "", first_seen: "" }); radar.reload();
  }); };
  const analyze = () => run(async () => setInsights(await api<Insights>(`/clients/${client.id}/radar/insights`, { method: "POST" })));

  return (
    <>
      <PageTitle title="Radar competitivo" subtitle="Concorrentes e anúncios públicos acompanhados, com ângulos e oportunidades de diferenciação."
        action={canAnalyze && <Button onClick={analyze} disabled={busy || !(radar.data?.ads.length)}>{busy ? "Analisando…" : "Analisar anúncios"}</Button>} />
      <div className="mb-4"><Notice>
        Anúncios são cadastrados manualmente a partir da Biblioteca de Anúncios da Meta ou do Centro de Transparência do Google. A busca automática
        exige um token aprovado pela Meta e ainda não está ativa. Tempo no ar indica investimento continuado, não prova que o anúncio dá resultado.
      </Notice></div>
      {error && <div className="mb-4"><Notice tone="error">{error}</Notice></div>}
      {insights && (
        <Card className="mb-6">
          <CardHeader title="Análise dos anúncios" hint={insights.source === "ia" ? `Escrita por IA · ${insights.model} · US$ ${insights.cost_usd?.toFixed(4).replace(".", ",")}` : "Resumo por regras"} />
          <div className="space-y-4 p-5 text-sm">
            {insights.note && <Notice tone="warn">{insights.note}</Notice>}
            {insights.angles && insights.angles.length > 0 && (
              <div><p className="mb-1 text-xs font-semibold uppercase tracking-wide text-muted">Ângulos usados</p>
                <ul className="space-y-1">{insights.angles.map((a, i) => <li key={i}><strong>{a.angle}</strong> ({a.competitors.join(", ")}) — <span className="text-muted">“{a.example}”</span></li>)}</ul></div>
            )}
            {insights.offers && insights.offers.length > 0 && (
              <div><p className="mb-1 text-xs font-semibold uppercase tracking-wide text-muted">Ofertas</p><ul className="list-disc pl-5">{insights.offers.map((o, i) => <li key={i}>{o}</li>)}</ul></div>
            )}
            {insights.opportunities && insights.opportunities.length > 0 && (
              <div><p className="mb-1 text-xs font-semibold uppercase tracking-wide text-muted">Ideias de teste</p>
                <ul className="space-y-1">{insights.opportunities.map((o, i) => <li key={i}><strong>{o.idea}</strong> — <span className="text-muted">{o.rationale}</span></li>)}</ul></div>
            )}
            {insights.long_running && insights.long_running.length > 0 && (
              <div><p className="mb-1 text-xs font-semibold uppercase tracking-wide text-muted">No ar há mais tempo</p>
                <ul className="space-y-1">{insights.long_running.map((a, i) => <li key={i}>{a.competitor}: {a.days_running} dias — <span className="text-muted">{a.ad_text}</span></li>)}</ul></div>
            )}
          </div>
        </Card>
      )}
      <div className="grid gap-6 xl:grid-cols-[380px_1fr]">
        <div className="space-y-6">
          <Card>
            <CardHeader title="Concorrentes" />
            <ul className="divide-y divide-line">
              {radar.data?.competitors.map((c) => (
                <li key={c.id} className="flex items-center justify-between gap-2 px-5 py-2.5 text-sm">
                  <span><span className="font-medium text-navy-900">{c.name}</span> <span className="text-xs text-muted">{c.website}</span></span>
                  <Badge>{c.ads} anúncio(s)</Badge>
                </li>
              ))}
            </ul>
            {canAnalyze && (
              <form onSubmit={addComp} className="space-y-2 border-t border-line p-5">
                <Field label="Nome"><input required minLength={2} value={comp.name} onChange={(e) => setComp({ ...comp, name: e.target.value })} className={inputClass} /></Field>
                <Field label="Site (opcional)"><input value={comp.website} onChange={(e) => setComp({ ...comp, website: e.target.value })} className={inputClass} /></Field>
                <Field label="Página no Facebook (opcional)"><input value={comp.facebook_page} onChange={(e) => setComp({ ...comp, facebook_page: e.target.value })} className={inputClass} /></Field>
                <Button type="submit" disabled={busy}>Adicionar concorrente</Button>
              </form>
            )}
          </Card>
          {canAnalyze && (radar.data?.competitors.length ?? 0) > 0 && (
            <Card>
              <CardHeader title="Registrar anúncio" />
              <form onSubmit={addAd} className="space-y-2 p-5">
                <Field label="Concorrente">
                  <select required value={ad.competitor} onChange={(e) => setAd({ ...ad, competitor: e.target.value })} className={inputClass}>
                    <option value="">Escolha</option>{radar.data?.competitors.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
                  </select>
                </Field>
                <Field label="Texto do anúncio"><textarea required minLength={3} rows={3} value={ad.ad_text} onChange={(e) => setAd({ ...ad, ad_text: e.target.value })} className={inputClass} /></Field>
                <Field label="Oferta (opcional)"><input value={ad.offer} onChange={(e) => setAd({ ...ad, offer: e.target.value })} className={inputClass} /></Field>
                <div className="grid grid-cols-2 gap-2">
                  <Field label="Formato">
                    <select value={ad.format} onChange={(e) => setAd({ ...ad, format: e.target.value })} className={inputClass}>
                      <option value="">—</option><option value="imagem">Imagem</option><option value="video">Vídeo</option><option value="carrossel">Carrossel</option><option value="outro">Outro</option>
                    </select>
                  </Field>
                  <Field label="No ar desde"><input type="date" value={ad.first_seen} onChange={(e) => setAd({ ...ad, first_seen: e.target.value })} className={inputClass} /></Field>
                </div>
                <Field label="Link (opcional)"><input value={ad.url} onChange={(e) => setAd({ ...ad, url: e.target.value })} className={inputClass} /></Field>
                <Button type="submit" disabled={busy}>Registrar</Button>
              </form>
            </Card>
          )}
        </div>
        <Card className="h-fit">
          <CardHeader title={`Anúncios acompanhados (${radar.data?.ads.length ?? 0})`} />
          {(radar.data?.ads.length ?? 0) === 0 ? <p className="p-6 text-sm text-muted">Nenhum anúncio registrado.</p> : (
            <ul className="divide-y divide-line">
              {radar.data!.ads.map((a) => (
                <li key={a.id} className="px-5 py-3 text-sm">
                  <div className="mb-1 flex flex-wrap gap-1.5">
                    <Badge tone="blue">{names.get(a.competitor_id)}</Badge>
                    {a.format && <Badge>{a.format}</Badge>}
                    {a.days_running != null && <Badge tone={a.days_running >= 30 ? "amber" : "neutral"}>{a.days_running} dias no ar</Badge>}
                    <Badge>{a.source === "manual" ? "Captura manual" : a.source}</Badge>
                  </div>
                  <p>{a.ad_text}</p>
                  {a.offer && <p className="text-xs text-muted">Oferta: {a.offer}</p>}
                  <p className="text-xs text-muted">Registrado em {dateTime(a.captured_at)}{a.url && <> · <a className="text-azure-600 hover:underline" href={a.url} target="_blank" rel="noreferrer noopener">ver anúncio</a></>}</p>
                </li>
              ))}
            </ul>
          )}
        </Card>
      </div>
    </>
  );
}
