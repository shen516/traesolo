import '../api/match_api.dart';
import '../models/match.dart';
import '../models/odds_snapshot.dart';

class MatchRepository {
  MatchRepository(this._api);

  final MatchApi _api;

  Future<MatchListPage> upcoming({
    int page = 1,
    int pageSize = 20,
    String? leagueId,
    String? keyword,
    String? matchDate,
  }) =>
      _api.getUpcoming(
        page: page,
        pageSize: pageSize,
        leagueId: leagueId,
        keyword: keyword,
        matchDate: matchDate,
      );

  Future<MatchListPage> finished({
    int page = 1,
    int pageSize = 20,
    String? leagueId,
    String? keyword,
    String? matchDate,
  }) =>
      _api.getFinished(
        page: page,
        pageSize: pageSize,
        leagueId: leagueId,
        keyword: keyword,
        matchDate: matchDate,
      );

  Future<MatchItem> detail(String id) => _api.getById(id);

  Future<PredictionSummary> prediction(String matchId) =>
      _api.getPrediction(matchId);

  Future<List<OddsSnapshot>> oddsSnapshots(
    String matchId, {
    int limit = 30,
  }) =>
      _api.getOddsSnapshots(matchId, limit: limit);
}
