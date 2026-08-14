/*
THESIS: Один матч — один проверяемый аналитический лист, не витрина прогнозов.
OWN-WORLD: Графитовая рабочая поверхность, известковый сигнал, строгие линии и крупные данные.
STORY: Пользователь узнаёт контекст, видит расчёт или честную причину его отсутствия, затем подписывается на обновления.
FIRST VIEWPORT: Навигация, лига и время, крупная пара команд, под ней три исхода и уровень надёжности.
FORM: Аналитический лист матча; первичная структура для Operate, продолжение существующего мира.
*/
"use client";

import { useEffect, useMemo, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";

type Match = {
  id: number;
  league: { name: string; sport: { code: string; name: string } };
  home_team: { name: string };
  away_team: { name: string };
  kickoff_at: string;
  status: string;
};

type Prediction = {
  match_id: number;
  market?: string;
  selection: string;
  model_probability: number;
  uncertainty?: number | null;
};

type MatchArticle = {
  match_id: number;
  status: "ready" | "waiting";
  title: string;
  lead: string;
  verdict: string;
  confidence_label: string;
  sections: Array<{ title: string; body: string }>;
  quality?: {
    evaluated_matches_30d: number;
    accuracy_30d?: number | null;
    calibration_error_30d?: number | null;
    state: "insufficient" | "watch" | "stable";
  } | null;
  updated_at?: string | null;
};

const API_URL = process.env.NEXT_PUBLIC_API_URL || "https://betvalue-api.onrender.com";
const TELEGRAM_URL = "https://t.me/BetValueAI_bot";
const SPORT_LABELS: Record<string, string> = {
  football: "ФУТБОЛ",
  hockey: "ХОККЕЙ",
  basketball: "БАСКЕТБОЛ",
};

function formatKickoff(value: string) {
  return new Intl.DateTimeFormat("ru-RU", {
    weekday: "long",
    day: "numeric",
    month: "long",
    hour: "2-digit",
    minute: "2-digit",
    timeZone: "Europe/Moscow",
  }).format(new Date(value));
}

function formatUpdatedAt(value?: string | null) {
  if (!value) return "обновление не указано";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "обновление не указано";
  return `${new Intl.DateTimeFormat("ru-RU", {
    day: "numeric",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
    timeZone: "Europe/Moscow",
  }).format(date)} МСК`;
}

function formatSelection(selection: string) {
  if (selection === "yes") return "Да";
  if (selection === "no") return "Нет";
  const total = selection.match(/^(over|under)_(.+)$/);
  if (total) return `${total[1] === "over" ? "Больше" : "Меньше"} ${total[2]}`;
  return selection.replaceAll("_", " ");
}

export default function MatchPage() {
  const params = useParams<{ id: string }>();
  const matchId = Number(params.id);
  const [match, setMatch] = useState<Match | null>(null);
  const [predictions, setPredictions] = useState<Prediction[]>([]);
  const [article, setArticle] = useState<MatchArticle | null>(null);
  const [state, setState] = useState<"loading" | "ready" | "missing" | "error">("loading");
  const [refreshToken, setRefreshToken] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    Promise.all([
      fetch(`${API_URL}/matches/${matchId}`, { signal: controller.signal }).then((response) => {
        if (!response.ok) throw new Error("match");
        return response.json();
      }),
      fetch(`${API_URL}/predictions?match_id=${matchId}&limit=50`, { signal: controller.signal })
        .then((response) => response.ok ? response.json() : []),
      fetch(`${API_URL}/match-articles/${matchId}`, { signal: controller.signal })
        .then((response) => response.ok ? response.json() : null),
    ])
      .then(([current, modelData, articleData]) => {
        setMatch(current && typeof current === "object" ? current : null);
        setPredictions(Array.isArray(modelData) ? modelData : []);
        setArticle(articleData && typeof articleData === "object" ? articleData : null);
        setState(current && typeof current === "object" ? "ready" : "missing");
      })
      .catch(() => setState("error"));
    return () => controller.abort();
  }, [matchId, refreshToken]);

  useEffect(() => {
    if (state !== "ready" || article?.status !== "waiting") return;
    const timer = window.setInterval(() => setRefreshToken((value) => value + 1), 60_000);
    return () => window.clearInterval(timer);
  }, [article?.status, state]);

  const outcomes = useMemo(
    () => Object.fromEntries(predictions.map((item) => [item.selection, item])) as Record<string, Prediction>,
    [predictions],
  );
  const marketRows = useMemo(
    () => predictions
      .filter((item) => !["home", "draw", "away"].includes(item.selection))
      .sort((left, right) => right.model_probability - left.model_probability),
    [predictions],
  );
  const uncertainty = outcomes.home?.uncertainty;
  const calculated = Boolean(
    outcomes.home
    && outcomes.draw
    && outcomes.away
    && uncertainty != null
    && uncertainty <= 0.5
  );
  const rawConfidence = uncertainty == null
    ? "Не оценена"
    : uncertainty <= 0.2 ? "Высокая" : uncertainty <= 0.35 ? "Средняя" : "Ограниченная";
  const quality = article?.quality;
  const confidence = quality?.state === "insufficient" ? "Предварительная" : rawConfidence;
  const qualityTitle = quality?.state === "stable"
    ? "Проверка в рабочем диапазоне"
    : quality?.state === "watch"
      ? "Нужна дополнительная проверка"
      : "Выборка ещё растёт";
  const qualityCopy = quality
    ? quality.evaluated_matches_30d > 0
      ? `Проверено матчей за 30 дней: ${quality.evaluated_matches_30d}`
      : "Истории проверок за последние 30 дней пока нет"
    : "Данные проверки появятся вместе с ближайшим обновлением";

  if (state === "loading") {
    return <main className="detail-shell"><div className="detail-state" role="status"><div className="loader" /><h1>Загружаем разбор матча</h1><p>Сверяем расписание и актуальность данных.</p></div></main>;
  }

  if (state === "error" || state === "missing" || !match) {
    return (
      <main className="detail-shell">
        <div className="detail-state">
          <span className="state-code">{state === "missing" ? "404" : "503"}</span>
          <h1>{state === "missing" ? "Матч не найден" : "Данные временно недоступны"}</h1>
          <p>{state === "missing" ? "Возможно, событие уже вышло из списка ближайших матчей." : "Сервер мог перейти в режим ожидания. Повторите попытку через минуту."}</p>
          <Link className="primary" href="/#matches">Вернуться к матчам</Link>
        </div>
      </main>
    );
  }

  return (
    <main className="match-detail">
      <header className="topbar">
        <Link className="brand" href="/"><span>BV</span>BetValue <b>AI</b></Link>
        <Link className="back-link" href="/#matches">← Все матчи</Link>
        <a className="bot-pill" href={TELEGRAM_URL} target="_blank" rel="noreferrer"><i /> Telegram</a>
      </header>

      <section className="match-sheet">
        <div className="match-context">
          <span>{SPORT_LABELS[match.league.sport.code] || match.league.sport.name.toUpperCase()} · {match.league.name}</span>
          <time dateTime={match.kickoff_at}>{formatKickoff(match.kickoff_at)} МСК</time>
        </div>

        <div className="detail-teams">
          <h1>{match.home_team.name}</h1>
          <span>VS</span>
          <h1>{match.away_team.name}</h1>
        </div>

        {calculated ? (
          <div className="outcome-board" aria-label="Вероятности исходов">
            {[
              ["П1", "Победа хозяев", outcomes.home],
              ["X", "Ничья", outcomes.draw],
              ["П2", "Победа гостей", outcomes.away],
            ].map(([code, label, item]) => (
              <div className="outcome" key={code as string}>
                <span>{code as string}</span>
                <strong>{Math.round((item as Prediction).model_probability * 100)}%</strong>
                <small>{label as string}</small>
              </div>
            ))}
          </div>
        ) : (
          <div className="calculation-pending">
            <span>АНАЛИТИКА · ОЖИДАНИЕ ДАННЫХ</span>
            <h2>Проценты пока не публикуем</h2>
            <p>Для уверенного расчёта нужна достаточная история завершённых матчей команд в этой лиге.</p>
          </div>
        )}

        {calculated && marketRows.length > 0 && (
          <section className="market-board" aria-labelledby="market-board-title">
            <div className="market-board-heading">
              <div>
                <span className="detail-kicker">ДОПОЛНИТЕЛЬНЫЕ РЫНКИ</span>
                <h2 id="market-board-title">Что ещё показывает расчёт</h2>
              </div>
              <p>Вероятности приведены отдельно по каждому доступному сценарию.</p>
            </div>
            <div className="market-grid">
              {marketRows.map((item) => (
                <article className="market-card" key={`${item.market || "market"}-${item.selection}`}>
                  <span>{item.market || "Дополнительный рынок"}</span>
                  <strong>{formatSelection(item.selection)}</strong>
                  <b>{Math.round(item.model_probability * 100)}%</b>
                  <small>{item.uncertainty == null ? "Уровень неопределённости не указан" : `Неопределённость: ${Math.round(item.uncertainty * 100)}%`}</small>
                </article>
              ))}
            </div>
          </section>
        )}

        <div className="evidence-layout">
          <section className="evidence-main">
            <span className="detail-kicker">КАК ЧИТАТЬ РАСЧЁТ</span>
            <h2>{calculated ? "Вероятность — не обещание результата" : "Почему расчёт ещё не появился"}</h2>
            <p>{calculated
              ? "Проценты показывают текущую оценку расклада перед матчем. Они помогают сравнить исходы, но не гарантируют результат."
              : "Мы не подставляем усреднённые или вымышленные значения. Аналитика появится автоматически, когда данных станет достаточно."}</p>
          </section>
          <aside className="model-facts">
            <div><span>Основание публикации</span><strong>{article?.status === "ready" ? `3 исхода · ${article.sections.length} разделов` : "Проверка ещё не завершена"}</strong></div>
            <div><span>Уверенность расчёта</span><strong>{calculated ? confidence : "Недостаточно данных"}</strong></div>
            <div><span>Статус данных</span><strong>{calculated ? "Расчёт доступен, проверка продолжается" : "Идёт накопление"}</strong></div>
            <div><span>Обновление</span><strong>При синхронизации матчей</strong></div>
            <div className="model-quality-fact"><span>Проверка модели</span><strong>{qualityTitle}<small>{qualityCopy}</small></strong></div>
          </aside>
        </div>

        {article && (
          <article className={`expert-article ${article.status === "ready" ? "is-ready" : "is-waiting"}`} aria-labelledby="expert-article-title">
            <header className="expert-article-head">
              <div>
                <span className="detail-kicker">ЭКСПЕРТНЫЙ РАЗБОР · ЧТЕНИЕ 1 МИНУТА</span>
                <h2 id="expert-article-title">{article.title}</h2>
                <p>{article.lead}</p>
              </div>
              <aside className="expert-verdict">
                <span>КОРОТКО</span>
                <strong>{article.verdict}</strong>
                <small>Уверенность расчёта: {article.confidence_label}</small>
              </aside>
            </header>
            <div className="expert-sections">
              {article.sections.map((section) => (
                <section key={section.title}>
                  <h3>{section.title}</h3>
                  <p>{section.body}</p>
                </section>
              ))}
            </div>
            <div className="expert-article-actions">
              <p className="expert-note">Разбор обновляется автоматически при поступлении новых проверенных данных.</p>
              <small className="expert-note">Обновлено: {formatUpdatedAt(article.updated_at)}</small>
              {article.status === "waiting" && (
                <button className="secondary" type="button" onClick={() => setRefreshToken((value) => value + 1)}>
                  Проверить обновление
                </button>
              )}
            </div>
          </article>
        )}
      </section>

      <section className="detail-telegram">
        <div><span>TELEGRAM · СЛЕДУЮЩИЙ ШАГ</span><h2>Следить за изменениями расчёта</h2></div>
        <p>Бот уже показывает ближайшие события. Персональные уведомления по выбранным матчам добавим следующим этапом.</p>
        <a className="primary" href={TELEGRAM_URL} target="_blank" rel="noreferrer">Открыть @BetValueAI_bot ↗</a>
      </section>
    </main>
  );
}
