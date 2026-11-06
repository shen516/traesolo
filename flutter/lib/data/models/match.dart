class TeamBrief {
  const TeamBrief({
    required this.id,
    required this.name,
    this.shortName,
    this.logo,
  });

  final String id;
  final String name;
  final String? shortName;
  final String? logo;

  factory TeamBrief.fromJson(Map<String, dynamic>? json) {
    if (json == null) {
      return const TeamBrief(id: '', name: '-');
    }
    return TeamBrief(
      id: (json['id'] ?? '').toString(),
      name: (json['name'] ?? json['short_name'] ?? '-').toString(),
      shortName: json['short_name']?.toString(),
      logo: json['logo']?.toString(),
    );
  }

  String get displayName => (shortName != null && shortName!.isNotEmpty) ? shortName! : name;

  Map<String, dynamic> toJson() => {
        'id': id,
        'name': name,
        if (shortName != null) 'short_name': shortName,
        if (logo != null) 'logo': logo,
      };
}

class LeagueBrief {
  const LeagueBrief({
    required this.id,
    required this.name,
    this.logo,
    this.icon,
  });

  final String id;
  final String name;
  final String? logo;
  final String? icon;

  factory LeagueBrief.fromJson(Map<String, dynamic>? json) {
    if (json == null) {
      return const LeagueBrief(id: '', name: '-');
    }
    return LeagueBrief(
      id: (json['id'] ?? '').toString(),
      name: (json['name'] ?? '-').toString(),
      logo: json['logo']?.toString(),
      icon: json['icon']?.toString(),
    );
  }

  Map<String, dynamic> toJson() => {
        'id': id,
        'name': name,
        if (logo != null) 'logo': logo,
        if (icon != null) 'icon': icon,
      };
}

class PredictionSummary {
  const PredictionSummary({
    this.mainScore,
    this.tendency,
    this.confidence,
    this.riskLevel,
    this.homeWinProb,
    this.drawProb,
    this.awayWinProb,
    this.totalGoals,
    this.modelVersion,
    this.analysis,
    this.altScores = const [],
    this.primaryScenario,
    this.scenarioReason,
    this.scenarioLabel,
  });

  final String? mainScore;
  final String? tendency;
  final String? confidence;
  final String? riskLevel;
  final double? homeWinProb;
  final double? drawProb;
  final double? awayWinProb;
  final dynamic totalGoals;
  final String? modelVersion;
  final String? analysis;
  final List<String> altScores;
  final String? primaryScenario;
  final String? scenarioReason;
  final String? scenarioLabel;

  factory PredictionSummary.fromJson(Map<String, dynamic>? json) {
    if (json == null) return const PredictionSummary();
    double? asDouble(dynamic v) {
      if (v == null) return null;
      if (v is num) return v.toDouble();
      return double.tryParse(v.toString());
    }

    final alts = json['alt_scores'];
    final primary = json['primary_scenario']?.toString();
    String? label;
    final scenarios = json['scenarios'];
    if (primary != null && scenarios is Map) {
      final pack = scenarios[primary];
      if (pack is Map) {
        label = pack['label']?.toString() ?? pack['name']?.toString();
      }
    }

    return PredictionSummary(
      mainScore: json['main_score']?.toString(),
      tendency: json['tendency']?.toString(),
      confidence: json['confidence']?.toString(),
      riskLevel: json['risk_level']?.toString(),
      homeWinProb: asDouble(json['home_win_prob']),
      drawProb: asDouble(json['draw_prob']),
      awayWinProb: asDouble(json['away_win_prob']),
      totalGoals: json['total_goals'],
      modelVersion: json['model_version']?.toString(),
      analysis: json['analysis']?.toString(),
      altScores: alts is List ? alts.map((e) => e.toString()).toList() : const [],
      primaryScenario: primary,
      scenarioReason: json['scenario_reason']?.toString(),
      scenarioLabel: label,
    );
  }

  bool get hasProbs => homeWinProb != null || drawProb != null || awayWinProb != null;

  bool get hasContent =>
      hasProbs ||
      (mainScore != null && mainScore!.isNotEmpty) ||
      (analysis != null && analysis!.isNotEmpty);

  String get scenarioTitle {
    if (scenarioLabel != null && scenarioLabel!.isNotEmpty) return scenarioLabel!;
    if (primaryScenario != null && primaryScenario!.isNotEmpty) {
      return primaryScenario!;
    }
    return '';
  }

  Map<String, dynamic> toJson() {
    final map = <String, dynamic>{
      if (mainScore != null) 'main_score': mainScore,
      if (tendency != null) 'tendency': tendency,
      if (confidence != null) 'confidence': confidence,
      if (riskLevel != null) 'risk_level': riskLevel,
      if (homeWinProb != null) 'home_win_prob': homeWinProb,
      if (drawProb != null) 'draw_prob': drawProb,
      if (awayWinProb != null) 'away_win_prob': awayWinProb,
      if (totalGoals != null) 'total_goals': totalGoals,
      if (modelVersion != null) 'model_version': modelVersion,
      if (analysis != null) 'analysis': analysis,
      if (altScores.isNotEmpty) 'alt_scores': altScores,
      if (primaryScenario != null) 'primary_scenario': primaryScenario,
      if (scenarioReason != null) 'scenario_reason': scenarioReason,
    };
    if (primaryScenario != null &&
        primaryScenario!.isNotEmpty &&
        scenarioLabel != null &&
        scenarioLabel!.isNotEmpty) {
      map['scenarios'] = {
        primaryScenario!: {'label': scenarioLabel},
      };
    }
    return map;
  }
}

class MatchItem {
  const MatchItem({
    required this.id,
    required this.status,
    this.matchDate,
    this.matchTime,
    this.homeGoals,
    this.awayGoals,
    this.result,
    this.homeTeam = const TeamBrief(id: '', name: '-'),
    this.awayTeam = const TeamBrief(id: '', name: '-'),
    this.league = const LeagueBrief(id: '', name: '-'),
    this.prediction,
    this.matchNo,
    this.handicap,
    this.oddsNspfWin,
    this.oddsNspfDraw,
    this.oddsNspfLose,
    this.oddsSpfWin,
    this.oddsSpfDraw,
    this.oddsSpfLose,
    this.isSingle = false,
  });

  final String id;
  final String status;
  final String? matchDate;
  final String? matchTime;
  final int? homeGoals;
  final int? awayGoals;
  final String? result;
  final TeamBrief homeTeam;
  final TeamBrief awayTeam;
  final LeagueBrief league;
  final PredictionSummary? prediction;
  final String? matchNo;
  final double? handicap;
  final double? oddsNspfWin;
  final double? oddsNspfDraw;
  final double? oddsNspfLose;
  final double? oddsSpfWin;
  final double? oddsSpfDraw;
  final double? oddsSpfLose;
  final bool isSingle;

  factory MatchItem.fromJson(Map<String, dynamic> json) {
    int? asInt(dynamic v) {
      if (v == null) return null;
      if (v is int) return v;
      if (v is num) return v.toInt();
      return int.tryParse(v.toString());
    }

    double? asDouble(dynamic v) {
      if (v == null) return null;
      if (v is num) return v.toDouble();
      return double.tryParse(v.toString());
    }

    final pred = json['prediction'];
    return MatchItem(
      id: (json['id'] ?? '').toString(),
      status: (json['status'] ?? '').toString(),
      matchDate: json['match_date']?.toString(),
      matchTime: json['match_time']?.toString(),
      homeGoals: asInt(json['home_goals']),
      awayGoals: asInt(json['away_goals']),
      result: json['result']?.toString(),
      homeTeam: TeamBrief.fromJson(json['home_team'] as Map<String, dynamic>?),
      awayTeam: TeamBrief.fromJson(json['away_team'] as Map<String, dynamic>?),
      league: LeagueBrief.fromJson(json['league'] as Map<String, dynamic>?),
      prediction: pred is Map<String, dynamic> ? PredictionSummary.fromJson(pred) : null,
      matchNo: json['match_no']?.toString(),
      handicap: asDouble(json['handicap'] ?? json['handicap_line']),
      oddsNspfWin: asDouble(json['odds_nspf_win']),
      oddsNspfDraw: asDouble(json['odds_nspf_draw']),
      oddsNspfLose: asDouble(json['odds_nspf_lose']),
      oddsSpfWin: asDouble(json['odds_spf_win']),
      oddsSpfDraw: asDouble(json['odds_spf_draw']),
      oddsSpfLose: asDouble(json['odds_spf_lose']),
      isSingle: json['is_single'] == true,
    );
  }

  bool get hasNspf =>
      oddsNspfWin != null || oddsNspfDraw != null || oddsNspfLose != null;

  String get scoreText {
    if (homeGoals == null || awayGoals == null) return 'vs';
    return '$homeGoals - $awayGoals';
  }

  String get whenText {
    final d = matchDate ?? '';
    final t = matchTime ?? '';
    if (d.isEmpty && t.isEmpty) return '-';
    if (t.isEmpty) return d;
    if (d.isEmpty) return t;
    return '$d $t';
  }

  static String formatOdds(double? v) {
    if (v == null) return '-';
    return v.toStringAsFixed(2);
  }

  Map<String, dynamic> toJson() => {
        'id': id,
        'status': status,
        if (matchDate != null) 'match_date': matchDate,
        if (matchTime != null) 'match_time': matchTime,
        if (homeGoals != null) 'home_goals': homeGoals,
        if (awayGoals != null) 'away_goals': awayGoals,
        if (result != null) 'result': result,
        'home_team': homeTeam.toJson(),
        'away_team': awayTeam.toJson(),
        'league': league.toJson(),
        if (prediction != null) 'prediction': prediction!.toJson(),
        if (matchNo != null) 'match_no': matchNo,
        if (handicap != null) 'handicap': handicap,
        if (oddsNspfWin != null) 'odds_nspf_win': oddsNspfWin,
        if (oddsNspfDraw != null) 'odds_nspf_draw': oddsNspfDraw,
        if (oddsNspfLose != null) 'odds_nspf_lose': oddsNspfLose,
        if (oddsSpfWin != null) 'odds_spf_win': oddsSpfWin,
        if (oddsSpfDraw != null) 'odds_spf_draw': oddsSpfDraw,
        if (oddsSpfLose != null) 'odds_spf_lose': oddsSpfLose,
        'is_single': isSingle,
      };
}

class MatchListPage {
  const MatchListPage({
    required this.matches,
    required this.page,
    required this.pageSize,
    required this.total,
    required this.pages,
    this.disclaimer,
    this.availableDates = const [],
    this.missingScoreTotal,
  });

  final List<MatchItem> matches;
  final int page;
  final int pageSize;
  final int total;
  final int pages;
  final String? disclaimer;
  final List<String> availableDates;
  final int? missingScoreTotal;

  factory MatchListPage.fromJson(Map<String, dynamic> json) {
    final list = json['matches'];
    final pagination = (json['pagination'] as Map<String, dynamic>?) ?? const {};
    final dates = json['available_dates'];
    return MatchListPage(
      matches: list is List
          ? list
              .whereType<Map>()
              .map((e) => MatchItem.fromJson(Map<String, dynamic>.from(e)))
              .toList()
          : const [],
      page: (pagination['page'] as num?)?.toInt() ?? 1,
      pageSize: (pagination['page_size'] as num?)?.toInt() ?? 20,
      total: (pagination['total'] as num?)?.toInt() ?? 0,
      pages: (pagination['pages'] as num?)?.toInt() ?? 0,
      disclaimer: json['disclaimer']?.toString(),
      availableDates: dates is List
          ? dates.map((e) => e.toString()).toList()
          : const [],
      missingScoreTotal: (json['missing_score_total'] as num?)?.toInt(),
    );
  }
}
