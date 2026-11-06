class LeagueItem {
  const LeagueItem({
    required this.id,
    required this.name,
    this.logo,
    this.icon,
    this.country,
    this.category,
    this.isActive = true,
    this.teamsCount = 0,
    this.matchesCount = 0,
    this.upcomingCount = 0,
    this.childIds = const [],
  });

  final String id;
  final String name;
  final String? logo;
  final String? icon;
  final String? country;
  final String? category;
  final bool isActive;
  final int teamsCount;
  final int matchesCount;
  final int upcomingCount;
  final List<String> childIds;

  factory LeagueItem.fromJson(Map<String, dynamic> json) {
    final children = json['child_ids'];
    return LeagueItem(
      id: (json['id'] ?? '').toString(),
      name: (json['name'] ?? '-').toString(),
      logo: json['logo']?.toString(),
      icon: json['icon']?.toString(),
      country: json['country']?.toString(),
      category: json['category']?.toString(),
      isActive: json['is_active'] != false,
      teamsCount: (json['teams_count'] as num?)?.toInt() ?? 0,
      matchesCount: (json['matches_count'] as num?)?.toInt() ?? 0,
      upcomingCount: (json['upcoming_count'] as num?)?.toInt() ?? 0,
      childIds: children is List
          ? children.map((e) => e.toString()).toList()
          : const [],
    );
  }
}

class LeagueListPage {
  const LeagueListPage({
    required this.leagues,
    required this.total,
    required this.page,
    required this.pageSize,
    required this.totalPages,
  });

  final List<LeagueItem> leagues;
  final int total;
  final int page;
  final int pageSize;
  final int totalPages;

  factory LeagueListPage.fromJson(Map<String, dynamic> json) {
    final list = json['leagues'];
    return LeagueListPage(
      leagues: list is List
          ? list
              .whereType<Map>()
              .map((e) => LeagueItem.fromJson(Map<String, dynamic>.from(e)))
              .toList()
          : const [],
      total: (json['total'] as num?)?.toInt() ?? 0,
      page: (json['page'] as num?)?.toInt() ?? 1,
      pageSize: (json['page_size'] as num?)?.toInt() ?? 20,
      totalPages: (json['total_pages'] as num?)?.toInt() ?? 0,
    );
  }
}
