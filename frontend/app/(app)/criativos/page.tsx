"use client";

import { useState } from "react";
import { useApp } from "@/components/app-context";
import { NoClient } from "@/components/no-client";
import { Badge, Button, Card, CardHeader, DemoBadge, Field, Loading, Notice, PageTitle, inputClass } from "@/components/ui";
import { api, useApi } from "@/lib/api";
import { dateTime, int, money, pct } from "@/lib/format";

interface Creative {
  ad_id: number; name: string; status: string | null; ad_set: string; campaign: string; spend: number; clicks: number;
  leads: number; ctr: number | null; cpl: number | null; campaign_cpl: number | null; spend_share_in_campaign: number | null;
  class: string; class_label: string; trend: string | null; is_demo: boolean;
}
interface Variation { name: string; angle: string; test_hypothesis: string; format: string; headline: string; primary_text: string; cta: string; visual_brief: string }
interface Brief { id: number; ad_id: number | null; objective: string; audience: string; offer: string; angle: string | null;
  variations: Variation[]; source: "ia" | "modelo"; ai_model: string | null; note: string | null; created_at: string }

const CLASS_TONE: Record<string, "green" | "neutral" | "amber" | "red" | "blue"> = {
  vencedor: "green", na_media: "neutral", pouco_volume: "blue", fraco: "amber", sem_resultado: "red",
};
const TREND: Record<string, string> = { ctr_caindo: "CTR caindo", ctr_subindo: "CTR subindo", estavel: "Estável" };

export default function CreativeStudio() {
  const { client, canAnalyze } = useApp();
  const lib = useApi<{ creatives: Creative[] }>(client ? `/clients/${client.id}/creatives?days=30` : null);
  const briefs = useApi<Brief[]>(client ? `/clients/${client.id}/briefs` : null);
  const [form, setForm] = useState({ objective: "", audience: "", offer: "", angle: "", ad_id: "" });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [open, setOpen] = useState<number | null>(null);
  if (!client) return <NoClient />;
  const cur = client.currency;

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true); setError(null);
    try {
      const b = await api<Brief>(`/clients/${client!.id}/briefs`, { method: "POST", body: {
        objective: form.objective, audience: form.audience, offer: form.offer, angle: form.angle || null,
        ad_id: form.ad_id ? Number(form.ad_id) : null } });
      setOpen(b.id);
      briefs.reload();
    } catch (err) { setError((err as Error).message); } finally { setBusy(false); }
  }

  const set = (k: keyof typeof form) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement>) => setForm({ ...form, [k]: e.target.value });

  return (
    <>
      <PageTitle title="Creative Studio" subtitle="Desempenho de cada criativo (últimos 30 dias) e briefings de novas variações para teste." />
      <Card className="mb-6">
        <CardHeader title="Biblioteca de criativos" hint="Classificação comparada à própria campanha (mesmo público e oferta), pelo custo por lead." />
        {lib.loading && <Loading />}
        {lib.data && lib.data.creatives.length === 0 && <p className="p-6 text-sm text-muted">Nenhum anúncio com dados no período.</p>}
        {lib.data && lib.data.creatives.length > 0 && (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[960px] text-sm">
              <thead className="border-b border-line bg-canvas text-xs text-muted">
                <tr>{["Criativo", "Classificação", "Tendência", "Investimento", "% da campanha", "Leads", "CTR", "CPL", "CPL campanha"].map((h, i) =>
                  <th key={h} className={`px-4 py-3 font-medium ${i < 3 ? "text-left" : "text-right"}`}>{h}</th>)}</tr>
              </thead>
              <tbody>
                {lib.data.creatives.map((c) => (
                  <tr key={c.ad_id} className="border-b border-line last:border-0">
                    <td className="px-4 py-3">
                      <p className="font-medium text-navy-900">{c.name} {c.status === "paused" && <Badge tone="amber">Pausado</Badge>}</p>
                      <p className="text-xs text-muted">{c.campaign} · {c.ad_set}</p>
                    </td>
                    <td className="px-4 py-3"><Badge tone={CLASS_TONE[c.class]}>{c.class_label}</Badge></td>
                    <td className="px-4 py-3 text-xs">{c.trend ? <span className={c.trend === "ctr_caindo" ? "text-amber-800" : "text-muted"}>{TREND[c.trend]}</span> : "—"}</td>
                    <td className="px-4 py-3 text-right">{money(c.spend, cur)}</td>
                    <td className="px-4 py-3 text-right">{pct(c.spend_share_in_campaign)}</td>
                    <td className="px-4 py-3 text-right">{int(c.leads)}</td>
                    <td className="px-4 py-3 text-right">{pct(c.ctr, 2)}</td>
                    <td className="px-4 py-3 text-right font-medium">{money(c.cpl, cur)}</td>
                    <td className="px-4 py-3 text-right text-muted">{money(c.campaign_cpl, cur)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      <div className="grid gap-6 xl:grid-cols-[420px_1fr]">
        <Card className="h-fit">
          <CardHeader title="Novo briefing" hint="Com a IA ativa, as variações são escritas por ela; sem IA, um modelo com ângulos clássicos." />
          <form onSubmit={submit} className="space-y-3 p-5">
            {error && <Notice tone="error">{error}</Notice>}
            <Field label="Objetivo do criativo"><input required minLength={3} value={form.objective} onChange={set("objective")} placeholder="Ex.: mais pedidos pelo WhatsApp" className={inputClass} /></Field>
            <Field label="Público"><input required minLength={3} value={form.audience} onChange={set("audience")} placeholder="Ex.: famílias do bairro, 25 a 45 anos" className={inputClass} /></Field>
            <Field label="Oferta" hint="Só o que está escrito aqui pode aparecer como preço, desconto ou prazo nas variações.">
              <textarea required minLength={3} rows={2} value={form.offer} onChange={set("offer")} className={inputClass} />
            </Field>
            <Field label="Ângulo sugerido (opcional)"><input value={form.angle} onChange={set("angle")} className={inputClass} /></Field>
            <Field label="Criativo de referência (opcional)">
              <select value={form.ad_id} onChange={set("ad_id")} className={inputClass}>
                <option value="">Nenhum</option>
                {lib.data?.creatives.map((c) => <option key={c.ad_id} value={c.ad_id}>{c.name} — {c.campaign} ({c.class_label})</option>)}
              </select>
            </Field>
            <Button type="submit" disabled={busy || !canAnalyze}>{busy ? "Gerando…" : "Gerar variações"}</Button>
            <p className="text-xs text-muted">Geração de imagens ainda não está disponível: cada variação traz um briefing visual para o designer.</p>
          </form>
        </Card>
        <div className="space-y-3">
          {(briefs.data ?? []).length === 0 && <Card className="p-8 text-center text-sm text-muted">Nenhum briefing ainda.</Card>}
          {briefs.data?.map((b) => (
            <Card key={b.id}>
              <button type="button" onClick={() => setOpen(open === b.id ? null : b.id)} className="flex w-full items-start justify-between gap-3 px-5 py-4 text-left" aria-expanded={open === b.id}>
                <div>
                  <div className="mb-1 flex flex-wrap gap-1.5">
                    <Badge tone={b.source === "ia" ? "cyan" : "neutral"}>{b.source === "ia" ? `Escrito por IA · ${b.ai_model}` : "Modelo padrão"}</Badge>
                    <Badge>{b.variations.length} variações</Badge>
                  </div>
                  <p className="text-sm font-semibold text-navy-900">{b.objective}</p>
                  <p className="text-xs text-muted">{b.audience} · {dateTime(b.created_at)}</p>
                </div>
                <span aria-hidden className="text-muted">{open === b.id ? "−" : "+"}</span>
              </button>
              {open === b.id && (
                <div className="space-y-3 border-t border-line px-5 py-4">
                  {b.note && <Notice tone="warn">{b.note}</Notice>}
                  <p className="text-xs text-muted">Oferta: {b.offer}</p>
                  <div className="grid gap-3 md:grid-cols-2">
                    {b.variations.map((v, i) => (
                      <div key={i} className="rounded-lg border border-line p-4 text-sm">
                        <div className="mb-2 flex flex-wrap gap-1.5"><Badge tone="blue">{v.name}</Badge><Badge>{v.format}</Badge><Badge>{v.cta}</Badge></div>
                        <p className="font-semibold text-navy-900">{v.headline}</p>
                        <p className="mt-1 whitespace-pre-line">{v.primary_text}</p>
                        <p className="mt-2 text-xs text-muted"><strong>Ângulo:</strong> {v.angle}</p>
                        <p className="text-xs text-muted"><strong>Hipótese:</strong> {v.test_hypothesis}</p>
                        <p className="text-xs text-muted"><strong>Visual:</strong> {v.visual_brief}</p>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </Card>
          ))}
        </div>
      </div>
      {client.data_mode === "demo" && <div className="mt-4"><DemoBadge /></div>}
    </>
  );
}
