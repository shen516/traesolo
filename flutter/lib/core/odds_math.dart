/// 市场隐含概率 vs 模型概率的简要比对（只读分析）。
class OddsVsModel {
  const OddsVsModel({
    required this.maxAbsDeltaPct,
    required this.agreeTendency,
    required this.level,
  });

  final double maxAbsDeltaPct;
  final bool agreeTendency;
  final String level; // low | mid | high
}

OddsVsModel? compareImpliedToModel({
  required double impliedHome,
  required double impliedDraw,
  required double impliedAway,
  required double modelHome,
  required double modelDraw,
  required double modelAway,
}) {
  final s = modelHome + modelDraw + modelAway;
  if (s <= 0) return null;
  final home = modelHome / s;
  final draw = modelDraw / s;
  final away = modelAway / s;
  final absHome = (impliedHome - home).abs();
  final absDraw = (impliedDraw - draw).abs();
  final absAway = (impliedAway - away).abs();
  var maxAbs = absHome;
  if (absDraw >= maxAbs) maxAbs = absDraw;
  if (absAway >= maxAbs) maxAbs = absAway;

  String modelTendency = 'H';
  if (draw >= home && draw >= away) {
    modelTendency = 'D';
  } else if (away >= home && away >= draw) {
    modelTendency = 'A';
  }
  String marketTendency = 'H';
  if (impliedDraw >= impliedHome && impliedDraw >= impliedAway) {
    marketTendency = 'D';
  } else if (impliedAway >= impliedHome && impliedAway >= impliedDraw) {
    marketTendency = 'A';
  }

  String level = 'low';
  if (maxAbs >= 0.12) {
    level = 'high';
  } else if (maxAbs >= 0.06) {
    level = 'mid';
  }

  return OddsVsModel(
    maxAbsDeltaPct: maxAbs * 100,
    agreeTendency: modelTendency == marketTendency,
    level: level,
  );
}
