"use client";

import { useState } from "react";
import { api, useApi } from "@/lib/api";
import { dateTime, day, money } from "@/lib/format";
import type { AccountRef, Client, DiscoveredAccount, IntegrationInfo, SyncRun } from "@/lib/types";
import { Badge, Button, Card, CardHeader, Field, Notice, inputClass } from "./ui";

const STATUS = { connected: ["Conectada", "green"], error: ["Com erro", "red"], untested: ["Não testada", "neutral"] } as const;
const RUN = { completed: ["Concluída", "green"], failed: ["Falhou", "red"], running: ["Executando", "blue"] } as const;
const PLATFORM = { meta: "Meta Ads", google: "Google Ads" };
const refKey = (a: AccountRef) => `${a.platform}:${a.external_id}`;

export function IntegrationPanel({ client, canManage }: { client: Client; canManage: boolean }) {
  const info = useApi<IntegrationInfo>(`/clients/${client.id}/integration`);
  const runs = useApi<SyncRun[]>(`/clients/${client.id}/sync-runs`);
  const [apiKey, setApiKey] = useState("");
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [found, setFound] = useState<DiscoveredAccount[] | null>(null);
  const [picked, setPicked] = useState<Record<string, AccountRef>>({});
  const [days, setDays] = useState(30);
  const live = client.data_mode === "live";
  const i = info.data;

  async function act(name: string, fn: () => Promise<void>) {
    setBusy(name);
    setError(null);
    setMessage(null);
    try {
      await fn();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(null);
    }
  }

  const saveKey = (e: React.FormEvent) => {
    e.preventDefault();
    return act("key", async () => {
      const out = await api<IntegrationInfo>(`/clients/${client.id}/integration/windsor`, { method: "PUT", body: { api_key: apiKey } });
      setApiKey("");
      if (out.status === "connected") setMessage(out.check ?? "Conexão confirmada.");
      else setError(out.last_error ?? "A conexão falhou.");
      info.reload();
    });
  };
  const discover = () => act("discover", async () => {
    const list = await api<DiscoveredAccount[]>(`/clients/${client.id}/integration/windsor/accounts`);
    setFound(list);
    setPicked(Object.fromEntries((i?.accounts ?? []).map((a) => [refKey(a), a])));
  });
  const saveAccounts = () => act("accounts", async () => {
    await api(`/clients/${client.id}/integration/windsor/accounts`, { method: "PUT", body: { accounts: Object.values(picked) } });
    setFound(null);
    info.reload();
  });
  const sync = () => act("sync", async () => {
    const run = await api<SyncRun>(`/clients/${client.id}/sync`, { method: "POST", body: { days } });
    if (run.status === "completed") setMessage(`Sincronização concluída: ${run.stats?.metric_rows ?? 0} linhas de campanha e ${run.stats?.breakdown_rows ?? 0} de detalhamento.`);
    else setError(run.error ?? "A sincronização falhou.");
    info.reload();
    runs.reload();
  });
  const remove = () => act("remove", async () => {
    if (!window.confirm("Remover a credencial do Windsor.ai deste cliente? Os dados já sincronizados permanecem.")) return;
    await api(`/clients/${client.id}/integration/windsor`, { method: "DELETE" });
    setFound(null);
    info.reload();
  });
  const toggle = (a: DiscoveredAccount) => setPicked((p) => {
    const next = { ...p };
    if (next[refKey(a)]) delete next[refKey(a)];
    else next[refKey(a)] = { platform: a.platform, external_id: a.external_id, name: a.name };
    return next;
  });

  return (
    <Card>
      <CardHeader
        title={`Fonte de dados — ${client.name}`}
        hint={live ? "Windsor.ai (somente leitura): Meta Ads e Google Ads" : "Cliente de demonstração: os dados vêm do gerador interno"}
        action={live && i?.configured && i.status ? <Badge tone={STATUS[i.status][1]}>{STATUS[i.status][0]}</Badge> : undefined}
      />
      <div className="space-y-5 p-5">
        {error && <Notice tone="error">{error}</Notice>}
        {message && <Notice>{message}</Notice>}

        {live && canManage && (
          <form onSubmit={saveKey} className="flex flex-wrap items-end gap-3">
            <div className="min-w-64 flex-1">
              <Field label={i?.configured ? `Substituir a chave de API (atual termina em …${i.key_hint})` : "Chave de API do Windsor.ai"}
                hint="A chave é cifrada antes de ser gravada, nunca é exibida de novo e é testada ao salvar.">
                <input type="password" required minLength={8} autoComplete="off" value={apiKey} onChange={(e) => setApiKey(e.target.value)} className={inputClass} />
              </Field>
            </div>
            <Button type="submit" disabled={busy !== null || !apiKey}>{busy === "key" ? "Testando…" : "Salvar e testar"}</Button>
            {i?.configured && <Button type="button" variant="danger" disabled={busy !== null} onClick={remove}>Remover</Button>}
          </form>
        )}
        {live && i?.configured && i.last_error && <Notice tone="error">Último erro: {i.last_error}</Notice>}

        {live && i?.configured && (
          <div>
            <div className="flex flex-wrap items-center justify-between gap-2">
              <p className="text-sm font-medium text-navy-900">Contas deste cliente ({i.accounts?.length ?? 0})</p>
              {canManage && <Button variant="secondary" disabled={busy !== null} onClick={discover}>{busy === "discover" ? "Buscando…" : "Escolher contas"}</Button>}
            </div>
            <p className="mt-1 text-xs text-muted">Uma chave costuma enxergar contas de vários clientes. Só as contas marcadas aqui são lidas para {client.name}.</p>
            {!found && (i.accounts?.length ?? 0) > 0 && (
              <ul className="mt-2 flex flex-wrap gap-2">{i.accounts!.map((a) => <li key={refKey(a)}><Badge tone="blue">{PLATFORM[a.platform]} · {a.name}</Badge></li>)}</ul>
            )}
            {found && (
              <div className="mt-3 rounded-lg border border-line">
                {found.length === 0 ? <p className="p-4 text-sm text-muted">Nenhuma conta com dados nos últimos 30 dias.</p> : (
                  <ul className="max-h-72 divide-y divide-line overflow-y-auto">
                    {found.map((a) => (
                      <li key={refKey(a)}>
                        <label className="flex cursor-pointer items-center gap-3 px-4 py-2 text-sm hover:bg-azure-50">
                          <input type="checkbox" checked={!!picked[refKey(a)]} onChange={() => toggle(a)} disabled={!!a.currency && a.currency !== client.currency} />
                          <span className="flex-1"><span className="font-medium text-navy-900">{a.name}</span> <span className="text-muted">· {PLATFORM[a.platform]} · {a.external_id}</span></span>
                          <span className="text-xs text-muted">
                            {a.currency && a.currency !== client.currency ? `moeda ${a.currency} ≠ ${client.currency}` : `${money(a.spend, a.currency ?? client.currency)} em 30 dias`}
                          </span>
                        </label>
                      </li>
                    ))}
                  </ul>
                )}
                <div className="flex items-center gap-2 border-t border-line p-3">
                  <Button disabled={busy !== null} onClick={saveAccounts}>Salvar seleção ({Object.keys(picked).length})</Button>
                  <Button variant="secondary" onClick={() => setFound(null)}>Cancelar</Button>
                  <span className="text-xs text-muted">A lista mostra apenas contas com dados nos últimos 30 dias.</span>
                </div>
              </div>
            )}
          </div>
        )}

        {canManage && (!live || (i?.configured && (i.accounts?.length ?? 0) > 0)) && (
          <div className="flex flex-wrap items-center gap-3 border-t border-line pt-4">
            <select aria-label="Período da sincronização" value={days} onChange={(e) => setDays(Number(e.target.value))} className="rounded-lg border border-line bg-white px-3 py-2 text-sm">
              <option value={7}>Últimos 7 dias</option><option value={30}>Últimos 30 dias</option><option value={90}>Últimos 90 dias</option>
            </select>
            <Button disabled={busy !== null} onClick={sync}>{busy === "sync" ? "Sincronizando…" : live ? "Sincronizar agora" : "Regerar dados demonstrativos"}</Button>
            <span className="text-xs text-muted">Última sincronização: {dateTime(i?.last_synced_at ?? runs.data?.find((r) => r.status === "completed")?.finished_at ?? null)}</span>
          </div>
        )}

        {(runs.data?.length ?? 0) > 0 && (
          <div>
            <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted">Histórico de sincronizações</p>
            <ul className="divide-y divide-line rounded-lg border border-line text-sm">
              {runs.data!.slice(0, 6).map((r) => (
                <li key={r.id} className="px-4 py-2.5">
                  <div className="flex flex-wrap items-center gap-2">
                    <Badge tone={RUN[r.status][1]}>{RUN[r.status][0]}</Badge>
                    <span>{dateTime(r.started_at)}</span>
                    <span className="text-muted">· {day(r.period_start)} a {day(r.period_end)} · {r.provider} · {r.triggered_by}</span>
                    {r.stats && <span className="text-muted">· {r.stats.campaigns} campanhas, {r.stats.metric_rows} linhas</span>}
                  </div>
                  {r.error && <p className="mt-1 text-rose-700">{r.error}</p>}
                  {r.issues.length > 0 && <ul className="mt-1 list-disc pl-5 text-xs text-amber-800">{r.issues.map((x) => <li key={x}>{x}</li>)}</ul>}
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>
    </Card>
  );
}
