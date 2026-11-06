import 'league.dart';
import 'match.dart';
import 'scorer.dart';
import 'standing.dart';

class FollowBoard {
  const FollowBoard({
    required this.leagueId,
    required this.leagueName,
    this.leagueLogo,
    this.leagueIcon,
    this.season,
    this.standings = const [],
    this.scorers = const [],
  });

  final String leagueId;
  final String leagueName;
  final String? leagueLogo;
  final String? leagueIcon;
  final String? season;
  final List<StandingRow> standings;
  final List<ScorerRow> scorers;

  factory FollowBoard.fromJson(Map<String, dynamic> json) {
    final standingsRaw = json['standings'];
    final scorersRaw = json['scorers'];
    return FollowBoard(
      leagueId: (json['league_id'] ?? '').toString(),
      leagueName: (json['league_name'] ?? json['league_id'] ?? '-').toString(),
      leagueLogo: json['league_logo']?.toString(),
      leagueIcon: json['league_icon']?.toString(),
      season: json['season']?.toString(),
      standings: standingsRaw is List
          ? standingsRaw
              .whereType<Map>()
              .map((e) => StandingRow.fromJson(Map<String, dynamic>.from(e)))
              .toList()
          : const [],
      scorers: scorersRaw is List
          ? scorersRaw
              .whereType<Map>()
              .map((e) => ScorerRow.fromJson(Map<String, dynamic>.from(e)))
              .toList()
          : const [],
    );
  }
}

class FollowState {
  const FollowState({
    this.leagues = const [],
    this.ids = const [],
  });

  final List<LeagueItem> leagues;
  final List<String> ids;

  factory FollowState.fromJson(Map<String, dynamic> json) {
    final leagues = json['leagues'];
    final ids = json['ids'];
    return FollowState(
      leagues: leagues is List
          ? leagues
              .whereType<Map>()
              .map((e) => LeagueItem.fromJson(Map<String, dynamic>.from(e)))
              .toList()
          : const [],
      ids: ids is List ? ids.map((e) => e.toString()).toList() : const [],
    );
  }

  bool isFollowed(String leagueId) => ids.contains(leagueId);
}

class FollowSummary {
  const FollowSummary({
    required this.state,
    this.matches = const [],
    this.boards = const [],
  });

  final FollowState state;
  final List<MatchItem> matches;
  final List<FollowBoard> boards;

  factory FollowSummary.fromJson(Map<String, dynamic> json) {
    final matches = json['matches'];
    final boards = json['boards'];
    return FollowSummary(
      state: FollowState.fromJson(json),
      matches: matches is List
          ? matches
              .whereType<Map>()
              .map((e) => MatchItem.fromJson(Map<String, dynamic>.from(e)))
              .toList()
          : const [],
      boards: boards is List
          ? boards
              .whereType<Map>()
              .map((e) => FollowBoard.fromJson(Map<String, dynamic>.from(e)))
              .toList()
          : const [],
    );
  }
}
