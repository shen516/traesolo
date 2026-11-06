class SimulationSideResult {
  const SimulationSideResult({
    this.homeWinProb,
    this.drawProb,
    this.awayWinProb,
    this.lambdaHome,
    this.lambdaAway,
    this.mainScore,
    this.altScores = const [],
    this.weightSource,
    this.over25,
    this.over35,
    this.btts,
    this.totalGoalsAvg,
    this.topScores = const [],
  });

  final double? homeWinProb;
  final double? drawProb;
  final double? awayWinProb;
  final double? lambdaHome;
  final double? lambdaAway;
  final String? mainScore;
  final List<String> altScores;
  final String? weightSource;
  final double? over25;
  final double? over35;
  final double? btts;
  final double? totalGoalsAvg;
  final List<String> topScores;

  bool get hasProbs =>
      homeWinProb != null || drawProb != null || awayWinProb != null;

  factory SimulationSideResult.fromJson(Map<String, dynamic>? json) {
    if (json == null) return const SimulationSideResult();
    double? asDouble(dynamic v) {
      if (v == null) return null;
      if (v is num) return v.toDouble();
      return double.tryParse(v.toString());
    }

    final alts = json['alt_scores'];
    final mc = json['mc'];
    List<String> tops = const [];
    if (mc is Map) {
      final raw = mc['top_scores'];
      if (raw is List) {
        tops = raw.map((e) {
          if (e is Map) return (e['score'] ?? e).toString();
          return e.toString();
        }).toList();
      }
    }

    return SimulationSideResult(
      homeWinProb: asDouble(json['home_win_prob']),
      drawProb: asDouble(json['draw_prob']),
      awayWinProb: asDouble(json['away_win_prob']),
      lambdaHome: asDouble(json['lambda_home']),
      lambdaAway: asDouble(json['lambda_away']),
      mainScore: json['main_score']?.toString(),
      altScores: alts is List ? alts.map((e) => e.toString()).toList() : const [],
      weightSource: json['weight_source']?.toString(),
      over25: mc is Map ? asDouble(mc['over_2_5_prob']) : null,
      over35: mc is Map ? asDouble(mc['over_3_5_prob']) : null,
      btts: mc is Map ? asDouble(mc['btts_prob']) : null,
      totalGoalsAvg: mc is Map ? asDouble(mc['total_goals_avg']) : null,
      topScores: tops,
    );
  }
}

class SimulationMeta {
  const SimulationMeta({
    this.elapsedMs,
    this.simulations,
    this.seed,
    this.appliedOverrides = const [],
    this.warnings = const [],
    this.cacheHit = false,
  });

  final int? elapsedMs;
  final int? simulations;
  final int? seed;
  final List<String> appliedOverrides;
  final List<String> warnings;
  final bool cacheHit;

  factory SimulationMeta.fromJson(Map<String, dynamic>? json) {
    if (json == null) return const SimulationMeta();
    final applied = json['applied_overrides'];
    final warnings = json['warnings'];
    return SimulationMeta(
      elapsedMs: (json['elapsed_ms'] as num?)?.toInt(),
      simulations: (json['simulations'] as num?)?.toInt(),
      seed: (json['seed'] as num?)?.toInt(),
      appliedOverrides: applied is List
          ? applied.map((e) => e.toString()).toList()
          : const [],
      warnings: warnings is List
          ? warnings.map((e) => e.toString()).toList()
          : const [],
      cacheHit: json['cache_hit'] == true,
    );
  }
}

class SimulationResult {
  const SimulationResult({
    required this.matchId,
    this.baseline = const SimulationSideResult(),
    this.simulated = const SimulationSideResult(),
    this.meta = const SimulationMeta(),
  });

  final String matchId;
  final SimulationSideResult baseline;
  final SimulationSideResult simulated;
  final SimulationMeta meta;

  factory SimulationResult.fromJson(Map<String, dynamic> json) {
    final match = json['match'];
    return SimulationResult(
      matchId: match is Map
          ? (match['id'] ?? '').toString()
          : (json['match_id'] ?? '').toString(),
      baseline: SimulationSideResult.fromJson(
        json['baseline'] is Map
            ? Map<String, dynamic>.from(json['baseline'] as Map)
            : null,
      ),
      simulated: SimulationSideResult.fromJson(
        json['simulated'] is Map
            ? Map<String, dynamic>.from(json['simulated'] as Map)
            : null,
      ),
      meta: SimulationMeta.fromJson(
        json['meta'] is Map
            ? Map<String, dynamic>.from(json['meta'] as Map)
            : null,
      ),
    );
  }
}

class SimulationHistoryItem {
  const SimulationHistoryItem({
    required this.id,
    required this.matchId,
    this.matchName,
    this.simulations,
    this.seed,
    this.elapsedMs,
    this.createdAt,
    this.mainScore,
    this.homeWinProb,
    this.drawProb,
    this.awayWinProb,
  });

  final int id;
  final String matchId;
  final String? matchName;
  final int? simulations;
  final int? seed;
  final int? elapsedMs;
  final String? createdAt;
  final String? mainScore;
  final double? homeWinProb;
  final double? drawProb;
  final double? awayWinProb;

  factory SimulationHistoryItem.fromJson(Map<String, dynamic> json) {
    double? asDouble(dynamic v) {
      if (v == null) return null;
      if (v is num) return v.toDouble();
      return double.tryParse(v.toString());
    }

    final summary = json['summary'];
    final sum = summary is Map ? Map<String, dynamic>.from(summary) : const {};
    return SimulationHistoryItem(
      id: (json['id'] as num?)?.toInt() ?? 0,
      matchId: (json['match_id'] ?? '').toString(),
      matchName: json['match_name']?.toString(),
      simulations: (json['simulations'] as num?)?.toInt(),
      seed: (json['seed'] as num?)?.toInt(),
      elapsedMs: (json['elapsed_ms'] as num?)?.toInt(),
      createdAt: json['created_at']?.toString(),
      mainScore: sum['main_score']?.toString(),
      homeWinProb: asDouble(sum['home_win_prob']),
      drawProb: asDouble(sum['draw_prob']),
      awayWinProb: asDouble(sum['away_win_prob']),
    );
  }
}
