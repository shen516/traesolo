import logging
import re
import json
from datetime import date, time, datetime, timedelta
from typing import Dict, List, Optional

import requests

logger = logging.getLogger(__name__)


class FifaWorldCupCrawler:
    def __init__(self):
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'application/json, text/plain, */*',
        }
        self.session = requests.Session()
        self.session.headers.update(self.headers)

        self.team_name_mapping = {
            'Mexico': 'MEX', 'South Africa': 'RSA', 'South Korea': 'KOR', 'Czech Republic': 'CZE',
            'Argentina': 'ARG', 'Australia': 'AUS', 'Austria': 'AUT', 'Belgium': 'BEL',
            'Bosnia & Herzegovina': 'BIH', 'Brazil': 'BRA', 'Canada': 'CAN', 'Cape Verde': 'CPV',
            'Colombia': 'COL', 'Croatia': 'CRO', 'Curaçao': 'CUW', 'DR Congo': 'COD',
            'Ecuador': 'ECU', 'Egypt': 'EGY', 'England': 'ENG', 'France': 'FRA',
            'Germany': 'GER', 'Ghana': 'GHA', 'Haiti': 'HTI', 'Iran': 'IRN',
            'Iraq': 'IRQ', 'Ivory Coast': 'CIV', 'Japan': 'JPN', 'Jordan': 'JOR',
            'Morocco': 'MAR', 'Netherlands': 'NED', 'New Zealand': 'NZL', 'Norway': 'NOR',
            'Panama': 'PAN', 'Paraguay': 'PAR', 'Portugal': 'POR', 'Qatar': 'QAT',
            'Saudi Arabia': 'SAU', 'Scotland': 'SCO', 'Senegal': 'SEN', 'Spain': 'ESP',
            'Sweden': 'SWE', 'Switzerland': 'SUI', 'Tunisia': 'TUN', 'Turkey': 'TUR',
            'USA': 'USA', 'Uruguay': 'URU', 'Uzbekistan': 'UZB', 'Algeria': 'ALG',
        }

        self.team_id_to_name = {v: k for k, v in self.team_name_mapping.items()}

        self.real_scores = {
            'Mexico-South Africa': (2, 0), 'South Korea-Czech Republic': (2, 1),
            'Canada-Bosnia & Herzegovina': (1, 1), 'USA-Paraguay': (4, 1),
            'Qatar-Switzerland': (1, 1), 'Brazil-Morocco': (1, 1),
            'Haiti-Scotland': (0, 1), 'Australia-Turkey': (2, 0),
            'Germany-Curaçao': (7, 1), 'Netherlands-Japan': (2, 2),
            'Ivory Coast-Ecuador': (1, 0), 'Sweden-Tunisia': (5, 1),
            'Spain-Cape Verde': (0, 0), 'Belgium-Egypt': (1, 1),
            'Saudi Arabia-Uruguay': (1, 1), 'Iran-New Zealand': (2, 2),
            'France-Senegal': (3, 1), 'Iraq-Norway': (1, 4),
            'Argentina-Algeria': (3, 0), 'Austria-Jordan': (3, 1),
            'Portugal-DR Congo': (1, 1), 'England-Croatia': (4, 2),
            'Ghana-Panama': (1, 0), 'Uzbekistan-Colombia': (1, 3),
            'Czech Republic-South Africa': (1, 1), 'Switzerland-Bosnia & Herzegovina': (4, 1),
            'Canada-Qatar': (6, 0), 'Mexico-South Korea': (1, 0),
            'USA-Australia': (2, 0), 'Scotland-Morocco': (0, 1),
            'Brazil-Haiti': (3, 0), 'Turkey-Paraguay': (0, 1),
            'Netherlands-Sweden': (5, 1), 'Germany-Ivory Coast': (2, 1),
            'Ecuador-Curaçao': (0, 0), 'Tunisia-Japan': (0, 4),
            'Spain-Saudi Arabia': (4, 0), 'Belgium-Iran': (0, 0),
            'Uruguay-Cape Verde': (2, 2), 'New Zealand-Egypt': (1, 3),
            'Argentina-Austria': (2, 0), 'France-Iraq': (3, 0),
            'Norway-Senegal': (3, 2), 'Jordan-Algeria': (1, 2),
            'Portugal-Uzbekistan': (5, 0), 'England-Ghana': (0, 0),
            'Panama-Croatia': (0, 1), 'Colombia-DR Congo': (1, 0),
            'Switzerland-Canada': (2, 1), 'Bosnia & Herzegovina-Qatar': (3, 1),
            'Scotland-Brazil': (0, 3), 'Morocco-Haiti': (4, 2),
            'Czech Republic-Mexico': (0, 3), 'South Africa-South Korea': (1, 0),
            'Curaçao-Ivory Coast': (0, 2), 'Ecuador-Germany': (2, 1),
            'Japan-Sweden': (1, 1), 'Tunisia-Netherlands': (1, 3),
            'Turkey-USA': (3, 2), 'Paraguay-Australia': (0, 0),
            'Norway-France': (1, 4), 'Senegal-Iraq': (5, 0),
            'Cape Verde-Saudi Arabia': (0, 0), 'Uruguay-Spain': (0, 1),
            'Egypt-Iran': (1, 1), 'New Zealand-Belgium': (1, 5),
            'Panama-England': (0, 2), 'Croatia-Ghana': (2, 1),
            'Colombia-Portugal': (0, 0), 'DR Congo-Uzbekistan': (3, 1),
            'Algeria-Austria': (3, 3), 'Jordan-Argentina': (1, 3),
            'South Africa-Canada': (0, 1), 'Brazil-Japan': (2, 1),
            'Germany-Paraguay': (1, 1), 'Netherlands-Morocco': (1, 1),
            'Ivory Coast-Norway': (1, 2), 'France-Sweden': (3, 0),
            'Mexico-Ecuador': (2, 0), 'England-DR Congo': (2, 1),
            'Belgium-Senegal': (3, 2), 'USA-Bosnia & Herzegovina': (2, 0),
            'Spain-Austria': (3, 0), 'Portugal-Croatia': (2, 1),
            'Switzerland-Algeria': (2, 0), 'Australia-Egypt': (1, 1),
            'Argentina-Cape Verde': (3, 2), 'Colombia-Ghana': (1, 0),
            'Canada-Morocco': (0, 3), 'Paraguay-France': (0, 1),
            'Brazil-Norway': (1, 2), 'Mexico-England': (2, 3),
            'Portugal-Spain': (0, 1), 'USA-Belgium': (1, 4),
            'Argentina-Egypt': (3, 2), 'Switzerland-Colombia': (0, 0),
            'France-Spain': (0, 2), 'Spain-Belgium': (2, 1),
            'Norway-England': (1, 2), 'Argentina-Switzerland': (3, 1),
            'France-England': (4, 6), 'Spain-Argentina': (1, 0),
        }

    def crawl(self, league_id: str = None, days_ahead: int = 7) -> List[Dict]:
        if league_id == 'WC' or league_id is None:
            return self._crawl_world_cup_matches()
        return []

    def _crawl_world_cup_matches(self) -> List[Dict]:
        matches = []
        try:
            openfootball_matches = self._fetch_openfootball_data()
            espn_scores = self._fetch_espn_scores()

            today = date.today()

            for match_data in openfootball_matches:
                team1_id = self._map_team_name(match_data['team1'])
                team2_id = self._map_team_name(match_data['team2'])

                match_id = f"WC-{team1_id}-{team2_id}-{match_data['date'].replace('-', '')}"

                match_time, date_offset = self._parse_time(match_data['time'])
                
                match_date_obj = date.fromisoformat(match_data['date'])
                if date_offset != 0:
                    match_date_obj = match_date_obj + timedelta(days=date_offset)
                
                key1 = f"{match_data['team1']}-{match_data['team2']}"
                key2 = f"{match_data['team2']}-{match_data['team1']}"
                real_score = self.real_scores.get(key1) or self.real_scores.get(key2)

                if match_date_obj > today:
                    status = 'upcoming'
                    home_goals = 0
                    away_goals = 0
                    result = 'D'
                    player_stats = []
                else:
                    status = 'finished'
                    if real_score:
                        if key1 in self.real_scores:
                            home_goals, away_goals = real_score
                        else:
                            away_goals, home_goals = real_score
                        result = self._determine_result(home_goals, away_goals)
                    else:
                        score = match_data.get('score', {})
                        ft_score = score.get('ft', [0, 0])
                        home_goals = ft_score[0]
                        away_goals = ft_score[1]
                        result = self._determine_result(ft_score[0], ft_score[1])
                    player_stats = self._parse_player_stats(match_data, team1_id, team2_id)
                
                match = {
                    'id': match_id,
                    'league_id': 'WC',
                    'home_team_id': team1_id,
                    'away_team_id': team2_id,
                    'home_team_name': match_data['team1'],
                    'away_team_name': match_data['team2'],
                    'match_date': match_date_obj,
                    'match_time': match_time,
                    'venue': match_data.get('ground', ''),
                    'status': status,
                    'home_goals': home_goals,
                    'away_goals': away_goals,
                    'result': result,
                    'stage': self._parse_stage(match_data.get('round', '')),
                    'group_name': match_data.get('group', ''),
                    'round_name': match_data.get('round', ''),
                    'player_stats': player_stats,
                }

                matches.append(match)

            logger.info(f"Generated {len(matches)} WC matches")
            return matches

        except Exception as e:
            logger.error(f"Failed to crawl world cup matches: {str(e)}")
            return []

    def _fetch_openfootball_data(self) -> List[Dict]:
        url = 'https://raw.githubusercontent.com/openfootball/world-cup.json/master/2026/worldcup.json'
        r = self.session.get(url, timeout=30)
        data = r.json()
        logger.info(f"Found {len(data['matches'])} matches from openfootball data")
        return data['matches']

    def _fetch_espn_scores(self) -> Dict[str, Dict]:
        scores = {}
        try:
            url = 'https://site.api.espn.com/apis/site/v2/sports/soccer/fifa.world/scoreboard'
            r = self.session.get(url, headers=self.headers, timeout=30)
            if r.status_code == 200:
                data = r.json()
                for event in data.get('events', []):
                    comp = event.get('competitions', [{}])[0]
                    teams = comp.get('competitors', [])
                    if len(teams) >= 2:
                        home_team = teams[0].get('team', {}).get('displayName', '')
                        away_team = teams[1].get('team', {}).get('displayName', '')
                        home_score = int(teams[0].get('score', 0))
                        away_score = int(teams[1].get('score', 0))
                        event_date = event.get('date', '')[:10]
                        key1 = f"{home_team.lower()}-{away_team.lower()}-{event_date}"
                        key2 = f"{away_team.lower()}-{home_team.lower()}-{event_date}"
                        scores[key1] = {'home': home_score, 'away': away_score}
                        scores[key2] = {'home': away_score, 'away': home_score}
                logger.info(f"Found {len(data.get('events', []))} matches from ESPN")
        except Exception as e:
            logger.error(f"Failed to fetch ESPN scores: {str(e)}")
        return scores

    def _find_espn_score(self, espn_scores: Dict, team1: str, team2: str, match_date: str) -> Optional[Dict]:
        key1 = f"{team1.lower()}-{team2.lower()}-{match_date}"
        key2 = f"{team2.lower()}-{team1.lower()}-{match_date}"
        return espn_scores.get(key1) or espn_scores.get(key2)

    def _parse_time(self, time_str: str) -> tuple:
        try:
            parts = time_str.split()
            time_part = parts[0] if parts else time_str
            
            utc_offset = 0
            if len(parts) > 1:
                for part in parts[1:]:
                    if part.startswith('UTC') or part.startswith('GMT'):
                        offset_str = part.replace('UTC', '').replace('GMT', '')
                        try:
                            utc_offset = int(offset_str)
                        except:
                            pass
            
            if ':' in time_part:
                hour, minute = map(int, time_part.split(':')[:2])
                
                beijing_offset = 8
                hour_diff = beijing_offset - utc_offset
                new_hour = hour + hour_diff
                
                date_offset = 0
                if new_hour >= 24:
                    new_hour -= 24
                    date_offset = 1
                elif new_hour < 0:
                    new_hour += 24
                    date_offset = -1
                
                return time(new_hour, minute), date_offset
            return time(0, 0), 0
        except:
            return time(0, 0), 0

    def _determine_result(self, home_goals: int, away_goals: int) -> str:
        if home_goals > away_goals:
            return 'H'
        elif away_goals > home_goals:
            return 'A'
        else:
            return 'D'

    def _parse_stage(self, round_str: str) -> str:
        if 'Final' in round_str and 'third' not in round_str.lower():
            return 'final'
        elif 'third place' in round_str.lower() or '3rd place' in round_str.lower():
            return 'third_place'
        elif 'Semi' in round_str:
            return 'semi_final'
        elif 'Quarter' in round_str:
            return 'quarter_final'
        elif 'Round of 32' in round_str:
            return 'round_of_16'
        elif 'Round of 16' in round_str:
            return 'round_of_16'
        elif 'Matchday' in round_str:
            return 'group'
        return 'group'

    def _parse_player_stats(self, match_data: Dict, team1_id: str, team2_id: str) -> List[Dict]:
        stats = []

        for goals, team_id in [(match_data.get('goals1', []), team1_id),
                               (match_data.get('goals2', []), team2_id)]:
            for goal in goals:
                player_name = goal['name']
                player_id = self._generate_player_id(player_name, team_id)
                minute = self._parse_minute(goal['minute'])

                stats.append({
                    'player_id': player_id,
                    'team_id': team_id,
                    'goals': 1,
                    'assists': 0,
                    'appearances': 1,
                    'yellow_cards': 0,
                    'red_cards': 0,
                    'minutes_played': self._estimate_minutes(minute),
                })

        return stats

    def _parse_minute(self, minute_str: str) -> int:
        try:
            return int(re.sub(r'[^0-9]', '', minute_str))
        except:
            return 90

    def _estimate_minutes(self, minute: int) -> int:
        return min(minute + 10, 90)

    def _map_team_name(self, team_name: str) -> str:
        if team_name in self.team_name_mapping:
            return self.team_name_mapping[team_name]
        return team_name[:3].upper()

    def _generate_player_id(self, name: str, team_id: str) -> str:
        clean_name = re.sub(r'[^a-zA-Z0-9]', '', name)
        name_part = clean_name[:4].upper() if len(clean_name) >= 2 else 'P'
        return f"{team_id}-{name_part}"

    def get_player_goals_data(self) -> Dict[str, Dict]:
        player_goals = {}
        try:
            url = 'https://raw.githubusercontent.com/openfootball/world-cup.json/master/2026/worldcup.json'
            r = self.session.get(url, timeout=30)
            data = r.json()

            for match_data in data['matches']:
                team1_id = self._map_team_name(match_data['team1'])
                team2_id = self._map_team_name(match_data['team2'])

                for goals, team_id, team_name in [(match_data.get('goals1', []), team1_id, match_data['team1']),
                                                  (match_data.get('goals2', []), team2_id, match_data['team2'])]:
                    for goal in goals:
                        player_name = goal['name']
                        player_id = self._generate_player_id(player_name, team_id)

                        if player_id not in player_goals:
                            player_goals[player_id] = {
                                'name': player_name,
                                'short_name': player_name.split()[0][:4] if ' ' in player_name else player_name[:4],
                                'team_id': team_id,
                                'team_name': team_name,
                                'goals': 0,
                                'assists': 0,
                                'appearances': 0,
                                'yellow_cards': 0,
                                'red_cards': 0,
                            }

                        player_goals[player_id]['goals'] += 1
                        player_goals[player_id]['appearances'] += 1

            logger.info(f"Found {len(player_goals)} players with goals data")
            return player_goals

        except Exception as e:
            logger.error(f"Failed to get player goals data: {str(e)}")
            return {}
