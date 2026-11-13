// Record real provider behavior against disposable data; never expose credentials on screen.
import { chromium } from '../frontend/node_modules/playwright/index.mjs';
import { readFile, writeFile, copyFile, mkdir } from 'node:fs/promises';
import assert from 'node:assert/strict';
import { performance } from 'node:perf_hooks';

const runtime = JSON.parse(await readFile('.leancode/demo-recording/runtime.json', 'utf8'));
const out = 'output/video';
await mkdir(`${out}/raw`, { recursive: true });
const browser = await chromium.launch({ headless: true, executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE });
const context = await browser.newContext({ viewport: { width: 1280, height: 720 }, reducedMotion: 'reduce', recordVideo: { dir: `${out}/raw`, size: { width: 1280, height: 720 } } });
await context.addInitScript(({ url, token }) => {
  if (location.origin === url && !sessionStorage.getItem('leancode-token')) sessionStorage.setItem('leancode-token', token);
}, runtime);
const page = await context.newPage();
page.setDefaultTimeout(120000);
const start = performance.now(), chapters = [], evidence = {};
const pause = seconds => page.waitForTimeout(seconds * 1000);
async function chapter(id) {
  chapters.push({ id, start: (performance.now() - start) / 1000 });
  await writeFile(`${out}/chapters.json`, JSON.stringify(chapters, null, 2));
  console.log(`Recording: ${id}`);
}
async function sessions(token = runtime.token) {
  const response = await fetch(`${runtime.url}/api/bootstrap`, { headers: { Authorization: `Bearer ${token}` } });
  assert.equal(response.status, 200);
  return (await response.json()).sessions;
}
async function latest(token = runtime.token) {
  const list = await sessions(token);
  const response = await fetch(`${runtime.url}/api/sessions/${list[0].id}`, { headers: { Authorization: `Bearer ${token}` } });
  return response.json();
}
async function awaitState(status) {
  let retries = 0;
  const deadline = performance.now() + 180000;
  while (performance.now() < deadline) {
    const session = await latest();
    if (session.status === status) { await page.reload(); return; }
    if (session.status === 'blocked') {
      assert.ok(retries++ < 2 && session.events.some(e => /unavailable|HTTP 50[234]/.test(e.data.message || '')), 'Only resume temporary provider failures');
      evidence.recoveredProviderError = true;
      await page.reload();
      await pause(5);
      await page.getByRole('button', { name: 'Resume saved session' }).click();
    }
    await pause(2);
  }
  throw new Error(`Agent did not reach ${status} within the bounded recording window`);
}
try {
  await chapter('welcome');
  await page.goto(runtime.url);
  await page.getByRole('heading', { name: 'Your code. Every token counts.' }).waitFor();
  await pause(7);
  await chapter('repositories');
  await page.getByRole('navigation').getByRole('button', { name: 'Repositories', exact: true }).click();
  await pause(7);
  await page.getByRole('button', { name: /demo-python Public workspace/ }).click();
  await chapter('task');
  await page.getByLabel('Coding task').fill('Fix the zero-boundary bug in maths.py. First use the approved python-unittest documentation topic, then inspect code and tests. Propose the smallest patch. After approval, run python -m unittest discover -s tests -v.');
  await pause(6);
  await page.getByRole('button', { name: 'Run agent', exact: true }).click();
  await awaitState('awaiting_approval');
  await chapter('patch');
  let session = await latest();
  const patch = session.actions.find(a => a.kind === 'patch' && a.status === 'pending');
  assert.ok(patch?.payload.diff.includes('-    return value >= 0'));
  assert.ok(patch.payload.diff.includes('+    return value > 0'));
  assert.match(await readFile(`${runtime.data_dir}/demo-python/maths.py`, 'utf8'), />= 0/);
  await page.screenshot({ path: `${out}/patch.png` });
  await pause(10);
  await page.getByRole('button', { name: 'Approve patch', exact: true }).click();
  await pause(2);
  await awaitState('awaiting_approval');
  await chapter('command');
  session = await latest();
  assert.deepEqual(session.actions.find(a => a.kind === 'command' && a.status === 'pending').payload.command, ['python', '-m', 'unittest', 'discover', '-s', 'tests', '-v']);
  await pause(8);
  await page.getByRole('button', { name: 'Approve command', exact: true }).click();
  await pause(2);
  await awaitState('completed');
  await chapter('result');
  session = await latest();
  assert.ok(session.state.verified_snapshot);
  assert.ok(session.events.some(e => e.data.output && /Ran [1-9]\d* tests?/.test(e.data.output)));
  evidence.completed = session;
  await writeFile(`${out}/evidence.json`, JSON.stringify(evidence, null, 2));
  const outputs = page.locator('details').filter({ hasText: /Ran [1-9]\d* tests?/ });
  await outputs.last().locator('summary').click();
  await outputs.last().scrollIntoViewIfNeeded();
  await page.screenshot({ path: `${out}/result.png` });
  await pause(12);
  await chapter('privacy');
  await page.getByRole('button', { name: 'New task', exact: true }).click();
  await page.getByLabel('Repository', { exact: true }).selectOption('confidential-demo');
  await page.getByLabel('Coding task').fill('Inspect this confidential repository and propose a boundary fix.');
  await pause(4);
  await page.getByRole('button', { name: 'Run agent', exact: true }).click();
  await page.locator('.execution-status').filter({ hasText: 'blocked' }).waitFor();
  evidence.privacy = await latest();
  await writeFile(`${out}/evidence.json`, JSON.stringify(evidence, null, 2));
  assert.equal(evidence.privacy.state.model_calls || 0, 0);
  assert.equal(evidence.privacy.state.cost_micro || 0, 0);
  await page.screenshot({ path: `${out}/privacy.png` });
  await pause(10);
  await chapter('budget');
  await page.evaluate(token => { sessionStorage.setItem('leancode-token', token); localStorage.removeItem('leancode-session'); }, runtime.budget_token);
  await page.reload();
  await page.getByLabel('Repository', { exact: true }).selectOption('demo-python');
  await page.getByLabel('Coding task').fill('Add a focused test for fractional positive values.');
  await pause(4);
  await page.getByRole('button', { name: 'Run agent', exact: true }).click();
  await page.locator('.execution-status').filter({ hasText: 'blocked' }).waitFor();
  evidence.budget = await latest(runtime.budget_token);
  assert.ok(evidence.budget.events.some(e => /Budget exhausted/.test(e.data.message || '')));
  assert.equal(evidence.budget.state.model_calls || 0, 0);
  assert.equal(evidence.budget.state.cost_micro || 0, 0);
  await page.screenshot({ path: `${out}/budget.png` });
  await pause(10);
  await chapter('benchmarks');
  await page.getByRole('navigation').getByRole('button', { name: 'Token benchmarks', exact: true }).click();
  await page.getByRole('heading', { name: 'Token savings need evidence.' }).waitFor();
  await pause(8);
  await chapter('end');
  await writeFile(`${out}/chapters.json`, JSON.stringify(chapters, null, 2));
  await writeFile(`${out}/evidence.json`, JSON.stringify(evidence, null, 2));
} finally {
  await context.close();
  await copyFile(await page.video().path(), `${out}/leancode-demo-raw.webm`);
  await browser.close();
}
