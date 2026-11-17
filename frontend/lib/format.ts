const DASH = "—";

export function money(v: number | string | null | undefined, currency = "BRL"): string {
  if (v === null || v === undefined || v === "") return DASH;
  return new Intl.NumberFormat("pt-BR", { style: "currency", currency }).format(Number(v));
}

export function int(v: number | null | undefined): string {
  return v === null || v === undefined ? DASH : new Intl.NumberFormat("pt-BR", { maximumFractionDigits: 0 }).format(v);
}

export function dec(v: number | string | null | undefined, digits = 2): string {
  if (v === null || v === undefined || v === "") return DASH;
  return new Intl.NumberFormat("pt-BR", { minimumFractionDigits: digits, maximumFractionDigits: digits }).format(Number(v));
}

export function pct(v: number | null | undefined, digits = 1): string {
  if (v === null || v === undefined) return DASH;
  return new Intl.NumberFormat("pt-BR", { style: "percent", minimumFractionDigits: digits, maximumFractionDigits: digits }).format(v);
}

export function day(iso: string): string {
  const [y, m, d] = iso.slice(0, 10).split("-");
  return `${d}/${m}/${y}`;
}

export function dateTime(iso: string | null, timeZone?: string): string {
  if (!iso) return DASH;
  return new Intl.DateTimeFormat("pt-BR", { dateStyle: "short", timeStyle: "short", timeZone }).format(new Date(iso));
}

export const STATUS_LABEL: Record<string, string> = {
  awaiting_approval: "Aguarda aprovação",
  informational: "Sem ação necessária",
  adjustment_requested: "Ajuste solicitado",
  rejected: "Rejeitada",
  approved: "Aprovada · tarefa manual",
  executing: "Executando",
  completed: "Concluída",
  failed: "Falhou",
  pending: "Pendente",
  running: "Executando",
};

export const ROLE_LABEL: Record<string, string> = {
  admin: "Administrador", manager: "Gestor", analyst: "Analista", viewer: "Leitura",
};
