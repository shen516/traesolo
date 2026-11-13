import 'package:dio/dio.dart';

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
    CancelToken? cancelToken,
  }) =>
      _api.simulate(
        matchId: matchId,
        simulations: simulations,
        seed: seed,
        cancelToken: cancelToken,
      );

  Future<SensitivityResult> sensitivity({
    required String matchId,
    int simulations = AppConfig.defaultSensitivitySimulations,
    int? seed,
    CancelToken? cancelToken,
  }) =>
      _api.sensitivity(
        matchId: matchId,
        simulations: simulations,
        seed: seed,
        cancelToken: cancelToken,
      );

  Future<List<SimulationHistoryItem>> history({
    int limit = 10,
    String? matchId,
  }) =>
      _api.history(limit: limit, matchId: matchId);

  Future<SimulationBetPage> listBets({
    int page = 1,
    int pageSize = 20,
    String? status,
    String? playType,
  }) =>
      _api.listBets(
        page: page,
        pageSize: pageSize,
        status: status,
        playType: playType,
      );

  Future<SimulationBet> createBet({
    required String matchId,
    required String playType,
    required String selection,
    required double sp,
    required String spSource,
    double stake = 2.0,
    int multiple = 1,
  }) =>
      _api.createBet(
        matchId: matchId,
        playType: playType,
        selection: selection,
        sp: sp,
        spSource: spSource,
        stake: stake,
        multiple: multiple,
      );

  Future<ParlayCreateResult> createParlay({
    required List<CreateParlayLeg> legs,
    double stake = 2.0,
    int multiple = 1,
  }) =>
      _api.createParlay(legs: legs, stake: stake, multiple: multiple);

  Future<SimulationBetStats> betStats() => _api.betStats();

  Future<SimulationBet> voidBet(int betId) => _api.voidBet(betId);
}
