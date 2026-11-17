"use client";

import { useState } from "react";
import { useApp } from "@/components/app-context";
import { Badge, Button, Card, Loading, Notice, PageTitle } from "@/components/ui";
import { api, useApi } from "@/lib/api";
import { dateTime } from "@/lib/format";
import type { AuditEntry } from "@/lib/types";

const ACTION: Record<string, string> = {
  "auth.login": "Login", "auth.login_failed": "Tentativa de login recusada", "client.created": "Cliente criado",
  "client.updated": "Cliente atualizado", "analysis.completed": "Análise concluída", "user.created": "Usuário criado",
  "recommendation.approved": "Recomendação aprovada", "recommendation.rejected": "Recomendação rejeitada",
  "recommendation.adjustment_requested": "Ajuste solicitado", "execution.completed": "Execução concluída e verificada",
  "execution.failed": "Execução bloqueada / falhou", "routine.completed": "Rotina concluída",
  "routine.failed": "Rotina falhou", "routine.updated": "Rotina alterada", "report.generated": "Relatório gerado",
  "alert.acknowledged": "Alerta reconhecido", "alert.resolved": "Alerta resolvido",
  "learning.created": "Aprendizado registrado", "learning.validated": "Aprendizado validado",
  "learning.refuted": "Aprendizado refutado",
};

export default function AuditPage() {
  const { client, user } = useApp();
  const [scope, setScope] = useState<"client" | "all">("client");
  const path = scope === "client" && client ? `/audit?client_id=${client.id}&limit=200` : "/audit?limit=200";
  const { data, error, loading } = useApi<AuditEntry[]>(path);
  const [chain, setChain] = useState<{ valid: boolean; entries: number; broken_at_id: number | null } | null>(null);

  return (
    <>
      <PageTitle title="Auditoria" subtitle="Registro somente-inserção de operações, decisões e execuções, encadeado por hash."
        action={
          <div className="flex items-center gap-2">
            <select aria-label="Escopo" value={scope} onChange={(e) => setScope(e.target.value as "client" | "all")} className="rounded-lg border border-line bg-white px-3 py-2 text-sm">
              <option value="client">Cliente selecionado</option>
              <option value="all">{user.role === "admin" ? "Todo o sistema" : "Todos os meus clientes"}</option>
            </select>
            {user.role === "admin" && <Button variant="secondary" onClick={async () => setChain(await api("/audit/verify"))}>Verificar integridade</Button>}
          </div>
        } />
      {chain && (
        <div className="mb-4">
          <Notice tone={chain.valid ? "info" : "error"}>
            {chain.valid ? `Cadeia íntegra: ${chain.entries} registro(s) verificados.` : `Cadeia violada no registro #${chain.broken_at_id}. Registros anteriores íntegros: ${chain.entries}.`}
          </Notice>
        </div>
      )}
      {error && <Notice tone="error">{error}</Notice>}
      {loading && <Loading />}
      {data && (
        <Card>
          {data.length === 0 ? <p className="p-10 text-center text-sm text-muted">Nenhum registro.</p> : (
            <div className="overflow-x-auto">
              <table className="w-full min-w-[820px] text-sm">
                <thead className="border-b border-line bg-canvas text-left text-xs text-muted">
                  <tr>{["#", "Quando", "Quem", "Operação", "Detalhes", "Hash"].map((h) => <th key={h} className="px-4 py-3 font-medium">{h}</th>)}</tr>
                </thead>
                <tbody>
                  {data.map((e) => (
                    <tr key={e.id} className="border-b border-line align-top last:border-0">
                      <td className="px-4 py-3 text-muted">{e.id}</td>
                      <td className="whitespace-nowrap px-4 py-3">{dateTime(e.ts)}</td>
                      <td className="px-4 py-3">{e.actor}</td>
                      <td className="px-4 py-3">
                        <Badge tone={e.action.includes("failed") || e.action.includes("rejected") ? "red" : e.action.startsWith("execution") ? "green" : "neutral"}>{ACTION[e.action] ?? e.action}</Badge>
                        {e.entity_type && <span className="mt-1 block text-xs text-muted">{e.entity_type} #{e.entity_id}</span>}
                      </td>
                      <td className="max-w-md px-4 py-3"><code className="block max-h-24 overflow-auto whitespace-pre-wrap break-words text-xs text-muted">{JSON.stringify(e.details)}</code></td>
                      <td className="px-4 py-3 font-mono text-xs text-muted" title={e.hash}>{e.hash.slice(0, 10)}…</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Card>
      )}
    </>
  );
}
