import 'package:dio/dio.dart';

import '../../core/config.dart';
import '../../core/network/api_client.dart';
import '../models/sensitivity.dart';
import '../models/simulation.dart';

class SimulationApi {
  SimulationApi(this._client);

  final ApiClient _client;

  Future<SimulationResult> simulate({
    required String matchId,
    int simulations = AppConfig.defaultSimulations,
    int? seed,
    CancelToken? cancelToken,
  }) async {
    final capped = simulations.clamp(1000, AppConfig.maxAppSimulations);
    final data = await _client.post<Map<String, dynamic>>(
      '/predictions/simulate',
      data: {
        'match_id': matchId,
        'simulations': capped,
        'seed': ?seed,
      },
      receiveTimeout: AppConfig.simulateReceiveTimeout,
      cancelToken: cancelToken,
      parser: (raw) => Map<String, dynamic>.from(raw as Map),
    );
    return SimulationResult.fromJson(data);
  }

  Future<SensitivityResult> sensitivity({
    required String matchId,
    int simulations = AppConfig.defaultSensitivitySimulations,
    int? seed,
    CancelToken? cancelToken,
  }) async {
    final capped =
        simulations.clamp(1000, AppConfig.maxSensitivitySimulations);
    final data = await _client.post<Map<String, dynamic>>(
      '/predictions/simulate/sensitivity',
      data: {
        'match_id': matchId,
        'simulations': capped,
        'seed': ?seed,
      },
      receiveTimeout: AppConfig.simulateReceiveTimeout,
      cancelToken: cancelToken,
      parser: (raw) => Map<String, dynamic>.from(raw as Map),
    );
    return SensitivityResult.fromJson(data);
  }

  Future<List<SimulationHistoryItem>> history({
    int limit = 10,
    String? matchId,
  }) async {
    final data = await _client.get<Map<String, dynamic>>(
      '/predictions/simulate/history',
      queryParameters: {
        'limit': limit,
        if (matchId != null && matchId.isNotEmpty) 'match_id': matchId,
      },
      parser: (raw) => Map<String, dynamic>.from(raw as Map),
    );
    final list = data['history'];
    if (list is! List) return const [];
    return list
        .whereType<Map>()
        .map((e) => SimulationHistoryItem.fromJson(Map<String, dynamic>.from(e)))
        .toList();
  }

  /// 我的模拟投注单列表（分页）。需 simulation:view。
  Future<SimulationBetPage> listBets({
    int page = 1,
    int pageSize = 20,
    String? status,
    String? playType,
  }) async {
    final data = await _client.get<Map<String, dynamic>>(
      '/simulation/bets',
      queryParameters: {
        'page': page,
        'page_size': pageSize,
        if (status != null && status.isNotEmpty) 'status': status,
        if (playType != null && playType.isNotEmpty) 'play_type': playType,
      },
      parser: (raw) => Map<String, dynamic>.from(raw as Map),
    );
    return SimulationBetPage.fromJson(data);
  }

  /// 创建单关模拟投注单。需 model:manage。
  Future<SimulationBet> createBet({
    required String matchId,
    required String playType,
    required String selection,
    required double sp,
    required String spSource,
    double stake = 2.0,
    int multiple = 1,
  }) async {
    final data = await _client.post<Map<String, dynamic>>(
      '/simulation/bets',
      data: {
        'match_id': matchId,
        'play_type': playType,
        'selection': selection,
        'sp': sp,
        'sp_source': spSource,
        'stake': stake,
        'multiple': multiple,
      },
      parser: (raw) => Map<String, dynamic>.from(raw as Map),
    );
    return SimulationBet.fromJson(data);
  }

  /// 创建串关模拟投注单（2~8 腿）。需 model:manage。
  Future<ParlayCreateResult> createParlay({
    required List<CreateParlayLeg> legs,
    double stake = 2.0,
    int multiple = 1,
  }) async {
    final data = await _client.post<Map<String, dynamic>>(
      '/simulation/bets/parlay',
      data: {
        'legs': legs.map((e) => e.toJson()).toList(),
        'stake': stake,
        'multiple': multiple,
      },
      parser: (raw) => Map<String, dynamic>.from(raw as Map),
    );
    return ParlayCreateResult.fromJson(data);
  }

  /// 累计模拟盈亏统计。需 simulation:view。
  Future<SimulationBetStats> betStats() async {
    final data = await _client.get<Map<String, dynamic>>(
      '/simulation/bets/stats',
      parser: (raw) => Map<String, dynamic>.from(raw as Map),
    );
    return SimulationBetStats.fromJson(data);
  }

  /// 开赛前整单作废。需 model:manage。
  Future<SimulationBet> voidBet(int betId) async {
    final data = await _client.post<Map<String, dynamic>>(
      '/simulation/bets/$betId/void',
      parser: (raw) => Map<String, dynamic>.from(raw as Map),
    );
    return SimulationBet.fromJson(data);
  }
}

/// 单关创建请求的腿部（串关 leg）。
class CreateParlayLeg {
  const CreateParlayLeg({
    required this.matchId,
    required this.playType,
    required this.selection,
    required this.sp,
    required this.spSource,
  });

  final String matchId;
  final String playType;
  final String selection;
  final double sp;
  final String spSource;

  Map<String, dynamic> toJson() => {
        'match_id': matchId,
        'play_type': playType,
        'selection': selection,
        'sp': sp,
        'sp_source': spSource,
      };
}

/// 串关创建结果。
class ParlayCreateResult {
  const ParlayCreateResult({required this.combinationId, this.legs = const []});

  final String combinationId;
  final List<SimulationBet> legs;

  factory ParlayCreateResult.fromJson(Map<String, dynamic> json) {
    final rawLegs = json['legs'];
    return ParlayCreateResult(
      combinationId: (json['combination_id'] ?? '').toString(),
      legs: rawLegs is List
          ? rawLegs
              .whereType<Map>()
              .map((e) => SimulationBet.fromJson(Map<String, dynamic>.from(e)))
              .toList()
          : const [],
    );
  }
}

/// 投注单分页。
class SimulationBetPage {
  const SimulationBetPage({
    this.items = const [],
    this.page = 1,
    this.pageSize = 20,
    this.total = 0,
  });

  final List<SimulationBet> items;
  final int page;
  final int pageSize;
  final int total;

  bool get hasMore => items.isNotEmpty && items.length < total;

  factory SimulationBetPage.fromJson(Map<String, dynamic> json) {
    final rawItems = json['items'];
    final pagination = json['pagination'];
    final pag = pagination is Map ? Map<String, dynamic>.from(pagination) : const <String, dynamic>{};
    return SimulationBetPage(
      items: rawItems is List
          ? rawItems
              .whereType<Map>()
              .map((e) => SimulationBet.fromJson(Map<String, dynamic>.from(e)))
              .toList()
          : const [],
      page: (pag['page'] as num?)?.toInt() ?? 1,
      pageSize: (pag['page_size'] as num?)?.toInt() ?? 20,
      total: (pag['total'] as num?)?.toInt() ?? 0,
    );
  }
}
