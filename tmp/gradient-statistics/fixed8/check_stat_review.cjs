const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const { pathToFileURL } = require("node:url");
const { chromium } = require("../../multimetric-review-20261118/work/node_modules/playwright");

async function main() {
  const target = path.resolve("metric/gradient-statistics/review.html");
  const csvPath = path.resolve("metric/gradient-statistics/statistical-screen.csv");
  const raw = fs.readFileSync(csvPath,"utf8").trim().replace(/^\uFEFF/,"").split(/\r?\n/);
  const header = raw[0].split(",");
  // The statistical summary stores numeric scalars, paths and fixed keys here.
  const expected = raw.slice(1).map(line=>Object.fromEntries(line.split(",").map((v,i)=>[header[i],v])));
  const browser = await chromium.launch({executablePath:"C:/Program Files/Google/Chrome/Application/chrome.exe",headless:true});
  try {
    const context = await browser.newContext({offline:true,viewport:{width:1280,height:800}});
    const page = await context.newPage(), errors=[], network=[];
    page.on("pageerror",e=>errors.push(e.message));
    page.on("request",r=>{if(r.url().startsWith("http"))network.push(r.url())});
    await page.goto(pathToFileURL(target).href);
    const readIds=async()=>await page.locator("#rows>tr[data-id]").evaluateAll(rows=>rows.map(r=>Number(r.dataset.id)));
    const initial=await readIds();
    assert.equal(initial.length,50); assert.equal(initial[0],698);
    const data=await page.evaluate(()=>JSON.parse(document.querySelector("#dataset").textContent));
    const gradientCSV=fs.readFileSync(path.resolve("metric/gradient-statistics/gradient-candidates.csv"),"utf8").trim().replace(/^\uFEFF/,"").split(/\r?\n/);
    const ghead=gradientCSV.shift().split(",");
    const grad=gradientCSV.map(line=>line.split(","));
    const gi=ghead.indexOf("id"),gp=ghead.indexOf("original_largest_gradient_component_pct");
    for (const s of data.rows) {
      const matching=expected.find(r=>Number(r.id)===s.id);
      assert.equal(s.p,Number(matching.p_any)); assert.equal(s.holm,Number(matching.p_any_holm50));
      assert.equal(s.fams.length,5); assert.equal(s.family,matching.strongest_family);
      assert.equal(grad[s.gradient_rank-1][gi],String(s.id).padStart(4,"0"));
      assert.equal(s.component,Number(grad[s.gradient_rank-1][gp]));
    }
    await page.selectOption("#order","gradient");
    assert.deepEqual(await readIds(),grad.map(row=>Number(row[gi])));
    assert.deepEqual((await readIds()).slice(0,4),[698,132,755,544]);
    assert.ok((await page.locator('tr[data-id="698"]').textContent()).includes("6.630%"));
    await page.check("#strict");
    assert.deepEqual((await readIds()).sort((a,b)=>a-b),expected.filter(s=>s.qualifies_both_0p1==="1").map(s=>Number(s.id)).sort((a,b)=>a-b));
    await page.click("#reset"); await page.selectOption("#order","reverse");
    const reversed=await readIds();
    assert.equal(reversed[49],698);
    await page.selectOption("#family","flat_steps"); await page.selectOption("#direction","A_worse"); await page.fill("#query","0698");
    assert.deepEqual(await readIds(),[698]); await page.click("#rows tr[data-id] button");
    assert.equal(await page.locator(".details table tr").count(),6);
    const deep=await page.locator("#rows tr[data-id] a").getAttribute("href");
    assert.ok(deep.endsWith("#0698/a/platform"));
    await page.click("#reset"); await page.fill("#query","not-a-real-asset"); assert.equal((await readIds()).length,0);
    await page.click("#reset"); await page.locator('tr[data-id="698"] a').click(); await page.waitForURL("**/gradient-screen-50/review.html#0698/a/platform");
    await page.waitForFunction(()=>document.querySelector("#choose").value==="698" || document.querySelector("#choose").selectedOptions[0]?.text.includes("0698"));
    assert.deepEqual(errors,[]);assert.deepEqual(network,[]);
    console.log("Offline Chrome: 50 image rows / 250 family rows, fifty original-area values and area ordering, strict filter, combined filters, per-family details and live gallery deep link passed. Zero JS errors and network requests.");
  } finally { await browser.close(); }
}
main().catch(e=>{console.error(e);process.exitCode=1});
