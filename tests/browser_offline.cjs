/* Verificação real de file://, rede desligada e downloads. Sem dependência no ZIP. */
"use strict";
const fs = require("node:fs");
const path = require("node:path");
const {pathToFileURL} = require("node:url");
const assert = require("node:assert/strict");
const {chromium, expect} = require(process.env.RADAR_PLAYWRIGHT_MODULE);
const work = path.resolve(process.argv[2]);
const fixture = JSON.parse(fs.readFileSync(path.join(work, "expected.json"), "utf8"));
(async () => {
  const context = await chromium.launchPersistentContext(path.join(work, "perfil"), {
    headless: true, viewport: {width: 1440, height: 1100}, locale: "pt-BR",
    downloadsPath: work, acceptDownloads: true,
    args: ["--disable-background-networking", "--disable-sync", "--no-first-run"]
  });
  await context.setOffline(true);
  const page = await context.newPage();
  const errors = [], network = [];
  page.on("pageerror", error => errors.push(error.message));
  page.on("request", request => { if (/^https?:/.test(request.url())) network.push(request.url()); });
  let serial = 0;
  async function download(expected) {
    const event = page.waitForEvent("download");
    await page.locator("#download").click();
    const result = await event;
    const dest = path.join(work, `download-${serial++}.csv`);
    await result.saveAs(dest);
    assert.deepEqual(fs.readFileSync(dest), fs.readFileSync(path.join(work, expected)));
    assert.match(result.suggestedFilename(), /^radar-ipca-inpc-\d{4}-\d\d-a-\d{4}-\d\d\.csv$/);
  }
  try {
    await page.goto(pathToFileURL(process.env.RADAR_DEMO_HTML || path.join(work, "Pasta com espaços", "ABRIR-DEMONSTRACAO.html")).href);
    await expect(page.locator("#results")).toBeVisible();
    assert.ok(page.url().startsWith("file:///"));
    await expect(page.locator("#rows tr")).toHaveCount(12);
    await page.screenshot({path: path.join(work, "desktop.png"), fullPage: true});
    for (const entry of fixture.cases) {
      await page.locator("#start").selectOption(entry.start);
      await page.locator("#end").selectOption(entry.end);
      for (const measure of Object.keys(entry.measures)) {
        await page.locator("#measure").selectOption(measure);
        await expect(page.locator("#error")).toBeHidden();
        await expect(page.locator("#rows tr")).toHaveCount(entry.count);
        assert.deepEqual(await page.locator("#rows tr").evaluateAll(rows => rows.map(tr => [...tr.children].slice(1).map(td => td.textContent))), entry.measures[measure]);
        const last = entry.measures[measure].at(-1);
        await expect(page.locator("#ipca-value")).toHaveText(last[0]);
        await expect(page.locator("#inpc-value")).toHaveText(last[1]);
        await expect(page.locator("#diff-value")).toHaveText(last[2]);
        await expect(page.locator("#evolution [data-point]")).toHaveCount(entry.count * 2);
        await expect(page.locator("#difference [data-value]")).toHaveCount(entry.count);
        assert.ok(await page.locator("#difference svg").evaluate(svg => {
          const grid = svg.querySelector("line");
          const left = Number(grid.getAttribute("x1")), right = Number(grid.getAttribute("x2"));
          return [...svg.querySelectorAll("rect[data-value]")].every(rect => {
            const box = rect.getBBox(); return box.x >= left && box.x + box.width <= right;
          });
        }), "As barras devem ficar dentro da área de dados, sem cobrir o eixo vertical.");
        assert.ok(!(await page.locator("#difference svg text").allTextContents()).includes("-0,00"));
        assert.ok(await page.locator("#evolution [data-point]").evaluateAll(nodes => nodes.every(n => Number.isFinite(n.cx.baseVal.value) && Number.isFinite(n.cy.baseVal.value) && n.r.baseVal.value > 0)));
        assert.ok(await page.locator("#difference [data-value]").evaluateAll(nodes => nodes.every(n => Number(n.dataset.value) === 0 || n.getAttribute("fill") === (Number(n.dataset.value) < 0 ? "#a74337" : "#245ca5"))));
        if (entry === fixture.cases[0] || measure === "monthly") await download(entry.csv);
      }
    }
    // Um intervalo invertido remove resultados antigos e bloqueia a exportação.
    await page.locator("#measure").selectOption("twelve_month");
    await page.locator("#end").selectOption("2024-03");
    await page.locator("#start").selectOption("2024-04");
    await expect(page.locator("#error")).toBeVisible();
    await expect(page.locator("#results")).toBeHidden();
    await expect(page.locator("#download")).toBeDisabled();
    await page.locator("#start").selectOption("2024-01");
    await expect(page.locator("#measure")).toHaveValue("twelve_month");
    await expect(page.locator("#measure-title")).toHaveText("Acumulado em 12 meses");
    await expect(page.locator("#download")).toBeEnabled();
    // Detalhe acessível pelo teclado, além do clique no gráfico.
    await page.locator("#detail-month").selectOption("2024-03");
    await page.locator("#detail-month").focus();
    await page.keyboard.press("ArrowUp");
    await expect(page.locator("#detail-month")).toHaveValue("2024-02");
    await expect(page.locator('#rows tr[data-period="2024-02"]')).toHaveClass("selected");
    await page.locator('#evolution [data-month="2024-01"]').click();
    await expect(page.locator("#detail-month")).toHaveValue("2024-01");
    // Atalhos mantêm a medida e o CSV do mesmo recorte.
    await page.locator("#all").click();
    await expect(page.locator("#rows tr")).toHaveCount(82);
    await page.locator("#last-year").click();
    await expect(page.locator("#rows tr")).toHaveCount(12);
    await expect(page.locator("#measure")).toHaveValue("twelve_month");
    for (const width of [390, 320]) {
      await page.setViewportSize({width, height: 900});
      await page.locator("#measure").selectOption("monthly");
      await expect(page.locator("#evolution svg")).toBeVisible();
      assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), `Transbordamento a ${width}px`);
      await page.locator("#start").selectOption("2026-10");
      await expect(page.locator("#rows tr")).toHaveCount(1);
      await download("single.csv");
      await page.locator("#last-year").click();
      if (width === 390) await page.screenshot({path: path.join(work, "mobile.png"), fullPage: true});
    }
    // Um caso sintético com diferenças iguais a zero preserva linha e valores.
    await page.goto(pathToFileURL(path.join(work, "zero.html")).href);
    await page.locator("#measure").selectOption("year_to_date");
    await expect(page.locator("#diff-value")).toHaveText("0,00");
    await expect(page.locator('#difference [data-value]')).toHaveCount(1);
    await download("zero.csv");
    assert.deepEqual(errors, []);
    assert.deepEqual(network, []);
    fs.writeFileSync(path.join(work, "browser-result.json"), JSON.stringify({
      passed:true, downloads:serial, networkRequests:network.length, javascriptErrors:errors.length,
      viewportWidths:[1440,390,320], fileProtocol:true, offline:true
    }, null, 2));
    console.log("OFFLINE_BROWSER_OK " + serial + " downloads idênticos ao CSV Python; 0 requisições; 0 erros JavaScript.");
  } catch (error) {
    await page.screenshot({path:path.join(work, "failure.png"), fullPage:true});
    console.error(JSON.stringify({errors, network, downloadsCompleted: serial}));
    throw error;
  } finally { await context.close(); }
})().catch(error => { console.error(error.stack); process.exitCode = 1; });
