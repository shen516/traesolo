import '../api/team_api.dart';
import '../models/team.dart';

class TeamRepository {
  TeamRepository(this._api);

  final TeamApi _api;

  Future<TeamDetail> detail(String id) => _api.getById(id);

  Future<List<TeamDetail>> byLeague(String leagueId) => _api.byLeague(leagueId);

  Future<Map<String, String>> nameMap(String leagueId) async {
    final teams = await byLeague(leagueId);
    return {
      for (final t in teams) t.id: t.displayName,
    };
  }
}
