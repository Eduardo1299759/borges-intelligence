/* Teste de ponta a ponta dos 10 critérios de aceitação do MVP, no navegador.
 *
 * Pré-requisitos: API e frontend no ar, banco com `python -m app.cli seed`.
 * Uso: E2E_EMAIL=... E2E_PASSWORD=... node e2e/mvp.cjs  (E2E_BASE_URL padrão: http://localhost:3000)
 */
const { chromium } = require("playwright");
const assert = require("node:assert/strict");
const path = require("node:path");

const BASE = process.env.E2E_BASE_URL || "http://localhost:3000";
const { E2E_EMAIL, E2E_PASSWORD, E2E_SHOTS } = process.env;
assert(E2E_EMAIL && E2E_PASSWORD, "Defina E2E_EMAIL e E2E_PASSWORD");

(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 2 });
  const errors = [];
  page.on("pageerror", (e) => errors.push(String(e)));
  const shot = async (name) => E2E_SHOTS && page.screenshot({ path: path.join(E2E_SHOTS, `${name}.png`), fullPage: true });
  const step = (msg) => console.log(`✓ ${msg}`);
  const nav = (label) => page.getByRole("navigation", { name: "Principal" }).getByRole("link", { name: label }).click();
  const clientName = `Cliente E2E ${Date.now()}`;

  // 2. Autenticação
  await page.goto(BASE + "/");
  await page.waitForURL("**/login");
  step("rota protegida redireciona para o login");
  await page.getByLabel("E-mail").fill(E2E_EMAIL);
  await page.getByLabel("Senha").fill("senha-errada");
  await page.getByRole("button", { name: "Entrar" }).click();
  await page.getByRole("alert").filter({ hasText: "inválidos" }).waitFor();
  step("senha incorreta é recusada");
  await page.getByLabel("Senha").fill(E2E_PASSWORD);
  await page.getByRole("button", { name: "Entrar" }).click();
  await page.getByRole("heading", { name: "Visão geral" }).waitFor();
  step("usuário autenticado");

  // 3. Cadastrar e selecionar um cliente
  await nav("Clientes e contas");
  await page.getByRole("button", { name: "Novo cliente" }).click();
  await page.getByLabel("Nome").fill(clientName);
  await page.getByLabel("Segmento").fill("Restaurante / delivery");
  await page.getByLabel("Meta de CAC").fill("25");
  await page.getByLabel("Meta de ROAS").fill("4");
  await page.getByLabel("Margem de contribuição (%)").fill("35");
  await page.getByRole("button", { name: "Salvar" }).click();
  await page.getByRole("row").filter({ hasText: clientName }).getByText("Selecionado").waitFor();
  assert.equal(await page.locator("header select option:checked").textContent(), clientName);
  await shot("2-clientes");
  step("cliente cadastrado e selecionado");

  // 4 e 5. Dados demonstrativos sinalizados e indicadores coerentes
  await nav("Visão geral");
  await page.getByText("Dados demonstrativos.").waitFor();
  const kpi = async (label) => {
    const card = page.locator("section").filter({ has: page.getByText(label, { exact: true }) }).first();
    const raw = await card.locator("p").nth(1).textContent();
    return Number(raw.replace(/[^\d,]/g, "").replace(",", "."));
  };
  await page.getByText("CAC real", { exact: true }).waitFor();
  const [spend, sales, cac, revenue, roas] = [await kpi("Investimento"), await kpi("Vendas confirmadas"), await kpi("CAC real"), await kpi("Receita confirmada"), await kpi("ROAS confirmado")];
  assert(spend > 0 && sales > 0);
  assert(Math.abs(cac - spend / sales) < 0.011, `CAC ${cac} != ${spend}/${sales}`);
  assert(Math.abs(roas - revenue / spend) < 0.011, `ROAS ${roas} != ${revenue}/${spend}`);
  await page.locator(".recharts-line").first().waitFor();
  await shot("1-visao-geral");
  step(`dashboard demonstrativo sinalizado; CAC (${cac}) e ROAS (${roas}) conferem com os totais exibidos`);

  // 6 e 7. Análise do Borges Core com recomendação estruturada
  await nav("Central de inteligência");
  await page.getByLabel("Pergunta ao Borges Core").fill("Existe alguma campanha que vale a pena escalar?");
  await page.getByRole("button", { name: "Analisar" }).click();
  await page.getByText("Recomendações (6)").waitFor();
  const scale = page.locator("article").filter({ hasText: "Escalar “Remarketing — Cardápio digital”" });
  await scale.getByText("Relacionada à pergunta").waitFor();
  await scale.getByRole("button").first().click();
  for (const block of ["Problema", "Causa provável", "Hipótese", "Ação recomendada", "Riscos", "Métrica de validação", "Evidências", "Prévia da mudança"]) {
    await scale.getByText(block, { exact: true }).waitFor();
  }
  await scale.getByRole("cell", { name: "ROAS confirmado" }).waitFor();
  await shot("3-inteligencia");
  step("análise retornou 6 recomendações estruturadas com evidências");

  // 8. Aprovar e rejeitar ações simuladas
  await nav("Central de aprovação");
  await page.getByRole("tab", { name: "Pendentes (4)" }).waitFor();
  await shot("4-aprovacoes");
  const pendingScale = page.locator("article").filter({ hasText: "Escalar “Remarketing" });
  await pendingScale.getByLabel("Comentário da decisão").fill("Aprovado no teste E2E");
  await pendingScale.getByRole("button", { name: "Aprovar e executar" }).click();
  await page.getByRole("tab", { name: "Pendentes (3)" }).waitFor();
  const pendingTracking = page.locator("article").filter({ hasText: "Auditar rastreamento" });
  await pendingTracking.getByRole("button", { name: "Rejeitar" }).click();
  await page.getByRole("tab", { name: "Pendentes (2)" }).waitFor();
  step("uma ação aprovada (execução simulada) e uma rejeitada");

  // 9. Resultado no histórico
  await page.getByRole("tab", { name: "Histórico (2)" }).click();
  const done = page.locator("article").filter({ hasText: "Escalar “Remarketing" });
  await done.getByText("Concluída", { exact: true }).waitFor();
  await done.getByRole("button").first().click();
  await done.getByText("verificada por releitura").waitFor();
  await done.getByText("R$ 60,00 → R$ 72,00").first().waitFor();
  await done.getByText("Aprovado no teste E2E").waitFor();
  await page.locator("article").filter({ hasText: "Auditar rastreamento" }).getByText("Rejeitada").waitFor();
  await shot("5-historico");
  await nav("Gestor de campanhas");
  const row = page.getByRole("row").filter({ hasText: "Remarketing — Cardápio digital" });
  await row.getByText("R$ 72,00").waitFor();
  await row.getByText("1 alteração(ões)").waitFor();
  await shot("6-campanhas");
  await nav("Auditoria");
  await page.getByText("Execução concluída e verificada").waitFor();
  await page.getByRole("button", { name: "Verificar integridade" }).click();
  await page.getByText(/Cadeia íntegra: \d+ registro/).waitFor();
  await shot("7-auditoria");
  step("decisões visíveis no histórico, na campanha e na auditoria (cadeia íntegra)");

  // Responsivo: sem rolagem horizontal da página em largura de celular
  await page.setViewportSize({ width: 390, height: 800 });
  await nav("Visão geral");
  // Rotas visitadas ficam no DOM, ocultas (Activity): restringir aos elementos visíveis.
  await page.locator("p:visible").filter({ hasText: /^CAC real$/ }).waitFor();
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
  assert(overflow <= 0, `rolagem horizontal de ${overflow}px no celular`);
  await shot("8-mobile");
  step("layout sem rolagem horizontal em 390px");

  assert.deepEqual(errors, [], "erros de JavaScript na página");
  await browser.close();
  console.log("\nMVP: todos os critérios verificados no navegador.");
})().catch((e) => {
  console.error("\n✕ FALHOU:", e.message);
  process.exit(1);
});
