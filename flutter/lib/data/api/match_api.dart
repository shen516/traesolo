import '../../core/network/api_client.dart';
import '../models/match.dart';
import '../models/odds_snapshot.dart';

class MatchApi {
  MatchApi(this._client);

  final ApiClient _client;

  Future<MatchListPage> getUpcoming({
    int page = 1,
    int pageSize = 20,
    String? leagueId,
    String? keyword,
    String? matchDate,
  }) {
    return _list(
      '/matches/upcoming',
      page: page,
      pageSize: pageSize,
      leagueId: leagueId,
      keyword: keyword,
      matchDate: matchDate,
    );
  }

  Future<MatchListPage> getFinished({
    int page = 1,
    int pageSize = 20,
    String? leagueId,
    String? keyword,
    String? matchDate,
  }) {
    return _list(
      '/matches/finished',
      page: page,
      pageSize: pageSize,
      leagueId: leagueId,
      keyword: keyword,
      matchDate: matchDate,
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

  /// 赔率时序快照（需权益 `odds:snapshot`）。
  Future<List<OddsSnapshot>> getOddsSnapshots(
    String matchId, {
    int limit = 30,
  }) async {
    final data = await _client.get<Map<String, dynamic>>(
      '/matches/$matchId/odds-snapshots',
      queryParameters: {'limit': limit},
      parser: (raw) => Map<String, dynamic>.from(raw as Map),
    );
    final list = data['snapshots'];
    if (list is! List) return const [];
    return list
        .whereType<Map>()
        .map((e) => OddsSnapshot.fromJson(Map<String, dynamic>.from(e)))
        .toList();
  }

  Future<MatchListPage> _list(
    String path, {
    required int page,
    required int pageSize,
    String? leagueId,
    String? keyword,
    String? matchDate,
  }) async {
    final data = await _client.get<Map<String, dynamic>>(
      path,
      queryParameters: {
        'page': page,
        'page_size': pageSize,
        'view': 'summary',
        if (leagueId != null && leagueId.isNotEmpty) 'league_id': leagueId,
        if (keyword != null && keyword.isNotEmpty) 'keyword': keyword,
        if (matchDate != null && matchDate.isNotEmpty) 'match_date': matchDate,
      },
      parser: (raw) => Map<String, dynamic>.from(raw as Map),
    );
    return MatchListPage.fromJson(data);
  }
}
