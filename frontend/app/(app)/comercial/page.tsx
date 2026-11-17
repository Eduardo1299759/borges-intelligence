"use client";

import { useState } from "react";
import { useApp } from "@/components/app-context";
import { NoClient } from "@/components/no-client";
import { Badge, Button, Card, CardHeader, Field, Notice, PageTitle, inputClass } from "@/components/ui";
import { api, useApi } from "@/lib/api";
import { dateTime, int, money, pct } from "@/lib/format";

interface Sales {
  has_crm_data: boolean; total_leads: number; notes: string[];
  funnel: { stage: string; label: string; count: number; rate_from_previous?: number | null }[];
  by_campaign: { campaign_id: number | null; campaign: string; platform_leads: number | null; crm_leads: number; qualified: number; sales: number; lost: number;
    qualified_rate: number | null; sale_rate: number | null; spend: number | null; cost_per_crm_lead: number | null; cost_per_sale: number | null; median_response_min: number | null }[];
  response: { answered: number; median_min: number | null; p75_min: number | null; within_5_min: number | null };
  lost_reasons: [string, number][];
}
interface ImportResult {
  committed: boolean; kind: string; rows_read: number; imported: number; skipped: Record<string, number>;
  unmatched_campaigns: [string, number][]; columns: Record<string, string>; ignored_personal_columns: string[];
  ignored_other_columns: string[]; totals: Record<string, unknown>;
}
interface ImportRow { id: number; kind: string; stats: ImportResult; created_at: string }

const FIELD_LABEL: Record<string, string> = {
  date: "data", value: "valor", campaign: "campanha", campaign_id: "ID da campanha", status: "status", order: "pedido",
  stage: "etapa", response: "tempo de resposta", lost_reason: "motivo de perda", lead_id: "ID",
};

function ImportCard({ clientId, isDemo, onDone }: { clientId: number; isDemo: boolean; onDone: () => void }) {
  const [kind, setKind] = useState<"orders" | "leads">("orders");
  const [text, setText] = useState("");
  const [fileName, setFileName] = useState("");
  const [preview, setPreview] = useState<ImportResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState<string | null>(null);

  async function send(commit: boolean) {
    setBusy(true); setError(null); setDone(null);
    try {
      const r = await api<ImportResult>(`/clients/${clientId}/imports`, { method: "POST", body: { kind, csv_text: text, commit } });
      if (commit) { setDone(`Importação concluída: ${r.imported} linha(s).`); setPreview(null); setText(""); setFileName(""); onDone(); }
      else setPreview(r);
    } catch (e) { setError((e as Error).message); } finally { setBusy(false); }
  }
  async function onFile(e: React.ChangeEvent<HTMLInputElement>) {
    const f = e.target.files?.[0];
    if (!f) return;
    setFileName(f.name); setPreview(null);
    setText(await f.text());
  }

  return (
    <Card>
      <CardHeader title="Importar do CRM ou sistema de pedidos" hint="Planilha CSV. Colunas com nome, telefone, e-mail ou documento são descartadas e nunca gravadas." />
      <div className="space-y-3 p-5 text-sm">
        {isDemo && <Notice>Cliente de demonstração: a prévia funciona, mas a importação só é gravada em clientes reais.</Notice>}
        {error && <Notice tone="error">{error}</Notice>}
        {done && <Notice>{done}</Notice>}
        <div className="grid gap-3">
          <Field label="Tipo">
            <select value={kind} onChange={(e) => { setKind(e.target.value as "orders" | "leads"); setPreview(null); }} className={inputClass}>
              <option value="orders">Pedidos / vendas</option><option value="leads">Leads (funil)</option>
            </select>
          </Field>
          <Field label="Arquivo CSV" hint={kind === "orders" ? "Colunas: data, valor e campanha (ou utm_campaign / ID da campanha); status e número do pedido opcionais." : "Colunas: data e etapa (ou status); campanha, tempo de resposta (min), motivo de perda e ID opcionais."}>
            <input type="file" accept=".csv,text/csv" onChange={onFile} className="block w-full max-w-full text-sm" aria-label="Arquivo CSV" />
          </Field>
        </div>
        {fileName && <p className="text-xs text-muted">Arquivo: {fileName}</p>}
        <Button variant="secondary" disabled={!text || busy} onClick={() => send(false)}>{busy ? "Lendo…" : "Pré-visualizar"}</Button>
        {preview && (
          <div className="space-y-2 rounded-lg border border-line p-4">
            <p><strong>{preview.imported}</strong> de {preview.rows_read} linha(s) prontas para importar.</p>
            <p className="text-xs text-muted">Colunas reconhecidas: {Object.entries(preview.columns).map(([k, v]) => `${v} → ${FIELD_LABEL[k] ?? k}`).join(", ")}</p>
            {preview.ignored_personal_columns.length > 0 && <p className="text-xs text-emerald-800">Descartadas por conterem dados pessoais: {preview.ignored_personal_columns.join(", ")}</p>}
            {Object.keys(preview.skipped).length > 0 && <p className="text-xs text-amber-800">Ignoradas: {Object.entries(preview.skipped).map(([k, v]) => `${k} (${v})`).join(", ")}</p>}
            {preview.unmatched_campaigns.length > 0 && <p className="text-xs text-amber-800">Sem campanha correspondente: {preview.unmatched_campaigns.map(([k, v]) => `${k} (${v})`).join(", ")}. Veja as UTMs sugeridas em Tracking & CRO.</p>}
            {kind === "orders" && <p className="text-xs text-muted">Total: {String(preview.totals.sales)} venda(s), {money(Number(preview.totals.revenue))}. A importação substitui os totais dos dias e campanhas do arquivo.</p>}
            <Button disabled={busy || isDemo || preview.imported === 0} onClick={() => send(true)}>Confirmar importação</Button>
          </div>
        )}
      </div>
    </Card>
  );
}

export default function CommercialPage() {
  const { client, canManage } = useApp();
  const sales = useApi<Sales>(client ? `/clients/${client.id}/sales?days=30` : null);
  const imports = useApi<ImportRow[]>(client ? `/clients/${client.id}/imports` : null);
  if (!client) return <NoClient />;
  const s = sales.data;
  const cur = client.currency;
  const top = s?.funnel[0]?.count || 0;

  return (
    <>
      <PageTitle title="Inteligência comercial" subtitle="Leads, funil, vendas confirmadas e qualidade por origem (últimos 30 dias)." />
      <div className="grid grid-cols-1 gap-6 xl:grid-cols-[minmax(0,1fr)_420px]">
        <div className="min-w-0 space-y-6">
          {s && !s.has_crm_data && <Notice tone="warn">Nenhum lead do CRM no período. Importe uma planilha de leads para ver o funil e o tempo de resposta.</Notice>}
          {s?.has_crm_data && (
            <div className="grid gap-6 lg:grid-cols-2">
              <Card>
                <CardHeader title={`Funil (${int(s.total_leads)} leads)`} hint="Por etapa alcançada; leads perdidos contam só na entrada." />
                <ul className="space-y-2 p-5 text-sm">
                  {s.funnel.map((f) => (
                    <li key={f.stage}>
                      <div className="flex justify-between"><span>{f.label}</span><span className="font-medium">{int(f.count)}{f.rate_from_previous != null && <span className="ml-2 text-xs text-muted">{pct(f.rate_from_previous)} da etapa anterior</span>}</span></div>
                      <div className="mt-1 h-2 rounded-full bg-canvas"><div className="h-2 rounded-full bg-azure-500" style={{ width: `${top ? (f.count / top) * 100 : 0}%` }} /></div>
                    </li>
                  ))}
                </ul>
              </Card>
              <Card>
                <CardHeader title="Atendimento" />
                <dl className="grid grid-cols-2 gap-4 p-5 text-sm">
                  <div><dt className="text-xs text-muted">Mediana da 1ª resposta</dt><dd className={`text-lg font-semibold ${s.response.median_min != null && s.response.median_min > 30 ? "text-amber-700" : ""}`}>{s.response.median_min == null ? "—" : `${int(s.response.median_min)} min`}</dd></div>
                  <div><dt className="text-xs text-muted">75% respondidos em até</dt><dd className="text-lg font-semibold">{s.response.p75_min == null ? "—" : `${int(s.response.p75_min)} min`}</dd></div>
                  <div><dt className="text-xs text-muted">Respondidos em até 5 min</dt><dd className="text-lg font-semibold">{pct(s.response.within_5_min)}</dd></div>
                  <div><dt className="text-xs text-muted">Leads com tempo registrado</dt><dd className="text-lg font-semibold">{int(s.response.answered)}</dd></div>
                </dl>
                {s.lost_reasons.length > 0 && (
                  <div className="border-t border-line px-5 py-3 text-sm"><p className="mb-1 text-xs font-semibold uppercase tracking-wide text-muted">Motivos de perda</p>
                    <ul>{s.lost_reasons.map(([r, n]) => <li key={r} className="flex justify-between"><span>{r}</span><span className="text-muted">{n}</span></li>)}</ul></div>
                )}
              </Card>
            </div>
          )}
          {s && s.by_campaign.length > 0 && (
            <Card>
              <CardHeader title="Qualidade por origem" hint="Leads da plataforma (atribuição dela) comparados aos leads registrados no CRM." />
              <div className="overflow-x-auto">
                <table className="w-full min-w-[900px] text-sm">
                  <thead className="border-b border-line bg-canvas text-xs text-muted"><tr>{["Campanha", "Leads plataforma", "Leads CRM", "Qualificados", "Vendas", "Lead → venda", "Investimento", "Custo por venda", "1ª resposta (mediana)"].map((h, i) => <th key={h} className={`px-4 py-3 font-medium ${i ? "text-right" : "text-left"}`}>{h}</th>)}</tr></thead>
                  <tbody>
                    {s.by_campaign.map((c) => (
                      <tr key={String(c.campaign_id)} className="border-b border-line last:border-0">
                        <td className="px-4 py-3 font-medium text-navy-900">{c.campaign}</td>
                        <td className="px-4 py-3 text-right">{int(c.platform_leads)}</td>
                        <td className="px-4 py-3 text-right">{c.platform_leads && c.crm_leads < c.platform_leads / 2 ? <Badge tone="amber">{int(c.crm_leads)}</Badge> : int(c.crm_leads)}</td>
                        <td className="px-4 py-3 text-right">{int(c.qualified)}</td>
                        <td className="px-4 py-3 text-right">{int(c.sales)}</td>
                        <td className="px-4 py-3 text-right">{pct(c.sale_rate)}</td>
                        <td className="px-4 py-3 text-right">{money(c.spend, cur)}</td>
                        <td className="px-4 py-3 text-right font-medium">{money(c.cost_per_sale, cur)}</td>
                        <td className="px-4 py-3 text-right">{c.median_response_min == null ? "—" : `${int(c.median_response_min)} min`}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <ul className="list-disc border-t border-line px-9 py-3 text-xs text-muted">{s.notes.map((n) => <li key={n}>{n}</li>)}</ul>
            </Card>
          )}
        </div>
        <div className="min-w-0 space-y-6">
          {canManage && <ImportCard clientId={client.id} isDemo={client.data_mode === "demo"} onDone={() => { sales.reload(); imports.reload(); }} />}
          <Card>
            <CardHeader title="Importações" />
            {(imports.data ?? []).length === 0 ? <p className="p-5 text-sm text-muted">Nenhuma importação.</p> : (
              <ul className="divide-y divide-line text-sm">
                {imports.data!.map((i) => (
                  <li key={i.id} className="px-5 py-2.5">
                    <Badge tone="blue">{i.kind === "orders" ? "Pedidos" : "Leads"}</Badge> <span className="ml-1">{i.stats.imported} linha(s)</span>
                    <span className="block text-xs text-muted">{dateTime(i.created_at)}{i.stats.unmatched_campaigns.length > 0 && ` · ${i.stats.unmatched_campaigns.length} campanha(s) sem correspondência`}</span>
                  </li>
                ))}
              </ul>
            )}
          </Card>
        </div>
      </div>
    </>
  );
}
