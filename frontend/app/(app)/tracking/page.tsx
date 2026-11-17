"use client";

import { useState } from "react";
import { useApp } from "@/components/app-context";
import { NoClient } from "@/components/no-client";
import { Badge, Button, Card, CardHeader, Field, Notice, PageTitle, inputClass } from "@/components/ui";
import { api, useApi } from "@/lib/api";
import { dateTime } from "@/lib/format";

interface CheckItem { key: string; label: string; ok: boolean | null; detail: string; severity: string }
interface CheckResult { url: string; final_url: string; status: number; seconds: number; title: string | null; items: CheckItem[]; problems: number; notes: string[] }
interface Tracking {
  findings: { severity: string; area: string; title: string; detail: string }[];
  utm: { meta_url_parameters: string; google_tracking_template: string; notes: string[];
    campaigns: { campaign_id: number; name: string; platform: string; external_id: string; utm_campaign: string; example: string }[] };
  page_checks: { id: number; url: string; created_at: string; result: CheckResult }[];
}

function CheckView({ r }: { r: CheckResult }) {
  return (
    <div className="space-y-2 text-sm">
      <p className="text-xs text-muted">{r.final_url} · HTTP {r.status} · {r.title ?? "sem título"}</p>
      <ul className="divide-y divide-line rounded-lg border border-line">
        {r.items.map((i) => (
          <li key={i.key} className="flex items-start justify-between gap-3 px-3 py-2">
            <span>{i.label}<span className="block text-xs text-muted">{i.detail}</span></span>
            <Badge tone={i.ok === true ? "green" : i.ok === null ? "amber" : "red"}>{i.ok === true ? "OK" : i.ok === null ? "Possível via GTM" : "Problema"}</Badge>
          </li>
        ))}
      </ul>
      <ul className="list-disc pl-5 text-xs text-muted">{r.notes.map((n) => <li key={n}>{n}</li>)}</ul>
    </div>
  );
}

export default function TrackingPage() {
  const { client, canAnalyze } = useApp();
  const data = useApi<Tracking>(client ? `/clients/${client.id}/tracking?days=30` : null);
  const [url, setUrl] = useState("");
  const [result, setResult] = useState<CheckResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState<string | null>(null);
  if (!client) return <NoClient />;
  const t = data.data;

  async function run(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true); setError(null);
    try { setResult(await api<CheckResult>(`/clients/${client!.id}/tracking/page-check`, { method: "POST", body: { url } })); data.reload(); }
    catch (err) { setError((err as Error).message); } finally { setBusy(false); }
  }
  async function copy(text: string) {
    try { await navigator.clipboard.writeText(text); setCopied(text); } catch { setCopied(null); }
  }

  return (
    <>
      <PageTitle title="Tracking & CRO" subtitle="Onde a mensuração falha: atribuição, CRM, UTMs e páginas de destino." />
      <Card className="mb-6">
        <CardHeader title="Pontos de atenção" hint="Cruzamento de plataformas, vendas confirmadas, CRM e verificações de página (últimos 30 dias)." />
        {t && t.findings.length === 0 && <p className="p-5 text-sm text-muted">Nenhum problema de mensuração encontrado nos dados disponíveis.</p>}
        <ul className="divide-y divide-line">
          {t?.findings.map((f, i) => (
            <li key={i} className="px-5 py-3 text-sm">
              <div className="flex flex-wrap items-center gap-2"><Badge tone={f.severity === "alta" ? "red" : "amber"}>{f.severity === "alta" ? "Alta" : "Média"}</Badge><Badge>{f.area}</Badge><span className="font-medium text-navy-900">{f.title}</span></div>
              <p className="mt-1 text-muted">{f.detail}</p>
            </li>
          ))}
        </ul>
      </Card>
      <div className="grid grid-cols-1 gap-6 xl:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
        <Card>
          <CardHeader title="Verificar página de destino" hint="Pixel da Meta, GTM, GA4, tag do Google Ads, versão para celular, velocidade e caminho de conversão." />
          <div className="space-y-3 p-5">
            {error && <Notice tone="error">{error}</Notice>}
            <form onSubmit={run} className="flex flex-wrap items-end gap-2">
              <div className="min-w-0 flex-1 basis-56"><Field label="Endereço da página"><input required type="url" value={url} onChange={(e) => setUrl(e.target.value)} placeholder="https://" className={inputClass} /></Field></div>
              <Button type="submit" disabled={busy || !canAnalyze}>{busy ? "Verificando…" : "Verificar"}</Button>
            </form>
            {result && <CheckView r={result} />}
            {!result && (t?.page_checks.length ?? 0) > 0 && (
              <div><p className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted">Últimas verificações</p>
                <ul className="divide-y divide-line rounded-lg border border-line text-sm">
                  {t!.page_checks.map((c) => (
                    <li key={c.id} className="flex items-center justify-between gap-2 px-3 py-2">
                      <button type="button" className="truncate text-left text-azure-700 hover:underline" onClick={() => setResult(c.result)}>{c.url}</button>
                      <span className="shrink-0 text-xs text-muted">{c.result.problems} problema(s) · {dateTime(c.created_at)}</span>
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        </Card>
        <Card>
          <CardHeader title="UTMs padronizadas" hint="Com elas, cada venda importada do CRM é ligada à campanha certa." />
          {t && (
            <div className="space-y-3 p-5 text-sm">
              {([["Meta: parâmetros de URL do anúncio", t.utm.meta_url_parameters], ["Google Ads: modelo de acompanhamento", t.utm.google_tracking_template]] as const).map(([label, value]) => (
                <div key={label}>
                  <p className="text-xs font-medium text-navy-800">{label}</p>
                  <div className="mt-1 flex min-w-0 gap-2"><code className="block min-w-0 flex-1 overflow-x-auto rounded bg-canvas px-2 py-1.5 text-xs">{value}</code>
                    <Button variant="secondary" onClick={() => copy(value)}>{copied === value ? "Copiado" : "Copiar"}</Button></div>
                </div>
              ))}
              <div className="overflow-x-auto rounded-lg border border-line">
                <table className="w-full min-w-[420px] text-xs">
                  <thead className="bg-canvas text-left text-muted"><tr><th className="px-3 py-2 font-medium">Campanha</th><th className="px-3 py-2 font-medium">utm_campaign</th></tr></thead>
                  <tbody>{t.utm.campaigns.map((c) => <tr key={c.campaign_id} className="border-t border-line"><td className="px-3 py-2">{c.name}</td><td className="px-3 py-2 font-mono">{c.utm_campaign}</td></tr>)}</tbody>
                </table>
              </div>
              <ul className="list-disc pl-5 text-xs text-muted">{t.utm.notes.map((n) => <li key={n}>{n}</li>)}</ul>
            </div>
          )}
        </Card>
      </div>
    </>
  );
}
