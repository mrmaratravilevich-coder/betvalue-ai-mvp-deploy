from dataclasses import dataclass


@dataclass(frozen=True)
class HistoricalMatch:
    home_team_id: int
    away_team_id: int
    home_score: int
    away_score: int
    xg_home: float | None = None
    xg_away: float | None = None


@dataclass(frozen=True)
class TeamForm:
    games: int
    wins: int
    draws: int
    losses: int
    goals_for: int
    goals_against: int
    results: tuple[str, ...]


def summarize_team(team_id: int, matches: list[HistoricalMatch]) -> TeamForm:
    rows: list[tuple[str, int, int]] = []
    for match in matches:
        if match.home_team_id == team_id:
            goals_for, goals_against = match.home_score, match.away_score
        elif match.away_team_id == team_id:
            goals_for, goals_against = match.away_score, match.home_score
        else:
            continue
        result = "В" if goals_for > goals_against else "Н" if goals_for == goals_against else "П"
        rows.append((result, goals_for, goals_against))
    return TeamForm(
        games=len(rows), wins=sum(row[0] == "В" for row in rows), draws=sum(row[0] == "Н" for row in rows),
        losses=sum(row[0] == "П" for row in rows), goals_for=sum(row[1] for row in rows),
        goals_against=sum(row[2] for row in rows), results=tuple(row[0] for row in rows),
    )


def _team_profile(name: str, form: TeamForm) -> str:
    if not form.games:
        return f"{name}: недостаточно исторических матчей для профиля."
    attack = form.goals_for / form.games
    defence = form.goals_against / form.games
    observations: list[str] = []
    if attack >= 1.5:
        observations.append(f"атака выглядит результативной ({attack:.1f} гола за матч)")
    elif attack < 1.0:
        observations.append(f"создание моментов и реализация ограничены ({attack:.1f} гола за матч)")
    if defence <= 1.0:
        observations.append(f"команда мало пропускает ({defence:.1f} за матч)")
    elif defence >= 1.5:
        observations.append(f"есть уязвимость в обороне ({defence:.1f} пропущенного за матч)")
    if not observations:
        observations.append("профиль без ярко выраженного перевеса")
    return f"{name}: " + "; ".join(observations) + "."


def build_context_sections(
    *, home_name: str, away_name: str, home_id: int, away_id: int, matches: list[HistoricalMatch]
) -> list[dict[str, str]]:
    home = summarize_team(home_id, matches)
    away = summarize_team(away_id, matches)
    sections: list[dict[str, str]] = []
    h2h = [m for m in matches if {m.home_team_id, m.away_team_id} == {home_id, away_id}]
    xg_matches = [m for m in matches if m.xg_home is not None and m.xg_away is not None]
    if matches:
        source_note = (
            f"В анализе использована история {len(matches)} последних завершённых матчей"
            f" и {len(h2h)} очных встреч. Сведения о составах, травмах и новостях"
            " не добавляются без подтверждённого источника."
        )
    else:
        source_note = (
            "Исторических матчей в базе пока нет. Поэтому расширенные выводы о форме"
            " и очных встречах не делаются, а итоговый расчёт нужно воспринимать осторожно."
        )
    sections.append({"title": "Качество и границы данных", "body": source_note})
    if home.games or away.games:
        def text(name: str, form: TeamForm) -> str:
            if not form.games:
                return f"По {name} пока нет достаточной истории в базе."
            return (f"Последние {form.games} матчей: {''.join(form.results)}. "
                    f"Баланс {form.wins}-{form.draws}-{form.losses}, мячи {form.goals_for}:{form.goals_against}.")
        sections.append({"title": "Текущая форма", "body": f"{text(home_name, home)} {text(away_name, away)}"})
        sections.append({
            "title": "Сильные стороны и зоны риска",
            "body": f"{_team_profile(home_name, home)} {_team_profile(away_name, away)}",
        })
    if h2h:
        home_wins = sum((m.home_score > m.away_score) if m.home_team_id == home_id else (m.away_score > m.home_score) for m in h2h)
        draws = sum(m.home_score == m.away_score for m in h2h)
        sections.append({"title": "Очные встречи", "body": f"В базе найдено {len(h2h)} последних очных матчей: {home_name} выиграл {home_wins}, ничьих — {draws}, остальные остались за {away_name}."})
    games = home.games + away.games
    if games:
        goals = home.goals_for + home.goals_against + away.goals_for + away.goals_against
        sections.append({"title": "Результативность последних матчей", "body": f"В доступной истории команды провели {games} матчей; в среднем суммарно забивалось {goals / games:.1f} гола за игру. Показатель помогает понять темп, но не заменяет свежие новости о составах."})
    if xg_matches:
        home_xg = [m.xg_home if m.home_team_id == home_id else m.xg_away for m in xg_matches if m.home_team_id == home_id or m.away_team_id == home_id]
        away_xg = [m.xg_home if m.home_team_id == away_id else m.xg_away for m in xg_matches if m.home_team_id == away_id or m.away_team_id == away_id]
        averages: list[str] = []
        if home_xg:
            averages.append(f"{home_name} — {sum(home_xg) / len(home_xg):.2f}")
        if away_xg:
            averages.append(f"{away_name} — {sum(away_xg) / len(away_xg):.2f}")
        if averages:
            sections.append({
                "title": "Качество создаваемых моментов",
                "body": "Средний xG в доступных матчах: " + "; ".join(averages) + ". Это справочный сигнал, а не гарантия количества голов.",
            })
    return sections
