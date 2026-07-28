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

test("server-renders the public BetValue AI experience", async () => {
  const response = await render();
  assert.equal(response.status, 200);
  assert.match(response.headers.get("content-type") ?? "", /^text\/html\b/i);

  const html = await response.text();
  assert.match(html, /<title>BetValue AI — спортивная аналитика<\/title>/i);
  assert.match(html, /Расписание уже live/);
  assert.match(html, /Загружаем матчи/);
  assert.match(html, /football-data\.org/);
  assert.match(html, /API-SPORTS/);
  assert.match(html, /MELBET API/);
  assert.match(html, /MELBET × BETVALUE AI/);
  assert.match(html, /Партнёрство подтверждено/);
  assert.match(html, /Интеграция ещё не запущена/);
  assert.match(html, /ПАРТНЁР · API ОЖИДАЕТСЯ/);
  assert.match(html, /следующий релиз/i);
  assert.match(html, /https:\/\/t\.me\/BetValueAI_bot/);
  assert.doesNotMatch(html, /54%|68%|Manchester Utd|ожидаем линию/);
});
