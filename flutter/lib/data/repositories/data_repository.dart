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
    final teams = await _teamRepository.byLeague(leagueId);
    final names = {for (final t in teams) t.id: t.displayName};
    final logos = {for (final t in teams) t.id: t.logo};
    final standings = await _standingApi.byLeague(
      leagueId,
      teamNames: names,
      teamLogos: logos,
    );
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
