from dataclasses import dataclass


@dataclass(frozen=True)
class HistoricalMatch:
    home_team_id: int
    away_team_id: int
    home_score: int
    away_score: int


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


def build_context_sections(
    *, home_name: str, away_name: str, home_id: int, away_id: int, matches: list[HistoricalMatch]
) -> list[dict[str, str]]:
    home = summarize_team(home_id, matches)
    away = summarize_team(away_id, matches)
    sections: list[dict[str, str]] = []
    if home.games or away.games:
        def text(name: str, form: TeamForm) -> str:
            if not form.games:
                return f"По {name} пока нет достаточной истории в базе."
            return (f"Последние {form.games} матчей: {''.join(form.results)}. "
                    f"Баланс {form.wins}-{form.draws}-{form.losses}, мячи {form.goals_for}:{form.goals_against}.")
        sections.append({"title": "Текущая форма", "body": f"{text(home_name, home)} {text(away_name, away)}"})
    h2h = [m for m in matches if {m.home_team_id, m.away_team_id} == {home_id, away_id}]
    if h2h:
        home_wins = sum((m.home_score > m.away_score) if m.home_team_id == home_id else (m.away_score > m.home_score) for m in h2h)
        draws = sum(m.home_score == m.away_score for m in h2h)
        sections.append({"title": "Очные встречи", "body": f"В базе найдено {len(h2h)} последних очных матчей: {home_name} выиграл {home_wins}, ничьих — {draws}, остальные остались за {away_name}."})
    games = home.games + away.games
    if games:
        goals = home.goals_for + home.goals_against + away.goals_for + away.goals_against
        sections.append({"title": "Результативность последних матчей", "body": f"В доступной истории команды провели {games} матчей; в среднем суммарно забивалось {goals / games:.1f} гола за игру. Показатель помогает понять темп, но не заменяет свежие новости о составах."})
    return sections
