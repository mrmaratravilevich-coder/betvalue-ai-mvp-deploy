"use client";

import { useEffect, useMemo, useState } from "react";

type SourceState = {
  football?: { ok: boolean; matches?: number };
  hockey?: { ok: boolean };
  basketball?: { ok: boolean };
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
type SportFilter = "all" | "football" | "hockey" | "basketball";
type DateFilter = "all" | "today" | "tomorrow";

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
const SPORT_LABELS: Record<string, string> = {
  football: "Футбол",
  hockey: "Хоккей",
  basketball: "Баскетбол",
};

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

function moscowDateKey(value: string | Date) {
  const date = typeof value === "string" ? new Date(value) : value;
  if (Number.isNaN(date.getTime())) return "";
  return new Intl.DateTimeFormat("en-CA", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    timeZone: "Europe/Moscow",
  }).format(date);
}

function countLabel(count: number) {
  const lastTwo = count % 100;
  const last = count % 10;
  const word = lastTwo >= 11 && lastTwo <= 14
    ? "матчей"
    : last === 1 ? "матч" : last >= 2 && last <= 4 ? "матча" : "матчей";
  return `${count} ${word}`;
}

function hasReliableCalculation(matchPredictions: Prediction[]) {
  const selections = new Map(matchPredictions.map((item) => [item.selection, item]));
  const uncertainty = selections.get("home")?.uncertainty;
  return Boolean(
    selections.get("home")
    && selections.get("draw")
    && selections.get("away")
    && uncertainty != null
    && uncertainty <= 0.5
  );
}

export default function Home() {
  const [state, setState] = useState<ApiState>("loading");
  const [sources, setSources] = useState<SourceState>({});
  const [matches, setMatches] = useState<Match[]>([]);
  const [predictions, setPredictions] = useState<Prediction[]>([]);
  const [sportFilter, setSportFilter] = useState<SportFilter>("all");
  const [leagueFilter, setLeagueFilter] = useState("all");
  const [dateFilter, setDateFilter] = useState<DateFilter>("all");
  const [analyticsOnly, setAnalyticsOnly] = useState(false);
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
      fetch(`${API_URL}/matches?limit=200`, { signal: controller.signal }).then((response) => {
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
    () => Number(Boolean(sources.football?.ok))
      + Number(Boolean(sources.hockey?.ok))
      + Number(Boolean(sources.basketball?.ok)),
    [sources],
  );
  const systemOnline = state === "ready" && onlineSources > 0;
  const availableLeagues = useMemo(() => {
    const filtered = sportFilter === "all"
      ? matches
      : matches.filter((match) => match.league.sport.code === sportFilter);
    return [...new Map(filtered.map((match) => [match.league_id, match.league.name])).entries()];
  }, [matches, sportFilter]);
  const predictionsByMatch = useMemo(() => {
    const grouped = new Map<number, Prediction[]>();
    predictions.forEach((prediction) => {
      const current = grouped.get(prediction.match_id) || [];
      current.push(prediction);
      grouped.set(prediction.match_id, current);
    });
    return grouped;
  }, [predictions]);
  const filteredMatches = useMemo(() => {
    const todayKey = moscowDateKey(new Date());
    const tomorrow = new Date();
    tomorrow.setDate(tomorrow.getDate() + 1);
    const tomorrowKey = moscowDateKey(tomorrow);

    return matches.filter((match) => {
      const matchDate = moscowDateKey(match.kickoff_at);
      const dateMatches = dateFilter === "all"
        || (dateFilter === "today" && matchDate === todayKey)
        || (dateFilter === "tomorrow" && matchDate === tomorrowKey);
      return (
        (sportFilter === "all" || match.league.sport.code === sportFilter)
        && (leagueFilter === "all" || String(match.league_id) === leagueFilter)
        && dateMatches
        && (!analyticsOnly || hasReliableCalculation(predictionsByMatch.get(match.id) || []))
      );
    });
  }, [matches, sportFilter, leagueFilter, dateFilter, analyticsOnly, predictionsByMatch]);

  return (
    <main>
      <header className="topbar">
        <a className="brand" href="#top" aria-label="BetValue AI — главная">
          <span>BV</span>BetValue <b>AI</b>
        </a>
        <nav aria-label="Основная навигация">
          <a href="#matches">Матчи</a>
          <a href="#about">Об аналитике</a>
        </nav>
        <a className="bot-pill" href={TELEGRAM_URL} target="_blank" rel="noreferrer">
          <i aria-hidden="true" /> Telegram
        </a>
      </header>

      <section className="hero" id="top">
        <div className="hero-copy">
          <div className="eyebrow">ФУТБОЛ · ХОККЕЙ · БАСКЕТБОЛ · ОТКРЫТАЯ BETA</div>
          <h1>Матчи — в одном месте.<br /><em>Аналитика — по делу.</em></h1>
          <p>
            Независимый умный сервис для быстрого разбора матчей: вероятности исходов,
            уровень уверенности и только те расчёты, которым хватает данных.
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
          <div className="score">{state === "loading" ? "—" : onlineSources}<span>/3</span></div>
          <p>
            {state === "loading"
              ? coldStart ? "Обновляем данные…" : "Проверяем источники…"
              : state === "error" ? "Данные временно недоступны" : "вида спорта доступны"}
          </p>
          <div className="source-mini">
            <span>Футбольные матчи</span>
            <strong>{state === "loading" ? "…" : sources.football?.ok ? "ГОТОВО" : "ПАУЗА"}</strong>
          </div>
          <div className="source-mini">
            <span>Хоккейные матчи</span>
            <strong>{state === "loading" ? "…" : sources.hockey?.ok ? "ГОТОВО" : "ПАУЗА"}</strong>
          </div>
          <div className="source-mini">
            <span>Баскетбольные матчи</span>
            <strong>{state === "loading" ? "…" : sources.basketball?.ok ? "ГОТОВО" : "ПАУЗА"}</strong>
          </div>
        </aside>
      </section>

      <section className="metrics" aria-label="Статус проекта">
        <article>
          <small>ДАННЫЕ МАТЧЕЙ</small>
          <strong>{state === "loading" ? "—" : `${onlineSources}/3`}</strong>
          <span>статус спортивных разделов</span>
        </article>
        <article>
          <small>ВИДЫ СПОРТА</small>
          <strong>03</strong>
          <span>футбол · хоккей · баскетбол</span>
        </article>
        <article>
          <small>МАТЧИ В БАЗЕ</small>
          <strong>{state === "ready" ? String(matches.length).padStart(2, "0") : "—"}</strong>
          <span>до 200 ближайших событий</span>
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
            <span>БЛИЖАЙШИЕ СОБЫТИЯ</span>
            <h2>Матчи и расчёты</h2>
          </div>
        </div>

        {state === "loading" && (
          <div className="state-panel" role="status">
            <div className="loader" aria-hidden="true" />
            <div>
              <h3>{coldStart ? "Готовим подборку" : "Загружаем матчи"}</h3>
              <p>{coldStart ? "Сверяем расписание и актуальность данных. Это может занять до 50 секунд." : "Получаем актуальное расписание и расчёты."}</p>
            </div>
          </div>
        )}

        {state === "error" && (
          <div className="state-panel error-panel" role="alert">
            <span className="state-code">503</span>
            <div>
              <h3>Матчи пока не загрузились</h3>
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
              Расписание обновляется. Пока матчи не появились на сайте,
              проверьте ближайшие события в Telegram.
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
                  ["basketball", "Баскетбол"],
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
              <output aria-live="polite">{countLabel(filteredMatches.length)}</output>
              <div className="quick-filters" role="group" aria-label="Период и готовность аналитики">
                {([
                  ["all", "Все даты"],
                  ["today", "Сегодня"],
                  ["tomorrow", "Завтра"],
                ] as const).map(([value, label]) => (
                  <button
                    key={value}
                    type="button"
                    className={dateFilter === value ? "active" : ""}
                    aria-pressed={dateFilter === value}
                    onClick={() => setDateFilter(value)}
                  >
                    {label}
                  </button>
                ))}
                <button
                  type="button"
                  className={analyticsOnly ? "active" : ""}
                  aria-pressed={analyticsOnly}
                  onClick={() => setAnalyticsOnly((current) => !current)}
                >
                  Аналитика готова
                </button>
              </div>
            </div>

            {filteredMatches.length === 0 && (
              <div className="filter-empty">
                <h3>В выбранном разделе матчей нет</h3>
                <p>
                  {analyticsOnly
                    ? "Для выбранных матчей пока нет расчётов с достаточной уверенностью."
                    : "Измените дату, вид спорта или лигу."}
                </p>
                <button type="button" onClick={() => {
                  setSportFilter("all");
                  setLeagueFilter("all");
                  setDateFilter("all");
                  setAnalyticsOnly(false);
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
              const outcomeUncertainty = winner.home?.uncertainty;
              const hasCalculation = Boolean(
                winner.home
                && winner.draw
                && winner.away
                && outcomeUncertainty != null
                && outcomeUncertainty <= 0.5
              );
              return (
              <article className="match-card" key={match.id}>
                <div className="match-meta">
                  <span>{SPORT_LABELS[match.league.sport.code] || match.league.sport.name} · {match.league.name}</span>
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
                    <b>{hasCalculation ? "АНАЛИТИКА ГОТОВА" : "АНАЛИТИКА ГОТОВИТСЯ"}</b>
                    <span>
                      {hasCalculation
                        ? "Данных достаточно для публикации"
                        : "Пока недостаточно данных о командах"}
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
                <a className="match-detail-link" href={`/matches/${match.id}`}>
                  Открыть разбор матча <span aria-hidden="true">→</span>
                </a>
              </article>
              );
            })}
            </div>
          </>
        )}
      </section>

      <section className="plain-explainer" id="about">
        <div>
          <span>НЕЗАВИСИМАЯ АНАЛИТИКА</span>
          <h2>Умный расчёт помогает оценить матч, но решение остаётся за вами</h2>
        </div>
        <p>
          Сервис обрабатывает спортивные данные, проверяет качество результата
          и не публикует проценты при низкой уверенности. Без образа «гуру»,
          громких обещаний и навязчивых рекомендаций.
        </p>
        <a className="primary" href={TELEGRAM_URL} target="_blank" rel="noreferrer">
          Следить в Telegram <span aria-hidden="true">↗</span>
        </a>
      </section>

      <footer>
        <div className="brand"><span>BV</span>BetValue <b>AI</b></div>
        <p>Аналитический сервис. Не принимает и не размещает ставки.</p>
        <small>© 2026 BetValue AI</small>
      </footer>
    </main>
  );
}
