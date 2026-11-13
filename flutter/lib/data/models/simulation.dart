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
    this.prize = const SimulationPrize(),
    this.matchName = '',
  });

  final String matchId;
  final SimulationSideResult baseline;
  final SimulationSideResult simulated;
  final SimulationMeta meta;
  final SimulationPrize prize;

  /// 冗余场次名（home vs away），便于落单展示。
  final String matchName;

  factory SimulationResult.fromJson(Map<String, dynamic> json) {
    final match = json['match'];
    final matchObj = match is Map ? Map<String, dynamic>.from(match) : const <String, dynamic>{};
    final home = matchObj['home_team'];
    final away = matchObj['away_team'];
    String name = '';
    if (home is Map && away is Map) {
      name = '${home['name']} vs ${away['name']}';
    }
    return SimulationResult(
      matchId: matchObj['id']?.toString() ?? (json['match_id'] ?? '').toString(),
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
      prize: SimulationPrize.fromJson(
        json['prize'] is Map
            ? Map<String, dynamic>.from(json['prize'] as Map)
            : null,
      ),
      matchName: name,
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

/// 单个玩法选项块（spf/nspf/bf/tg/hspf）。
class PrizeOptionBlock {
  const PrizeOptionBlock({
    this.probs = const {},
    this.sp = const {},
    this.implied = const {},
    this.ev = const {},
    this.valueFlags = const {},
    this.payout = const {},
    this.handicap,
    this.handicapSource,
  });

  final Map<String, double> probs;
  final Map<String, double> sp;
  final Map<String, double> implied;
  final Map<String, double> ev;
  final Map<String, double> valueFlags;
  final Map<String, double> payout;
  final int? handicap;
  final String? handicapSource;

  bool get hasAny => sp.isNotEmpty;

  factory PrizeOptionBlock.fromJson(Map<String, dynamic>? json) {
    if (json == null) return const PrizeOptionBlock();
    Map<String, double> toD(Map<String, dynamic>? raw) {
      if (raw == null) return const {};
      return raw.map((k, v) => MapEntry(k, _asD(v) ?? 0));
    }

    return PrizeOptionBlock(
      probs: toD(_map(json['probs'])),
      sp: toD(_map(json['sp'])),
      implied: toD(_map(json['implied'])),
      ev: toD(_map(json['ev'])),
      valueFlags: toD(_map(json['value_flags'])),
      payout: toD(_map(json['payout'])),
      handicap: (json['handicap'] as num?)?.toInt(),
      handicapSource: json['handicap_source']?.toString(),
    );
  }
}

/// 奖金预估块：五玩法 + 块级 SP 来源。
class SimulationPrize {
  const SimulationPrize({
    this.spSource = const {},
    this.spSourceDetail = const {},
    this.snapshotAt,
    this.overround,
    this.spf = const PrizeOptionBlock(),
    this.nspf = const PrizeOptionBlock(),
    this.bf = const PrizeOptionBlock(),
    this.tg = const PrizeOptionBlock(),
    this.hspf = const PrizeOptionBlock(),
  });

  final Map<String, String> spSource;
  final Map<String, String> spSourceDetail;
  final String? snapshotAt;
  final double? overround;
  final PrizeOptionBlock spf;
  final PrizeOptionBlock nspf;
  final PrizeOptionBlock bf;
  final PrizeOptionBlock tg;
  final PrizeOptionBlock hspf;

  PrizeOptionBlock blockOf(String playType) {
    switch (playType) {
      case 'spf':
        return spf;
      case 'nspf':
        return nspf;
      case 'bf':
        return bf;
      case 'tg':
        return tg;
      case 'hspf':
        return hspf;
      default:
        return const PrizeOptionBlock();
    }
  }

  factory SimulationPrize.fromJson(Map<String, dynamic>? json) {
    if (json == null) return const SimulationPrize();
    Map<String, String> toS(Map<String, dynamic>? raw) {
      if (raw == null) return const {};
      return raw.map((k, v) => MapEntry(k, v.toString()));
    }

    return SimulationPrize(
      spSource: toS(_map(json['sp_source'])),
      spSourceDetail: toS(_map(json['sp_source_detail'])),
      snapshotAt: json['snapshot_at']?.toString(),
      overround: _asD(json['overround']),
      spf: PrizeOptionBlock.fromJson(_map(json['spf'])),
      nspf: PrizeOptionBlock.fromJson(_map(json['nspf'])),
      bf: PrizeOptionBlock.fromJson(_map(json['bf'])),
      tg: PrizeOptionBlock.fromJson(_map(json['tg'])),
      hspf: PrizeOptionBlock.fromJson(_map(json['hspf'])),
    );
  }
}

/// 模拟投注单行（后端 bet_to_dict 结构）。
class SimulationBet {
  const SimulationBet({
    required this.id,
    this.combinationId,
    this.isParlay = false,
    this.userId,
    this.matchId = '',
    this.matchNo,
    this.matchName,
    this.playType = '',
    this.selection = '',
    this.spAtCreate,
    this.spSourceAtCreate,
    this.stake,
    this.multiple = 1,
    this.status = 'pending',
    this.payout = 0,
    this.settledAt,
    this.createdAt,
    this.potentialPayout,
  });

  final int id;
  final String? combinationId;
  final bool isParlay;
  final int? userId;
  final String matchId;
  final String? matchNo;
  final String? matchName;
  final String playType;
  final String selection;
  final double? spAtCreate;
  final String? spSourceAtCreate;
  final double? stake;
  final int multiple;
  final String status;
  final double payout;
  final String? settledAt;
  final String? createdAt;

  /// 串关预测派奖（仅组首行返回时非空）。
  final double? potentialPayout;

  bool get isPending => status == 'pending';
  bool get isWon => status == 'won';
  bool get isLost => status == 'lost';
  bool get isVoid => status == 'void';

  factory SimulationBet.fromJson(Map<String, dynamic> json) {
    return SimulationBet(
      id: (json['id'] as num?)?.toInt() ?? 0,
      combinationId: json['combination_id']?.toString(),
      isParlay: json['is_parlay'] == true,
      userId: (json['user_id'] as num?)?.toInt(),
      matchId: (json['match_id'] ?? '').toString(),
      matchNo: json['match_no']?.toString(),
      matchName: json['match_name']?.toString(),
      playType: (json['play_type'] ?? '').toString(),
      selection: (json['selection'] ?? '').toString(),
      spAtCreate: _asD(json['sp_at_create']),
      spSourceAtCreate: json['sp_source_at_create']?.toString(),
      stake: _asD(json['stake']),
      multiple: (json['multiple'] as num?)?.toInt() ?? 1,
      status: (json['status'] ?? 'pending').toString(),
      payout: _asD(json['payout']) ?? 0,
      settledAt: json['settled_at']?.toString(),
      createdAt: json['created_at']?.toString(),
      potentialPayout: _asD(json['potential_payout']),
    );
  }
}

/// 投注统计（/bets/stats，与后端 stats_for_user 一致）。
class SimulationBetStats {
  const SimulationBetStats({
    this.totalStake = 0,
    this.totalPayout = 0,
    this.profit = 0,
    this.settled = 0,
    this.won = 0,
    this.hitRate,
  });

  /// 累计投注金额（已结算部分，元）。
  final double totalStake;

  /// 累计派奖金额（元）。
  final double totalPayout;

  /// 累计盈亏（派奖 - 投注）。
  final double profit;

  /// 已结算单数（组合计一次）。
  final int settled;

  /// 命中单数。
  final int won;

  /// 命中率（won / settled，可能为 null）。
  final double? hitRate;

  factory SimulationBetStats.fromJson(Map<String, dynamic>? json) {
    if (json == null) return const SimulationBetStats();
    return SimulationBetStats(
      totalStake: _asD(json['total_stake']) ?? 0,
      totalPayout: _asD(json['total_payout']) ?? 0,
      profit: _asD(json['profit']) ?? 0,
      settled: (json['settled'] as num?)?.toInt() ?? 0,
      won: (json['won'] as num?)?.toInt() ?? 0,
      hitRate: _asD(json['hit_rate']),
    );
  }
}

double? _asD(dynamic v) {
  if (v == null) return null;
  if (v is num) return v.toDouble();
  return double.tryParse(v.toString());
}

Map<String, dynamic>? _map(dynamic v) {
  if (v is Map) return Map<String, dynamic>.from(v);
  return null;
}
