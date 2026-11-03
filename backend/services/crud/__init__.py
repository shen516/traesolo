"""CRUD service layer (split by entity)."""

from services.crud.league import LeagueService
from services.crud.team import TeamService
from services.crud.match import MatchService
from services.crud.prediction import PredictionService
from services.crud.user import UserService
from services.crud.favorite import FavoriteService
from services.crud.follow import FollowService
from services.crud.history import HistoryService
from services.crud.preference import PreferenceService
from services.crud.model import ModelService
from services.crud.risk import RiskService
from services.crud.standing import StandingService
from services.crud.scorer import ScorerService
from services.crud.trend import TrendService
from services.crud.crawl_log import CrawlLogService
from services.crud.player import PlayerService
from services.crud.match_player_stat import MatchPlayerStatService
from services.crud.match_team_stat import MatchTeamStatService

__all__ = [
    "LeagueService",
    "TeamService",
    "MatchService",
    "PredictionService",
    "UserService",
    "FavoriteService",
    "FollowService",
    "HistoryService",
    "PreferenceService",
    "ModelService",
    "RiskService",
    "StandingService",
    "ScorerService",
    "TrendService",
    "CrawlLogService",
    "PlayerService",
    "MatchPlayerStatService",
    "MatchTeamStatService",
]
