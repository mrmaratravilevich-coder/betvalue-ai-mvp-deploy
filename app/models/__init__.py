"""
Импорт всех моделей в одном месте — нужен, чтобы Base.metadata видел все таблицы
(используется в alembic/env.py и при create_all в dev-режиме).
"""
from app.models.ingestion_log import IngestionLog
from app.models.match import Match, MatchTeamStat
from app.models.odds import Market, OddsLine, OddsSource
from app.models.prediction import EVBet, Prediction
from app.models.team import League, Sport, Team
from app.models.telegram_account import TelegramAccount
from app.models.telegram_payment import TelegramPayment
from app.models.user import BankTransaction, User, UserSettings

__all__ = [
    "IngestionLog",
    "Match",
    "MatchTeamStat",
    "Market",
    "OddsLine",
    "OddsSource",
    "EVBet",
    "Prediction",
    "League",
    "Sport",
    "Team",
    "TelegramAccount",
    "TelegramPayment",
    "BankTransaction",
    "User",
    "UserSettings",
]
