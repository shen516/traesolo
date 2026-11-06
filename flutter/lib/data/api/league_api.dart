import '../../core/network/api_client.dart';
import '../models/league.dart';

class LeagueApi {
  LeagueApi(this._client);

  final ApiClient _client;

  Future<LeagueListPage> list({
    int page = 1,
    int pageSize = 200,
    bool? isActive = true,
    bool hasData = true,
    bool hideDuplicates = true,
  }) async {
    final data = await _client.get<Map<String, dynamic>>(
      '/leagues/',
      queryParameters: {
        'page': page,
        'page_size': pageSize,
        'is_active': ?isActive,
        'has_data': hasData,
        'hide_duplicates': hideDuplicates,
      },
      parser: (raw) => Map<String, dynamic>.from(raw as Map),
    );
    return LeagueListPage.fromJson(data);
  }

  Future<List<LeagueItem>> active() async {
    final data = await _client.get<Map<String, dynamic>>(
      '/leagues/active',
      parser: (raw) => Map<String, dynamic>.from(raw as Map),
    );
    final list = data['leagues'];
    if (list is! List) return const [];
    return list
        .whereType<Map>()
        .map((e) => LeagueItem.fromJson(Map<String, dynamic>.from(e)))
        .toList();
  }

  Future<LeagueItem> getById(String id) async {
    final data = await _client.get<Map<String, dynamic>>(
      '/leagues/$id',
      parser: (raw) => Map<String, dynamic>.from(raw as Map),
    );
    return LeagueItem.fromJson(data);
  }
}
