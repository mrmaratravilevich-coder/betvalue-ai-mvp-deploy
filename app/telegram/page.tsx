/*
THESIS: Матч и готовность разбора видны за один взгляд; экран не копирует букмекерскую витрину.
OWN-WORLD: Графитовый фон, лаймовый сигнал готовности, строгие строки событий и крупная типографика.
STORY: Пользователь видит сегодняшнюю подборку, понимает статус аналитики и открывает полный разбор.
FIRST VIEWPORT: Компактная шапка, спокойное обещание пользы, фильтр спорта и начало списка матчей.
FORM: Мобильная оперативная лента, первый вариант структуры, без отдельного концептуального seed.
*/
"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";

type Match = {
  id: number;
  league: { name: string; sport: { code: string; name: string } };
  home_team: { name: string };
  away_team: { name: string };
  kickoff_at: string;
  status: string;
};

type Prediction = { match_id: number; selection: string; model_probability: number; uncertainty?: number | null };
type TelegramSession = { first_name: string; username?: string | null; subscription_plan: string; access_token: string };
type SubscriptionPlan = { code: string; name: string; description: string; features: string[]; available: boolean; price_stars?: number | null };
type Sport = "all" | "football" | "hockey" | "basketball";
const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
const TELEGRAM_BOT_URL = "https://t.me/BetValueAI_bot";
const SPORT_LABELS: Record<string, string> = { football: "Футбол", hockey: "Хоккей", basketball: "Баскетбол" };

type TelegramWindow = Window & {
  Telegram?: { WebApp?: {
    ready: () => void;
    expand: () => void;
    initData?: string;
    openInvoice?: (url: string, callback?: (status: "paid" | "cancelled" | "failed" | "pending") => void) => void;
    HapticFeedback?: { impactOccurred: (style: "light") => void };
    initDataUnsafe?: { user?: { first_name?: string } };
  } };
};

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
  const [firstName, setFirstName] = useState("");
  const [updatedAt, setUpdatedAt] = useState<Date | null>(null);
  const [session, setSession] = useState<TelegramSession | null>(null);
  const [sessionState, setSessionState] = useState<"loading" | "ready" | "outside" | "error">("loading");
  const [plans, setPlans] = useState<SubscriptionPlan[]>([]);
  const [invoiceState, setInvoiceState] = useState<"idle" | "loading" | "pending" | "error">("idle");

  useEffect(() => {
    const telegram = (window as TelegramWindow).Telegram?.WebApp;
    telegram?.ready();
    telegram?.expand();
    const timer = window.setTimeout(() => {
      setFirstName(telegram?.initDataUnsafe?.user?.first_name?.trim() || "");
    }, 0);
    return () => window.clearTimeout(timer);
  }, []);

  const authenticateTelegram = useCallback(async () => {
    const initData = (window as TelegramWindow).Telegram?.WebApp?.initData || "";
    if (!initData) {
      setSessionState("outside");
      return;
    }
    setSessionState("loading");
    try {
      const response = await fetch(`${API_URL}/telegram/session`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ init_data: initData }),
      });
      if (!response.ok) throw new Error("telegram-session");
      const data = await response.json() as TelegramSession;
      window.sessionStorage.setItem("bvai_access_token", data.access_token);
      setSession(data);
      setFirstName(data.first_name);
      setSessionState("ready");
    } catch {
      setSessionState("error");
    }
  }, []);

  useEffect(() => {
    const timer = window.setTimeout(() => { void authenticateTelegram(); }, 0);
    return () => window.clearTimeout(timer);
  }, [authenticateTelegram]);

  useEffect(() => {
    const controller = new AbortController();
    fetch(`${API_URL}/telegram/plans`, { signal: controller.signal })
      .then((response) => response.ok ? response.json() : [])
      .then((data) => setPlans(Array.isArray(data) ? data : []))
      .catch(() => setPlans([]));
    return () => controller.abort();
  }, []);

  const loadMatches = useCallback(() => {
    const controller = new AbortController();
    setState("loading");
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
      setUpdatedAt(new Date());
      setState("ready");
    }).catch(() => setState("error"));
    return () => controller.abort();
  }, []);

  useEffect(() => {
    let cancel: (() => void) | undefined;
    const timer = window.setTimeout(() => { cancel = loadMatches(); }, 0);
    return () => {
      window.clearTimeout(timer);
      cancel?.();
    };
  }, [loadMatches]);

  function selectSport(value: Sport) {
    (window as TelegramWindow).Telegram?.WebApp?.HapticFeedback?.impactOccurred("light");
    setSport(value);
  }

  const openProInvoice = useCallback(async () => {
    const telegram = (window as TelegramWindow).Telegram?.WebApp;
    if (!session?.access_token || !telegram?.openInvoice) return;
    setInvoiceState("loading");
    try {
      const response = await fetch(`${API_URL}/telegram/invoice`, {
        method: "POST",
        headers: { Authorization: `Bearer ${session.access_token}` },
      });
      if (!response.ok) throw new Error("telegram-invoice");
      const data = await response.json() as { invoice_url: string };
      telegram.openInvoice(data.invoice_url, (status) => {
        if (status === "paid") {
          setInvoiceState("pending");
          window.setTimeout(() => { void authenticateTelegram(); setInvoiceState("idle"); }, 1200);
        } else if (status === "failed") {
          setInvoiceState("error");
        } else {
          setInvoiceState("idle");
        }
      });
    } catch {
      setInvoiceState("error");
    }
  }, [authenticateTelegram, session]);

  const predictionsByMatch = useMemo(() => {
    const result = new Map<number, Prediction[]>();
    predictions.forEach((item) => result.set(item.match_id, [...(result.get(item.match_id) || []), item]));
    return result;
  }, [predictions]);
  const filtered = matches.filter((match) => sport === "all" || match.league.sport.code === sport).slice(0, 20);

  return (
    <main className="tg-app">
      <header className="tg-head">
        <Link className="brand" href="/" aria-label="BetValue AI"><span>BV</span>BetValue <b>AI</b></Link>
        <span className="tg-plan">BETA</span>
      </header>

      <section className="tg-intro">
        <p>АНАЛИТИКА МАТЧЕЙ</p>
        <h1>{firstName ? `${firstName}, главное перед игрой` : "Главное перед игрой"}</h1>
        <span>Расписание, вероятности и уровень уверенности — коротко и без громких обещаний.</span>
      </section>

      <div className="tg-tabs" role="group" aria-label="Вид спорта">
        {(["all", "football", "hockey", "basketball"] as Sport[]).map((value) => (
          <button key={value} type="button" aria-pressed={sport === value} className={sport === value ? "active" : ""} onClick={() => selectSport(value)}>
            {value === "all" ? "Все" : SPORT_LABELS[value]}
          </button>
        ))}
      </div>

      <section className="tg-feed" aria-live="polite">
        <div className="tg-feed-head">
          <div><h2>Ближайшие матчи</h2>{updatedAt && <small>Обновлено {updatedAt.toLocaleTimeString("ru-RU", { hour: "2-digit", minute: "2-digit" })}</small>}</div>
          <button type="button" onClick={loadMatches} disabled={state === "loading"} aria-label="Обновить матчи">↻</button>
        </div>
        {state === "loading" && <div className="tg-message" role="status"><div className="loader" /><p><b>Собираем матчи</b><br />Проверяем расписание и расчёты.</p></div>}
        {state === "error" && <div className="tg-message" role="alert"><p><b>Данные временно недоступны</b><br />Попробуйте обновить экран через минуту.</p><button onClick={() => window.location.reload()}>Обновить</button></div>}
        {state === "ready" && filtered.length === 0 && <div className="tg-message"><p><b>Матчей пока нет</b><br />Выберите другой вид спорта или загляните позже.</p></div>}
        {state === "ready" && filtered.map((match) => {
          const matchPredictions = predictionsByMatch.get(match.id) || [];
          const outcomes = new Map(matchPredictions.map((item) => [item.selection, item]));
          const ready = ["home", "draw", "away"].every((selection) => outcomes.has(selection))
            && (outcomes.get("home")?.uncertainty ?? 1) <= 0.5;
          return (
            <Link className="tg-match" href={`/matches/${match.id}`} key={match.id}>
              <div className="tg-match-meta"><span>{SPORT_LABELS[match.league.sport.code] || match.league.sport.name} · {match.league.name}</span><time>{kickoff(match.kickoff_at)} МСК</time></div>
              <div className="tg-teams"><strong>{match.home_team.name}</strong><i>—</i><strong>{match.away_team.name}</strong></div>
              <div className={`tg-analysis ${ready ? "ready" : ""}`}>
                <b>{ready ? "Разбор готов" : "Собираем данные"}</b>
                {ready ? <span>П1 {Math.round((outcomes.get("home")?.model_probability || 0) * 100)}% · Х {Math.round((outcomes.get("draw")?.model_probability || 0) * 100)}% · П2 {Math.round((outcomes.get("away")?.model_probability || 0) * 100)}%</span> : <span>Откроем расчёт, когда данных будет достаточно</span>}
              </div>
            </Link>
          );
        })}
      </section>

      <section className={`tg-account ${sessionState}`} aria-live="polite">
        <div>
          <span>ВАШ ДОСТУП</span>
          {sessionState === "ready" && <><h2>{session?.first_name}, базовый доступ активен</h2><p>Аккаунт подтверждён Telegram. Расширенные функции пока закрыты до запуска подписки.</p></>}
          {sessionState === "loading" && <><h2>Проверяем аккаунт</h2><p>Подтверждаем безопасный запуск приложения через Telegram.</p></>}
          {sessionState === "outside" && <><h2>Откройте приложение из бота</h2><p>Авторизация работает только при запуске через кнопку в @BetValueAI_bot.</p></>}
          {sessionState === "error" && <><h2>Не удалось подтвердить аккаунт</h2><p>Вернитесь в бот и откройте приложение ещё раз или повторите проверку.</p></>}
        </div>
        {sessionState === "ready" && <strong>{session?.subscription_plan === "free" ? "БАЗОВЫЙ" : session?.subscription_plan.toUpperCase()}</strong>}
        {sessionState === "loading" && <div className="loader" />}
        {sessionState === "outside" && <a className="tg-open-telegram" href={TELEGRAM_BOT_URL}>Открыть в Telegram</a>}
        {sessionState === "error" && <button type="button" onClick={authenticateTelegram}>Повторить</button>}
      </section>

      <section className="tg-access" id="access" aria-labelledby="tg-access-title">
        <div>
          <span>РАСШИРЕННЫЙ ДОСТУП</span>
          <h2 id="tg-access-title">Больше контекста по матчу</h2>
          <p>{plans.some((plan) => plan.code === "pro" && plan.available) ? "Форма команд, очные встречи, расширенная статистика и подборки событий доступны в тарифе Pro." : "Форма команд, очные встречи, расширенная статистика и подборки событий появятся после проверки источников и запуска подписки."}</p>
        </div>
        {plans.some((plan) => plan.code === "pro" && plan.available) ? <a className="tg-access-cta" href="#plans">Перейти к тарифу</a> : <button type="button" disabled>Скоро</button>}
      </section>

      {plans.length > 0 && <section className="tg-plans" id="plans" aria-label="Тарифы">
        {plans.map((plan) => <article key={plan.code} className={plan.available ? "available" : ""}>
          <div><span>{plan.available ? "ДОСТУПЕН" : "ГОТОВИТСЯ"}</span><h3>{plan.name}</h3><p>{plan.description}</p></div>
          <ul>{plan.features.map((feature) => <li key={feature}>{feature}</li>)}</ul>
          <div className="tg-plan-action">
            <strong>{plan.price_stars ? `${plan.price_stars} Stars` : plan.available ? "Без оплаты" : "Цена позже"}</strong>
            {plan.code === "pro" && plan.available && sessionState === "outside" && (
              <a className="tg-plan-button" href={TELEGRAM_BOT_URL}>Открыть в Telegram</a>
            )}
            {plan.code === "pro" && plan.available && sessionState === "ready" && session?.subscription_plan !== "pro" && (
              <button type="button" onClick={openProInvoice} disabled={invoiceState === "loading" || invoiceState === "pending"}>
                {invoiceState === "loading" ? "Открываем…" : invoiceState === "pending" ? "Проверяем…" : "Подключить"}
              </button>
            )}
            {plan.code === "pro" && session?.subscription_plan === "pro" && <em>Подписка активна</em>}
          </div>
          {plan.code === "pro" && invoiceState === "error" && <small role="alert">Не удалось открыть оплату. Попробуйте ещё раз.</small>}
        </article>)}
      </section>}

      <nav className="tg-nav" aria-label="Навигация приложения">
        <Link className="active" href="/telegram"><span>●</span>Матчи</Link>
        <a href="#access"><span>＋</span>Расширить</a>
        <Link href="/"><span>↗</span>Сайт</Link>
      </nav>
      <p className="tg-disclaimer">Аналитический сервис. Не принимает и не размещает ставки.</p>
    </main>
  );
}
