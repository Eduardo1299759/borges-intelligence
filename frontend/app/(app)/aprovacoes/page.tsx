"use client";

import { useState } from "react";
import { useApp } from "@/components/app-context";
import { NoClient } from "@/components/no-client";
import { RecommendationCard } from "@/components/recommendation-card";
import { Card, Loading, Notice, PageTitle } from "@/components/ui";
import { useApi } from "@/lib/api";
import type { Recommendation } from "@/lib/types";

export default function ApprovalsPage() {
  const { client, canManage } = useApp();
  const [tab, setTab] = useState<"pending" | "history">("pending");
  const base = client ? `/clients/${client.id}/recommendations` : null;
  const pending = useApi<Recommendation[]>(base && `${base}?scope=pending`);
  const history = useApi<Recommendation[]>(base && `${base}?scope=history`);
  if (!client) return <NoClient />;
  const current = tab === "pending" ? pending : history;
  const reload = () => { pending.reload(); history.reload(); };

  return (
    <>
      <PageTitle title="Central de aprovação" subtitle={`Nível de operação ${client.operation_level} · limite de variação de orçamento ${Number(client.max_budget_change_pct)}%`} />
      {client.operation_level === 1 && <div className="mb-4"><Notice>Cliente em nível consultivo: aprovações são registradas, mas nada é executado.</Notice></div>}
      {!canManage && <div className="mb-4"><Notice>Seu papel permite visualizar, mas não decidir.</Notice></div>}
      <div role="tablist" className="mb-4 inline-flex rounded-lg border border-line bg-white p-1 text-sm">
        {([["pending", `Pendentes (${pending.data?.length ?? 0})`], ["history", `Histórico (${history.data?.length ?? 0})`]] as const).map(([key, label]) => (
          <button key={key} role="tab" aria-selected={tab === key} onClick={() => setTab(key)}
            className={`rounded-md px-4 py-1.5 ${tab === key ? "bg-azure-600 font-medium text-white" : "text-muted hover:text-navy-900"}`}>{label}</button>
        ))}
      </div>
      {current.error && <Notice tone="error">{current.error}</Notice>}
      {current.loading && <Loading />}
      {current.data?.length === 0 && (
        <Card className="p-10 text-center text-sm text-muted">
          {tab === "pending" ? "Nenhuma recomendação aguardando decisão." : "Nenhuma decisão registrada ainda."}
        </Card>
      )}
      <div className="space-y-3">
        {current.data?.map((r) => (
          <RecommendationCard key={`${r.id}-${r.status}`} rec={r} clientId={client.id} currency={client.currency} canDecide={canManage} defaultOpen={tab === "pending"} onChanged={reload} />
        ))}
      </div>
    </>
  );
}
