/* Nenhuma página pode ter rolagem horizontal, no computador (1440 px) nem no celular (390 px).
 * Uso: E2E_EMAIL=... E2E_PASSWORD=... node e2e/layout.cjs */
const { chromium } = require("playwright");
const BASE = process.env.E2E_BASE_URL || "http://localhost:3000";
(async () => {
  const b = await chromium.launch();
  const bad = [];
  for (const [w, h] of [[1440, 900], [390, 844]]) {
    const p = await b.newPage({ viewport: { width: w, height: h } });
    await p.goto(BASE + "/login");
    await p.getByLabel("Login").fill(process.env.E2E_EMAIL);
    await p.getByLabel("Senha").fill(process.env.E2E_PASSWORD);
    await p.getByRole("button", { name: "Entrar" }).click();
    await p.waitForURL(BASE + "/");
    for (const route of ["/", "/clientes", "/inteligencia", "/campanhas", "/aprovacoes", "/criativos", "/experimentos", "/radar", "/comercial", "/tracking", "/auditoria", "/configuracoes"]) {
      await p.goto(BASE + route);
      await p.waitForLoadState("networkidle");
      await p.waitForTimeout(400);
      const over = await p.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
      if (over > 0) bad.push(`${w}px ${route}: +${over}px`);
    }
    await p.close();
  }
  console.log(bad.length ? "ROLAGEM HORIZONTAL:\n" + bad.join("\n") : "Nenhuma página com rolagem horizontal (1440 e 390 px).");
  if (bad.length) process.exitCode = 1;
  await b.close();
})();
