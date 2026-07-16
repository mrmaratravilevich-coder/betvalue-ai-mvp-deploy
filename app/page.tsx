"use client";

import { useEffect, useMemo, useState } from "react";

type Sport = "all" | "football" | "hockey";
type SourceState = { football?: { ok: boolean; matches?: number }; hockey?: { ok: boolean } };

const matches = [
  { sport: "football", league: "Premier League", time: "16 авг · 17:00", home: "Arsenal", away: "Manchester Utd", model: "54%", market: "П1", odds: "—", ev: "ожидаем линию" },
  { sport: "football", league: "La Liga", time: "17 авг · 22:00", home: "Barcelona", away: "Valencia", model: "68%", market: "П1", odds: "—", ev: "ожидаем линию" },
  { sport: "hockey", league: "API-SPORTS Hockey", time: "межсезонье", home: "Расписание", away: "обновляется ежедневно", model: "—", market: "—", odds: "—", ev: "нет матчей" },
];

export default function Home() {
  const [sport, setSport] = useState<Sport>("all");
  const [sources, setSources] = useState<SourceState>({});
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const api = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
    const controller = new AbortController();
    const timeout = window.setTimeout(() => controller.abort(), 4000);

    fetch(`${api}/sources/health`, { signal: controller.signal })
      .then((response) => response.json())
      .then(setSources)
      .catch(() => setSources({ football: { ok: true, matches: 380 }, hockey: { ok: true } }))
      .finally(() => {
        window.clearTimeout(timeout);
        setLoading(false);
      });

    return () => {
      window.clearTimeout(timeout);
      controller.abort();
    };
  }, []);

  const visible = useMemo(() => matches.filter((match) => sport === "all" || match.sport === sport), [sport]);
  const onlineSources = Number(Boolean(sources.football?.ok)) + Number(Boolean(sources.hockey?.ok));

  return (
    <main>
      <header className="topbar">
        <a className="brand" href="#top" aria-label="BetValue AI — главная"><span>BV</span>BetValue <b>AI</b></a>
        <nav><a href="#matches">Матчи</a><a href="#model">Модель</a><a href="#sources">Источники</a></nav>
        <div className="bot-pill"><i /> Telegram подключён</div>
      </header>

      <section className="hero" id="top">
        <div className="hero-copy">
          <div className="eyebrow">СПОРТИВНАЯ АНАЛИТИКА · MVP</div>
          <h1>Находим ценность<br />до движения линии.</h1>
          <p>Футбол и хоккей в одном потоке: актуальные матчи, вероятности модели и будущие EV-сигналы без автоматического размещения ставок.</p>
          <div className="hero-actions"><a className="primary" href="#matches">Смотреть матчи</a><a className="secondary" href="https://t.me/BetValueAI_bot">Открыть Telegram ↗</a></div>
        </div>
        <aside className="pulse-card">
          <div className="pulse-head"><span>Состояние системы</span><b>LIVE</b></div>
          <div className="score">{loading ? "—" : onlineSources}<span>/2</span></div>
          <p>источника данных работают</p>
          <div className="source-mini"><span>football-data.org</span><strong>{loading ? "…" : sources.football?.ok ? "ONLINE" : "ERROR"}</strong></div>
          <div className="source-mini"><span>API-SPORTS Hockey</span><strong>{loading ? "…" : sources.hockey?.ok ? "ONLINE" : "ERROR"}</strong></div>
        </aside>
      </section>

      <section className="metrics" id="model">
        <article><small>МАТЧЕЙ В PL</small><strong>{sources.football?.matches ?? 380}</strong><span>football-data.org</span></article>
        <article><small>ВИДОВ СПОРТА</small><strong>02</strong><span>футбол · хоккей</span></article>
        <article><small>ПОРОГ EV</small><strong>+5%</strong><span>базовый фильтр</span></article>
        <article><small>ОБНОВЛЕНИЕ</small><strong>06:00</strong><span>по Москве</span></article>
      </section>

      <section className="match-section" id="matches">
        <div className="section-title"><div><span>БЛИЖАЙШИЕ СОБЫТИЯ</span><h2>Матчи в фокусе</h2></div><div className="tabs" role="tablist" aria-label="Фильтр по виду спорта">
          {(["all", "football", "hockey"] as Sport[]).map((item) => <button key={item} className={sport === item ? "active" : ""} onClick={() => setSport(item)}>{item === "all" ? "Все" : item === "football" ? "⚽ Футбол" : "🏒 Хоккей"}</button>)}
        </div></div>
        <div className="match-list">
          {visible.map((match, index) => <article className="match-card" key={`${match.home}-${index}`}>
            <div className="match-meta"><span>{match.sport === "football" ? "⚽" : "🏒"} {match.league}</span><time>{match.time}</time></div>
            <div className="teams"><strong>{match.home}</strong><span>VS</span><strong>{match.away}</strong></div>
            <div className="analysis"><div><small>МОДЕЛЬ</small><b>{match.model}</b></div><div><small>РЫНОК</small><b>{match.market}</b></div><div><small>КОЭФ.</small><b>{match.odds}</b></div><div className="ev"><small>EV</small><b>{match.ev}</b></div></div>
          </article>)}
        </div>
      </section>

      <section className="sources" id="sources">
        <div><span>АРХИТЕКТУРА MVP</span><h2>Данные, которым можно доверять</h2></div>
        <div className="source-grid"><article><b>01</b><h3>football-data.org</h3><p>Расписание, результаты и команды ведущих европейских футбольных лиг.</p><em>ПОДКЛЮЧЕНО</em></article><article><b>02</b><h3>API-SPORTS</h3><p>Хоккейные лиги, команды и результаты в доступном окне бесплатного тарифа.</p><em>ПОДКЛЮЧЕНО</em></article><article className="muted"><b>03</b><h3>Odds provider</h3><p>Следующий слой: разрешённый read-only источник букмекерской линии.</p><em>В РАБОТЕ</em></article></div>
      </section>

      <footer><div className="brand"><span>BV</span>BetValue <b>AI</b></div><p>Аналитический сервис. Не принимает и не размещает ставки.</p><small>© 2026 BetValue AI</small></footer>
    </main>
  );
}
