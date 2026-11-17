"use client";

import Link from "next/link";
import { useState } from "react";
import { useApp } from "@/components/app-context";
import { NoClient } from "@/components/no-client";
import { RecommendationCard } from "@/components/recommendation-card";
import { Badge, Button, Card, CardHeader, DemoBadge, Notice, PageTitle, inputClass } from "@/components/ui";
import { api, useApi } from "@/lib/api";
import { dateTime, day, dec, money } from "@/lib/format";
import type { Analysis } from "@/lib/types";

const SUGGESTIONS = [
  "Quais campanhas estão com CAC acima do sustentável?",
  "Existe alguma campanha que vale a pena escalar?",
  "Há sinais de fadiga de criativos?",
  "O rastreamento de conversões está confiável?",
];

function AnalysisView({ a, clientId, currency }: { a: Analysis; clientId: number; currency: string }) {
  const s = a.summary;
  if (!s) return null;
  const f = s.finance;
  return (
    <div className="space-y-4">
      <Card className="p-5">
        <div className="mb-2 flex flex-wrap items-center gap-2">
          <Badge tone="blue">Borges Core</Badge>
          {a.is_demo && <DemoBadge />}
          <span className="text-xs text-muted">{dateTime(a.created_at)} · período {day(a.period_start)} a {day(a.period_end)}</span>
        </div>
        <p className="text-xs text-muted">Pergunta: “{a.question}”</p>
        <p className="mt-2 whitespace-pre-line text-sm leading-relaxed text-ink">{s.answer}</p>
        {s.ai?.used && (
          <p className="mt-2 text-xs text-muted">
            <Badge tone="cyan">Redigido por IA</Badge> {s.ai.model} · custo US$ {s.ai.cost_usd?.toFixed(4).replace(".", ",")} · números conferidos com os dados
          </p>
        )}
        {s.ai?.note && <div className="mt-3"><Notice tone="warn">{s.ai.note} Abaixo, a resposta das regras.</Notice></div>}
        {s.ai?.used && s.ai.rules_answer && (
          <details className="mt-2 text-xs text-muted">
            <summary className="cursor-pointer">Ver resposta das regras (sem IA)</summary>
            <p className="mt-1">{s.ai.rules_answer}</p>
          </details>
        )}
        {s.method && <p className="mt-2 text-xs text-muted">Método: {s.method} Agentes: {s.agents?.join(", ")}.</p>}
      </Card>

      {f && (
        <Card>
          <CardHeader title="Financial Intelligence — economia da conta" />
          <dl className="grid grid-cols-2 gap-4 p-5 text-sm md:grid-cols-5">
            <div><dt className="text-xs text-muted">CAC real</dt><dd className="font-semibold">{money(f.real_cac, currency)}</dd></div>
            <div><dt className="text-xs text-muted">Meta de CAC</dt><dd className="font-semibold">{money(f.target_cac, currency)}</dd></div>
            <div><dt className="text-xs text-muted">CAC máx. sustentável</dt><dd className="font-semibold">{money(f.max_sustainable_cac, currency)}</dd></div>
            <div><dt className="text-xs text-muted">ROAS conf. / equilíbrio</dt><dd className="font-semibold">{dec(f.confirmed_roas)}x / {dec(f.breakeven_roas)}x</dd></div>
            <div><dt className="text-xs text-muted">Lucro de contribuição</dt><dd className="font-semibold">{money(f.contribution_profit, currency)}</dd></div>
          </dl>
          <ul className="list-disc space-y-0.5 border-t border-line px-9 py-3 text-xs text-muted">{f.limitations.map((l) => <li key={l}>{l}</li>)}</ul>
        </Card>
      )}

      {s.data_quality.issues.length > 0 && <Notice tone="warn"><strong>Data Intelligence:</strong> {s.data_quality.issues.join(" ")}</Notice>}

      {a.recommendations.length > 0 && (
        <div className="space-y-3">
          <div className="flex items-center justify-between">
            <h2 className="text-sm font-semibold text-navy-900">Recomendações ({a.recommendations.length})</h2>
            <Link href="/aprovacoes" className="text-sm font-medium text-azure-600 hover:underline">Decidir na Central de aprovação →</Link>
          </div>
          {a.recommendations.map((r) => (
            <RecommendationCard key={r.id} rec={r} clientId={clientId} currency={currency} highlighted={s.matched_ids.includes(r.id)} />
          ))}
        </div>
      )}
    </div>
  );
}

export default function IntelligencePage() {
  const { client, canAnalyze } = useApp();
  const history = useApi<Analysis[]>(client ? `/clients/${client.id}/analyses` : null);
  const [question, setQuestion] = useState("");
  const [days, setDays] = useState(30);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [shownId, setShownId] = useState<number | null>(null);

  if (!client) return <NoClient />;
  const analyses = history.data ?? [];
  const shown = analyses.find((a) => a.id === shownId) ?? analyses[0];

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const a = await api<Analysis>(`/clients/${client!.id}/analyses`, { method: "POST", body: { question, days } });
      setShownId(a.id);
      setQuestion("");
      history.reload();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <PageTitle title="Central de inteligência" subtitle="Solicite uma análise ao Borges Core. Cada recomendação traz evidências, hipótese, riscos e métrica de validação." />
      <div className="grid gap-6 xl:grid-cols-[1fr_300px]">
        <div className="space-y-6">
          <Card className="p-5">
            <form onSubmit={submit} className="space-y-3">
              <Notice>
                O diagnóstico e as recomendações vêm sempre de regras auditáveis. Com a IA ativada em Configurações, o Borges Core
                também interpreta a pergunta e redige a resposta a partir desses dados; sem ela, a pergunta só destaca as
                recomendações do tema.
              </Notice>
              <textarea required minLength={3} maxLength={1000} rows={2} value={question} onChange={(e) => setQuestion(e.target.value)}
                disabled={!canAnalyze} placeholder="Ex.: Quais campanhas estão com CAC acima do sustentável?" aria-label="Pergunta ao Borges Core" className={inputClass} />
              <div className="flex flex-wrap gap-2">
                {SUGGESTIONS.map((s) => (
                  <button key={s} type="button" onClick={() => setQuestion(s)} className="rounded-full border border-line bg-canvas px-3 py-1 text-xs text-navy-800 hover:border-azure-500">{s}</button>
                ))}
              </div>
              {error && <Notice tone="error">{error}</Notice>}
              <div className="flex items-center gap-3">
                <select aria-label="Período da análise" value={days} onChange={(e) => setDays(Number(e.target.value))} className="rounded-lg border border-line bg-white px-3 py-2 text-sm">
                  <option value={14}>Últimos 14 dias</option><option value={30}>Últimos 30 dias</option><option value={60}>Últimos 60 dias</option>
                </select>
                <Button type="submit" disabled={busy || !canAnalyze}>{busy ? "Analisando…" : "Analisar"}</Button>
                {!canAnalyze && <span className="text-xs text-muted">Seu papel permite apenas leitura.</span>}
              </div>
            </form>
          </Card>
          {shown ? <AnalysisView a={shown} clientId={client.id} currency={client.currency} /> : !history.loading && (
            <Card className="p-10 text-center text-sm text-muted">Nenhuma análise ainda. Faça a primeira pergunta acima.</Card>
          )}
        </div>
        <Card className="h-fit">
          <CardHeader title="Análises anteriores" />
          {analyses.length === 0 ? <p className="px-5 py-6 text-sm text-muted">Sem histórico.</p> : (
            <ul className="divide-y divide-line">
              {analyses.map((a) => (
                <li key={a.id}>
                  <button onClick={() => setShownId(a.id)} className={`block w-full px-5 py-3 text-left hover:bg-azure-50 ${shown?.id === a.id ? "bg-azure-50" : ""}`}>
                    <p className="line-clamp-2 text-sm text-navy-900">{a.question}</p>
                    <p className="mt-0.5 text-xs text-muted">{dateTime(a.created_at)} · {a.recommendations.length} recomendações</p>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </Card>
      </div>
    </>
  );
}
