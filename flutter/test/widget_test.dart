import 'package:flutter_test/flutter_test.dart';
import 'package:traesolo/core/config.dart';
import 'package:traesolo/data/models/follow_summary.dart';
import 'package:traesolo/data/models/league.dart';
import 'package:traesolo/data/models/match.dart';
import 'package:traesolo/data/models/scorer.dart';
import 'package:traesolo/data/models/standing.dart';
import 'package:traesolo/data/models/team.dart';

void main() {
  test('AppConfig exposes default API base and disclaimer', () {
    expect(AppConfig.apiBaseUrl, contains('/api/v1'));
    expect(AppConfig.disclaimer, contains('不构成任何投注建议'));
  });

  test('MatchItem parses summary payload', () {
    final item = MatchItem.fromJson({
      'id': 'M1',
      'status': 'upcoming',
      'match_date': '2026-11-05',
      'match_time': '20:00',
      'home_team': {'id': 'T1', 'name': '主队', 'short_name': '主'},
      'away_team': {'id': 'T2', 'name': '客队'},
      'league': {'id': 'L1', 'name': '测试联赛'},
      'prediction': {
        'main_score': '1-0',
        'home_win_prob': 0.5,
        'draw_prob': 0.3,
        'away_win_prob': 0.2,
      },
    });
    expect(item.id, 'M1');
    expect(item.homeTeam.displayName, '主');
    expect(item.prediction?.hasProbs, isTrue);
    expect(item.whenText, '2026-11-05 20:00');
  });

  test('StandingRow resolves team name map', () {
    final row = StandingRow.fromJson(
      {
        'team_id': 'ARS',
        'rank': 1,
        'played': 10,
        'points': 25,
        'goals_for': 20,
        'goals_against': 8,
        'goal_diff': 12,
      },
      teamNames: const {'ARS': '阿森纳'},
    );
    expect(row.displayName, '阿森纳');
    expect(row.points, 25);
  });

  test('ScorerRow and TeamDetail parse API shapes', () {
    final scorer = ScorerRow.fromJson(
      {
        'player_name': '哈兰德',
        'team_id': 'MCI',
        'goals': 18,
        'assists': 3,
        'rank': 1,
      },
      teamNames: const {'MCI': '曼城'},
    );
    expect(scorer.teamLabel, '曼城');
    expect(scorer.goals, 18);

    final team = TeamDetail.fromJson({
      'id': 'MCI',
      'name': '曼城',
      'short_name': '曼城',
      'elo_rating': 1900,
      'attack_strength': '1.250',
      'defense_strength': 0.9,
      'league_id': 'EPL',
    });
    expect(team.eloRating, 1900);
    expect(team.attackStrength, 1.25);
  });

  test('FollowSummary parses boards and matches', () {
    final summary = FollowSummary.fromJson({
      'ids': ['EPL'],
      'leagues': [
        {'id': 'EPL', 'name': '英超', 'is_active': true},
      ],
      'matches': [
        {
          'id': 'M9',
          'status': 'upcoming',
          'home_team': {'id': 'T1', 'name': 'A'},
          'away_team': {'id': 'T2', 'name': 'B'},
          'league': {'id': 'EPL', 'name': '英超'},
        }
      ],
      'boards': [
        {
          'league_id': 'EPL',
          'league_name': '英超',
          'season': '2025-2026',
          'standings': [
            {'team_id': 'ARS', 'rank': 1, 'points': 20},
          ],
          'scorers': [
            {'player_name': 'Salah', 'goals': 10, 'team_id': 'LIV'},
          ],
        }
      ],
    });
    expect(summary.state.isFollowed('EPL'), isTrue);
    expect(summary.matches, hasLength(1));
    expect(summary.boards.first.standings.first.points, 20);
  });

  test('LeagueListPage parses paginated payload', () {
    final page = LeagueListPage.fromJson({
      'leagues': [
        {'id': 'EPL', 'name': '英超', 'teams_count': 20},
      ],
      'total': 1,
      'page': 1,
      'page_size': 200,
      'total_pages': 1,
    });
    expect(page.leagues.first.name, '英超');
    expect(page.total, 1);
  });
}
