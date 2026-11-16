"use client";

import { useCallback, useEffect, useState } from "react";

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

export async function api<T>(path: string, init?: { method?: string; body?: unknown }): Promise<T> {
  const res = await fetch(`/api${path}`, {
    method: init?.method ?? "GET",
    headers: init?.body !== undefined ? { "Content-Type": "application/json" } : undefined,
    body: init?.body !== undefined ? JSON.stringify(init.body) : undefined,
    credentials: "same-origin",
  });
  if (res.status === 401 && !path.startsWith("/auth/")) {
    window.location.assign("/login");
  }
  if (!res.ok) {
    let message = `Erro ${res.status}`;
    try {
      const data = await res.json();
      if (typeof data.detail === "string") message = data.detail;
      else if (Array.isArray(data.detail)) {
        message = data.detail
          .map((d: { loc?: string[]; msg: string }) => `${d.loc?.slice(1).join(".") ?? ""}: ${d.msg}`)
          .join(" · ");
      }
    } catch {
      /* resposta sem JSON */
    }
    throw new ApiError(res.status, message);
  }
  return res.status === 204 ? (undefined as T) : res.json();
}

interface State<T> { data: T | null; error: string | null; key: string | null }

/** Busca dados de leitura. `path = null` desliga a busca (ex.: nenhum cliente selecionado). */
export function useApi<T>(path: string | null) {
  const [state, setState] = useState<State<T>>({ data: null, error: null, key: null });
  const [tick, setTick] = useState(0);
  useEffect(() => {
    if (!path) return;
    let cancelled = false;
    api<T>(path)
      .then((data) => !cancelled && setState({ data, error: null, key: path }))
      .catch((e: Error) => !cancelled && setState({ data: null, error: e.message, key: path }));
    return () => {
      cancelled = true;
    };
  }, [path, tick]);
  const reload = useCallback(() => setTick((t) => t + 1), []);
  const loading = path !== null && state.key !== path;
  return { data: loading || !path ? null : state.data, error: loading || !path ? null : state.error, loading, reload };
}
