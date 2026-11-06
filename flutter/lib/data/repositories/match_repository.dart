import '../api/match_api.dart';
import '../models/match.dart';

class MatchRepository {
  MatchRepository(this._api);

  final MatchApi _api;

  Future<MatchListPage> upcoming({int page = 1}) =>
      _api.getUpcoming(page: page);

  Future<MatchListPage> finished({int page = 1}) =>
      _api.getFinished(page: page);

  Future<MatchItem> detail(String id) => _api.getById(id);

  Future<PredictionSummary> prediction(String matchId) =>
      _api.getPrediction(matchId);
}
