/* Fase 4 no navegador: Creative Studio, Experimentos e Radar (cliente de demonstração, IA desligada).
 * Uso: E2E_EMAIL=... E2E_PASSWORD=... node e2e/phase4.cjs
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
  const visible = (sel) => page.locator(`${sel}:visible`);

  await page.goto(BASE + "/login");
  await page.getByLabel("Login").fill(E2E_EMAIL);
  await page.getByLabel("Senha").fill(E2E_PASSWORD);
  await page.getByRole("button", { name: "Entrar" }).click();
  await page.getByRole("heading", { name: "Visão geral" }).waitFor();

  // Creative Studio
  await nav("Creative Studio");
  await page.getByRole("heading", { name: "Creative Studio" }).waitFor();
  const combo = visible("tr").filter({ hasText: "Imagem combo" }).filter({ hasText: "Remarketing" });
  await combo.getByText("Sem resultado").waitFor();
  await visible("tr").filter({ hasText: "Vídeo depoimento" }).getByText("Vencedor").first().waitFor();
  await page.getByLabel("Objetivo do criativo").fill("Mais pedidos pelo WhatsApp");
  await page.getByLabel("Público", { exact: true }).fill("Famílias do bairro, 25 a 45 anos");
  await page.getByLabel(/^Oferta/).fill("Combo família com entrega grátis");
  const ref = page.getByLabel(/Criativo de referência/);
  const refValue = await ref.locator("option", { hasText: "Imagem combo — Remarketing" }).getAttribute("value");
  await ref.selectOption(refValue);
  await page.getByRole("button", { name: "Gerar variações" }).click();
  await page.getByText("Modelo padrão").first().waitFor();
  await page.getByText("Prova social").first().waitFor();
  await shot("p4-1-criativos");
  step("biblioteca classifica criativos; briefing gerado pelo modelo padrão (IA desligada)");

  // Experimentos
  await nav("Experimentos");
  await page.getByRole("button", { name: "Novo experimento" }).click();
  await page.getByLabel("Nome").fill("Vídeo x imagem no WhatsApp");
  await page.getByLabel("Problema").fill("Custo por lead alto nos anúncios de imagem");
  await page.getByLabel("Hipótese").fill("Depoimento em vídeo converte mais clique em lead");
  await page.getByLabel("Campanha").selectOption({ label: "Conversas WhatsApp — Público aberto" });
  const controle = page.locator("fieldset").filter({ hasText: "Controle" });
  const variante = page.locator("fieldset").filter({ hasText: "Variante" });
  await controle.getByLabel("Imagem oferta").check();
  await variante.getByLabel("Vídeo depoimento").check();
  await page.getByRole("button", { name: "Criar rascunho" }).click();
  const card = visible("section").filter({ hasText: "Vídeo x imagem no WhatsApp" }).first();
  await card.getByText("Rascunho").waitFor();
  const past = new Date(Date.now() - 15 * 864e5).toISOString().slice(0, 10);
  await card.getByLabel(/Início/).fill(past);
  await card.getByRole("button", { name: "Iniciar" }).click();
  const running = visible("section").filter({ hasText: "Vídeo x imagem no WhatsApp" }).first();
  await running.getByText("Em andamento").waitFor();
  await running.getByText("Análise retroativa").waitFor();
  await running.getByRole("cell", { name: "Variante" }).waitFor();
  await running.getByText(/p-valor/).waitFor();
  await shot("p4-2-experimento");
  await running.getByLabel(/Aprendizado/).fill("Depoimento em vídeo converte melhor neste público.");
  await running.getByRole("button", { name: "Concluir e registrar" }).click();
  const done = visible("section").filter({ hasText: "Vídeo x imagem no WhatsApp" }).first();
  await done.getByText("Concluído").waitFor();
  await done.getByText(/Aprendizado registrado/).waitFor();
  step("experimento criado, iniciado de forma retroativa, avaliado com teste estatístico e concluído");

  // Radar
  await nav("Radar competitivo");
  await page.getByLabel("Nome").fill("Pizzaria Rival");
  await page.getByLabel("Site (opcional)").fill("https://rival.test");
  await page.getByRole("button", { name: "Adicionar concorrente" }).click();
  await page.getByText("0 anúncio(s)").waitFor();
  await page.getByLabel("Concorrente").selectOption({ label: "Pizzaria Rival" });
  await page.getByLabel("Texto do anúncio").fill("Rodízio às quartas com refrigerante incluso");
  await page.getByLabel("Oferta (opcional)").fill("Rodízio R$ 49,90");
  await page.getByLabel("Formato").selectOption("video");
  await page.getByLabel("No ar desde").fill(new Date(Date.now() - 40 * 864e5).toISOString().slice(0, 10));
  await page.getByRole("button", { name: "Registrar" }).click();
  await page.getByText("40 dias no ar").waitFor();
  await page.getByRole("button", { name: "Analisar anúncios" }).click();
  await page.getByText("Resumo por regras").waitFor();
  await page.getByText("Pizzaria Rival: Rodízio R$ 49,90").waitFor();
  await shot("p4-3-radar");
  step("concorrente e anúncio registrados; resumo por regras (IA desligada)");

  // auditoria registra o ciclo do experimento
  await nav("Auditoria");
  await page.getByText("experiment.concluded").waitFor();
  assert.deepEqual(errors, []);
  await browser.close();
  console.log("\nFase 4: fluxo verificado no navegador.");
})().catch((e) => { console.error("\n✕ FALHOU:", e.message); process.exit(1); });
