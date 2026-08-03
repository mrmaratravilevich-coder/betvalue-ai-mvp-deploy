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

type QualityMetrics = {
  evaluated_matches: number;
  accuracy: number | null;
  brier_score: number | null;
  log_loss: number | null;
  calibration_error: number | null;
};

type QualityWindow = {
  days: number;
  overall: QualityMetrics;
};

type ModelQuality = {
  windows: QualityWindow[];
};

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
const TELEGRAM_URL = "https://t.me/BetValueAI_bot";
const SPORT_LABELS: Record<string, string> = {
  football: "Р¤СѓС‚Р±РѕР»",
  hockey: "РҐРѕРєРєРµР№",
  basketball: "Р‘Р°СЃРєРµС‚Р±РѕР»",
};

function formatKickoff(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "Р’СЂРµРјСЏ СѓС‚РѕС‡РЅСЏРµС‚СЃСЏ";

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
    scheduled: "Р—Р°РїР»Р°РЅРёСЂРѕРІР°РЅ",
    live: "Р’ СЌС„РёСЂРµ",
    finished: "Р—Р°РІРµСЂС€С‘РЅ",
    postponed: "РџРµСЂРµРЅРµСЃС‘РЅ",
    cancelled: "РћС‚РјРµРЅС‘РЅ",
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
    ? "РјР°С‚С‡РµР№"
    : last === 1 ? "РјР°С‚С‡" : last >= 2 && last <= 4 ? "РјР°С‚С‡Р°" : "РјР°С‚С‡РµР№";
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
  const [quality, setQuality] = useState<ModelQuality | null>(null);
  const [qualityDays, setQualityDays] = useState(30);
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
      fetch(`${API_URL}/model-quality`, { signal: controller.signal })
        .then((response) => response.ok ? response.json() : null)
        .catch(() => null),
    ])
      .then(([, sourceData, matchData, predictionData, qualityData]) => {
        setSources(sourceData);
        setMatches(Array.isArray(matchData) ? matchData : []);
        setPredictions(Array.isArray(predictionData) ? predictionData : []);
        setQuality(qualityData && Array.isArray(qualityData.windows) ? qualityData : null);
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
  const selectedQuality = quality?.windows.find((window) => window.days === qualityDays)
    || quality?.windows[0]
    || null;
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
        <a className="brand" href="#top" aria-label="BetValue AI вЂ” РіР»Р°РІРЅР°СЏ">
          <span>BV</span>BetValue <b>AI</b>
        </a>
        <nav aria-label="РћСЃРЅРѕРІРЅР°СЏ РЅР°РІРёРіР°С†РёСЏ">
          <a href="#matches">РњР°С‚С‡Рё</a>
          <a href="#about">РћР± Р°РЅР°Р»РёС‚РёРєРµ</a>
        </nav>
        <a className="bot-pill" href={TELEGRAM_URL} target="_blank" rel="noreferrer">
          <i aria-hidden="true" /> Telegram
        </a>
      </header>

      <section className="hero" id="top">
        <div className="hero-copy">
          <div className="eyebrow">Р¤РЈРўР‘РћР› В· РҐРћРљРљР•Р™ В· Р‘РђРЎРљР•РўР‘РћР› В· РћРўРљР Р«РўРђРЇ BETA</div>
          <h1>РњР°С‚С‡Рё вЂ” РІ РѕРґРЅРѕРј РјРµСЃС‚Рµ.<br /><em>РђРЅР°Р»РёС‚РёРєР° вЂ” РїРѕ РґРµР»Сѓ.</em></h1>
          <p>
            РќРµР·Р°РІРёСЃРёРјС‹Р№ СѓРјРЅС‹Р№ СЃРµСЂРІРёСЃ РґР»СЏ Р±С‹СЃС‚СЂРѕРіРѕ СЂР°Р·Р±РѕСЂР° РјР°С‚С‡РµР№: РІРµСЂРѕСЏС‚РЅРѕСЃС‚Рё РёСЃС…РѕРґРѕРІ,
            СѓСЂРѕРІРµРЅСЊ СѓРІРµСЂРµРЅРЅРѕСЃС‚Рё Рё С‚РѕР»СЊРєРѕ С‚Рµ СЂР°СЃС‡С‘С‚С‹, РєРѕС‚РѕСЂС‹Рј С…РІР°С‚Р°РµС‚ РґР°РЅРЅС‹С….
          </p>
          <div className="hero-actions">
            <a className="primary" href="#matches">РџСЂРѕРІРµСЂРёС‚СЊ РјР°С‚С‡Рё</a>
            <a className="secondary" href={TELEGRAM_URL} target="_blank" rel="noreferrer">
              РћС‚РєСЂС‹С‚СЊ Telegram <span aria-hidden="true">в†—</span>
            </a>
          </div>
          <p className="hero-note"><i aria-hidden="true" /> Р‘РµР· СЃС‚Р°РІРѕРє Рё Р°РІС‚РѕРґРµР№СЃС‚РІРёР№ вЂ” С‚РѕР»СЊРєРѕ РґР°РЅРЅС‹Рµ Рё Р°РЅР°Р»РёС‚РёРєР°.</p>
        </div>

        <aside className={`pulse-card ${state === "error" ? "is-error" : ""}`} aria-live="polite">
          <div className="pulse-head">
            <span>РЎРѕСЃС‚РѕСЏРЅРёРµ СЃРёСЃС‚РµРјС‹</span>
            <b>{state === "loading" ? "CHECK" : systemOnline ? "LIVE" : "OFFLINE"}</b>
          </div>
          <div className="score">{state === "loading" ? "вЂ”" : onlineSources}<span>/3</span></div>
          <p>
            {state === "loading"
              ? coldStart ? "РћР±РЅРѕРІР»СЏРµРј РґР°РЅРЅС‹РµвЂ¦" : "РџСЂРѕРІРµСЂСЏРµРј РёСЃС‚РѕС‡РЅРёРєРёвЂ¦"
              : state === "error" ? "Р”Р°РЅРЅС‹Рµ РІСЂРµРјРµРЅРЅРѕ РЅРµРґРѕСЃС‚СѓРїРЅС‹" : "РІРёРґР° СЃРїРѕСЂС‚Р° РґРѕСЃС‚СѓРїРЅС‹"}
          </p>
          <div className="source-mini">
            <span>Р¤СѓС‚Р±РѕР»СЊРЅС‹Рµ РјР°С‚С‡Рё</span>
            <strong>{state === "loading" ? "вЂ¦" : sources.football?.ok ? "Р“РћРўРћР’Рћ" : "РџРђРЈР—Рђ"}</strong>
          </div>
          <div className="source-mini">
            <span>РҐРѕРєРєРµР№РЅС‹Рµ РјР°С‚С‡Рё</span>
            <strong>{state === "loading" ? "вЂ¦" : sources.hockey?.ok ? "Р“РћРўРћР’Рћ" : "РџРђРЈР—Рђ"}</strong>
          </div>
          <div className="source-mini">
            <span>Р‘Р°СЃРєРµС‚Р±РѕР»СЊРЅС‹Рµ РјР°С‚С‡Рё</span>
            <strong>{state === "loading" ? "вЂ¦" : sources.basketball?.ok ? "Р“РћРўРћР’Рћ" : "РџРђРЈР—Рђ"}</strong>
          </div>
        </aside>
      </section>

      <section className="metrics" aria-label="РЎС‚Р°С‚СѓСЃ РїСЂРѕРµРєС‚Р°">
        <article>
          <small>Р”РђРќРќР«Р• РњРђРўР§Р•Р™</small>
          <strong>{state === "loading" ? "вЂ”" : `${onlineSources}/3`}</strong>
          <span>СЃС‚Р°С‚СѓСЃ СЃРїРѕСЂС‚РёРІРЅС‹С… СЂР°Р·РґРµР»РѕРІ</span>
        </article>
        <article>
          <small>Р’РР”Р« РЎРџРћР РўРђ</small>
          <strong>03</strong>
          <span>С„СѓС‚Р±РѕР» В· С…РѕРєРєРµР№ В· Р±Р°СЃРєРµС‚Р±РѕР»</span>
        </article>
        <article>
          <small>РњРђРўР§Р Р’ Р‘РђР—Р•</small>
          <strong>{state === "ready" ? String(matches.length).padStart(2, "0") : "вЂ”"}</strong>
          <span>РґРѕ 200 Р±Р»РёР¶Р°Р№С€РёС… СЃРѕР±С‹С‚РёР№</span>
        </article>
        <article>
          <small>Р Р•Р–РРњ</small>
          <strong>BETA</strong>
          <span>РѕС‚РєСЂС‹С‚РѕРµ С‚РµСЃС‚РёСЂРѕРІР°РЅРёРµ</span>
        </article>
      </section>

      <section className="quality-section" aria-labelledby="quality-title">
        <div className="quality-heading">
          <div>
            <span>Р Р•Р—РЈР›Р¬РўРђРўР« РђРќРђР›РРўРРљР</span>
            <h2 id="quality-title">РџСЂРѕРІРµСЂСЏРµРј СЂР°СЃС‡С‘С‚С‹ РїРѕСЃР»Рµ С„РёРЅР°Р»СЊРЅРѕРіРѕ СЃРІРёСЃС‚РєР°</h2>
          </div>
          <div className="quality-periods" role="group" aria-label="РџРµСЂРёРѕРґ РїСЂРѕРІРµСЂРєРё">
            {[7, 30, 90].map((days) => (
              <button
                key={days}
                type="button"
                className={qualityDays === days ? "active" : ""}
                aria-pressed={qualityDays === days}
                onClick={() => setQualityDays(days)}
              >
                {days} РґРЅРµР№
              </button>
            ))}
          </div>
        </div>
        <div className="quality-board" aria-live="polite">
          <div className="quality-main-stat">
            <small>РЎРћР’РџРђР”Р•РќРР• РЎ РРўРћР“РћРњ</small>
            <strong>
              {selectedQuality?.overall.accuracy == null
                ? "вЂ”"
                : `${Math.round(selectedQuality.overall.accuracy * 100)}%`}
            </strong>
            <p>
              {selectedQuality?.overall.evaluated_matches
                ? `РџСЂРѕРІРµСЂРµРЅРѕ ${countLabel(selectedQuality.overall.evaluated_matches)} Р·Р° РІС‹Р±СЂР°РЅРЅС‹Р№ РїРµСЂРёРѕРґ.`
                : "Р РµР·СѓР»СЊС‚Р°С‚С‹ РїРѕСЏРІСЏС‚СЃСЏ РїРѕСЃР»Рµ Р·Р°РІРµСЂС€РµРЅРёСЏ РїРµСЂРІС‹С… РјР°С‚С‡РµР№."}
            </p>
          </div>
          <div className="quality-detail">
            <span>Р§С‚Рѕ СЌС‚Рѕ Р·РЅР°С‡РёС‚</span>
            <p>РњС‹ РІРѕР·РІСЂР°С‰Р°РµРјСЃСЏ Рє РѕРїСѓР±Р»РёРєРѕРІР°РЅРЅС‹Рј СЂР°СЃС‡С‘С‚Р°Рј Рё СЃРѕРїРѕСЃС‚Р°РІР»СЏРµРј РёС… СЃ С„Р°РєС‚РёС‡РµСЃРєРёРј РёС‚РѕРіРѕРј. РўР°Рє РІРёРґРЅРѕ, РєР°Рє Р°РЅР°Р»РёС‚РёРєР° РІРµРґС‘С‚ СЃРµР±СЏ РЅР° СЂРµР°Р»СЊРЅРѕР№ РґРёСЃС‚Р°РЅС†РёРё.</p>
          </div>
          <div className="quality-detail quality-status">
            <span>РЎС‚Р°С‚СѓСЃ РїСЂРѕРІРµСЂРєРё</span>
            <strong>{selectedQuality?.overall.evaluated_matches ? "РћР±РЅРѕРІР»СЏРµС‚СЃСЏ Р°РІС‚РѕРјР°С‚РёС‡РµСЃРєРё" : "РќР°РєРѕРїР»РµРЅРёРµ РґР°РЅРЅС‹С…"}</strong>
            <p>Р‘РµР· РіСЂРѕРјРєРёС… РѕР±РµС‰Р°РЅРёР№ вЂ” С‚РѕР»СЊРєРѕ РїСЂРѕРІРµСЂСЏРµРјС‹Рµ СЂРµР·СѓР»СЊС‚Р°С‚С‹.</p>
          </div>
        </div>
      </section>

      <section className="match-section" id="matches">
        <div className="section-title">
          <div>
            <span>Р‘Р›РР–РђР™РЁРР• РЎРћР‘Р«РўРРЇ</span>
            <h2>РњР°С‚С‡Рё Рё СЂР°СЃС‡С‘С‚С‹</h2>
          </div>
        </div>

        {state === "loading" && (
          <div className="state-panel" role="status">
            <div className="loader" aria-hidden="true" />
            <div>
              <h3>{coldStart ? "Р“РѕС‚РѕРІРёРј РїРѕРґР±РѕСЂРєСѓ" : "Р—Р°РіСЂСѓР¶Р°РµРј РјР°С‚С‡Рё"}</h3>
              <p>{coldStart ? "РЎРІРµСЂСЏРµРј СЂР°СЃРїРёСЃР°РЅРёРµ Рё Р°РєС‚СѓР°Р»СЊРЅРѕСЃС‚СЊ РґР°РЅРЅС‹С…. Р­С‚Рѕ РјРѕР¶РµС‚ Р·Р°РЅСЏС‚СЊ РґРѕ 50 СЃРµРєСѓРЅРґ." : "РџРѕР»СѓС‡Р°РµРј Р°РєС‚СѓР°Р»СЊРЅРѕРµ СЂР°СЃРїРёСЃР°РЅРёРµ Рё СЂР°СЃС‡С‘С‚С‹."}</p>
            </div>
          </div>
        )}

        {state === "error" && (
          <div className="state-panel error-panel" role="alert">
            <span className="state-code">503</span>
            <div>
              <h3>РњР°С‚С‡Рё РїРѕРєР° РЅРµ Р·Р°РіСЂСѓР·РёР»РёСЃСЊ</h3>
              <p>РћР±РЅРѕРІРёС‚Рµ СЃС‚СЂР°РЅРёС†Сѓ С‡РµСЂРµР· РјРёРЅСѓС‚Сѓ РёР»Рё РїСЂРѕРІРµСЂСЊС‚Рµ С‚РµРєСѓС‰РёРµ РјР°С‚С‡Рё РІ Telegram.</p>
            </div>
            <button type="button" onClick={() => window.location.reload()}>РџРѕРІС‚РѕСЂРёС‚СЊ</button>
          </div>
        )}

        {state === "ready" && matches.length === 0 && (
          <div className="empty-state">
            <div>
              <span className="state-code">00</span>
              <h3>Р’РµР±-Р±Р°Р·Р° Р¶РґС‘С‚ РїРµСЂРІСѓСЋ СЃРёРЅС…СЂРѕРЅРёР·Р°С†РёСЋ</h3>
            </div>
            <p>
              Р Р°СЃРїРёСЃР°РЅРёРµ РѕР±РЅРѕРІР»СЏРµС‚СЃСЏ. РџРѕРєР° РјР°С‚С‡Рё РЅРµ РїРѕСЏРІРёР»РёСЃСЊ РЅР° СЃР°Р№С‚Рµ,
              РїСЂРѕРІРµСЂСЊС‚Рµ Р±Р»РёР¶Р°Р№С€РёРµ СЃРѕР±С‹С‚РёСЏ РІ Telegram.
            </p>
            <a className="primary" href={TELEGRAM_URL} target="_blank" rel="noreferrer">РњР°С‚С‡Рё РІ Telegram</a>
          </div>
        )}

        {state === "ready" && matches.length > 0 && (
          <>
            <div className="match-filters" aria-label="Р¤РёР»СЊС‚СЂС‹ РјР°С‚С‡РµР№">
              <div className="sport-tabs" role="group" aria-label="Р’РёРґ СЃРїРѕСЂС‚Р°">
                {([
                  ["all", "Р’СЃРµ"],
                  ["football", "Р¤СѓС‚Р±РѕР»"],
                  ["hockey", "РҐРѕРєРєРµР№"],
                  ["basketball", "Р‘Р°СЃРєРµС‚Р±РѕР»"],
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
                <span>Р›РёРіР°</span>
                <select value={leagueFilter} onChange={(event) => setLeagueFilter(event.target.value)}>
                  <option value="all">Р’СЃРµ Р»РёРіРё</option>
                  {availableLeagues.map(([id, name]) => (
                    <option key={id} value={id}>{name}</option>
                  ))}
                </select>
              </label>
              <output aria-live="polite">{countLabel(filteredMatches.length)}</output>
              <div className="quick-filters" role="group" aria-label="РџРµСЂРёРѕРґ Рё РіРѕС‚РѕРІРЅРѕСЃС‚СЊ Р°РЅР°Р»РёС‚РёРєРё">
                {([
                  ["all", "Р’СЃРµ РґР°С‚С‹"],
                  ["today", "РЎРµРіРѕРґРЅСЏ"],
                  ["tomorrow", "Р—Р°РІС‚СЂР°"],
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
                  РђРЅР°Р»РёС‚РёРєР° РіРѕС‚РѕРІР°
                </button>
              </div>
            </div>

            {filteredMatches.length === 0 && (
              <div className="filter-empty">
                <h3>Р’ РІС‹Р±СЂР°РЅРЅРѕРј СЂР°Р·РґРµР»Рµ РјР°С‚С‡РµР№ РЅРµС‚</h3>
                <p>
                  {analyticsOnly
                    ? "Р”Р»СЏ РІС‹Р±СЂР°РЅРЅС‹С… РјР°С‚С‡РµР№ РїРѕРєР° РЅРµС‚ СЂР°СЃС‡С‘С‚РѕРІ СЃ РґРѕСЃС‚Р°С‚РѕС‡РЅРѕР№ СѓРІРµСЂРµРЅРЅРѕСЃС‚СЊСЋ."
                    : "РР·РјРµРЅРёС‚Рµ РґР°С‚Сѓ, РІРёРґ СЃРїРѕСЂС‚Р° РёР»Рё Р»РёРіСѓ."}
                </p>
                <button type="button" onClick={() => {
                  setSportFilter("all");
                  setLeagueFilter("all");
                  setDateFilter("all");
                  setAnalyticsOnly(false);
                }}>РџРѕРєР°Р·Р°С‚СЊ РІСЃРµ РјР°С‚С‡Рё</button>
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
                  <span>{SPORT_LABELS[match.league.sport.code] || match.league.sport.name} В· {match.league.name}</span>
                  <time dateTime={match.kickoff_at}>{formatKickoff(match.kickoff_at)} РњРЎРљ</time>
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
                    <b>{hasCalculation ? "РђРќРђР›РРўРРљРђ Р“РћРўРћР’Рђ" : "РђРќРђР›РРўРРљРђ Р“РћРўРћР’РРўРЎРЇ"}</b>
                    <span>
                      {hasCalculation
                        ? "Р”Р°РЅРЅС‹С… РґРѕСЃС‚Р°С‚РѕС‡РЅРѕ РґР»СЏ РїСѓР±Р»РёРєР°С†РёРё"
                        : "РџРѕРєР° РЅРµРґРѕСЃС‚Р°С‚РѕС‡РЅРѕ РґР°РЅРЅС‹С… Рѕ РєРѕРјР°РЅРґР°С…"}
                    </span>
                  </div>
                  {hasCalculation ? (
                    <dl>
                      <div><dt>Рџ1</dt><dd>{Math.round(winner.home.model_probability * 100)}%</dd></div>
                      <div><dt>РҐ</dt><dd>{Math.round(winner.draw.model_probability * 100)}%</dd></div>
                      <div><dt>Рџ2</dt><dd>{Math.round(winner.away.model_probability * 100)}%</dd></div>
                    </dl>
                  ) : (
                    <em>Р РђРЎР§РЃРў Р“РћРўРћР’РРўРЎРЇ</em>
                  )}
                </div>
                <a className="match-detail-link" href={`/matches/${match.id}`}>
                  РћС‚РєСЂС‹С‚СЊ СЂР°Р·Р±РѕСЂ РјР°С‚С‡Р° <span aria-hidden="true">в†’</span>
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
          <span>РќР•Р—РђР’РРЎРРњРђРЇ РђРќРђР›РРўРРљРђ</span>
          <h2>РЈРјРЅС‹Р№ СЂР°СЃС‡С‘С‚ РїРѕРјРѕРіР°РµС‚ РѕС†РµРЅРёС‚СЊ РјР°С‚С‡, РЅРѕ СЂРµС€РµРЅРёРµ РѕСЃС‚Р°С‘С‚СЃСЏ Р·Р° РІР°РјРё</h2>
        </div>
        <p>
          РЎРµСЂРІРёСЃ РѕР±СЂР°Р±Р°С‚С‹РІР°РµС‚ СЃРїРѕСЂС‚РёРІРЅС‹Рµ РґР°РЅРЅС‹Рµ, РїСЂРѕРІРµСЂСЏРµС‚ РєР°С‡РµСЃС‚РІРѕ СЂРµР·СѓР»СЊС‚Р°С‚Р°
          Рё РЅРµ РїСѓР±Р»РёРєСѓРµС‚ РїСЂРѕС†РµРЅС‚С‹ РїСЂРё РЅРёР·РєРѕР№ СѓРІРµСЂРµРЅРЅРѕСЃС‚Рё. Р‘РµР· РѕР±СЂР°Р·Р° В«РіСѓСЂСѓВ»,
          РіСЂРѕРјРєРёС… РѕР±РµС‰Р°РЅРёР№ Рё РЅР°РІСЏР·С‡РёРІС‹С… СЂРµРєРѕРјРµРЅРґР°С†РёР№.
        </p>
        <a className="primary" href={TELEGRAM_URL} target="_blank" rel="noreferrer">
          РЎР»РµРґРёС‚СЊ РІ Telegram <span aria-hidden="true">в†—</span>
        </a>
      </section>

      <footer>
        <div className="brand"><span>BV</span>BetValue <b>AI</b></div>
        <p>РђРЅР°Р»РёС‚РёС‡РµСЃРєРёР№ СЃРµСЂРІРёСЃ. РќРµ РїСЂРёРЅРёРјР°РµС‚ Рё РЅРµ СЂР°Р·РјРµС‰Р°РµС‚ СЃС‚Р°РІРєРё.</p>
        <small>В© 2026 BetValue AI</small>
      </footer>
    </main>
  );
}
