import '../../core/network/api_client.dart';
import '../models/scorer.dart';

class ScorerApi {
  ScorerApi(this._client);

  final ApiClient _client;

  Future<List<ScorerRow>> byLeague(
    String leagueId, {
    String? season,
    Map<String, String>? teamNames,
  }) async {
    final data = await _client.get<Map<String, dynamic>>(
      '/scorers/league/$leagueId',
      queryParameters: {
        if (season != null && season.isNotEmpty) 'season': season,
      },
      parser: (raw) => Map<String, dynamic>.from(raw as Map),
    );
    final list = data['scorers'];
    if (list is! List) return const [];
    return list
        .whereType<Map>()
        .map(
          (e) => ScorerRow.fromJson(
            Map<String, dynamic>.from(e),
            teamNames: teamNames,
          ),
        )
        .toList();
  }
}
