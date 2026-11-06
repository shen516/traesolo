import '../api/scorer_api.dart';
import '../api/standing_api.dart';
import '../models/scorer.dart';
import '../models/standing.dart';
import 'team_repository.dart';

class LeagueBoardData {
  const LeagueBoardData({
    required this.standings,
    required this.scorers,
    this.season,
  });

  final List<StandingRow> standings;
  final List<ScorerRow> scorers;
  final String? season;
}

class DataRepository {
  DataRepository(this._standingApi, this._scorerApi, this._teamRepository);

  final StandingApi _standingApi;
  final ScorerApi _scorerApi;
  final TeamRepository _teamRepository;

  Future<LeagueBoardData> board(String leagueId) async {
    final names = await _teamRepository.nameMap(leagueId);
    final standings = await _standingApi.byLeague(leagueId, teamNames: names);
    final scorers = await _scorerApi.byLeague(leagueId, teamNames: names);
    final season = standings.isNotEmpty
        ? standings.first.season
        : (scorers.isNotEmpty ? scorers.first.season : null);
    return LeagueBoardData(
      standings: standings,
      scorers: scorers,
      season: season,
    );
  }
}
