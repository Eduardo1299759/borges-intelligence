/* Fase 5 no navegador, contra o Windsor.ai FALSO (backend/tests/fake_windsor_server.py, com ações de escrita).
 * Uso: E2E_EMAIL=... E2E_PASSWORD=... node e2e/phase5.cjs
 */
const { chromium } = require("playwright");
const assert = require("node:assert/strict");
const path = require("node:path");
const BASE = process.env.E2E_BASE_URL || "http://localhost:3000";
const { E2E_EMAIL, E2E_PASSWORD, E2E_SHOTS } = process.env;
const KEY = "wk_test_valid_key_1234";

const d = (n) => { const x = new Date(Date.now() - n * 864e5); return `${String(x.getDate()).padStart(2, "0")}/${String(x.getMonth() + 1).padStart(2, "0")}/${x.getFullYear()}`; };
const orders = ["Pedido;Data;Nome;Telefone;Valor;utm_campaign;Status",
  ...Array.from({ length: 60 }, (_, i) => `P${i};${d(1 + (i % 25))};Cliente ${i};11999990000;R$ 100,00;studio-eng-wpp-pilates;pago`),
  `P99;${d(2)};X;1;R$ 40,00;campanha-perdida;pago`].join("\n");
const leads = ["ID,Data,Nome,Campanha,Status,Tempo resposta (min),Motivo perda",
  ...Array.from({ length: 30 }, (_, i) => `L${i},${d(1 + (i % 20))},Pessoa ${i},[Studio] [Eng-WPP] [Pilates],${["novo", "qualificado", "venda", "perdido", "proposta"][i % 5]},50,preço`)].join("\n");

(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 2 });
  const errors = [];
  page.on("pageerror", (e) => errors.push(String(e)));
  const shot = async (n) => E2E_SHOTS && page.screenshot({ path: path.join(E2E_SHOTS, `${n}.png`), fullPage: true });
  const step = (m) => console.log(`✓ ${m}`);
  const nav = (l) => page.getByRole("navigation", { name: "Principal" }).getByRole("link", { name: l }).click();
  const name = `Studio Real ${Date.now()}`;

  await page.goto(BASE + "/login");
  await page.getByLabel("Login").fill(E2E_EMAIL);
  await page.getByLabel("Senha").fill(E2E_PASSWORD);
  await page.getByRole("button", { name: "Entrar" }).click();
  await page.getByRole("heading", { name: "Visão geral" }).waitFor();

  // cliente real conectado e sincronizado
  await nav("Clientes e contas");
  await page.getByRole("button", { name: "Novo cliente" }).click();
  await page.getByLabel("Nome").fill(name);
  await page.getByLabel("Fonte de dados").selectOption("live");
  await page.getByLabel("Meta de CAC").fill("40");
  await page.getByLabel("Meta de ROAS").fill("3");
  await page.getByLabel("Margem de contribuição (%)").fill("40");
  await page.getByRole("button", { name: "Salvar" }).click();
  await page.getByRole("row").filter({ hasText: name }).getByText("Selecionado").waitFor();
  await nav("Configurações");
  await page.getByLabel(/Chave de API do Windsor\.ai|Substituir a chave/).fill(KEY);
  await page.getByRole("button", { name: "Salvar e testar" }).click();
  await page.getByText("Conectada", { exact: true }).waitFor();
  await page.getByRole("button", { name: "Escolher contas" }).click();
  await page.getByLabel(/CA Studio/).check();
  await page.getByLabel(/111-222-3333 · Google Ads/).check();
  await page.getByRole("button", { name: "Salvar seleção (2)" }).click();
  await page.getByRole("button", { name: "Sincronizar agora" }).click();
  await page.getByText(/Sincronização concluída/).waitFor();
  step("cliente real conectado e sincronizado");

  // importação de pedidos e leads
  await nav("Inteligência comercial");
  await page.getByText(/Nenhum lead do CRM no período/).waitFor();
  await page.getByLabel("Arquivo CSV").setInputFiles({ name: "pedidos.csv", mimeType: "text/csv", buffer: Buffer.from(orders) });
  await page.getByRole("button", { name: "Pré-visualizar" }).click();
  await page.getByText(/60.*de 61 linha\(s\) prontas/).waitFor();
  await page.getByText("Descartadas por conterem dados pessoais: Nome, Telefone").waitFor();
  await page.getByText(/campanha-perdida \(1\)/).waitFor();
  await shot("p5-1-previa");
  await page.getByRole("button", { name: "Confirmar importação" }).click();
  await page.getByText("Importação concluída: 60 linha(s).").waitFor();
  await page.getByLabel("Tipo").selectOption("leads");
  await page.getByLabel("Arquivo CSV").setInputFiles({ name: "leads.csv", mimeType: "text/csv", buffer: Buffer.from(leads) });
  await page.getByRole("button", { name: "Pré-visualizar" }).click();
  await page.getByText("Descartadas por conterem dados pessoais: Nome").waitFor();
  await page.getByRole("button", { name: "Confirmar importação" }).click();
  await page.getByText(/Funil \(30 leads\)/).waitFor();
  await page.getByText("50 min").first().waitFor();
  await shot("p5-2-comercial");
  step("pedidos e leads importados sem dados pessoais; funil e tempo de resposta");

  await nav("Visão geral");
  const cac = await page.locator("section:visible").filter({ has: page.getByText("CAC real", { exact: true }) }).first().locator("p").nth(1).textContent();
  assert.notEqual(cac, "—", "CAC real deve aparecer depois da importação de vendas");
  step(`CAC real destravado: ${cac}`);

  // Tracking & CRO
  await nav("Tracking & CRO");
  await page.getByText("Vendas sem campanha identificada na última importação").waitFor();
  await page.getByText("studio-eng-wpp-pilates").first().waitFor();
  await page.getByLabel("Endereço da página").fill("https://dominio-que-nao-existe.invalid/");
  await page.getByRole("button", { name: "Verificar" }).click();
  await page.getByRole("alert").filter({ hasText: "domínio" }).waitFor();
  await shot("p5-3-tracking");
  step("auditoria aponta UTM sem correspondência; UTMs sugeridas; domínio inexistente tratado");

  // escrita real
  await nav("Clientes e contas");
  page.once("dialog", (dlg) => dlg.accept(name));
  await page.getByRole("row").filter({ hasText: name }).getByRole("button", { name: "Ligar escrita real" }).click();
  await page.getByRole("row").filter({ hasText: name }).getByText("Escrita real ligada").waitFor();
  step("escrita real ligada com confirmação pelo nome do cliente");

  await nav("Central de inteligência");
  await page.getByLabel("Pergunta ao Borges Core").fill("Vale escalar alguma campanha?");
  await page.getByRole("button", { name: "Analisar" }).click();
  await page.locator("article:visible").filter({ hasText: "Escalar" }).first().waitFor();
  await page.locator("article:visible").filter({ hasText: "Reduzir o tempo de primeira resposta" }).first().waitFor();
  await nav("Central de aprovação");
  const scale = page.locator("article:visible").filter({ hasText: "Escalar" }).first();
  await scale.getByText("executado pelo Windsor.ai somente se a escrita real estiver ligada").waitFor();
  await scale.getByRole("button", { name: "Aprovar e executar" }).click();
  await page.getByRole("tab", { name: /Histórico/ }).click();
  const done = page.locator("article:visible").filter({ hasText: "Escalar" }).first();
  await done.getByText("Concluída", { exact: true }).waitFor();
  await done.getByRole("button").first().click();
  await done.getByText(/real \(Windsor\.ai\).*verificada por releitura/).waitFor();
  await done.getByText(/set_campaign_budget na conta 1000000000000001/).waitFor();
  await shot("p5-4-execucao-real");
  step("aumento de orçamento aprovado, enviado ao Windsor.ai (falso) e verificado por releitura");

  assert.deepEqual(errors, []);
  await browser.close();
  console.log("\nFase 5: fluxo verificado no navegador (contra o Windsor.ai falso).");
})().catch((e) => { console.error("\n✕ FALHOU:", e.message); process.exit(1); });
