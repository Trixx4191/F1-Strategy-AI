/** Browser smoke checks for the bundled Bahrain demo.
 * npm install --prefix /tmp/f1-ui-browser playwright
 * NODE_PATH=/tmp/f1-ui-browser/node_modules node scripts/smoke_ui.cjs URL
 * Uses installed Chromium; override CHROMIUM_PATH if needed.
 * Writes screenshots and the downloaded CSV under UI_ARTIFACT_DIR or /tmp/f1-ui-check.
 */
const { chromium } = require("playwright");
const assert = require("node:assert/strict");
const fs = require("node:fs/promises");
const base = (process.argv[2] || "http://127.0.0.1:8000").replace(/\/$/, "");
const artifacts = process.env.UI_ARTIFACT_DIR || "/tmp/f1-ui-check";
(async () => {
  await fs.mkdir(artifacts, { recursive: true });
  const browser = await chromium.launch({
    executablePath: process.env.CHROMIUM_PATH || "/usr/bin/chromium",
    headless: true,
    args: ["--no-sandbox"],
  });
  const page = await browser.newPage({
    viewport: { width: 1440, height: 1050 },
    deviceScaleFactor: 1,
  });
  const errors = [],
    posts = [],
    failures = [];
  page.on("pageerror", (e) => errors.push(e.message));
  page.on("request", (r) => {
    if (r.method() === "POST") posts.push(r.url());
  });
  page.on("response", (r) => {
    if (r.status() >= 400 && r.url().startsWith(base))
      failures.push(`${r.status()} ${r.url()}`);
  });
  const nav = (label) => {
    console.log("tab", label);
    return page
      .getByRole("navigation")
      .getByRole("button", { name: label, exact: true })
      .click();
  };
  const noOverflow = async (label) =>
    assert.ok(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
      `${label}: horizontal page overflow`,
    );
  await page.goto(base);
  await page.getByText("Lowest expected race time", { exact: true }).waitFor();
  assert.match(
    await page.locator(".stint-plan").innerText(),
    /SOFT\nL1–20\nHARD\nL21–38\nHARD\nL39–57/,
  );
  assert.equal(
    posts.length,
    0,
    "initial load must not start expensive requests",
  );
  await page.screenshot({
    path: `${artifacts}/f1-overview-desktop.png`,
    fullPage: true,
  });
  await page.getByRole("button", { name: "Save run", exact: true }).click();
  await page
    .getByText("Run saved in this browser.", { exact: false })
    .waitFor();
  await nav("Results");
  assert.equal(await page.locator("tbody tr").count(), 30);
  await page.getByRole("button", { name: "Next", exact: true }).click();
  assert.equal(
    await page.locator("tbody tr").first().locator("td").first().innerText(),
    "31",
  );
  await page.getByLabel("Search strategies").fill("impossible-compound");
  await page.getByText("No matching strategies.", { exact: false }).waitFor();
  await page.getByLabel("Search strategies").fill("");
  await page.getByRole("main").getByRole("combobox").selectOption("1");
  assert.equal(await page.locator("tbody tr").count(), 30);
  assert.ok(
    (
      await page.locator("tbody tr").first().locator("td").nth(2).innerText()
    ).indexOf("/") === -1,
  );
  const downloadPromise = page.waitForEvent("download");
  await page.getByRole("button", { name: "Download all results CSV" }).click();
  const download = await downloadPromise;
  await download.saveAs(`${artifacts}/f1-ui-results.csv`);
  assert.equal(
    (await fs.readFile(`${artifacts}/f1-ui-results.csv`, "utf8"))
      .trim()
      .split("\n").length,
    2773,
  );
  assert.match(
    await fs.readFile(`${artifacts}/f1-ui-results.csv`, "utf8"),
    /SOFT→HARD→HARD/,
  );
  for (const label of [
    "Strategy",
    "Tyres",
    "Pit windows",
    "Rival analysis",
    "Backtest",
    "Saved runs",
    "Overview",
  ]) {
    await nav(label);
    await noOverflow(`desktop ${label}`);
  }
  assert.equal(
    posts.length,
    0,
    "browsing completed results must not launch calculations",
  );
  await page.getByLabel("Driver", { exact: true }).selectOption("NOR");
  await page.locator(".settings-notice").waitFor();
  assert.match(
    await page.locator(".recommendation .panel-header").innerText(),
    /VER/,
  );
  assert.equal(
    await page
      .getByRole("button", { name: "Save run", exact: true })
      .isDisabled(),
    true,
  );
  await page.getByLabel("Pit stops", { exact: true }).selectOption("1-stop");
  await page.locator("#iterations").fill("100");
  console.log("fresh simulation");
  await page
    .getByRole("button", { name: "Run simulation", exact: true })
    .click();
  await page.waitForFunction(
    () =>
      document
        .querySelector(".run-status")
        ?.textContent?.includes("NOR · 100 iterations"),
    { timeout: 120000 },
  );
  await page.locator(".settings-notice").waitFor({ state: "hidden" });
  assert.match(
    await page.locator(".recommendation .panel-header").innerText(),
    /NOR/,
  );
  await page.getByRole("button", { name: "Save run", exact: true }).click();
  await nav("Saved runs");
  assert.equal(await page.locator(".saved-run-row").count(), 2);
  for (const checkbox of await page
    .locator('.saved-run-row input[type="checkbox"]')
    .all())
    await checkbox.check();
  await page.getByRole("button", { name: "Compare selected (2)" }).click();
  await page.locator("#saved-compare-panel").waitFor();
  await page.screenshot({
    path: `${artifacts}/f1-saved-desktop.png`,
    fullPage: true,
  });
  await page.getByRole("button", { name: "Load", exact: true }).last().click();
  assert.match(
    await page.locator(".run-status").innerText(),
    /VER · 500 iterations/,
  );
  await nav("Rival analysis");
  const rivalRequest = page.waitForResponse(
    (r) =>
      r.url().endsWith("/api/rival-analysis") &&
      r.request().method() === "POST",
    { timeout: 120000 },
  );
  await page
    .getByRole("button", { name: "Run rival analysis", exact: true })
    .click();
  assert.equal((await rivalRequest).status(), 200);
  await page.getByText("Model comparison", { exact: true }).waitFor();
  await page.screenshot({
    path: `${artifacts}/f1-rival-desktop.png`,
    fullPage: true,
  });
  await nav("Backtest");
  await page.getByText("Illustrative race replay", { exact: true }).click();
  await page.getByRole("button", { name: "Play", exact: true }).click();
  await page.getByRole("button", { name: "Pause", exact: true }).click();
  for (const width of [1024, 768, 390, 320]) {
    await page.setViewportSize({ width, height: 844 });
    for (const label of [
      "Overview",
      "Strategy",
      "Tyres",
      "Pit windows",
      "Rival analysis",
      "Backtest",
      "Results",
      "Saved runs",
    ]) {
      await nav(label);
      await noOverflow(`${width}px ${label}`);
      if (width === 390)
        await page.screenshot({
          path: `${artifacts}/f1-${label.toLowerCase().replaceAll(" ", "-")}-mobile.png`,
          fullPage: true,
        });
    }
  }
  await page.setViewportSize({ width: 390, height: 844 });
  await nav("Overview");
  assert.equal(
    await page.getByLabel("Driver", { exact: true }).isVisible(),
    false,
  );
  await page.getByRole("button", { name: "Settings", exact: true }).click();
  await page
    .getByLabel("Driver", { exact: true })
    .waitFor({ state: "visible" });
  await noOverflow("mobile settings");
  await page.screenshot({
    path: `${artifacts}/f1-settings-mobile.png`,
    fullPage: true,
  });
  await page.getByRole("button", { name: "Close settings" }).click();
  await page.reload();
  await page.waitForFunction(() =>
    document
      .querySelector(".run-status")
      ?.textContent?.includes("VER · 500 iterations"),
  );
  await page.getByText("Lowest expected race time", { exact: true }).waitFor();
  assert.match(
    await page.locator(".run-status").innerText(),
    /VER · 500 iterations/,
  );
  assert.equal(errors.length, 0, JSON.stringify(errors));
  assert.equal(failures.length, 0, JSON.stringify(failures));
  console.log(
    JSON.stringify(
      {
        result: "PASS",
        checks: [
          "ordered stints",
          "no background calculations",
          "results filtering and pagination",
          "full CSV download",
          "saved runs and comparison",
          "stale result warning",
          "fresh simulation",
          "rival analysis",
          "replay controls",
          "8 tabs at 4 widths",
          "mobile settings",
          "reload persistence",
        ],
        posts,
        errors,
        failures,
      },
      null,
      2,
    ),
  );
  await browser.close();
})().catch((error) => {
  console.error(error);
  process.exit(1);
});
