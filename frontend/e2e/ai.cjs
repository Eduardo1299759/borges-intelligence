/* IA no Borges Core, no navegador, contra a Anthropic FALSA (backend/tests/fake_anthropic_server.py).
 * A API precisa rodar com BORGES_ANTHROPIC_BASE_URL apontando para ela. Nunca usa a API real.
 * Uso: E2E_EMAIL=... E2E_PASSWORD=... node e2e/ai.cjs
 */
const { chromium } = require("playwright");
const assert = require("node:assert/strict");
const path = require("node:path");
const BASE = process.env.E2E_BASE_URL || "http://localhost:3000";
const { E2E_EMAIL, E2E_PASSWORD, E2E_SHOTS } = process.env;

(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 2 });
  const errors = [];
  page.on("pageerror", (e) => errors.push(String(e)));
  const shot = async (n) => E2E_SHOTS && page.screenshot({ path: path.join(E2E_SHOTS, `${n}.png`), fullPage: true });
  const step = (m) => console.log(`✓ ${m}`);
  const nav = (l) => page.getByRole("navigation", { name: "Principal" }).getByRole("link", { name: l }).click();

  await page.goto(BASE + "/login");
  await page.getByLabel("Login").fill(E2E_EMAIL);
  await page.getByLabel("Senha").fill(E2E_PASSWORD);
  await page.getByRole("button", { name: "Entrar" }).click();
  await page.getByRole("heading", { name: "Visão geral" }).waitFor();

  await nav("Configurações");
  const card = page.locator("section").filter({ hasText: "IA (Anthropic)" }).first();
  await card.getByText("Desativada", { exact: true }).waitFor();
  await card.getByLabel("Usar IA nas análises").check();
  await card.getByRole("button", { name: "Salvar" }).click();
  await card.getByRole("alert").filter({ hasText: "chave de API" }).waitFor();
  step("ativar sem chave é recusado");
  await card.getByLabel(/Chave de API da Anthropic/).fill("sk-ant-e2e-fake-key-000000000000");
  await card.getByLabel(/Limite mensal/).fill("5");
  await card.getByRole("button", { name: "Salvar" }).click();
  await card.getByText("Ativada", { exact: true }).waitFor();
  await card.getByText(/atual termina em …0000/).waitFor();
  assert(!(await page.content()).includes("sk-ant-e2e-fake-key"), "a chave não pode voltar para a página");
  step("IA ativada com limite de US$ 5; a chave não é exibida de volta");

  await nav("Central de inteligência");
  await page.getByLabel("Pergunta ao Borges Core").fill("O que devo priorizar esta semana?");
  await page.getByRole("button", { name: "Analisar" }).click();
  const answer = page.locator("section:visible").filter({ hasText: "Resposta de teste da IA" }).first();
  await answer.getByText("Redigido por IA").waitFor();
  await answer.getByText(/custo US\$ 0,0\d+|custo US\$ 0\.0\d+/).waitFor();
  await answer.getByText("Ver resposta das regras (sem IA)").click();
  await answer.getByText(/^Analisei/).waitFor();
  await shot("ai-1-resposta");
  step("resposta redigida pela IA, com custo e a resposta das regras disponível");

  await nav("Configurações");
  await card.getByText(/US\$ 0,05 de US\$ 5,00/).waitFor(); // 8000 x $4 + 900 x $20 por milhão = 0,05
  await card.getByRole("cell", { name: "Usada" }).first().waitFor();
  await shot("ai-2-config");
  step("gasto do mês e a chamada aparecem no quadro da IA");

  assert.deepEqual(errors, []);
  await browser.close();
  console.log("\nIA: fluxo verificado no navegador (contra a Anthropic falsa).");
})().catch((e) => { console.error("\n✕ FALHOU:", e.message); process.exit(1); });
