/* Fase 6 no navegador: rotinas, alertas, relatórios (com PDF) e aprendizados (cliente de demonstração, IA desligada).
 * Uso: E2E_EMAIL=... E2E_PASSWORD=... node e2e/phase6.cjs
 */
const { chromium } = require("playwright");
const assert = require("node:assert/strict");
const path = require("node:path");
const fs = require("node:fs");
const BASE = process.env.E2E_BASE_URL || "http://localhost:3000";
const { E2E_EMAIL, E2E_PASSWORD, E2E_SHOTS } = process.env;

(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 2 });
  const errors = [];
  page.on("pageerror", (e) => errors.push(String(e)));
  const shot = async (n) => E2E_SHOTS && page.screenshot({ path: path.join(E2E_SHOTS, `${n}.png`), fullPage: true });
  const step = (m) => console.log(`✓ ${m}`);
  const visible = (sel) => page.locator(`${sel}:visible`);
  const nav = (l) => page.getByRole("navigation", { name: "Principal" }).getByRole("link", { name: l, exact: true }).click();

  await page.goto(BASE + "/login");
  await page.getByLabel("Login").fill(E2E_EMAIL);
  await page.getByLabel("Senha").fill(E2E_PASSWORD);
  await page.getByRole("button", { name: "Entrar" }).click();
  await page.getByRole("heading", { name: "Visão geral" }).waitFor();

  // Automações: rotinas padrão, rodar agora, alertas
  await nav("Automações");
  await page.getByRole("heading", { name: "Automações" }).waitFor();
  for (const r of ["Auditoria diária", "Revisão competitiva", "Relatório semanal", "Relatório mensal", "Revisão de criativos"]) {
    await page.locator("li").filter({ hasText: r }).first().waitFor();
  }
  const audit = visible("li").filter({ hasText: "Auditoria diária" }).filter({ has: page.getByRole("button", { name: "Rodar agora" }) });
  await audit.getByRole("button", { name: "Rodar agora" }).click();
  await audit.getByText("Concluída").waitFor({ timeout: 60000 });
  const creative = visible("li").filter({ hasText: "Revisão de criativos" }).filter({ has: page.getByRole("button", { name: "Rodar agora" }) });
  await creative.getByRole("button", { name: "Rodar agora" }).click();
  await creative.getByText("Concluída").waitFor({ timeout: 60000 });
  await page.getByText(/Criativo para revisar:/).first().waitFor();
  await page.getByText(/criativo\(s\) para revisar/).first().waitFor();
  step("rotinas padrão listadas, auditoria diária e revisão de criativos executadas, alerta criado");
  await shot("p6-automacoes");

  // Visão geral mostra os alertas abertos
  await nav("Visão geral");
  await page.getByText("Alertas automáticos").waitFor();
  step("alertas na visão geral");

  await nav("Automações");
  await page.getByRole("heading", { name: "Automações" }).waitFor();
  await visible("li").filter({ hasText: /Criativo para revisar:/ }).first().waitFor();
  const before = await visible("li").filter({ hasText: /Criativo para revisar:/ }).count();
  await visible("li").filter({ hasText: /Criativo para revisar:/ }).first().getByRole("button", { name: "Resolver" }).click();
  await page.waitForTimeout(800);
  assert.equal(await visible("li").filter({ hasText: /Criativo para revisar:/ }).count(), before - 1);
  step("alerta resolvido sai da lista");

  // Relatórios
  await nav("Relatórios");
  await page.getByRole("heading", { name: "Relatórios", exact: true }).waitFor();
  await page.getByRole("button", { name: "Gerar semanal" }).click();
  await page.getByRole("heading", { name: /Relatório semanal —/ }).waitFor();
  for (const s of ["Resumo executivo", "Indicadores", "O que aconteceu por campanha", "O que foi feito", "Qualidade dos dados e observações"]) {
    await page.getByRole("heading", { name: s }).waitFor();
  }
  await page.getByText("Dados simulados de demonstração — não representam resultados reais.").waitFor();
  await page.getByRole("button", { name: "Exportar PDF" }).waitFor();
  await shot("p6-relatorio");
  await page.emulateMedia({ media: "print" });
  assert.equal(await page.getByRole("navigation", { name: "Principal" }).isVisible(), false, "menu não deve sair no PDF");
  assert.equal(await page.getByRole("button", { name: "Exportar PDF" }).isVisible(), false);
  const pdf = await page.pdf({ format: "A4", printBackground: true });
  assert.ok(pdf.length > 20000);
  if (E2E_SHOTS) fs.writeFileSync(path.join(E2E_SHOTS, "p6-relatorio.pdf"), pdf);
  await page.emulateMedia({ media: "screen" });
  step(`relatório semanal com todas as seções; PDF sem menu (${Math.round(pdf.length / 1024)} KB)`);

  await page.getByRole("button", { name: "Gerar mensal" }).click();
  await page.getByRole("heading", { name: /Relatório mensal executivo —/ }).waitFor();
  await page.getByRole("button", { name: /Relatório diário operacional/ }).click();
  await page.getByRole("heading", { name: /Relatório diário operacional —/ }).waitFor();
  step("relatório mensal gerado; diário (da rotina) aberto pelo histórico");

  // Aprendizados
  await nav("Aprendizados");
  await page.getByRole("heading", { name: "Aprendizados" }).waitFor();
  await page.getByLabel("Título").fill("Atendimento noturno");
  await page.getByLabel("O que foi observado").fill("Leads que chegam à noite parecem fechar mais quando respondidos em até 10 minutos.");
  await page.getByRole("button", { name: "Registrar" }).click();
  const item = visible("li").filter({ hasText: "Atendimento noturno" });
  await item.getByText("Hipótese", { exact: true }).waitFor();
  await item.getByText("confiabilidade baixa").waitFor();
  await page.getByLabel("Buscar").fill("noite minutos");
  await page.getByRole("button", { name: "Buscar" }).click();
  await item.waitFor();
  await page.getByLabel("Buscar").fill("inexistentexyz");
  await page.getByRole("button", { name: "Buscar" }).click();
  await page.getByText("Nenhum aprendizado encontrado.").waitFor();
  step("aprendizado manual registrado como hipótese; busca por palavra-chave");
  await page.getByLabel("Buscar").fill("");
  await page.getByRole("button", { name: "Buscar" }).click();
  await item.waitFor();
  await shot("p6-aprendizados");

  // Auditoria registra as rotinas
  await nav("Auditoria");
  await page.getByText("Rotina concluída").first().waitFor();
  step("execuções das rotinas na trilha de auditoria");

  assert.deepEqual(errors, []);
  console.log("Fase 6 no navegador: OK");
  await browser.close();
})().catch((e) => { console.error(e); process.exit(1); });
