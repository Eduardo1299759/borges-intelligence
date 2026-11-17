"use client";

import Link from "next/link";
import { useApp } from "@/components/app-context";
import { IntegrationPanel } from "@/components/integration-panel";
import { Badge, Card, CardHeader, PageTitle } from "@/components/ui";
import { useApi } from "@/lib/api";
import type { Integration } from "@/lib/types";

const LEVELS = [
  { n: 1, name: "Consultivo", text: "Consulta dados e recomenda. Aprovações são registradas; nada é executado.", available: true },
  { n: 2, name: "Supervisionado", text: "Prepara alterações e executa somente após aprovação humana. Padrão.", available: true },
  { n: 3, name: "Autônomo limitado", text: "Executa ações pré-autorizadas dentro de limites. Disponível com a execução real (Fase 5).", available: false },
];

export default function SettingsPage() {
  const { client, canManage } = useApp();
  const integrations = useApi<Integration[]>("/integrations");
  return (
    <>
      <PageTitle title="Configurações" subtitle="Integrações, limites de execução e custos." />
      {client && <div className="mb-6"><IntegrationPanel key={client.id} client={client} canManage={canManage} /></div>}
      <div className="grid gap-6 xl:grid-cols-2">
        <Card>
          <CardHeader title="Catálogo de integrações" hint="O que existe na plataforma. A conexão de cada cliente fica no painel acima." />
          <ul className="divide-y divide-line">
            {(integrations.data ?? []).map((i) => (
              <li key={i.key} className="flex items-start justify-between gap-4 px-5 py-3">
                <div>
                  <p className="text-sm font-medium text-navy-900">{i.name} <span className="font-normal text-muted">· {i.kind}</span></p>
                  {i.note && <p className="text-xs text-muted">{i.note}</p>}
                </div>
                {i.status === "available" ? <Badge tone="green">Disponível</Badge> : <Badge>Planejada · Fase {i.phase}</Badge>}
              </li>
            ))}
          </ul>
          <p className="border-t border-line px-5 py-3 text-xs text-muted">Credenciais são cifradas em repouso com uma chave que fica fora do banco (BORGES_ENCRYPTION_KEY) e nunca retornam pela API.</p>
        </Card>
        <div className="space-y-6">
          <Card>
            <CardHeader title="Níveis de operação" hint={client ? `${client.name}: nível ${client.operation_level}, limite de ${Number(client.max_budget_change_pct)}% por alteração de orçamento` : undefined}
              action={<Link href="/clientes" className="text-xs font-medium text-azure-600 hover:underline">Editar no cliente</Link>} />
            <ul className="divide-y divide-line">
              {LEVELS.map((l) => (
                <li key={l.n} className="flex items-start justify-between gap-4 px-5 py-3">
                  <div>
                    <p className="text-sm font-medium text-navy-900">Nível {l.n} — {l.name}</p>
                    <p className="text-xs text-muted">{l.text}</p>
                  </div>
                  {client?.operation_level === l.n ? <Badge tone="blue">Em uso</Badge> : !l.available ? <Badge>Fase 5</Badge> : null}
                </li>
              ))}
            </ul>
          </Card>
          <Card>
            <CardHeader title="Custos de uso de IA" />
            <p className="px-5 py-4 text-sm text-muted">Nenhum. Esta versão não chama modelos de linguagem nem serviços pagos: o Borges Core opera com regras determinísticas. O controle de custos entra junto com o provedor de LLM (Fase 3).</p>
          </Card>
          <Card>
            <CardHeader title="Automações" />
            <p className="px-5 py-4 text-sm text-muted">O agendador por cliente (rotinas diárias, semanais e a cada três dias) faz parte da Fase 6. Hoje sincronizações e análises são iniciadas manualmente.</p>
          </Card>
        </div>
      </div>
    </>
  );
}
