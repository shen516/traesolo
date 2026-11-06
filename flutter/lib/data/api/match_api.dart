import '../../core/network/api_client.dart';
import '../models/match.dart';

class MatchApi {
  MatchApi(this._client);

  final ApiClient _client;

  Future<MatchListPage> getUpcoming({
    int page = 1,
    int pageSize = 20,
    String? leagueId,
    String? keyword,
  }) {
    return _list(
      '/matches/upcoming',
      page: page,
      pageSize: pageSize,
      leagueId: leagueId,
      keyword: keyword,
    );
  }

  Future<MatchListPage> getFinished({
    int page = 1,
    int pageSize = 20,
    String? leagueId,
    String? keyword,
  }) {
    return _list(
      '/matches/finished',
      page: page,
      pageSize: pageSize,
      leagueId: leagueId,
      keyword: keyword,
    );
  }

  Future<MatchItem> getById(String id) async {
    final data = await _client.get<Map<String, dynamic>>(
      '/matches/$id',
      parser: (raw) => Map<String, dynamic>.from(raw as Map),
    );
    return MatchItem.fromJson(data);
  }

  /// 默认不 recalculate，避免详情页触达重算。
  Future<PredictionSummary> getPrediction(String matchId) async {
    final data = await _client.get<Map<String, dynamic>>(
      '/matches/$matchId/prediction',
      queryParameters: const {'recalculate': false},
      parser: (raw) => Map<String, dynamic>.from(raw as Map),
    );
    return PredictionSummary.fromJson(data);
  }

  Future<MatchListPage> _list(
    String path, {
    required int page,
    required int pageSize,
    String? leagueId,
    String? keyword,
  }) async {
    final data = await _client.get<Map<String, dynamic>>(
      path,
      queryParameters: {
        'page': page,
        'page_size': pageSize,
        'view': 'summary',
        if (leagueId != null && leagueId.isNotEmpty) 'league_id': leagueId,
        if (keyword != null && keyword.isNotEmpty) 'keyword': keyword,
      },
      parser: (raw) => Map<String, dynamic>.from(raw as Map),
    );
    return MatchListPage.fromJson(data);
  }
}
