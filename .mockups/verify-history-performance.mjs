import { chromium } from "playwright";

const url = process.argv[2];
const output = process.argv[3];
if (!url || !output) throw new Error("usage: node verify-history-performance.mjs URL OUTPUT_DIR");

const browser = await chromium.launch({ headless: true });
const page = await browser.newPage({ viewport: { width: 1440, height: 1000 }, deviceScaleFactor: 1 });
const errors = [];
page.on("console", message => { if (message.type() === "error") errors.push(`console: ${message.text()}`); });
page.on("pageerror", error => errors.push(`pageerror: ${error.message}`));

await page.goto(url, { waitUntil: "networkidle" });
if ((await page.title()) !== "AI Caddie · 成绩信息架构联合稿") throw new Error("unexpected title");

const expected = ["home", "results", "trend", "archive", "analysis", "distribution", "review"];
for (const name of expected) {
  await page.locator(`.select-screen[data-view="${name}"]`).click();
  const visible = await page.locator(`.view[data-view="${name}"]`).evaluate(element => getComputedStyle(element).display !== "none");
  if (!visible) throw new Error(`${name}: selected view is hidden`);
  const activeViews = await page.locator(".view.on").count();
  if (activeViews !== 1) throw new Error(`${name}: expected exactly one active view, got ${activeViews}`);
  await page.locator(".phone").screenshot({ path: `${output}/${name}.png` });
}

for (const name of ["period", "calendar"]) {
  await page.locator('.select-screen[data-view="trend"]').click();
  await page.locator(`.view[data-view="trend"] [data-go="${name}"]`).click();
  const visible = await page.locator(`.view[data-view="${name}"]`).evaluate(element => getComputedStyle(element).display !== "none");
  if (!visible) throw new Error(`${name}: internal drill-down is hidden`);
  const activeViews = await page.locator(".view.on").count();
  if (activeViews !== 1) throw new Error(`${name}: expected exactly one active view, got ${activeViews}`);
  await page.locator(".phone").screenshot({ path: `${output}/${name}.png` });
}

await page.locator('.select-screen[data-view="trend"]').click();
for (const range of ["10", "20", "12m", "all"]) {
  await page.locator(`#range-seg [data-range="${range}"]`).click();
  const activeRange = await page.locator("#range-seg button.on").getAttribute("data-range");
  if (activeRange !== range) throw new Error(`range ${range}: not active`);
  const enabledGrains = await page.locator("#grain-seg button:not([disabled])").evaluateAll(nodes => nodes.map(node => node.dataset.grain));
  const expectedGrains = range === "10" || range === "20" ? ["round"] : range === "12m" ? ["round", "month", "quarter"] : ["month", "quarter", "year"];
  if (JSON.stringify(enabledGrains) !== JSON.stringify(expectedGrains)) throw new Error(`range ${range}: grains ${enabledGrains}`);
}

await page.locator('.select-screen[data-view="results"]').click();
await page.locator('.view[data-view="results"] [data-go="archive"]').first().click();
if (!(await page.locator('.view[data-view="archive"]').evaluate(element => element.classList.contains("on")))) throw new Error("results -> archive failed");
await page.locator('.view[data-view="archive"] [data-go="review"]').first().click();
if (!(await page.locator('.view[data-view="review"]').evaluate(element => element.classList.contains("on")))) throw new Error("archive -> review failed");

if (errors.length) throw new Error(errors.join("\n"));
console.log(JSON.stringify({ title: await page.title(), screens: expected.length + 2, rangeModes: 4, drillPath: "results>archive>review", errors: 0 }));
await browser.close();
