import enum


class MatchStatus(str, enum.Enum):
    SCHEDULED = "scheduled"
    LIVE = "live"
    FINISHED = "finished"
    POSTPONED = "postponed"
    CANCELLED = "cancelled"


class MarketCode(str, enum.Enum):
    MATCH_WINNER = "1x2"              # Победа
    DOUBLE_CHANCE = "double_chance"   # Двойной шанс
    TOTAL_OVER = "total_over"         # Тотал больше
    TOTAL_UNDER = "total_under"       # Тотал меньше
    BTTS = "btts"                     # Обе забьют
    HANDICAP = "handicap"             # Фора
    TEAM_TOTAL = "team_total"         # Индивидуальный тотал


class OddsSourceType(str, enum.Enum):
    OPEN_DATA = "open_data"           # StatsBomb Open Data, football-data.org и т.п.
    AGGREGATOR = "aggregator"         # Легальный агрегатор коэффициентов
    BOOKMAKER_OFFICIAL_API = "bookmaker_official_api"
    EXCHANGE = "exchange"             # Betfair Exchange и т.п. — котировки формирует рынок, а не букмекер


class BetStatus(str, enum.Enum):
    PENDING = "pending"
    WON = "won"
    LOST = "lost"
    VOID = "void"
    FILTERED_OUT = "filtered_out"     # Не прошла фильтры (EV<5%, коэфф>6, и т.д.)


class BankTxType(str, enum.Enum):
    DEPOSIT = "deposit"
    WITHDRAWAL = "withdrawal"
    BET_PLACED = "bet_placed"
    BET_SETTLED = "bet_settled"
    ADJUSTMENT = "adjustment"


class UserRole(str, enum.Enum):
    ADMIN = "admin"
    USER = "user"


class IngestionStatus(str, enum.Enum):
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
