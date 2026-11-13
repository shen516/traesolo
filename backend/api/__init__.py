"""API路由注册"""
from fastapi import APIRouter

router = APIRouter()

from .auth import router as auth_router
from .leagues import router as leagues_router
from .teams import router as teams_router
from .matches import router as matches_router
from .predictions import router as predictions_router
from .simulation_bets import router as simulation_bets_router
from .users import router as users_router
from .favorites import router as favorites_router
from .history import router as history_router
from .models import router as models_router
from .risk import router as risk_router
from .standings import router as standings_router
from .scorers import router as scorers_router
from .trend import router as trend_router
from .crawler import router as crawler_router
from .players import router as players_router
from .permissions import router as permissions_router
from .subscription import router as subscription_router
from .follows import router as follows_router
from .health import router as health_router
from .jingcai_trade import router as jingcai_trade_router

router.include_router(auth_router, prefix="/auth", tags=["Auth"])
router.include_router(leagues_router, prefix="/leagues", tags=["Leagues"])
router.include_router(teams_router, prefix="/teams", tags=["Teams"])
router.include_router(matches_router, prefix="/matches", tags=["Matches"])
router.include_router(predictions_router, prefix="/predictions", tags=["Predictions"])
router.include_router(simulation_bets_router, prefix="/simulation", tags=["Simulation"])
router.include_router(users_router, prefix="/users", tags=["Users"])
router.include_router(favorites_router, prefix="/favorites", tags=["Favorites"])
router.include_router(history_router, prefix="/history", tags=["History"])
router.include_router(models_router, prefix="/model", tags=["Models"])
router.include_router(risk_router, prefix="/risk", tags=["Risk"])
router.include_router(standings_router, prefix="/standings", tags=["Standings"])
router.include_router(scorers_router, prefix="/scorers", tags=["TopScorers"])
router.include_router(trend_router, prefix="/trend", tags=["Trend"])
router.include_router(crawler_router, prefix="/crawler", tags=["Crawler"])
router.include_router(players_router, prefix="/players", tags=["Players"])
router.include_router(permissions_router, prefix="/permissions", tags=["Permissions"])
router.include_router(subscription_router, prefix="/subscription", tags=["Subscription"])
router.include_router(follows_router, prefix="/follows", tags=["Follows"])
router.include_router(health_router, tags=["Health"])
router.include_router(jingcai_trade_router, prefix="/jingcai/trade", tags=["JingcaiTrade"])
