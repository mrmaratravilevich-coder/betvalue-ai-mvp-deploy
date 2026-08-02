# BetValue AI — Backend

Backend-скелет: схема БД (SQLAlchemy 2.0, async) + FastAPI роуты по API из ТЗ.

Реальных коэффициентов на этом этапе нет — используются только открытые
источники матчей (StatsBomb Open Data, football-data.org). Таблицы под
коэффициенты (`odds_sources`, `odds_lines`) и связанные фильтры/EV уже
готовы к работе, когда появится легальный источник линий.

## Структура

```
app/
  core/       конфигурация (.env), JWT/безопасность
  db/         async engine, declarative base
  models/     SQLAlchemy-модели (сущности из ТЗ: матчи, коэффициенты,
              прогнозы, EV-ставки, банк, пользователи, журнал загрузки)
  schemas/    Pydantic-схемы ответов API
  api/routes/ роуты: /auth, /matches, /ev, /predictions, /model-quality,
              /history, /bank, /settings, /stats
  services/   бизнес-логика: ev_engine.py (формулы EV/Kelly/фильтры — уже
              реализовано и проверено на примере из ТЗ), заглушки под
              загрузку матчей и коэффициентов (следующий этап)
alembic/      миграции БД
```

## Быстрый старт (Docker)

```bash
cp .env.example .env
docker compose up --build
```

API поднимется на http://localhost:8000, документация — http://localhost:8000/docs.

## Первая миграция

```bash
docker compose exec api alembic revision --autogenerate -m "init schema"
docker compose exec api alembic upgrade head
```

## Загрузка матчей (открытые источники)

Реализовано: `app/services/match_ingestion.py` — синк из football-data.org
(актуальные расписания/результаты) и StatsBomb Open Data (детальная
статистика: xG, удары — используется как признаки для будущей ML-модели).
Список турниров — `app/core/leagues.py`.

```bash
# 1. Получите бесплатный ключ: https://www.football-data.org/client/register
#    и впишите его в .env как FOOTBALL_DATA_API_KEY
# 2. Примените миграции (см. выше)
# 3. Запустите синк вручную:
docker compose exec api python -m app.cli sync-football-data
docker compose exec api python -m app.cli sync-statsbomb
docker compose exec api python -m app.cli sync-all
```

StatsBomb Open Data покрывает не все турниры и не текущий сезон — это
источник статистики для обучения модели, а не живых расписаний.

## ML-пайплайн: прогнозы (Poisson)

Реализовано: `app/services/prediction_engine.py` + `app/services/models/poisson_model.py`.

Считает силу атаки/обороны каждой команды по завершённым матчам лиги
(классический метод Maher — независимые распределения Пуассона для голов
каждой команды, без поправки Диксона-Коулза на низкие счета — это можно
добавить позже, не меняя интерфейс). Формирует `Prediction` для рынков
Победа/Тотал/Обе забьют по всем матчам лиги в статусе `SCHEDULED`.

Прогнан end-to-end на реальном Postgres с синтетическими данными: явный
фаворит корректно получает ~65% на победу, вероятности 1X2 суммируются в 1,
`/predictions` и `/matches` отдают эти данные через API без ошибок.

XGBoost / LightGBM / логрегрессия / ансамбль (ТЗ, раздел "Алгоритмы") —
следующий слой: каждая новая модель добавляет свою вероятность в
`ensemble_components` существующих `Prediction`, не заменяя Poisson.

```bash
docker compose exec api python -m app.cli predict
```

## Источник коэффициентов: Betfair Exchange API

Реализовано: `app/services/sources/betfair.py` (клиент) + `app/services/odds_ingestion.py`
(синк и запись в `OddsLine`).

Используется Delayed Application Key — бесплатный, активен сразу после
создания, без одобрения Betfair (данные с задержкой 1-180 сек, чего для
дневного EV-анализа достаточно). Live-ключ с разовым сбором не нужен —
он вообще не работает в режиме read-only, только для реальных ставок.

Цена в `OddsLine.price` — лучшая доступная цена "back" (`EX_BEST_OFFERS`):
прямой аналог букмекерского коэффициента ("по какой цене я реально могу
поставить на этот исход прямо сейчас").

Betfair не даёt прямого соответствия со своими событиями и нашими `Match`
из football-data.org — матчи сопоставляются эвристически (окно ±3ч по
времени + похожесть названий команд, `difflib.SequenceMatcher`). Это
MVP-уровень; риск — пропущенные совпадения при сильно разных названиях
команд у источников, разрешается вручную (см. TODO в `odds_ingestion.py`
про таблицу-кэш маппинга).

Прогнано end-to-end на реальном Postgres с замоканными ответами Betfair
(без реального ключа): событие корректно сматчилось с синтетическим
матчем и записало 5 `OddsLine` (1X2 + тотал 2.5) с точными переданными ценами.

```bash
# 1. Получить Delayed App Key: https://developer.betfair.com/en/get-started/
#    и учётные данные аккаунта — вписать в .env (BETFAIR_APP_KEY/USERNAME/PASSWORD)
# 2. Найти competitionId нужных турниров (Betfair не публикует статичный справочник):
docker compose exec api python -m app.cli list-betfair-competitions
# 3. Вписать найденные id в betfair_competition_id соответствующих LeagueConfig
#    в app/core/leagues.py
# 4. Синк:
docker compose exec api python -m app.cli sync-odds
```

## Поиск EV+ (Prediction + OddsLine -> EVBet)

Реализовано: `app/services/ev_generation.py`. Для каждого `Prediction`
находит последнюю известную `OddsLine` того же рынка/исхода, считает
EV/Kelly (`ev_engine.py`), прогоняет через `passes_filters()` (EV<5%,
коэфф.>6, <1000 матчей лиги, высокая неопределённость модели,
подозрительное движение линии — сравнение первой и последней цены по
исходу) и создаёт/обновляет `EVBet`: `status=PENDING`, если прошла все
фильтры, иначе `FILTERED_OUT` с причиной в тексте `reasoning` (тот же
текст — заготовка под блок "AI Explain" из ТЗ, собирается из реальных
данных БД без обращения к внешней LLM).

Идемпотентно: на каждый `Prediction` — ровно один `EVBet`, при новой
цене (почасовое обновление линии) он обновляется, а не дублируется.

Фильтр по составам ("неизвестный состав") пока условный — источника
данных о заявках нет, поэтому проверка всегда пропускает. Появится
вместе с модулем обновления составов (по ТЗ — "за 30 минут").

Прогнано end-to-end на реальном Postgres с синтетическими данными
(включая намеренную проверку обеих веток — "прошла фильтры" и
"отсеяна"): пайплайн `Match -> Prediction -> OddsLine -> EVBet` и
выдача через `/ev` работают корректно. По пути нашёл и исправил два
реальных бага с ленивой подгрузкой связей в async-сессии (`MissingGreenlet`)
— в `ev_generation.py` и в самом роуте `/ev`.

```bash
docker compose exec api python -m app.cli find-ev
```

## Планировщик: Celery beat

Реализовано: `app/worker.py`. Ежедневный цикл из ТЗ переведён в
`beat_schedule` (часовой пояс `Europe/Moscow` — тот же оффсет, что и в
Татарстане, где базируется STZ16):

| Время (МСК)      | Задача                | Что делает |
|-------------------|------------------------|------------|
| 06:00 ежедневно    | `task_update_matches`  | `match_ingestion.run_daily_match_update` |
| каждый час (:00)   | `task_update_odds`     | `odds_ingestion.sync_all_betfair_leagues` — покрывает и "07:00" из ТЗ |
| 08:00 ежедневно    | `task_train_model`     | `prediction_engine.generate_predictions_all_leagues` |
| 09:00 и каждый час (:05) | `task_find_ev`   | `ev_generation.generate_ev_bets_all` — пересчитывается вслед за каждым обновлением линии |
| каждые 30 минут    | `task_update_lineups`  | ЗАГЛУШКА — источника данных о составах пока нет |

Каждый запуск пишется в `IngestionLog` (`RUNNING -> SUCCESS/FAILED`,
с текстом ошибки при падении) — эта таблица для того и создавалась.
Проверено на реальном сбое (отсутствующий `FOOTBALL_DATA_API_KEY`):
запись корректно переходит в `FAILED` с текстом ошибки, исключение
пробрасывается дальше для `autoretry_for`. Сетевые задачи
(`update_matches`, `update_odds`) автоматически перезапускаются до
3 раз при ошибке.

**Реальная проблема, найденная при проверке (а не гипотетическая):**
Celery-воркер выполняет задачи одна за другой в одном процессе, но каждый
вызов `asyncio.run()` создаёт новый event loop, а соединения `asyncpg`
привязаны к тому loop, на котором были открыты. Исходная версия вызывала
`engine.dispose()` отдельным `asyncio.run()` снаружи корутины — при прогоне
нескольких задач подряд на реальном Postgres это ловило `RuntimeError:
Event loop is closed` при закрытии соединения (сам dispose() пытался
закрыться в чужом loop). Исправлено: `dispose()` теперь вызывается изнутри
той же корутины `runner()`, в том же loop, где соединение и открывалось.
Проверено: три задачи (`find_ev`, `train_model`, `update_lineups`) подряд
в одном процессе на реальном Postgres — без ошибок при закрытии.

```bash
docker compose up --build   # поднимет api + worker + beat + db + redis
```

## Что дальше

1. ~~`app/services/match_ingestion.py`~~ ✅ готово.
2. ~~Источник коэффициентов (Betfair Exchange API)~~ ✅ готово.
3. ~~ML-пайплайн: Poisson~~ ✅ готово. Следующий шаг внутри этого пункта —
   XGBoost/LightGBM поверх тех же признаков (`MatchTeamStat`), затем ансамбль.
4. ~~Формирование `EVBet` из `Prediction` + `OddsLine`~~ ✅ готово.
5. ~~Celery beat~~ ✅ готово.
6. Обновление составов — нужен источник данных (`task_update_lineups` пока заглушка).
7. Telegram-уведомления, frontend (Next.js).
