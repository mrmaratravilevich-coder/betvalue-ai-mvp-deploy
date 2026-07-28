"use client";

import { useEffect, useMemo, useState } from "react";

type SourceState = {
  football?: { ok: boolean; matches?: number };
  hockey?: { ok: boolean };
};

type Match = {
  id: number;
  league_id: number;
  league: {
    name: string;
    original_name?: string;
    sport: { code: string; name: string };
  };
  home_team: { name: string };
  away_team: { name: string };
  kickoff_at: string;
  status: string;
  home_score?: number | null;
  away_score?: number | null;
};

type ApiState = "loading" | "ready" | "error";
type SportFilter = "all" | "football" | "hockey";

type Prediction = {
  id: number;
  match_id: number;
  market: string;
  selection: string;
  model_probability: number;
  model_version: string;
  uncertainty?: number | null;
};

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
const TELEGRAM_URL = "https://t.me/BetValueAI_bot";

function formatKickoff(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "Время уточняется";

  return new Intl.DateTimeFormat("ru-RU", {
    day: "numeric",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
    timeZone: "Europe/Moscow",
  }).format(date);
}

function statusLabel(status: string) {
  const labels: Record<string, string> = {
    scheduled: "Запланирован",
    live: "В эфире",
    finished: "Завершён",
    postponed: "Перенесён",
    cancelled: "Отменён",
  };
  return labels[status.toLowerCase()] || status;
}

export default function Home() {
  const [state, setState] = useState<ApiState>("loading");
  const [sources, setSources] = useState<SourceState>({});
  const [matches, setMatches] = useState<Match[]>([]);
  const [predictions, setPredictions] = useState<Prediction[]>([]);
  const [sportFilter, setSportFilter] = useState<SportFilter>("all");
  const [leagueFilter, setLeagueFilter] = useState("all");
  const [coldStart, setColdStart] = useState(false);

  useEffect(() => {
    const controller = new AbortController();
    const coldTimer = window.setTimeout(() => setColdStart(true), 8000);
    const timeout = window.setTimeout(() => controller.abort(), 50000);

    Promise.all([
      fetch(`${API_URL}/health`, { signal: controller.signal }).then((response) => {
        if (!response.ok) throw new Error("API unavailable");
        return response.json();
      }),
      fetch(`${API_URL}/sources/health`, { signal: controller.signal }).then((response) => {
        if (!response.ok) throw new Error("Sources unavailable");
        return response.json();
      }),
      fetch(`${API_URL}/matches?limit=50`, { signal: controller.signal }).then((response) => {
        if (!response.ok) throw new Error("Matches unavailable");
        return response.json();
      }),
      fetch(`${API_URL}/predictions?limit=200`, { signal: controller.signal })
        .then((response) => response.ok ? response.json() : [])
        .catch(() => []),
    ])
      .then(([, sourceData, matchData, predictionData]) => {
        setSources(sourceData);
        setMatches(Array.isArray(matchData) ? matchData : []);
        setPredictions(Array.isArray(predictionData) ? predictionData : []);
        setState("ready");
      })
      .catch(() => setState("error"))
      .finally(() => {
        window.clearTimeout(coldTimer);
        window.clearTimeout(timeout);
      });

    return () => {
      window.clearTimeout(coldTimer);
      window.clearTimeout(timeout);
      controller.abort();
    };
  }, []);

  const onlineSources = useMemo(
    () => Number(Boolean(sources.football?.ok)) + Number(Boolean(sources.hockey?.ok)),
    [sources],
  );
  const systemOnline = state === "ready" && onlineSources > 0;
  const availableLeagues = useMemo(() => {
    const filtered = sportFilter === "all"
      ? matches
      : matches.filter((match) => match.league.sport.code === sportFilter);
    return [...new Map(filtered.map((match) => [match.league_id, match.league.name])).entries()];
  }, [matches, sportFilter]);
  const filteredMatches = useMemo(
    () => matches.filter((match) => (
      (sportFilter === "all" || match.league.sport.code === sportFilter)
      && (leagueFilter === "all" || String(match.league_id) === leagueFilter)
    )),
    [matches, sportFilter, leagueFilter],
  );
  const predictionsByMatch = useMemo(() => {
    const grouped = new Map<number, Prediction[]>();
    predictions.forEach((prediction) => {
      const current = grouped.get(prediction.match_id) || [];
      current.push(prediction);
      grouped.set(prediction.match_id, current);
    });
    return grouped;
  }, [predictions]);

  return (
    <main>
      <header className="topbar">
        <a className="brand" href="#top" aria-label="BetValue AI — главная">
          <span>BV</span>BetValue <b>AI</b>
        </a>
        <nav aria-label="Основная навигация">
          <a href="#matches">Матчи</a>
          <a href="#sources">Источники</a>
          <a href="#roadmap">Развитие</a>
        </nav>
        <a className="bot-pill" href={TELEGRAM_URL} target="_blank" rel="noreferrer">
          <i aria-hidden="true" /> Telegram
        </a>
      </header>

      <section className="hero" id="top">
        <div className="hero-copy">
          <div className="eyebrow">СПОРТИВНАЯ АНАЛИТИКА · PUBLIC BETA</div>
          <h1>Расписание уже live.<br /><em>Расчёт — в beta.</em></h1>
          <p>
            Единый поток футбольных и хоккейных данных с вероятностями модели Пуассона.
            Расчёт включается только при достаточной истории команд. Следующий слой —
            сравнение модели с разрешённым источником коэффициентов.
          </p>
          <div className="hero-actions">
            <a className="primary" href="#matches">Проверить матчи</a>
            <a className="secondary" href={TELEGRAM_URL} target="_blank" rel="noreferrer">
              Открыть Telegram <span aria-hidden="true">↗</span>
            </a>
          </div>
          <p className="hero-note"><i aria-hidden="true" /> Без ставок и автодействий — только данные и аналитика.</p>
        </div>

        <aside className={`pulse-card ${state === "error" ? "is-error" : ""}`} aria-live="polite">
          <div className="pulse-head">
            <span>Состояние системы</span>
            <b>{state === "loading" ? "CHECK" : systemOnline ? "LIVE" : "OFFLINE"}</b>
          </div>
          <div className="score">{state === "loading" ? "—" : onlineSources}<span>/2</span></div>
          <p>
            {state === "loading"
              ? coldStart ? "Пробуждаем API после паузы…" : "Проверяем источники…"
              : state === "error" ? "API временно не ответил" : "источника данных доступны"}
          </p>
          <div className="source-mini">
            <span>football-data.org</span>
            <strong>{state === "loading" ? "…" : sources.football?.ok ? "ONLINE" : "ERROR"}</strong>
          </div>
          <div className="source-mini">
            <span>API-SPORTS Hockey</span>
            <strong>{state === "loading" ? "…" : sources.hockey?.ok ? "ONLINE" : "ERROR"}</strong>
          </div>
        </aside>
      </section>

      <section className="metrics" aria-label="Статус проекта">
        <article>
          <small>ИСТОЧНИКИ</small>
          <strong>{state === "loading" ? "—" : `${onlineSources}/2`}</strong>
          <span>проверяются в реальном времени</span>
        </article>
        <article>
          <small>ВИДЫ СПОРТА</small>
          <strong>02</strong>
          <span>футбол · хоккей</span>
        </article>
        <article>
          <small>МАТЧИ В БАЗЕ</small>
          <strong>{state === "ready" ? String(matches.length).padStart(2, "0") : "—"}</strong>
          <span>до 50 ближайших событий API</span>
        </article>
        <article>
          <small>РЕЖИМ</small>
          <strong>BETA</strong>
          <span>открытое тестирование</span>
        </article>
      </section>

      <section className="match-section" id="matches">
        <div className="section-title">
          <div>
            <span>ДАННЫЕ ИЗ PUBLIC API</span>
            <h2>Матчи в потоке</h2>
          </div>
          <a className="text-link" href={`${API_URL}/docs`} target="_blank" rel="noreferrer">
            Документация API <span aria-hidden="true">↗</span>
          </a>
        </div>

        {state === "loading" && (
          <div className="state-panel" role="status">
            <div className="loader" aria-hidden="true" />
            <div>
              <h3>{coldStart ? "Запускаем сервер" : "Загружаем матчи"}</h3>
              <p>{coldStart ? "Бесплатный сервер Render может просыпаться до 50 секунд." : "Получаем свежий срез из API."}</p>
            </div>
          </div>
        )}

        {state === "error" && (
          <div className="state-panel error-panel" role="alert">
            <span className="state-code">503</span>
            <div>
              <h3>API пока не ответил</h3>
              <p>Обновите страницу через минуту или проверьте текущие матчи в Telegram.</p>
            </div>
            <button type="button" onClick={() => window.location.reload()}>Повторить</button>
          </div>
        )}

        {state === "ready" && matches.length === 0 && (
          <div className="empty-state">
            <div>
              <span className="state-code">00</span>
              <h3>Веб-база ждёт первую синхронизацию</h3>
            </div>
            <p>
              Подключения к football-data.org и API-SPORTS уже работают. Пока расписание
              не записано в веб-базу, бот получает ближайшие события напрямую у провайдеров.
            </p>
            <a className="primary" href={TELEGRAM_URL} target="_blank" rel="noreferrer">Матчи в Telegram</a>
          </div>
        )}

        {state === "ready" && matches.length > 0 && (
          <>
            <div className="match-filters" aria-label="Фильтры матчей">
              <div className="sport-tabs" role="group" aria-label="Вид спорта">
                {([
                  ["all", "Все"],
                  ["football", "Футбол"],
                  ["hockey", "Хоккей"],
                ] as const).map(([value, label]) => (
                  <button
                    key={value}
                    type="button"
                    className={sportFilter === value ? "active" : ""}
                    aria-pressed={sportFilter === value}
                    onClick={() => {
                      setSportFilter(value);
                      setLeagueFilter("all");
                    }}
                  >
                    {label}
                  </button>
                ))}
              </div>
              <label>
                <span>Лига</span>
                <select value={leagueFilter} onChange={(event) => setLeagueFilter(event.target.value)}>
                  <option value="all">Все лиги</option>
                  {availableLeagues.map(([id, name]) => (
                    <option key={id} value={id}>{name}</option>
                  ))}
                </select>
              </label>
              <output aria-live="polite">{filteredMatches.length} матчей</output>
            </div>

            {filteredMatches.length === 0 && (
              <div className="filter-empty">
                <h3>В выбранном разделе матчей нет</h3>
                <p>Сбросьте фильтры или выберите другой вид спорта и лигу.</p>
                <button type="button" onClick={() => {
                  setSportFilter("all");
                  setLeagueFilter("all");
                }}>Показать все матчи</button>
              </div>
            )}

            <div className="match-list">
            {filteredMatches.map((match) => {
              const matchPredictions = predictionsByMatch.get(match.id) || [];
              const winner = Object.fromEntries(
                matchPredictions
                  .filter((prediction) => ["home", "draw", "away"].includes(prediction.selection))
                  .map((prediction) => [prediction.selection, prediction]),
              ) as Record<string, Prediction>;
              const hasCalculation = Boolean(winner.home && winner.draw && winner.away);
              return (
              <article className="match-card" key={match.id}>
                <div className="match-meta">
                  <span>{match.league.sport.code === "football" ? "Футбол" : "Хоккей"} · {match.league.name}</span>
                  <time dateTime={match.kickoff_at}>{formatKickoff(match.kickoff_at)} МСК</time>
                </div>
                <div className="teams">
                  <strong>{match.home_team.name}</strong>
                  <span>{match.home_score ?? "VS"}{match.home_score != null ? ` : ${match.away_score ?? 0}` : ""}</span>
                  <strong>{match.away_team.name}</strong>
                </div>
                <div className="match-status">
                  <i className={match.status.toLowerCase() === "live" ? "live-dot" : ""} aria-hidden="true" />
                  {statusLabel(match.status)}
                </div>
                <div className={`model-analysis ${hasCalculation ? "is-ready" : ""}`}>
                  <div>
                    <b>{hasCalculation ? "РАСЧЁТ МОДЕЛИ · POISSON V1" : "УМНЫЙ РАСЧЁТ"}</b>
                    <span>
                      {hasCalculation
                        ? `Неопределённость ${Math.round((winner.home.uncertainty ?? 0) * 100)}%`
                        : "Нужна история завершённых матчей команд"}
                    </span>
                  </div>
                  {hasCalculation ? (
                    <dl>
                      <div><dt>П1</dt><dd>{Math.round(winner.home.model_probability * 100)}%</dd></div>
                      <div><dt>Х</dt><dd>{Math.round(winner.draw.model_probability * 100)}%</dd></div>
                      <div><dt>П2</dt><dd>{Math.round(winner.away.model_probability * 100)}%</dd></div>
                    </dl>
                  ) : (
                    <em>РАСЧЁТ ГОТОВИТСЯ</em>
                  )}
                </div>
              </article>
              );
            })}
            </div>
          </>
        )}
      </section>

      <section className="sources" id="sources">
        <div className="sources-heading">
          <div><span>АРХИТЕКТУРА MVP</span><h2>От расписания к сигналу</h2></div>
          <p>Каждый следующий слой включаем только после проверки предыдущего.</p>
        </div>
        <div className="source-grid">
          <article>
            <b>01 · LIVE</b>
            <h3>football-data.org</h3>
            <p>Расписание, результаты и команды ведущих европейских футбольных лиг.</p>
            <em>ПОДКЛЮЧЕНО</em>
          </article>
          <article>
            <b>02 · LIVE</b>
            <h3>API-SPORTS</h3>
            <p>Хоккейные лиги, команды и результаты в доступном окне API.</p>
            <em>ПОДКЛЮЧЕНО</em>
          </article>
          <article className="muted">
            <b>03 · BETA</b>
            <h3>Poisson v1</h3>
            <p>Вероятности исходов по истории голов команд с отдельной оценкой неопределённости.</p>
            <em>РАСЧЁТ ПОДКЛЮЧЁН</em>
          </article>
        </div>
      </section>

      <section className="roadmap" id="roadmap">
        <div><span>ДОРОЖНАЯ КАРТА</span><h2>Модель → коэффициенты → EV</h2></div>
        <ol>
          <li className="done"><b>01</b><span>Провайдеры матчей</span><em>готово</em></li>
          <li className="done"><b>02</b><span>Вероятности Poisson v1</span><em>beta</em></li>
          <li><b>03</b><span>Источник коэффициентов</span><em>следующий релиз</em></li>
          <li><b>04</b><span>EV-уведомления</span><em>после линии</em></li>
        </ol>
      </section>

      <footer>
        <div className="brand"><span>BV</span>BetValue <b>AI</b></div>
        <p>Аналитический сервис. Не принимает и не размещает ставки.</p>
        <small>© 2026 BetValue AI</small>
      </footer>
    </main>
  );
}
