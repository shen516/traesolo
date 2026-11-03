"""Shared CRUD imports."""
from sqlalchemy.orm import Session, aliased
from sqlalchemy import desc, asc, and_, or_, func
from datetime import date, datetime, time as dt_time
from fastapi.encoders import jsonable_encoder
from db.models import (
    League, Team, Match, MatchPrediction, User, UserFavorite,
    UserFollowedLeague, UserHistory, UserPreference, ModelVersion, RiskAlert, Standing,
    TopScorer, AccuracyTrend, CrawlLog, Player, MatchPlayerStat, MatchTeamStat,
    OddsSnapshot,
)
