import '../api/jingcai_api.dart';
import '../models/match.dart';

class JingcaiRepository {
  JingcaiRepository(this._api);

  final JingcaiApi _api;

  Future<MatchListPage> bf({
    int page = 1,
    int pageSize = 20,
    String? keyword,
    String? matchDate,
    String? status,
  }) =>
      _api.bf(
        page: page,
        pageSize: pageSize,
        keyword: keyword,
        matchDate: matchDate,
        status: status,
      );

  Future<MatchListPage> bfHistory({
    int page = 1,
    int pageSize = 20,
    String? keyword,
    String? matchDate,
    bool missingScore = false,
  }) =>
      _api.bfHistory(
        page: page,
        pageSize: pageSize,
        keyword: keyword,
        matchDate: matchDate,
        missingScore: missingScore,
      );
}
