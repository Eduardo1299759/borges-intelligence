"use client";

import { useState } from "react";
import { Button, Field, Notice, inputClass } from "@/components/ui";
import { api } from "@/lib/api";

export default function LoginPage() {
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const form = new FormData(e.currentTarget);
    setBusy(true);
    setError(null);
    try {
      await api("/auth/login", { method: "POST", body: { email: form.get("email"), password: form.get("password") } });
      window.location.assign("/");
    } catch (err) {
      setError((err as Error).message);
      setBusy(false);
    }
  }

  return (
    <div className="grid min-h-screen place-items-center bg-gradient-to-br from-navy-950 via-navy-900 to-azure-700 px-4">
      <form onSubmit={submit} className="w-full max-w-sm space-y-4 rounded-2xl bg-white p-8 shadow-xl">
        <div>
          <div className="mb-4 grid h-10 w-10 place-items-center rounded-lg bg-gradient-to-br from-azure-500 to-aqua font-bold text-white">B</div>
          <h1 className="text-xl font-semibold text-navy-900">Borges Intelligence</h1>
          <p className="text-sm text-muted">AI Traffic Operating System</p>
        </div>
        {error && <Notice tone="error">{error}</Notice>}
        <Field label="Login">
          <input name="email" type="text" required autoCapitalize="none" autoCorrect="off" spellCheck={false} autoComplete="username" className={inputClass} />
        </Field>
        <Field label="Senha">
          <input name="password" type="password" required autoComplete="current-password" className={inputClass} />
        </Field>
        <Button type="submit" disabled={busy} className="w-full">{busy ? "Entrando…" : "Entrar"}</Button>
      </form>
    </div>
  );
}
