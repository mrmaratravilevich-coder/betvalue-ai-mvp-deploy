/*
THESIS: Матч и готовность разбора видны за один взгляд; экран не копирует букмекерскую витрину.
OWN-WORLD: Графитовый фон, лаймовый сигнал готовности, строгие строки событий и крупная типографика.
STORY: Пользователь видит сегодняшнюю подборку, понимает статус аналитики и открывает полный разбор.
FIRST VIEWPORT: Компактная шапка, спокойное обещание пользы, фильтр спорта и начало списка матчей.
FORM: Мобильная оперативная лента, первый вариант структуры, без отдельного концептуального seed.
*/
"use client";

import { useEffect, useMemo, useState } from "react";

type Match = {
  id: number;
  league: { name: string; sport: { code: string; name: string } };
  home_team: { name: string };
  away_team: { name: string };
  kickoff_at: string;
  status: string;
};

type Prediction = { match_id: number; selection: string; model_probability: number; uncertainty?: number | null };
type Sport = "all" | "football" | "hockey" | "basketball";
const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
const SPORT_LABELS: Record<string, string> = { football: "Футбол", hockey: "Хоккей", basketball: "Баскетбол" };

function kickoff(value: string) {
  return new Intl.DateTimeFormat("ru-RU", {
    weekday: "short", day: "numeric", month: "short", hour: "2-digit", minute: "2-digit", timeZone: "Europe/Moscow",
  }).format(new Date(value));
}

export default function TelegramApp() {
  const [matches, setMatches] = useState<Match[]>([]);
  const [predictions, setPredictions] = useState<Prediction[]>([]);
  const [sport, setSport] = useState<Sport>("all");
  const [state, setState] = useState<"loading" | "ready" | "error">("loading");

  useEffect(() => {
    const controller = new AbortController();
    Promise.all([
      fetch(`${API_URL}/matches?limit=100`, { signal: controller.signal }).then((response) => {
        if (!response.ok) throw new Error("matches");
        return response.json();
      }),
      fetch(`${API_URL}/predictions?limit=200`, { signal: controller.signal })
        .then((response) => response.ok ? response.json() : [])
        .catch(() => []),
    ]).then(([matchData, predictionData]) => {
      setMatches(Array.isArray(matchData) ? matchData : []);
      setPredictions(Array.isArray(predictionData) ? predictionData : []);
      setState("ready");
    }).catch(() => setState("error"));
    return () => controller.abort();
  }, []);

  const predictionsByMatch = useMemo(() => {
    const result = new Map<number, Prediction[]>();
    predictions.forEach((item) => result.set(item.match_id, [...(result.get(item.match_id) || []), item]));
    return result;
  }, [predictions]);
  const filtered = matches.filter((match) => sport === "all" || match.league.sport.code === sport).slice(0, 20);

  return (
    <main className="tg-app">
      <header className="tg-head">
        <a className="brand" href="/" aria-label="BetValue AI"><span>BV</span>BetValue <b>AI</b></a>
        <span className="tg-plan">BETA</span>
      </header>

      <section className="tg-intro">
        <p>АНАЛИТИКА МАТЧЕЙ</p>
        <h1>Главное перед игрой</h1>
        <span>Расписание, вероятности и уровень уверенности — коротко и без громких обещаний.</span>
      </section>

      <div className="tg-tabs" role="group" aria-label="Вид спорта">
        {(["all", "football", "hockey", "basketball"] as Sport[]).map((value) => (
          <button key={value} type="button" aria-pressed={sport === value} className={sport === value ? "active" : ""} onClick={() => setSport(value)}>
            {value === "all" ? "Все" : SPORT_LABELS[value]}
          </button>
        ))}
      </div>

      <section className="tg-feed" aria-live="polite">
        <div className="tg-feed-head"><h2>Ближайшие матчи</h2><span>{state === "ready" ? filtered.length : "—"}</span></div>
        {state === "loading" && <div className="tg-message" role="status"><div className="loader" /><p><b>Собираем матчи</b><br />Проверяем расписание и расчёты.</p></div>}
        {state === "error" && <div className="tg-message" role="alert"><p><b>Данные временно недоступны</b><br />Попробуйте обновить экран через минуту.</p><button onClick={() => window.location.reload()}>Обновить</button></div>}
        {state === "ready" && filtered.length === 0 && <div className="tg-message"><p><b>Матчей пока нет</b><br />Выберите другой вид спорта или загляните позже.</p></div>}
        {state === "ready" && filtered.map((match) => {
          const matchPredictions = predictionsByMatch.get(match.id) || [];
          const outcomes = new Map(matchPredictions.map((item) => [item.selection, item]));
          const ready = ["home", "draw", "away"].every((selection) => outcomes.has(selection))
            && (outcomes.get("home")?.uncertainty ?? 1) <= 0.5;
          return (
            <a className="tg-match" href={`/matches/${match.id}`} key={match.id}>
              <div className="tg-match-meta"><span>{SPORT_LABELS[match.league.sport.code] || match.league.sport.name} · {match.league.name}</span><time>{kickoff(match.kickoff_at)} МСК</time></div>
              <div className="tg-teams"><strong>{match.home_team.name}</strong><i>—</i><strong>{match.away_team.name}</strong></div>
              <div className={`tg-analysis ${ready ? "ready" : ""}`}>
                <b>{ready ? "Разбор готов" : "Собираем данные"}</b>
                {ready ? <span>П1 {Math.round((outcomes.get("home")?.model_probability || 0) * 100)}% · Х {Math.round((outcomes.get("draw")?.model_probability || 0) * 100)}% · П2 {Math.round((outcomes.get("away")?.model_probability || 0) * 100)}%</span> : <span>Откроем расчёт, когда данных будет достаточно</span>}
              </div>
            </a>
          );
        })}
      </section>

      <nav className="tg-nav" aria-label="Навигация приложения">
        <a className="active" href="/telegram"><span>●</span>Матчи</a>
        <a href="/#quality-title"><span>◒</span>Результаты</a>
        <a href="/"><span>↗</span>Сайт</a>
      </nav>
      <p className="tg-disclaimer">Аналитический сервис. Не принимает и не размещает ставки.</p>
    </main>
  );
}
