class TeamDetail {
  const TeamDetail({
    required this.id,
    required this.name,
    required this.shortName,
    this.logo,
    this.leagueId,
    this.country,
    this.eloRating = 1500,
    this.attackStrength = 1.0,
    this.defenseStrength = 1.0,
    this.homeGround,
    this.foundedYear,
  });

  final String id;
  final String name;
  final String shortName;
  final String? logo;
  final String? leagueId;
  final String? country;
  final int eloRating;
  final double attackStrength;
  final double defenseStrength;
  final String? homeGround;
  final int? foundedYear;

  String get displayName => shortName.isNotEmpty ? shortName : name;

  factory TeamDetail.fromJson(Map<String, dynamic> json) {
    double asDouble(dynamic v, [double fallback = 0]) {
      if (v == null) return fallback;
      if (v is num) return v.toDouble();
      return double.tryParse(v.toString()) ?? fallback;
    }

    int asInt(dynamic v, [int fallback = 0]) {
      if (v == null) return fallback;
      if (v is int) return v;
      if (v is num) return v.toInt();
      return int.tryParse(v.toString()) ?? fallback;
    }

    return TeamDetail(
      id: (json['id'] ?? '').toString(),
      name: (json['name'] ?? '-').toString(),
      shortName: (json['short_name'] ?? json['name'] ?? '-').toString(),
      logo: json['logo']?.toString(),
      leagueId: json['league_id']?.toString(),
      country: json['country']?.toString(),
      eloRating: asInt(json['elo_rating'], 1500),
      attackStrength: asDouble(json['attack_strength'], 1),
      defenseStrength: asDouble(json['defense_strength'], 1),
      homeGround: json['home_ground']?.toString(),
      foundedYear: json['founded_year'] == null
          ? null
          : asInt(json['founded_year']),
    );
  }
}
