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
  const visibleText = html
    .replace(/<script\b[^>]*>[\s\S]*?<\/script>/gi, " ")
    .replace(/<style\b[^>]*>[\s\S]*?<\/style>/gi, " ")
    .replace(/<[^>]+>/g, " ");
  assert.match(html, /<title>BetValue AI — спортивная аналитика<\/title>/i);
  assert.match(html, /<link rel="canonical" href="https:\/\/bvai\.onrender\.com\/"/i);
  assert.match(html, /<meta property="og:url" content="https:\/\/bvai\.onrender\.com\/"/i);
  assert.match(html, /<meta property="og:image" content="https:\/\/bvai\.onrender\.com\/og\.png"/i);
  assert.match(html, /Матчи — в одном месте/);
  assert.match(html, /Загружаем матчи/);
  assert.match(html, /Аналитика — по делу/);
  assert.match(html, /Линия рядом с аналитикой/);
  assert.match(html, /Состояние линии/);
  assert.match(html, /есть расхождение/);
  assert.match(html, /ФУТБОЛ · ХОККЕЙ · БАСКЕТБОЛ/);
  assert.match(html, /https:\/\/t\.me\/BetValueAI_bot/);
  assert.doesNotMatch(html, /football-data\.org|API-SPORTS|Документация API|PUBLIC API|АРХИТЕКТУРА MVP/i);
  assert.doesNotMatch(visibleText, /бесплатн|Render|Запускаем сервер|Пробуждаем API/i);
  assert.doesNotMatch(html, /Poisson|Как считаем/i);
  assert.doesNotMatch(html, /54%|68%|Manchester Utd|ожидаем линию/i);
});

test("server-renders a dedicated match analysis route", async () => {
  const response = await renderPath("/matches/1");
  assert.equal(response.status, 200);
  const html = await response.text();
  assert.match(html, /Загружаем разбор матча/);
  assert.match(html, /Сверяем расписание и актуальность данных/);
});

test("server-renders the Telegram Mini App route", async () => {
  const response = await renderPath("/telegram");
  assert.equal(response.status, 200);
  const html = await response.text();
  const visibleText = html
    .replace(/<script\b[^>]*>[\s\S]*?<\/script>/gi, " ")
    .replace(/<style\b[^>]*>[\s\S]*?<\/style>/gi, " ")
    .replace(/<[^>]+>/g, " ");
  assert.match(html, /Главное перед игрой/);
  assert.match(html, /Ближайшие матчи/);
  assert.match(html, /Собираем матчи/);
  assert.match(html, /Базовый/);
  assert.match(html, /Расширенный/);
  assert.doesNotMatch(visibleText, /гарант|железн|выигрыш|Render/i);
});
