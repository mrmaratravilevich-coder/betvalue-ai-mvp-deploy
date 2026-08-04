from fastapi import APIRouter

from app.api.routes import affiliate, auth, bank, ev, history, match_articles, matches, model_quality, predictions, settings, sources, stats, telegram

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(matches.router)
api_router.include_router(match_articles.router)
api_router.include_router(ev.router)
api_router.include_router(predictions.router)
api_router.include_router(model_quality.router)
api_router.include_router(history.router)
api_router.include_router(bank.router)
api_router.include_router(settings.router)
api_router.include_router(stats.router)
api_router.include_router(sources.router)
api_router.include_router(telegram.router)
api_router.include_router(affiliate.router)
