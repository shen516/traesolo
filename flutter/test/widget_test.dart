import 'package:flutter_test/flutter_test.dart';
import 'package:traesolo/core/config.dart';
import 'package:traesolo/core/media.dart';
import 'package:traesolo/core/odds_math.dart';
import 'package:traesolo/data/match_detail_cache.dart';
import 'package:traesolo/data/models/follow_summary.dart';
import 'package:traesolo/data/models/league.dart';
import 'package:traesolo/data/models/match.dart';
import 'package:traesolo/data/models/odds_snapshot.dart';
import 'package:traesolo/data/models/scorer.dart';
import 'package:traesolo/data/models/sensitivity.dart';
import 'package:traesolo/data/models/simulation.dart';
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
      'match_no': '周三001',
      'handicap': -1,
      'odds_nspf_win': 2.15,
      'odds_nspf_draw': 3.2,
      'odds_nspf_lose': 3.4,
      'is_single': true,
      'home_team': {'id': 'T1', 'name': '主队', 'short_name': '主'},
      'away_team': {'id': 'T2', 'name': '客队'},
      'league': {'id': 'L1', 'name': '测试联赛'},
      'prediction': {
        'main_score': '1-0',
        'home_win_prob': 0.5,
        'draw_prob': 0.3,
        'away_win_prob': 0.2,
        'primary_scenario': 'balanced',
        'scenario_reason': '攻防均衡',
        'scenarios': {
          'balanced': {'label': '均衡情景'},
        },
      },
    });
    expect(item.id, 'M1');
    expect(item.homeTeam.displayName, '主');
    expect(item.prediction?.hasProbs, isTrue);
    expect(item.prediction?.scenarioTitle, '均衡情景');
    expect(item.whenText, '2026-11-05 20:00');
    expect(item.hasNspf, isTrue);
    expect(item.matchNo, '周三001');
    expect(item.isSingle, isTrue);
  });

  test('AppConfig version and disclaimer stay aligned', () {
    expect(AppConfig.appVersion, contains('1.0.0'));
    expect(AppConfig.disclaimer, contains('不构成任何投注建议'));
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
      teamLogos: const {'ARS': '/static/teams/ars.png'},
    );
    expect(row.displayName, '阿森纳');
    expect(row.points, 25);
    expect(row.teamLogo, '/static/teams/ars.png');
  });

  test('resolveMediaUrl joins /static with api origin', () {
    expect(AppConfig.apiOrigin, isNot(contains('/api/v1')));
    expect(
      resolveMediaUrl('/static/teams/x.png'),
      '${AppConfig.apiOrigin}/static/teams/x.png',
    );
    expect(resolveMediaUrl('https://cdn.example/a.png'), 'https://cdn.example/a.png');
    expect(resolveMediaUrl('emoji'), isNull);
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

  test('SimulationResult parses simulate response', () {
    final result = SimulationResult.fromJson({
      'match': {'id': 'M1'},
      'baseline': {
        'home_win_prob': 0.4,
        'draw_prob': 0.3,
        'away_win_prob': 0.3,
        'main_score': '1-1',
      },
      'simulated': {
        'home_win_prob': 0.55,
        'draw_prob': 0.25,
        'away_win_prob': 0.2,
        'lambda_home': 1.4,
        'lambda_away': 1.1,
        'main_score': '2-1',
        'alt_scores': ['1-0', '2-0'],
        'mc': {
          'over_2_5_prob': 0.52,
          'btts_prob': 0.48,
          'top_scores': [
            {'score': '2-1'},
            {'score': '1-0'},
          ],
        },
      },
      'meta': {
        'elapsed_ms': 1200,
        'simulations': 5000,
        'cache_hit': false,
        'warnings': [],
      },
    });
    expect(result.matchId, 'M1');
    expect(result.simulated.mainScore, '2-1');
    expect(result.simulated.hasProbs, isTrue);
    expect(result.meta.simulations, 5000);
    expect(result.simulated.topScores.first, '2-1');
  });

  test('SimulationHistoryItem parses history row', () {
    final item = SimulationHistoryItem.fromJson({
      'id': 9,
      'match_id': 'M1',
      'match_name': 'A vs B',
      'simulations': 5000,
      'summary': {
        'main_score': '1-0',
        'home_win_prob': 0.5,
        'draw_prob': 0.3,
        'away_win_prob': 0.2,
      },
      'created_at': '2026-11-06T12:00:00',
    });
    expect(item.id, 9);
    expect(item.mainScore, '1-0');
    expect(item.homeWinProb, 0.5);
  });

  test('MatchItem toJson round-trips for detail cache', () {
    final original = MatchItem.fromJson({
      'id': 'M9',
      'status': 'upcoming',
      'match_date': '2026-11-07',
      'match_time': '19:30',
      'home_team': {
        'id': 'H',
        'name': '主队',
        'short_name': '主',
        'logo': '/static/h.png',
      },
      'away_team': {'id': 'A', 'name': '客队', 'logo': '/static/a.png'},
      'league': {'id': 'L1', 'name': '联赛'},
      'prediction': {
        'main_score': '2-1',
        'home_win_prob': 0.4,
        'draw_prob': 0.3,
        'away_win_prob': 0.3,
        'primary_scenario': 'balanced',
        'scenarios': {
          'balanced': {'label': '均衡'},
        },
      },
    });
    final again = MatchItem.fromJson(original.toJson());
    expect(again.id, 'M9');
    expect(again.homeTeam.logo, '/static/h.png');
    expect(again.prediction?.mainScore, '2-1');
    expect(again.prediction?.scenarioTitle, '均衡');

    final cached = CachedMatchDetail(
      match: original,
      prediction: original.prediction,
      savedAt: DateTime.parse('2026-11-06T12:00:00'),
    );
    final restored = CachedMatchDetail.fromJson(cached.toJson());
    expect(restored.match.id, 'M9');
    expect(restored.prediction?.homeWinProb, 0.4);
    expect(restored.savedAt.toIso8601String(), startsWith('2026-11-06'));
  });

  test('MatchDetailCache prune keeps newest entries', () {
    final t0 = DateTime.parse('2026-11-01T00:00:00');
    final map = {
      for (var i = 0; i < 5; i++)
        'M$i': CachedMatchDetail(
          match: MatchItem(
            id: 'M$i',
            status: 'upcoming',
            homeTeam: const TeamBrief(id: 'h', name: 'H'),
            awayTeam: const TeamBrief(id: 'a', name: 'A'),
          ),
          savedAt: t0.add(Duration(hours: i)),
        ),
    };
    final pruned = MatchDetailCache.pruneToLimit(map, 2);
    expect(pruned.keys.toSet(), {'M3', 'M4'});
  });

  test('SensitivityResult parses lambda scan payload', () {
    final result = SensitivityResult.fromJson({
      'match': {'id': 'M1', 'home_team': '主', 'away_team': '客'},
      'meta': {'simulations': 2000, 'step': 0.1, 'range': 0.3},
      'series': {
        'lambda_home': {
          'base': 1.4,
          'points': [
            {
              'lambda': 1.1,
              'delta': -0.3,
              'home_win_prob': 0.3,
              'draw_prob': 0.3,
              'away_win_prob': 0.4,
            },
            {
              'lambda': 1.4,
              'delta': 0.0,
              'home_win_prob': 0.4,
              'draw_prob': 0.3,
              'away_win_prob': 0.3,
            },
          ],
        },
        'lambda_away': {
          'base': 1.1,
          'points': [
            {
              'lambda': 1.1,
              'delta': 0.0,
              'home_win_prob': 0.4,
              'draw_prob': 0.3,
              'away_win_prob': 0.3,
            },
          ],
        },
      },
    });
    expect(result.matchId, 'M1');
    expect(result.lambdaHome.points, hasLength(2));
    expect(result.lambdaHome.base, 1.4);
    expect(result.lambdaHome.points.first.delta, -0.3);
  });

  test('OddsSnapshot implied probs and vs-model compare', () {
    final snap = OddsSnapshot.fromJson({
      'id': 1,
      'match_id': 'M1',
      'captured_at': '2026-11-06T10:00:00',
      'handicap': -1,
      'odds_nspf_win': 2.0,
      'odds_nspf_draw': 3.0,
      'odds_nspf_lose': 4.0,
      'source': '500',
    });
    expect(snap.handicap, -1);
    final implied = snap.implied;
    expect(implied, isNotNull);
    expect(implied!.home + implied.draw + implied.away, closeTo(1.0, 1e-9));

    final vs = compareImpliedToModel(
      impliedHome: implied.home,
      impliedDraw: implied.draw,
      impliedAway: implied.away,
      modelHome: 0.5,
      modelDraw: 0.3,
      modelAway: 0.2,
    );
    expect(vs, isNotNull);
    expect(vs!.maxAbsDeltaPct, greaterThan(0));
  });
}
