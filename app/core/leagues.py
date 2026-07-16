"""
Список турниров, поддерживаемых на старте (v1 — футбол).

football_data_code — код соревнования в football-data.org (GET /v4/competitions/{code}).
statsbomb — competition_id/season_id из открытого датасета StatsBomb Open Data
(доступны только некоторые сезоны — в основном исторические/учебные, а не
текущий сезон; используются как источник детальной статистики (xG, удары,
владение) для обучения модели, а не как источник актуальных матчей).
betfair_competition_id — числовой id соревнования на Betfair Exchange.
НЕ угадывается заранее и не хардкодится "на глаз" — Betfair не публикует
статичный справочник id по турнирам, они специфичны для аккаунта/периода.
Получить актуальный список для аккаунта:

    docker compose exec api python -m app.cli list-betfair-competitions

и вписать нужные id сюда вручную.

Список — отправная точка, его можно расширять по мере подключения новых лиг.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class LeagueConfig:
    name: str
    country: str
    football_data_code: str | None = None
    statsbomb_competition_id: int | None = None
    statsbomb_season_id: int | None = None
    betfair_competition_id: str | None = None


SUPPORTED_LEAGUES: list[LeagueConfig] = [
    LeagueConfig(name="Premier League", country="England", football_data_code="PL"),
    LeagueConfig(name="La Liga", country="Spain", football_data_code="PD"),
    LeagueConfig(name="Bundesliga", country="Germany", football_data_code="BL1"),
    LeagueConfig(name="Serie A", country="Italy", football_data_code="SA"),
    LeagueConfig(name="Ligue 1", country="France", football_data_code="FL1"),
    # StatsBomb Open Data: пример открытого набора (La Liga, Messi era) —
    # актуальный id стоит сверить со свежим индексом датасета перед использованием.
    LeagueConfig(name="La Liga (StatsBomb historical)", country="Spain",
                 statsbomb_competition_id=11, statsbomb_season_id=90),
]
