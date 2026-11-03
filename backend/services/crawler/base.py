"""Crawler abstract base classes (real sources only; no mock implementations)."""
from abc import ABC, abstractmethod
from typing import Dict, List


class MatchCrawler(ABC):
    @abstractmethod
    def crawl(self, league_id: str, days_ahead: int = 7) -> List[Dict]:
        pass


class PlayerCrawler(ABC):
    @abstractmethod
    def crawl(self, league_id: str = None, team_id: str = None) -> List[Dict]:
        pass
