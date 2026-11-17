"use client";

import { useState } from "react";
import { api, useApi } from "@/lib/api";
import { dateTime } from "@/lib/format";
import type { AISettings, AIUsageRow } from "@/lib/types";
import { Badge, Button, Card, CardHeader, Field, Notice, inputClass } from "./ui";

const USD = (v: number) => `US$ ${v.toFixed(2).replace(".", ",")}`;
const STATUS: Record<string, [string, "green" | "red" | "amber" | "neutral"]> = {
  ok: ["Usada", "green"], refused: ["Recusada pelo modelo", "amber"], error: ["Erro", "red"],
  blocked_budget: ["Bloqueada pelo limite", "amber"], rejected_validation: ["Descartada (números)", "amber"],
};

function AIForm({ s, onSaved }: { s: AISettings; onSaved: () => void }) {
  // Estado inicial vem da configuração salva; o componente é recriado (key) quando ela muda.
  const [form, setForm] = useState({ enabled: s.enabled, model: s.model, effort: s.effort, cap: String(s.monthly_cap_usd), key: "" });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState<string | null>(null);
  const model = s.models.find((m) => m.id === form.model);

  async function save(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true); setError(null); setDone(null);
    try {
      await api("/ai/settings", { method: "PUT", body: {
        enabled: form.enabled, model: form.model, effort: form.effort, monthly_cap_usd: form.cap || "0", api_key: form.key || null,
      } });
      setDone("Configuração da IA salva.");
      onSaved();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
          <form onSubmit={save} className="space-y-4">
            {error && <Notice tone="error">{error}</Notice>}
            {done && <Notice>{done}</Notice>}
            <label className="flex items-center gap-2 text-sm font-medium text-navy-900">
              <input type="checkbox" checked={form.enabled} onChange={(e) => setForm({ ...form, enabled: e.target.checked })} />
              Usar IA nas análises
            </label>
            <Field label={s.configured ? `Chave de API da Anthropic (atual termina em …${s.key_hint}; deixe em branco para manter)` : "Chave de API da Anthropic"}
              hint="Criada em console.anthropic.com. É cifrada antes de ser gravada e nunca é exibida de novo.">
              <input type="password" autoComplete="off" value={form.key} onChange={(e) => setForm({ ...form, key: e.target.value })} className={inputClass} />
            </Field>
            <div className="grid gap-4 sm:grid-cols-3">
              <Field label="Modelo" hint={model ? `US$ ${model.input_per_mtok} / ${model.output_per_mtok} por milhão de tokens (entrada / saída)` : undefined}>
                <select value={form.model} onChange={(e) => setForm({ ...form, model: e.target.value })} className={inputClass}>
                  {s.models.map((m) => <option key={m.id} value={m.id}>{m.label}</option>)}
                </select>
              </Field>
              <Field label="Esforço" hint="Mais esforço: respostas mais cuidadosas, mais caras.">
                <select value={form.effort} onChange={(e) => setForm({ ...form, effort: e.target.value as AISettings["effort"] })} className={inputClass}>
                  <option value="low">Baixo</option><option value="medium">Médio</option><option value="high">Alto</option>
                </select>
              </Field>
              <Field label="Limite mensal (US$)" hint="Antes de cada chamada, o pior custo possível é conferido contra este limite.">
                <input type="number" min="0" step="1" value={form.cap} onChange={(e) => setForm({ ...form, cap: e.target.value })} className={inputClass} />
              </Field>
            </div>
            <p className="text-xs text-muted">
              Ao ativar, nome do cliente, nomes de campanhas e anúncios e métricas agregadas são enviados à Anthropic. Nenhum dado
              pessoal de leads é enviado. Os números da resposta são conferidos com os dados; se a IA citar um número que não está
              neles, a resposta é descartada.
            </p>
            <Button type="submit" disabled={busy}>{busy ? "Salvando…" : "Salvar"}</Button>
          </form>
  );
}

export function AICard({ isAdmin, canSeeUsage }: { isAdmin: boolean; canSeeUsage: boolean }) {
  const settings = useApi<AISettings>("/ai/settings");
  const usage = useApi<AIUsageRow[]>(canSeeUsage ? "/ai/usage" : null);
  const s = settings.data;
  const pctUsed = s && s.monthly_cap_usd > 0 ? Math.min(100, (s.month_spend_usd / s.monthly_cap_usd) * 100) : 0;

  return (
    <Card>
      <CardHeader title="IA (Anthropic)" hint="Interpreta a pergunta e redige a resposta do Borges Core a partir dos dados calculados"
        action={s && <Badge tone={s.enabled ? "green" : "neutral"}>{s.enabled ? "Ativada" : "Desativada"}</Badge>} />
      <div className="space-y-4 p-5">
        {s && (
          <div>
            <div className="flex justify-between text-sm">
              <span className="text-muted">Gasto neste mês</span>
              <span className="font-medium text-navy-900">{USD(s.month_spend_usd)} de {USD(s.monthly_cap_usd)}</span>
            </div>
            <div className="mt-1 h-2 rounded-full bg-canvas"><div className="h-2 rounded-full bg-azure-500" style={{ width: `${pctUsed}%` }} /></div>
          </div>
        )}
        {isAdmin ? (
          s && <AIForm key={`${s.enabled}-${s.model}-${s.effort}-${s.monthly_cap_usd}-${s.key_hint}`} s={s} onSaved={() => { settings.reload(); usage.reload(); }} />
        ) : (
          <p className="text-sm text-muted">Somente administradores alteram a configuração da IA.</p>
        )}
        {canSeeUsage && (usage.data?.length ?? 0) > 0 && (
          <div>
            <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted">Últimas chamadas</p>
            <div className="overflow-x-auto rounded-lg border border-line">
              <table className="w-full min-w-[560px] text-sm">
                <thead className="bg-canvas text-left text-xs text-muted">
                  <tr>{["Quando", "Resultado", "Modelo", "Tokens (entrada / saída)", "Custo"].map((h) => <th key={h} className="px-3 py-2 font-medium">{h}</th>)}</tr>
                </thead>
                <tbody>
                  {usage.data!.slice(0, 10).map((u) => (
                    <tr key={u.id} className="border-t border-line">
                      <td className="px-3 py-2">{dateTime(u.created_at)}</td>
                      <td className="px-3 py-2"><Badge tone={STATUS[u.status]?.[1] ?? "neutral"}>{STATUS[u.status]?.[0] ?? u.status}</Badge>
                        {u.detail && <span className="block text-xs text-muted">{u.detail}</span>}</td>
                      <td className="px-3 py-2 text-muted">{u.model}</td>
                      <td className="px-3 py-2">{u.input_tokens.toLocaleString("pt-BR")} / {u.output_tokens.toLocaleString("pt-BR")}</td>
                      <td className="px-3 py-2">US$ {u.cost_usd.toFixed(4).replace(".", ",")}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </div>
    </Card>
  );
}
