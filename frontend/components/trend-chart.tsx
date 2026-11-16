"use client";

import { CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { money } from "@/lib/format";
import type { Dashboard } from "@/lib/types";

export function TrendChart({ series, currency }: { series: Dashboard["series"]; currency: string }) {
  const data = series.map((p) => ({ ...p, label: `${p.date.slice(8, 10)}/${p.date.slice(5, 7)}` }));
  return (
    <div className="h-72 w-full">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={data} margin={{ top: 8, right: 12, bottom: 0, left: 0 }}>
          <CartesianGrid stroke="#e7edf5" vertical={false} />
          <XAxis dataKey="label" tick={{ fontSize: 11, fill: "#5b6b82" }} tickLine={false} axisLine={{ stroke: "#dfe6ef" }} minTickGap={24} />
          <YAxis tick={{ fontSize: 11, fill: "#5b6b82" }} tickLine={false} axisLine={false} width={64}
                 tickFormatter={(v: number) => new Intl.NumberFormat("pt-BR", { notation: "compact" }).format(v)} />
          <Tooltip formatter={(v) => money(v as number, currency)} labelStyle={{ color: "#0a2540", fontWeight: 600 }}
                   contentStyle={{ borderRadius: 8, border: "1px solid #dfe6ef", fontSize: 12 }} />
          <Legend iconType="plainline" wrapperStyle={{ fontSize: 12 }} />
          {/* connectNulls=false: dia sem dado aparece como lacuna, não como zero. */}
          <Line type="monotone" dataKey="confirmed_revenue" name="Receita confirmada" stroke="#0b6bcb" strokeWidth={2} dot={false} connectNulls={false} isAnimationActive={false} />
          <Line type="monotone" dataKey="spend" name="Investimento" stroke="#0a2540" strokeWidth={2} strokeDasharray="5 4" dot={false} connectNulls={false} isAnimationActive={false} />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
