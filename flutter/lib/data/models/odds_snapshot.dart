class OddsSnapshot {
  const OddsSnapshot({
    required this.id,
    required this.matchId,
    this.capturedAt,
    this.source,
    this.handicap,
    this.oddsNspfWin,
    this.oddsNspfDraw,
    this.oddsNspfLose,
    this.oddsSpfWin,
    this.oddsSpfDraw,
    this.oddsSpfLose,
  });

  final int id;
  final String matchId;
  final String? capturedAt;
  final String? source;
  final int? handicap;
  final double? oddsNspfWin;
  final double? oddsNspfDraw;
  final double? oddsNspfLose;
  final double? oddsSpfWin;
  final double? oddsSpfDraw;
  final double? oddsSpfLose;

  double? get win => oddsNspfWin ?? oddsSpfWin;
  double? get draw => oddsNspfDraw ?? oddsSpfDraw;
  double? get lose => oddsNspfLose ?? oddsSpfLose;

  bool get hasOdds => win != null || draw != null || lose != null;

  /// 去水后隐含概率（胜/平/负），与 Web `impliedFromSp` 对齐。
  ({double home, double draw, double away, double overroundPct})? get implied {
    final w = win;
    final d = draw;
    final l = lose;
    if (w == null || d == null || l == null || w <= 0 || d <= 0 || l <= 0) {
      return null;
    }
    final rw = 1 / w;
    final rd = 1 / d;
    final rl = 1 / l;
    final s = rw + rd + rl;
    if (s <= 0) return null;
    return (
      home: rw / s,
      draw: rd / s,
      away: rl / s,
      overroundPct: (s - 1) * 100,
    );
  }

  factory OddsSnapshot.fromJson(Map<String, dynamic> json) {
    double? asDouble(dynamic v) {
      if (v == null) return null;
      if (v is num) return v.toDouble();
      return double.tryParse(v.toString());
    }

    return OddsSnapshot(
      id: (json['id'] as num?)?.toInt() ?? 0,
      matchId: (json['match_id'] ?? '').toString(),
      capturedAt: json['captured_at']?.toString(),
      source: json['source']?.toString(),
      handicap: (json['handicap'] as num?)?.toInt(),
      oddsNspfWin: asDouble(json['odds_nspf_win']),
      oddsNspfDraw: asDouble(json['odds_nspf_draw']),
      oddsNspfLose: asDouble(json['odds_nspf_lose']),
      oddsSpfWin: asDouble(json['odds_spf_win']),
      oddsSpfDraw: asDouble(json['odds_spf_draw']),
      oddsSpfLose: asDouble(json['odds_spf_lose']),
    );
  }
}
