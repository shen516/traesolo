import '../api/match_api.dart';
import '../models/match.dart';

class MatchRepository {
  MatchRepository(this._api);

  final MatchApi _api;

  Future<MatchListPage> upcoming({
    int page = 1,
    int pageSize = 20,
    String? leagueId,
    String? keyword,
  }) =>
      _api.getUpcoming(
        page: page,
        pageSize: pageSize,
        leagueId: leagueId,
        keyword: keyword,
      );

  Future<MatchListPage> finished({
    int page = 1,
    int pageSize = 20,
    String? leagueId,
    String? keyword,
  }) =>
      _api.getFinished(
        page: page,
        pageSize: pageSize,
        leagueId: leagueId,
        keyword: keyword,
      );

  Future<MatchItem> detail(String id) => _api.getById(id);

  Future<PredictionSummary> prediction(String matchId) =>
      _api.getPrediction(matchId);
}
