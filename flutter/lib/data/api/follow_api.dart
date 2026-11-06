import '../../core/network/api_client.dart';
import '../models/follow_summary.dart';

class FollowApi {
  FollowApi(this._client);

  final ApiClient _client;

  Future<FollowState> list({bool includeChildren = false}) async {
    final data = await _client.get<Map<String, dynamic>>(
      '/follows/leagues',
      queryParameters: {'include_children': includeChildren},
      parser: (raw) => Map<String, dynamic>.from(raw as Map),
    );
    return FollowState.fromJson(data);
  }

  Future<FollowSummary> summary({
    int matchLimit = 8,
    int perLeagueMatches = 0,
    int standingsLimit = 8,
    int scorersLimit = 5,
  }) async {
    final data = await _client.get<Map<String, dynamic>>(
      '/follows/summary',
      queryParameters: {
        'match_limit': matchLimit,
        'per_league_matches': perLeagueMatches,
        'standings_limit': standingsLimit,
        'scorers_limit': scorersLimit,
      },
      parser: (raw) => Map<String, dynamic>.from(raw as Map),
    );
    return FollowSummary.fromJson(data);
  }

  Future<void> follow(String leagueId) async {
    await _client.post<Map<String, dynamic>>(
      '/follows/leagues/$leagueId',
      parser: (raw) => Map<String, dynamic>.from(raw as Map? ?? const {}),
    );
  }

  Future<void> unfollow(String leagueId) async {
    await _client.delete<Map<String, dynamic>>(
      '/follows/leagues/$leagueId',
      parser: (raw) => Map<String, dynamic>.from(raw as Map? ?? const {}),
    );
  }
}
