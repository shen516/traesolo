import '../../core/network/api_client.dart';

class FavoriteApi {
  FavoriteApi(this._client);

  final ApiClient _client;

  Future<Set<String>> matchIds(int userId) async {
    final data = await _client.get<Map<String, dynamic>>(
      '/favorites/user/$userId/matches',
      parser: (raw) => Map<String, dynamic>.from(raw as Map),
    );
    final list = data['favorites'];
    if (list is! List) return {};
    final ids = <String>{};
    for (final item in list) {
      if (item is! Map) continue;
      final target = item['target_id'] ?? item['match_id'] ?? item['id'];
      if (target != null) ids.add(target.toString());
    }
    return ids;
  }

  Future<void> addMatch(int userId, String matchId) async {
    await _client.post<Map<String, dynamic>>(
      '/favorites/user/$userId/match/$matchId',
      parser: (raw) => Map<String, dynamic>.from(raw as Map? ?? const {}),
    );
  }

  Future<void> removeMatch(int userId, String matchId) async {
    await _client.delete<Map<String, dynamic>>(
      '/favorites/user/$userId/match/$matchId',
      parser: (raw) => Map<String, dynamic>.from(raw as Map? ?? const {}),
    );
  }
}
