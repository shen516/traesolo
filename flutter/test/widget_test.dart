import 'package:flutter_test/flutter_test.dart';
import 'package:traesolo/core/config.dart';
import 'package:traesolo/data/models/match.dart';

void main() {
  test('AppConfig exposes default emulator API base', () {
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
}
