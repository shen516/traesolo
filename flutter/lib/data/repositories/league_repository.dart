import '../api/league_api.dart';
import '../models/league.dart';

class LeagueRepository {
  LeagueRepository(this._api);

  final LeagueApi _api;

  Future<List<LeagueItem>> selectable() async {
    final page = await _api.list();
    if (page.leagues.isNotEmpty) return page.leagues;
    return _api.active();
  }

  Future<LeagueItem> byId(String id) => _api.getById(id);
}
