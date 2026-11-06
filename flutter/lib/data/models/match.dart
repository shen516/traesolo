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

  factory PredictionSummary.fromJson(Map<String, dynamic>? json) {
    if (json == null) return const PredictionSummary();
    double? asDouble(dynamic v) {
      if (v == null) return null;
      if (v is num) return v.toDouble();
      return double.tryParse(v.toString());
    }

    final alts = json['alt_scores'];
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
    );
  }

  bool get hasProbs => homeWinProb != null || drawProb != null || awayWinProb != null;
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

  factory MatchItem.fromJson(Map<String, dynamic> json) {
    int? asInt(dynamic v) {
      if (v == null) return null;
      if (v is int) return v;
      if (v is num) return v.toInt();
      return int.tryParse(v.toString());
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
    );
  }

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
}

class MatchListPage {
  const MatchListPage({
    required this.matches,
    required this.page,
    required this.pageSize,
    required this.total,
    required this.pages,
  });

  final List<MatchItem> matches;
  final int page;
  final int pageSize;
  final int total;
  final int pages;

  factory MatchListPage.fromJson(Map<String, dynamic> json) {
    final list = json['matches'];
    final pagination = (json['pagination'] as Map<String, dynamic>?) ?? const {};
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
    );
  }
}
