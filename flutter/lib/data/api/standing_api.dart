import '../../core/network/api_client.dart';
import '../models/standing.dart';

class StandingApi {
  StandingApi(this._client);

  final ApiClient _client;

  Future<List<StandingRow>> byLeague(
    String leagueId, {
    String? season,
    Map<String, String>? teamNames,
    Map<String, String?>? teamLogos,
  }) async {
    final data = await _client.get<Map<String, dynamic>>(
      '/standings/league/$leagueId',
      queryParameters: {
        if (season != null && season.isNotEmpty) 'season': season,
      },
      parser: (raw) => Map<String, dynamic>.from(raw as Map),
    );
    final list = data['standings'];
    if (list is! List) return const [];
    return list
        .whereType<Map>()
        .map(
          (e) => StandingRow.fromJson(
            Map<String, dynamic>.from(e),
            teamNames: teamNames,
            teamLogos: teamLogos,
          ),
        )
        .toList();
  }
}
