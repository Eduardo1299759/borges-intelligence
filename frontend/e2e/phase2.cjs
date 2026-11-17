/* Fase 2 de ponta a ponta no navegador: conectar Windsor.ai, escolher contas, sincronizar e consultar.
 *
 * Usa o Windsor.ai FALSO (backend/tests/fake_windsor_server.py); a API precisa estar rodando com
 * BORGES_WINDSOR_BASE_URL apontando para ele. Não exercita a API real do Windsor.ai.
 * Uso: E2E_EMAIL=... E2E_PASSWORD=... node e2e/phase2.cjs
 */
const { chromium } = require("playwright");
const assert = require("node:assert/strict");
const path = require("node:path");

const BASE = process.env.E2E_BASE_URL || "http://localhost:3000";
const { E2E_EMAIL, E2E_PASSWORD, E2E_SHOTS } = process.env;
const FAKE_KEY = "wk_test_valid_key_1234";
assert(E2E_EMAIL && E2E_PASSWORD, "Defina E2E_EMAIL e E2E_PASSWORD");

(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 2 });
  const errors = [];
  page.on("pageerror", (e) => errors.push(String(e)));
  const shot = async (name) => E2E_SHOTS && page.screenshot({ path: path.join(E2E_SHOTS, `${name}.png`), fullPage: true });
  const step = (msg) => console.log(`✓ ${msg}`);
  const nav = (label) => page.getByRole("navigation", { name: "Principal" }).getByRole("link", { name: label }).click();
  const clientName = `Studio Real ${Date.now()}`;

  await page.goto(BASE + "/login");
  await page.getByLabel("E-mail").fill(E2E_EMAIL);
  await page.getByLabel("Senha").fill(E2E_PASSWORD);
  await page.getByRole("button", { name: "Entrar" }).click();
  await page.getByRole("heading", { name: "Visão geral" }).waitFor();

  await nav("Clientes e contas");
  await page.getByRole("button", { name: "Novo cliente" }).click();
  await page.getByLabel("Nome").fill(clientName);
  await page.getByLabel("Fonte de dados").selectOption("live");
  await page.getByLabel("Meta de CAC").fill("40");
  await page.getByLabel("Orçamento mensal de mídia").fill("1500");
  await page.getByRole("button", { name: "Salvar" }).click();
  await page.getByRole("row").filter({ hasText: clientName }).getByText("Selecionado").waitFor();
  await nav("Visão geral");
  await page.getByText("Este cliente ainda não tem dados.").waitFor();
  assert.equal(await page.getByText("Dados demonstrativos.").count(), 0);
  step("cliente real criado: sem dados e sem aviso de demonstração");

  await nav("Configurações");
  const keyInput = page.getByLabel(/Chave de API do Windsor\.ai|Substituir a chave/);
  await keyInput.fill("chave-invalida-123");
  await page.getByRole("button", { name: "Salvar e testar" }).click();
  await page.getByRole("alert").filter({ hasText: "recusou a chave" }).first().waitFor();
  await page.getByText("Com erro", { exact: true }).waitFor();
  step("chave inválida é recusada e a integração fica marcada com erro");

  await keyInput.fill(FAKE_KEY);
  await page.getByRole("button", { name: "Salvar e testar" }).click();
  await page.getByText("Conectada", { exact: true }).waitFor();
  await page.getByText(/Leitura confirmada/).waitFor();
  assert.equal(await keyInput.inputValue(), "");
  assert(!(await page.content()).includes(FAKE_KEY), "a chave não pode aparecer na página");
  step("chave válida: conexão testada, chave não é exibida de volta");

  await page.getByRole("button", { name: "Escolher contas" }).click();
  await page.getByText("CA Outro Cliente").waitFor();
  await page.getByLabel(/CA Studio/).check();
  await page.getByLabel(/111-222-3333 · Google Ads/).check();
  await page.getByRole("button", { name: "Salvar seleção (2)" }).click();
  await page.getByText("Contas deste cliente (2)").waitFor();
  await shot("p2-1-integracao");
  await page.getByRole("button", { name: "Sincronizar agora" }).click();
  await page.getByText(/Sincronização concluída: 60 linhas de campanha/).waitFor();
  await page.getByText(/contas não selecionadas foram descartadas/).first().waitFor();
  await shot("p2-2-sincronizado");
  step("2 de 3 contas selecionadas; sincronização concluída e linhas da conta alheia descartadas");

  await nav("Visão geral");
  await page.locator("p:visible").filter({ hasText: /^CAC real$/ }).waitFor();
  const card = (label) => page.locator("section:visible").filter({ has: page.getByText(label, { exact: true }) }).first().locator("p").nth(1);
  assert.equal(await card("CAC real").textContent(), "—");
  assert.equal(await card("Vendas confirmadas").textContent(), "—");
  assert.equal(await card("Investimento").textContent(), "R$ 1.182,00"); // 30 dias x (20,00 + 19,40)
  await page.getByText("Fontes: windsor").waitFor();
  await page.getByText(/Ritmo de investimento/).waitFor();
  assert.equal(await page.getByText("Dados demonstrativos.").count(), 0);
  await shot("p2-3-visao-geral");
  step("dashboard com dados da fonte: investimento confere; CAC e vendas indisponíveis (sem CRM), não zero");

  await nav("Gestor de campanhas");
  await page.getByRole("button", { name: /\[Studio\] \[Eng-WPP\] \[Pilates\]/ }).click();
  await page.getByRole("cell", { name: "[Pub Frio]", exact: true }).waitFor();
  await page.getByRole("cell", { name: "[Ads - Vídeo]", exact: true }).waitFor();
  assert.equal(await page.getByText("Campanha de outro cliente").count(), 0);
  await shot("p2-4-campanhas");
  step("hierarquia campanha → conjunto → anúncio visível; nenhuma campanha de outra conta");

  await nav("Central de inteligência");
  await page.getByLabel("Pergunta ao Borges Core").fill("Como está o CAC?");
  await page.getByRole("button", { name: "Analisar" }).click();
  await page.getByText("Recomendações (2)").waitFor();
  assert.equal(await page.locator("article:visible").filter({ hasText: "Demonstração" }).count(), 0);
  step("análise sobre dados da fonte, sem selo de demonstração");

  assert.deepEqual(errors, [], "erros de JavaScript na página");
  await browser.close();
  console.log("\nFase 2: fluxo verificado no navegador (contra o Windsor.ai falso).");
})().catch((e) => {
  console.error("\n✕ FALHOU:", e.message);
  process.exit(1);
});
