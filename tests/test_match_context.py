from app.services.match_context import HistoricalMatch, build_context_sections, summarize_team


def test_team_form_counts_results_from_both_sides():
    form = summarize_team(1, [
        HistoricalMatch(1, 2, 2, 0),
        HistoricalMatch(3, 1, 1, 1),
        HistoricalMatch(1, 4, 0, 1),
    ])

    assert form.games == 3
    assert (form.wins, form.draws, form.losses) == (1, 1, 1)
    assert (form.goals_for, form.goals_against) == (3, 2)
    assert form.results == ("В", "Н", "П")


def test_context_sections_include_form_h2h_and_scoring():
    sections = build_context_sections(
        home_name="Команда A", away_name="Команда B", home_id=1, away_id=2,
        matches=[
            HistoricalMatch(1, 2, 2, 0),
            HistoricalMatch(2, 1, 1, 1),
            HistoricalMatch(1, 3, 1, 0),
            HistoricalMatch(4, 2, 0, 2),
        ],
    )

    titles = {section["title"] for section in sections}
    assert {"Текущая форма", "Очные встречи", "Результативность последних матчей"} <= titles
