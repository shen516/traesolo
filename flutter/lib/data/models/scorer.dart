class ScorerRow {
  const ScorerRow({
    required this.playerName,
    this.teamId,
    this.rank = 0,
    this.goals = 0,
    this.assists = 0,
    this.gamesPlayed = 0,
    this.season,
    this.teamName,
  });

  final String playerName;
  final String? teamId;
  final int rank;
  final int goals;
  final int assists;
  final int gamesPlayed;
  final String? season;
  final String? teamName;

  String get teamLabel {
    if (teamName != null && teamName!.isNotEmpty) return teamName!;
    if (teamId != null && teamId!.isNotEmpty) return teamId!;
    return '-';
  }

  factory ScorerRow.fromJson(
    Map<String, dynamic> json, {
    Map<String, String>? teamNames,
  }) {
    int asInt(dynamic v) {
      if (v == null) return 0;
      if (v is int) return v;
      if (v is num) return v.toInt();
      return int.tryParse(v.toString()) ?? 0;
    }

    final teamId = json['team_id']?.toString() ?? json['team']?.toString();
    return ScorerRow(
      playerName: (json['player_name'] ?? json['name'] ?? '-').toString(),
      teamId: teamId,
      rank: asInt(json['rank'] ?? json['position']),
      goals: asInt(json['goals']),
      assists: asInt(json['assists']),
      gamesPlayed: asInt(json['games_played']),
      season: json['season']?.toString(),
      teamName: teamId == null ? null : teamNames?[teamId],
    );
  }
}
