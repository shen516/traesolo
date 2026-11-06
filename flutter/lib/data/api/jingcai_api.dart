import '../../core/network/api_client.dart';
import '../models/match.dart';

class JingcaiApi {
  JingcaiApi(this._client);

  final ApiClient _client;

  /// 竞彩比分投注区列表（只读）。
  Future<MatchListPage> bf({
    int page = 1,
    int pageSize = 50,
    String? keyword,
    String? matchDate,
    String? status,
  }) {
    return _list(
      '/matches/jingcai/bf',
      page: page,
      pageSize: pageSize,
      keyword: keyword,
      matchDate: matchDate,
      status: status,
    );
  }

  /// 历史竞彩比分（已过开赛时间）。
  Future<MatchListPage> bfHistory({
    int page = 1,
    int pageSize = 50,
    String? keyword,
    String? matchDate,
    bool missingScore = false,
  }) {
    return _list(
      '/matches/jingcai/bf/expired',
      page: page,
      pageSize: pageSize,
      keyword: keyword,
      matchDate: matchDate,
      extra: {
        'missing_score': missingScore,
      },
    );
  }

  Future<MatchListPage> _list(
    String path, {
    required int page,
    required int pageSize,
    String? keyword,
    String? matchDate,
    String? status,
    Map<String, dynamic>? extra,
  }) async {
    final data = await _client.get<Map<String, dynamic>>(
      path,
      queryParameters: {
        'page': page,
        'page_size': pageSize,
        'view': 'summary',
        if (keyword != null && keyword.isNotEmpty) 'keyword': keyword,
        if (matchDate != null && matchDate.isNotEmpty) 'match_date': matchDate,
        if (status != null && status.isNotEmpty) 'status': status,
        ...?extra,
      },
      parser: (raw) => Map<String, dynamic>.from(raw as Map),
    );
    return MatchListPage.fromJson(data);
  }
}
