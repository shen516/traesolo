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
      parser: (raw) => Map<String, dynamic>.from(raw as Map),
    );
    return SimulationResult.fromJson(data);
  }

  Future<SensitivityResult> sensitivity({
    required String matchId,
    int simulations = AppConfig.defaultSensitivitySimulations,
    int? seed,
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
}
