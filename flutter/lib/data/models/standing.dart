class StandingRow {
  const StandingRow({
    required this.teamId,
    this.rank = 0,
    this.played = 0,
    this.won = 0,
    this.drawn = 0,
    this.lost = 0,
    this.goalsFor = 0,
    this.goalsAgainst = 0,
    this.goalDiff = 0,
    this.points = 0,
    this.season,
    this.teamName,
    this.teamLogo,
  });

  final String teamId;
  final int rank;
  final int played;
  final int won;
  final int drawn;
  final int lost;
  final int goalsFor;
  final int goalsAgainst;
  final int goalDiff;
  final int points;
  final String? season;
  final String? teamName;
  final String? teamLogo;

  String get displayName =>
      (teamName != null && teamName!.isNotEmpty) ? teamName! : teamId;

  factory StandingRow.fromJson(
    Map<String, dynamic> json, {
    Map<String, String>? teamNames,
    Map<String, String?>? teamLogos,
  }) {
    int asInt(dynamic v) {
      if (v == null) return 0;
      if (v is int) return v;
      if (v is num) return v.toInt();
      return int.tryParse(v.toString()) ?? 0;
    }

    final teamId = (json['team_id'] ?? json['team'] ?? '').toString();
    return StandingRow(
      teamId: teamId,
      rank: asInt(json['rank'] ?? json['position']),
      played: asInt(json['played'] ?? json['matches_played']),
      won: asInt(json['won'] ?? json['wins']),
      drawn: asInt(json['drawn'] ?? json['draws']),
      lost: asInt(json['lost'] ?? json['losses']),
      goalsFor: asInt(json['goals_for'] ?? json['gf']),
      goalsAgainst: asInt(json['goals_against'] ?? json['ga']),
      goalDiff: asInt(json['goal_diff'] ?? json['gd']),
      points: asInt(json['points']),
      season: json['season']?.toString(),
      teamName: teamNames?[teamId] ?? json['team_name']?.toString(),
      teamLogo: teamLogos?[teamId] ?? json['team_logo']?.toString() ?? json['logo']?.toString(),
    );
  }
}
