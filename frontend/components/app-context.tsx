"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { api } from "@/lib/api";
import type { Client, User } from "@/lib/types";

interface Ctx {
  user: User;
  clients: Client[];
  client: Client | null;
  selectClient: (id: number) => void;
  reloadClients: () => Promise<void>;
  canManage: boolean;
  canAnalyze: boolean;
}

const AppContext = createContext<Ctx | null>(null);
const KEY = "borges.client";

export function useApp(): Ctx {
  const ctx = useContext(AppContext);
  if (!ctx) throw new Error("useApp fora do AppProvider");
  return ctx;
}

export function AppProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [clients, setClients] = useState<Client[]>([]);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  const reloadClients = useCallback(async () => {
    setClients(await api<Client[]>("/clients"));
  }, []);

  useEffect(() => {
    let cancelled = false;
    Promise.all([api<User>("/auth/me"), api<Client[]>("/clients")])
      .then(([u, c]) => {
        if (cancelled) return;
        setUser(u);
        setClients(c);
        setSelectedId(Number(window.localStorage.getItem(KEY)) || null);
      })
      .catch((e: { status?: number; message: string }) => {
        if (e.status === 401) window.location.assign("/login");
        else if (!cancelled) setError(e.message);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const selectClient = useCallback((id: number) => {
    window.localStorage.setItem(KEY, String(id));
    setSelectedId(id);
  }, []);

  const value = useMemo<Ctx | null>(() => {
    if (!user) return null;
    const client = clients.find((c) => c.id === selectedId) ?? clients[0] ?? null;
    return {
      user, clients, client, selectClient, reloadClients,
      canManage: user.role === "admin" || user.role === "manager",
      canAnalyze: user.role !== "viewer",
    };
  }, [user, clients, selectedId, selectClient, reloadClients]);

  if (error) return <p className="p-10 text-sm text-rose-700">Não foi possível conectar à API: {error}</p>;
  if (!value) return <p className="p-10 text-sm text-muted">Carregando…</p>;
  return <AppContext.Provider value={value}>{children}</AppContext.Provider>;
}
