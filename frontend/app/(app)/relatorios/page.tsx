"use client";

import { useState } from "react";
import { useApp } from "@/components/app-context";
import { NoClient } from "@/components/no-client";
import { ReportContent, ReportView } from "@/components/report-view";
import { Badge, Button, Card, CardHeader, Loading, Notice, PageTitle } from "@/components/ui";
import { api, useApi } from "@/lib/api";
import { dateTime, day } from "@/lib/format";

interface ReportMeta { id: number; kind: string; label: string | null; period_start: string; period_end: string; is_demo: boolean; created_by: string; created_at: string }
interface ReportFull extends ReportMeta { content: ReportContent }

const KINDS = [{ kind: "daily", label: "Diário" }, { kind: "weekly", label: "Semanal" }, { kind: "monthly", label: "Mensal" }];

export default function RelatoriosPage() {
  const { client, canAnalyze } = useApp();
  const list = useApi<ReportMeta[]>(client ? `/clients/${client.id}/reports` : null);
  const [selected, setSelected] = useState<number | null>(null);
  const current = selected ?? list.data?.[0]?.id ?? null;
  const report = useApi<ReportFull>(client && current ? `/clients/${client.id}/reports/${current}` : null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  if (!client) return <NoClient />;

  async function generate(kind: string) {
    setBusy(true); setError(null);
    try {
      const r = await api<ReportFull>(`/clients/${client!.id}/reports`, { method: "POST", body: { kind } });
      list.reload(); setSelected(r.id);
    } catch (e) { setError((e as Error).message); } finally { setBusy(false); }
  }

  return (
    <>
      <div className="print:hidden">
        <PageTitle title="Relatórios" subtitle="O que aconteceu, por que pode ter acontecido, o que foi feito e o que será testado — sempre com período e comparação."
          action={canAnalyze && <div className="flex flex-wrap gap-2">{KINDS.map((k) => <Button key={k.kind} variant="secondary" disabled={busy} onClick={() => generate(k.kind)}>Gerar {k.label.toLowerCase()}</Button>)}</div>} />
        <div className="mb-4"><Notice>
          Os relatórios também são gerados automaticamente pelas rotinas (veja Automações). Para salvar em PDF, abra o relatório e use
          “Exportar PDF” — o navegador abre a janela de impressão; escolha “Salvar como PDF”.
        </Notice></div>
        {error && <div className="mb-4"><Notice tone="error">{error}</Notice></div>}
      </div>
      <div className="grid grid-cols-1 gap-6 xl:grid-cols-[300px_minmax(0,1fr)]">
        <Card className="h-fit print:hidden">
          <CardHeader title="Histórico" />
          {list.loading ? <Loading /> : (list.data?.length ?? 0) === 0 ? <p className="p-5 text-sm text-muted">Nenhum relatório ainda.</p> : (
            <ul className="max-h-[70vh] divide-y divide-line overflow-y-auto">
              {list.data!.map((r) => (
                <li key={r.id}>
                  <button onClick={() => setSelected(r.id)} className={`w-full px-5 py-2.5 text-left text-sm ${r.id === current ? "bg-azure-50" : "hover:bg-slate-50"}`}>
                    <span className="font-medium text-navy-900">{r.label ?? r.kind}</span>
                    <span className="block text-xs text-muted">{day(r.period_start)}{r.period_end !== r.period_start && <> a {day(r.period_end)}</>} · {dateTime(r.created_at)}</span>
                    <span className="text-xs text-muted">{r.created_by}</span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </Card>
        <div className="min-w-0">
          {report.loading && <Loading />}
          {report.error && <Notice tone="error">{report.error}</Notice>}
          {report.data && (
            <>
              <div className="mb-3 flex flex-wrap items-center justify-between gap-2 print:hidden">
                <Badge>Gerado por {report.data.created_by} em {dateTime(report.data.created_at)}</Badge>
                <Button onClick={() => window.print()}>Exportar PDF</Button>
              </div>
              <ReportView c={report.data.content} />
            </>
          )}
        </div>
      </div>
    </>
  );
}
