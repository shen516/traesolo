import '../../core/network/api_client.dart';
import '../models/team.dart';

class TeamApi {
  TeamApi(this._client);

  final ApiClient _client;

  Future<TeamDetail> getById(String id) async {
    final data = await _client.get<Map<String, dynamic>>(
      '/teams/$id',
      parser: (raw) => Map<String, dynamic>.from(raw as Map),
    );
    return TeamDetail.fromJson(data);
  }

  Future<List<TeamDetail>> byLeague(String leagueId) async {
    final data = await _client.get<Map<String, dynamic>>(
      '/teams/league/$leagueId',
      parser: (raw) => Map<String, dynamic>.from(raw as Map),
    );
    final list = data['teams'];
    if (list is! List) return const [];
    return list
        .whereType<Map>()
        .map((e) => TeamDetail.fromJson(Map<String, dynamic>.from(e)))
        .toList();
  }
}
