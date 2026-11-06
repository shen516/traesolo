import '../../core/config.dart';
import '../api/simulation_api.dart';
import '../models/sensitivity.dart';
import '../models/simulation.dart';

class SimulationRepository {
  SimulationRepository(this._api);

  final SimulationApi _api;

  Future<SimulationResult> simulate({
    required String matchId,
    int simulations = AppConfig.defaultSimulations,
    int? seed,
  }) =>
      _api.simulate(matchId: matchId, simulations: simulations, seed: seed);

  Future<SensitivityResult> sensitivity({
    required String matchId,
    int simulations = AppConfig.defaultSensitivitySimulations,
    int? seed,
  }) =>
      _api.sensitivity(
        matchId: matchId,
        simulations: simulations,
        seed: seed,
      );

  Future<List<SimulationHistoryItem>> history({
    int limit = 10,
    String? matchId,
  }) =>
      _api.history(limit: limit, matchId: matchId);
}
