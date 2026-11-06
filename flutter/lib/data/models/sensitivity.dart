class SensitivityPoint {
  const SensitivityPoint({
    required this.lambda,
    required this.delta,
    this.homeWinProb,
    this.drawProb,
    this.awayWinProb,
  });

  final double lambda;
  final double delta;
  final double? homeWinProb;
  final double? drawProb;
  final double? awayWinProb;

  factory SensitivityPoint.fromJson(Map<String, dynamic> json) {
    double asDouble(dynamic v, [double fallback = 0]) {
      if (v == null) return fallback;
      if (v is num) return v.toDouble();
      return double.tryParse(v.toString()) ?? fallback;
    }

    double? asOpt(dynamic v) {
      if (v == null) return null;
      if (v is num) return v.toDouble();
      return double.tryParse(v.toString());
    }

    return SensitivityPoint(
      lambda: asDouble(json['lambda']),
      delta: asDouble(json['delta']),
      homeWinProb: asOpt(json['home_win_prob']),
      drawProb: asOpt(json['draw_prob']),
      awayWinProb: asOpt(json['away_win_prob']),
    );
  }
}

class SensitivitySeries {
  const SensitivitySeries({
    required this.base,
    this.points = const [],
  });

  final double base;
  final List<SensitivityPoint> points;

  factory SensitivitySeries.fromJson(Map<String, dynamic>? json) {
    if (json == null) return const SensitivitySeries(base: 0);
    final raw = json['points'];
    return SensitivitySeries(
      base: (json['base'] as num?)?.toDouble() ??
          double.tryParse(json['base']?.toString() ?? '') ??
          0,
      points: raw is List
          ? raw
              .whereType<Map>()
              .map((e) => SensitivityPoint.fromJson(Map<String, dynamic>.from(e)))
              .toList()
          : const [],
    );
  }
}

class SensitivityResult {
  const SensitivityResult({
    required this.matchId,
    this.homeTeam,
    this.awayTeam,
    this.simulations,
    this.seed,
    this.step,
    this.range,
    this.lambdaHome = const SensitivitySeries(base: 0),
    this.lambdaAway = const SensitivitySeries(base: 0),
  });

  final String matchId;
  final String? homeTeam;
  final String? awayTeam;
  final int? simulations;
  final int? seed;
  final double? step;
  final double? range;
  final SensitivitySeries lambdaHome;
  final SensitivitySeries lambdaAway;

  factory SensitivityResult.fromJson(Map<String, dynamic> json) {
    final match = json['match'];
    final meta = json['meta'];
    final series = json['series'];
    final seriesMap =
        series is Map ? Map<String, dynamic>.from(series) : const <String, dynamic>{};
    final metaMap =
        meta is Map ? Map<String, dynamic>.from(meta) : const <String, dynamic>{};

    return SensitivityResult(
      matchId: match is Map
          ? (match['id'] ?? '').toString()
          : (json['match_id'] ?? '').toString(),
      homeTeam: match is Map ? match['home_team']?.toString() : null,
      awayTeam: match is Map ? match['away_team']?.toString() : null,
      simulations: (metaMap['simulations'] as num?)?.toInt(),
      seed: (metaMap['seed'] as num?)?.toInt(),
      step: (metaMap['step'] as num?)?.toDouble(),
      range: (metaMap['range'] as num?)?.toDouble(),
      lambdaHome: SensitivitySeries.fromJson(
        seriesMap['lambda_home'] is Map
            ? Map<String, dynamic>.from(seriesMap['lambda_home'] as Map)
            : null,
      ),
      lambdaAway: SensitivitySeries.fromJson(
        seriesMap['lambda_away'] is Map
            ? Map<String, dynamic>.from(seriesMap['lambda_away'] as Map)
            : null,
      ),
    );
  }
}
