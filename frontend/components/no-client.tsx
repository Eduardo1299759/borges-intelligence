import Link from "next/link";
import { Card } from "./ui";

export function NoClient() {
  return (
    <Card className="p-10 text-center">
      <p className="text-sm text-muted">Nenhum cliente cadastrado ainda.</p>
      <Link href="/clientes" className="mt-3 inline-block text-sm font-medium text-azure-600 hover:underline">Cadastrar o primeiro cliente →</Link>
    </Card>
  );
}
