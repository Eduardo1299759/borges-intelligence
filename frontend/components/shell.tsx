"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import type { ReactNode } from "react";
import { api } from "@/lib/api";
import { ROLE_LABEL } from "@/lib/format";
import { useApp } from "./app-context";

const NAV = [
  { href: "/", label: "Visão geral" },
  { href: "/clientes", label: "Clientes e contas" },
  { href: "/inteligencia", label: "Central de inteligência" },
  { href: "/campanhas", label: "Gestor de campanhas" },
  { href: "/aprovacoes", label: "Central de aprovação" },
  { href: "/auditoria", label: "Auditoria" },
  { href: "/configuracoes", label: "Configurações" },
];

// Áreas previstas que ainda não existem. Ficam visíveis como roteiro, nunca como tela vazia.
const ROADMAP = [
  { label: "Creative Studio", phase: 4 },
  { label: "Radar competitivo", phase: 4 },
  { label: "Inteligência comercial", phase: 5 },
  { label: "Relatórios", phase: 6 },
];

export function Shell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const { user, clients, client, selectClient } = useApp();

  async function logout() {
    await api("/auth/logout", { method: "POST" });
    window.location.assign("/login");
  }

  return (
    <div className="flex min-h-screen flex-col lg:flex-row">
      <aside className="flex shrink-0 flex-col bg-navy-950 text-slate-200 lg:w-64">
        <div className="flex items-center gap-3 px-5 py-5">
          <div className="grid h-9 w-9 place-items-center rounded-lg bg-gradient-to-br from-azure-500 to-aqua text-sm font-bold text-white">B</div>
          <div>
            <p className="text-sm font-semibold leading-tight text-white">Borges Intelligence</p>
            <p className="text-[11px] uppercase tracking-wider text-slate-400">AI Traffic OS</p>
          </div>
        </div>
        <nav aria-label="Principal" className="flex gap-1 overflow-x-auto px-3 pb-3 lg:flex-col lg:overflow-visible">
          {NAV.map((item) => {
            const active = item.href === "/" ? pathname === "/" : pathname.startsWith(item.href);
            return (
              <Link
                key={item.href}
                href={item.href}
                aria-current={active ? "page" : undefined}
                className={`whitespace-nowrap rounded-lg px-3 py-2 text-sm transition-colors ${active ? "bg-azure-600 font-medium text-white" : "text-slate-300 hover:bg-navy-800 hover:text-white"}`}
              >
                {item.label}
              </Link>
            );
          })}
        </nav>
        <div className="hidden px-3 pb-4 lg:block">
          <p className="px-3 pb-1 pt-3 text-[11px] font-medium uppercase tracking-wider text-slate-500">Próximas fases</p>
          {ROADMAP.map((item) => (
            <div key={item.label} className="flex items-center justify-between px-3 py-1.5 text-sm text-slate-500">
              <span>{item.label}</span>
              <span className="rounded bg-navy-800 px-1.5 py-0.5 text-[10px] text-slate-400">Fase {item.phase}</span>
            </div>
          ))}
        </div>
        <div className="mt-auto hidden border-t border-navy-800 px-5 py-4 lg:block">
          <p className="truncate text-sm text-white">{user.name}</p>
          <p className="truncate text-xs text-slate-400">{user.email} · {ROLE_LABEL[user.role]}</p>
          <button onClick={logout} className="mt-2 text-xs text-aqua hover:underline">Sair</button>
        </div>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex flex-wrap items-center justify-between gap-3 border-b border-line bg-white px-4 py-3 sm:px-8">
          <label className="flex items-center gap-2 text-sm">
            <span className="text-muted">Cliente</span>
            <select
              value={client?.id ?? ""}
              onChange={(e) => selectClient(Number(e.target.value))}
              disabled={clients.length === 0}
              className="max-w-[60vw] rounded-lg border border-line bg-white px-3 py-1.5 text-sm font-medium text-navy-900"
            >
              {clients.length === 0 && <option value="">Nenhum cliente cadastrado</option>}
              {clients.map((c) => (
                <option key={c.id} value={c.id}>{c.name}</option>
              ))}
            </select>
          </label>
          <button onClick={logout} className="text-sm text-azure-600 hover:underline lg:hidden">Sair</button>
        </header>
        {client?.data_mode === "demo" && (
          <div role="status" className="border-b border-cyan-200 bg-cyan-50 px-4 py-2 text-xs text-cyan-900 sm:px-8">
            <strong className="font-semibold">Dados demonstrativos.</strong> Os números deste cliente são gerados pelo sistema para
            validação e não representam campanhas reais. Nenhuma plataforma de anúncios é alterada.
          </div>
        )}
        <main className="flex-1 px-4 py-6 sm:px-8">{children}</main>
      </div>
    </div>
  );
}
