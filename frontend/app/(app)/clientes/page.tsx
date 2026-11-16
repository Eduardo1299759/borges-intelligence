"use client";

import { useState } from "react";
import { useApp } from "@/components/app-context";
import { Badge, Button, Card, CardHeader, DemoBadge, Field, Notice, PageTitle, inputClass } from "@/components/ui";
import { api } from "@/lib/api";
import { dec, money } from "@/lib/format";
import type { Client } from "@/lib/types";

const EMPTY = { name: "", segment: "", business_goal: "", timezone: "America/Sao_Paulo", currency: "BRL", data_mode: "demo",
  monthly_budget: "", target_cac: "", target_roas: "", gross_margin_pct: "", operation_level: "2", max_budget_change_pct: "30" };
type Form = typeof EMPTY;

function toForm(c: Client): Form {
  return { name: c.name, segment: c.segment ?? "", business_goal: c.business_goal ?? "", timezone: c.timezone, currency: c.currency,
    data_mode: c.data_mode, monthly_budget: c.monthly_budget ?? "", target_cac: c.target_cac ?? "", target_roas: c.target_roas ?? "",
    gross_margin_pct: c.gross_margin_pct ?? "", operation_level: String(c.operation_level), max_budget_change_pct: c.max_budget_change_pct };
}

export default function ClientsPage() {
  const { clients, client: selected, selectClient, reloadClients, canManage } = useApp();
  const [editing, setEditing] = useState<Client | "new" | null>(null);
  const [form, setForm] = useState<Form>(EMPTY);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  function open(target: Client | "new") {
    setEditing(target);
    setForm(target === "new" ? EMPTY : toForm(target));
    setError(null);
  }
  const set = (key: keyof Form) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement>) =>
    setForm((f) => ({ ...f, [key]: e.target.value }));

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    const orNull = (v: string) => (v.trim() === "" ? null : v.trim());
    const body = {
      name: form.name.trim(), segment: orNull(form.segment), business_goal: orNull(form.business_goal), timezone: form.timezone,
      currency: form.currency, monthly_budget: orNull(form.monthly_budget), target_cac: orNull(form.target_cac),
      target_roas: orNull(form.target_roas), gross_margin_pct: orNull(form.gross_margin_pct),
      operation_level: Number(form.operation_level), max_budget_change_pct: form.max_budget_change_pct || "0",
    };
    try {
      if (editing === "new") {
        const created = await api<Client>("/clients", { method: "POST", body: { ...body, data_mode: form.data_mode } });
        selectClient(created.id);
      } else if (editing) {
        await api(`/clients/${editing.id}`, { method: "PUT", body });
      }
      await reloadClients();
      setEditing(null);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <PageTitle title="Clientes e contas" subtitle="Objetivos, metas, margens e nível de operação de cada cliente."
        action={canManage && <Button onClick={() => open("new")}>Novo cliente</Button>} />

      {editing && (
        <Card className="mb-6">
          <CardHeader title={editing === "new" ? "Novo cliente" : `Editar ${editing.name}`} />
          <form onSubmit={submit} className="grid gap-4 p-5 md:grid-cols-2 xl:grid-cols-3">
            {error && <div className="md:col-span-2 xl:col-span-3"><Notice tone="error">{error}</Notice></div>}
            <Field label="Nome"><input required minLength={2} value={form.name} onChange={set("name")} className={inputClass} /></Field>
            <Field label="Segmento"><input value={form.segment} onChange={set("segment")} placeholder="Ex.: Restaurante / delivery" className={inputClass} /></Field>
            <Field label="Fonte de dados" hint={editing === "new" ? "Demonstração gera 90 dias de dados sinalizados. Real fica sem dados até a Fase 2." : "Definida na criação."}>
              <select value={form.data_mode} onChange={set("data_mode")} disabled={editing !== "new"} className={inputClass}>
                <option value="demo">Demonstração (dados simulados)</option>
                <option value="live">Real (aguarda integrações)</option>
              </select>
            </Field>
            <div className="md:col-span-2 xl:col-span-3">
              <Field label="Objetivo comercial"><textarea rows={2} value={form.business_goal} onChange={set("business_goal")} className={inputClass} /></Field>
            </div>
            <Field label="Orçamento mensal de mídia"><input type="number" min="0" step="0.01" value={form.monthly_budget} onChange={set("monthly_budget")} className={inputClass} /></Field>
            <Field label="Meta de CAC" hint="Custo máximo desejado por cliente confirmado."><input type="number" min="0.01" step="0.01" value={form.target_cac} onChange={set("target_cac")} className={inputClass} /></Field>
            <Field label="Meta de ROAS"><input type="number" min="0.01" step="0.01" value={form.target_roas} onChange={set("target_roas")} className={inputClass} /></Field>
            <Field label="Margem de contribuição (%)" hint="Sem margem, lucro e ROAS de equilíbrio não são calculados."><input type="number" min="0.01" max="100" step="0.01" value={form.gross_margin_pct} onChange={set("gross_margin_pct")} className={inputClass} /></Field>
            <Field label="Nível de operação" hint="Nível 3 (autônomo limitado) chega com a execução real, na Fase 5.">
              <select value={form.operation_level} onChange={set("operation_level")} className={inputClass}>
                <option value="1">1 — Consultivo (só recomenda)</option>
                <option value="2">2 — Supervisionado (executa após aprovação)</option>
              </select>
            </Field>
            <Field label="Limite de variação de orçamento (%)" hint="Nenhuma execução altera o orçamento além deste limite."><input type="number" min="0" max="100" step="1" value={form.max_budget_change_pct} onChange={set("max_budget_change_pct")} className={inputClass} /></Field>
            <Field label="Fuso horário"><input required value={form.timezone} onChange={set("timezone")} className={inputClass} /></Field>
            <Field label="Moeda"><input required pattern="[A-Z]{3}" value={form.currency} onChange={set("currency")} className={inputClass} /></Field>
            <div className="flex items-end gap-2 md:col-span-2 xl:col-span-3">
              <Button type="submit" disabled={busy}>{busy ? "Salvando…" : "Salvar"}</Button>
              <Button type="button" variant="secondary" onClick={() => setEditing(null)}>Cancelar</Button>
            </div>
          </form>
        </Card>
      )}

      <Card>
        {clients.length === 0 ? (
          <p className="p-10 text-center text-sm text-muted">Nenhum cliente cadastrado.</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[820px] text-sm">
              <thead className="border-b border-line bg-canvas text-left text-xs text-muted">
                <tr>{["Cliente", "Dados", "Meta CAC", "Meta ROAS", "Margem", "Operação", ""].map((h) => <th key={h} className="px-5 py-3 font-medium">{h}</th>)}</tr>
              </thead>
              <tbody>
                {clients.map((c) => (
                  <tr key={c.id} className="border-b border-line last:border-0">
                    <td className="px-5 py-3">
                      <p className="font-medium text-navy-900">{c.name}</p>
                      <p className="text-xs text-muted">{c.segment ?? "Segmento não informado"}</p>
                    </td>
                    <td className="px-5 py-3">{c.data_mode === "demo" ? <DemoBadge /> : <Badge tone="amber">Real · sem integração</Badge>}</td>
                    <td className="px-5 py-3">{money(c.target_cac, c.currency)}</td>
                    <td className="px-5 py-3">{c.target_roas ? `${dec(c.target_roas)}x` : "—"}</td>
                    <td className="px-5 py-3">{c.gross_margin_pct ? `${dec(c.gross_margin_pct, 0)}%` : "—"}</td>
                    <td className="px-5 py-3">Nível {c.operation_level} · limite {dec(c.max_budget_change_pct, 0)}%</td>
                    <td className="px-5 py-3 text-right">
                      <div className="flex justify-end gap-2">
                        {selected?.id === c.id ? <Badge tone="blue">Selecionado</Badge> : <Button variant="secondary" onClick={() => selectClient(c.id)}>Selecionar</Button>}
                        {canManage && <Button variant="secondary" onClick={() => open(c)}>Editar</Button>}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </>
  );
}
