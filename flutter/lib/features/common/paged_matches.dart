import 'package:flutter/foundation.dart';

import '../../data/models/match.dart';

@immutable
class PagedMatches {
  const PagedMatches({
    this.matches = const [],
    this.page = 1,
    this.pages = 0,
    this.total = 0,
    this.loadingMore = false,
    this.missingScoreTotal,
  });

  final List<MatchItem> matches;
  final int page;
  final int pages;
  final int total;
  final bool loadingMore;
  final int? missingScoreTotal;

  bool get hasMore => pages > 0 ? page < pages : false;

  PagedMatches copyWith({
    List<MatchItem>? matches,
    int? page,
    int? pages,
    int? total,
    bool? loadingMore,
    int? missingScoreTotal,
  }) {
    return PagedMatches(
      matches: matches ?? this.matches,
      page: page ?? this.page,
      pages: pages ?? this.pages,
      total: total ?? this.total,
      loadingMore: loadingMore ?? this.loadingMore,
      missingScoreTotal: missingScoreTotal ?? this.missingScoreTotal,
    );
  }

  factory PagedMatches.fromPage(MatchListPage page) {
    return PagedMatches(
      matches: page.matches,
      page: page.page,
      pages: page.pages,
      total: page.total,
      missingScoreTotal: page.missingScoreTotal,
    );
  }

  PagedMatches appendPage(MatchListPage next) {
    return PagedMatches(
      matches: [...matches, ...next.matches],
      page: next.page,
      pages: next.pages,
      total: next.total,
      loadingMore: false,
      missingScoreTotal: next.missingScoreTotal ?? missingScoreTotal,
    );
  }
}
