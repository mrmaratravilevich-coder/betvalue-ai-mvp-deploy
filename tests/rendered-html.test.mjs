import assert from "node:assert/strict";
import test from "node:test";

async function render() {
  const workerUrl = new URL("../dist/server/index.js", import.meta.url);
  workerUrl.searchParams.set("test", `${process.pid}-${Date.now()}`);
  const { default: worker } = await import(workerUrl.href);

  return worker.fetch(
    new Request("http://localhost/", { headers: { accept: "text/html" } }),
    { ASSETS: { fetch: async () => new Response("Not found", { status: 404 }) } },
    { waitUntil() {}, passThroughOnException() {} },
  );
}

async function renderPath(pathname) {
  const workerUrl = new URL("../dist/server/index.js", import.meta.url);
  workerUrl.searchParams.set("test", `${process.pid}-${Date.now()}-${pathname}`);
  const { default: worker } = await import(workerUrl.href);
  return worker.fetch(
    new Request(`http://localhost${pathname}`, { headers: { accept: "text/html" } }),
    { ASSETS: { fetch: async () => new Response("Not found", { status: 404 }) } },
    { waitUntil() {}, passThroughOnException() {} },
  );
}

test("server-renders the public BetValue AI experience", async () => {
  const response = await render();
  assert.equal(response.status, 200);
  assert.match(response.headers.get("content-type") ?? "", /^text\/html\b/i);

  const html = await response.text();
  assert.match(html, /<title>BetValue AI — спортивная аналитика<\/title>/i);
  assert.match(html, /Матчи — в одном месте/);
  assert.match(html, /Загружаем матчи/);
  assert.match(html, /Вероятность показывает расклад/);
  assert.match(html, /https:\/\/t\.me\/BetValueAI_bot/);
  assert.doesNotMatch(html, /football-data\.org|API-SPORTS|Документация API|PUBLIC API|АРХИТЕКТУРА MVP/i);
  assert.doesNotMatch(html, /54%|68%|Manchester Utd|ожидаем линию/i);
});

test("server-renders a dedicated match analysis route", async () => {
  const response = await renderPath("/matches/1");
  assert.equal(response.status, 200);
  const html = await response.text();
  assert.match(html, /Загружаем разбор матча/);
  assert.match(html, /Сверяем расписание и последнюю версию модели/);
});
