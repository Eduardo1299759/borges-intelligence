"use client";

import { useState } from "react";
import { api } from "@/lib/api";
import type { User } from "@/lib/types";
import { Button, Card, CardHeader, Field, Notice, inputClass } from "./ui";

export function AccountCard({ user }: { user: User }) {
  const [login, setLogin] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [current, setCurrent] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState<string | null>(null);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setDone(null);
    if (password && password !== confirm) {
      setError("A confirmação não é igual à nova senha.");
      return;
    }
    setBusy(true);
    try {
      const updated = await api<User>("/auth/me/credentials", {
        method: "PUT",
        body: { current_password: current, new_login: login || null, new_password: password || null },
      });
      setDone(`Dados de acesso atualizados. Seu login agora é: ${updated.email}`);
      setLogin(""); setPassword(""); setConfirm(""); setCurrent("");
      window.setTimeout(() => window.location.reload(), 2500);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card>
      <CardHeader title="Minha conta" hint={`Login atual: ${user.email}`} />
      <form onSubmit={submit} className="grid gap-4 p-5 md:grid-cols-2">
        {error && <div className="md:col-span-2"><Notice tone="error">{error}</Notice></div>}
        {done && <div className="md:col-span-2"><Notice>{done}</Notice></div>}
        <Field label="Novo login" hint="Deixe em branco para manter o atual. Sem espaços.">
          <input value={login} onChange={(e) => setLogin(e.target.value)} autoCapitalize="none" autoComplete="off" spellCheck={false} className={inputClass} />
        </Field>
        <div />
        <Field label="Nova senha" hint="Deixe em branco para manter a atual. Mínimo de 8 caracteres.">
          <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} autoComplete="new-password" className={inputClass} />
        </Field>
        <Field label="Confirme a nova senha">
          <input type="password" value={confirm} onChange={(e) => setConfirm(e.target.value)} autoComplete="new-password" className={inputClass} />
        </Field>
        <Field label="Senha atual" hint="Obrigatória para confirmar a alteração.">
          <input type="password" required value={current} onChange={(e) => setCurrent(e.target.value)} autoComplete="current-password" className={inputClass} />
        </Field>
        <div className="flex items-end">
          <Button type="submit" disabled={busy || (!login && !password)}>{busy ? "Salvando…" : "Salvar"}</Button>
        </div>
      </form>
    </Card>
  );
}
