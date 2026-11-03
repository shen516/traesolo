"""Crawler subpackage: base ABCs and (historically) mock helpers — mock removed."""
from services.crawler.base import MatchCrawler, PlayerCrawler

__all__ = ["MatchCrawler", "PlayerCrawler"]
