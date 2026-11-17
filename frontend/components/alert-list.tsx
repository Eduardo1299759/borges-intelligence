"use client";

import { Badge } from "@/components/ui";
import { dateTime } from "@/lib/format";

export interface AlertItem { id: number; kind: string; severity: string; title: string; detail: string; status: string; is_demo: boolean; created_at: string }

export function AlertList({ alerts, canAct, onChange }: { alerts: AlertItem[]; canAct: boolean; onChange: (id: number, status: string) => void }) {
  if (alerts.length === 0) return <p className="p-5 text-sm text-muted">Nenhum alerta aberto.</p>;
  return (
    <ul className="divide-y divide-line">
      {alerts.map((a) => (
        <li key={a.id} className="px-5 py-3 text-sm">
          <div className="flex flex-wrap items-center gap-1.5">
            <Badge tone={a.severity === "alta" ? "red" : a.severity === "media" ? "amber" : "neutral"}>{a.severity === "media" ? "média" : a.severity}</Badge>
            {a.status === "acknowledged" && <Badge tone="blue">Ciente</Badge>}
            <span className="font-medium text-navy-900">{a.title}</span>
          </div>
          <p className="mt-1 text-muted">{a.detail}</p>
          <div className="mt-1 flex flex-wrap items-center gap-3 text-xs text-muted">
            <span>{dateTime(a.created_at)}{a.is_demo && " · demonstração"}</span>
            {canAct && a.status === "open" && <button className="text-azure-600 hover:underline" onClick={() => onChange(a.id, "acknowledged")}>Estou ciente</button>}
            {canAct && <button className="text-azure-600 hover:underline" onClick={() => onChange(a.id, "resolved")}>Resolver</button>}
          </div>
        </li>
      ))}
    </ul>
  );
}
