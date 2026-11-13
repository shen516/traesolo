import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/config.dart';
import '../../core/providers.dart';
import '../../core/theme.dart';
import '../../data/models/league.dart';
import '../../data/models/match.dart';
import '../../widgets/league_picker_field.dart';
import '../../widgets/prediction_panel.dart';
import '../../widgets/skeleton.dart';
import '../../widgets/team_logo.dart';
import '../common/async_state_pane.dart';
import '../common/paged_matches.dart';
import '../data/data_screen.dart' show leaguesProvider;
import '../follows/follow_providers.dart';

enum MatchTab { upcoming, finished }

enum MatchTimeRange { all, today }

enum MatchSort { time, league }

@immutable
class MatchFilter {
  const MatchFilter({
    this.leagueId,
    this.keyword = '',
    this.matchDate,
    this.onlyFollow = false,
    this.timeRange = MatchTimeRange.all,
    this.sortBy = MatchSort.time,
  });

  final String? leagueId;
  final String keyword;
  final DateTime? matchDate;
  final bool onlyFollow;
  final MatchTimeRange timeRange;
  final MatchSort sortBy;

  bool get hasActive =>
      (leagueId != null && leagueId!.isNotEmpty) ||
      keyword.trim().isNotEmpty ||
      matchDate != null ||
      onlyFollow ||
      timeRange != MatchTimeRange.all ||
      sortBy != MatchSort.time;

  String? get matchDateParam {
    final d = matchDate;
    if (d == null) return null;
    final y = d.year.toString().padLeft(4, '0');
    final m = d.month.toString().padLeft(2, '0');
    final day = d.day.toString().padLeft(2, '0');
    return '$y-$m-$day';
  }

  MatchFilter copyWith({
    String? leagueId,
    String? keyword,
    DateTime? matchDate,
    bool? onlyFollow,
    MatchTimeRange? timeRange,
    MatchSort? sortBy,
    bool clearLeague = false,
    bool clearDate = false,
  }) {
    return MatchFilter(
      leagueId: clearLeague ? null : (leagueId ?? this.leagueId),
      keyword: keyword ?? this.keyword,
      matchDate: clearDate ? null : (matchDate ?? this.matchDate),
      onlyFollow: onlyFollow ?? this.onlyFollow,
      timeRange: timeRange ?? this.timeRange,
      sortBy: sortBy ?? this.sortBy,
    );
  }
}

class MatchTabNotifier extends Notifier<MatchTab> {
  @override
  MatchTab build() => MatchTab.upcoming;

  void setTab(MatchTab tab) => state = tab;
}

class MatchFilterNotifier extends Notifier<MatchFilter> {
  @override
  MatchFilter build() => const MatchFilter();

  void setLeague(String? id) {
    state = state.copyWith(leagueId: id, clearLeague: id == null || id.isEmpty);
  }

  void setKeyword(String keyword) {
    state = state.copyWith(keyword: keyword);
  }

  void setDate(DateTime? date) {
    state = state.copyWith(matchDate: date, clearDate: date == null);
  }

  void setOnlyFollow(bool v) => state = state.copyWith(onlyFollow: v);

  void setTimeRange(MatchTimeRange v) => state = state.copyWith(timeRange: v);

  void setSortBy(MatchSort v) => state = state.copyWith(sortBy: v);

  void clear() => state = const MatchFilter();
}

final matchTabProvider =
    NotifierProvider<MatchTabNotifier, MatchTab>(MatchTabNotifier.new);

final matchFilterProvider =
    NotifierProvider<MatchFilterNotifier, MatchFilter>(MatchFilterNotifier.new);

class MatchListNotifier extends AsyncNotifier<PagedMatches> {
  @override
  Future<PagedMatches> build() async {
    ref.watch(matchTabProvider);
    ref.watch(matchFilterProvider);
    final followed = await ref.watch(followedIdsProvider.future);
    return PagedMatches.fromPage(await _fetch(page: 1, followed: followed));
  }

  Future<MatchListPage> _fetch({
    required int page,
    required Set<String> followed,
  }) {
    final tab = ref.read(matchTabProvider);
    final filter = ref.read(matchFilterProvider);
    final repo = ref.read(matchRepositoryProvider);
    final keyword = filter.keyword.trim();
    final date = filter.matchDateParam;
    final Future<MatchListPage> future;
    if (tab == MatchTab.upcoming) {
      future = repo.upcoming(
        page: page,
        pageSize: AppConfig.pageSize,
        leagueId: filter.leagueId,
        keyword: keyword.isEmpty ? null : keyword,
        matchDate: date,
      );
    } else {
      future = repo.finished(
        page: page,
        pageSize: AppConfig.pageSize,
        leagueId: filter.leagueId,
        keyword: keyword.isEmpty ? null : keyword,
        matchDate: date,
      );
    }
    return future.then((page) => _applyLocal(page: page, filter: filter, followed: followed));
  }

  MatchListPage _applyLocal({
    required MatchListPage page,
    required MatchFilter filter,
    required Set<String> followed,
  }) {
    var list = page.matches;
    if (filter.onlyFollow) {
      list = list.where((m) => followed.contains(m.league.id)).toList();
    }
    if (filter.timeRange == MatchTimeRange.today) {
      final now = DateTime.now();
      list = list.where((m) {
        final d = m.matchDate;
        if (d == null) return false;
        return d == _todayParam(now);
      }).toList();
    }
    if (filter.sortBy == MatchSort.league) {
      list = [...list]..sort((a, b) {
          final c = a.league.name.compareTo(b.league.name);
          return c != 0 ? c : a.whenText.compareTo(b.whenText);
        });
    } else if (filter.sortBy == MatchSort.time) {
      list = [...list]..sort((a, b) => a.whenText.compareTo(b.whenText));
    }
    return MatchListPage(
      matches: list,
      page: page.page,
      pageSize: page.pageSize,
      total: list.length,
      pages: page.pages,
      disclaimer: page.disclaimer,
      availableDates: page.availableDates,
      missingScoreTotal: page.missingScoreTotal,
    );
  }

  String _todayParam(DateTime now) {
    final y = now.year.toString().padLeft(4, '0');
    final m = now.month.toString().padLeft(2, '0');
    final d = now.day.toString().padLeft(2, '0');
    return '$y-$m-$d';
  }

  Future<void> refresh() async {
    final followed = await ref.read(followedIdsProvider.future);
    state = const AsyncLoading();
    state = await AsyncValue.guard(
      () async => PagedMatches.fromPage(await _fetch(page: 1, followed: followed)),
    );
  }

  Future<void> loadMore() async {
    final current = switch (state) {
      AsyncData(:final value) => value,
      _ => null,
    };
    if (current == null || current.loadingMore || !current.hasMore) return;
    state = AsyncData(current.copyWith(loadingMore: true));
    try {
      final followed = await ref.read(followedIdsProvider.future);
      final next = await _fetch(page: current.page + 1, followed: followed);
      state = AsyncData(current.appendPage(next));
    } catch (_) {
      state = AsyncData(current.copyWith(loadingMore: false));
    }
  }
}

final matchListProvider =
    AsyncNotifierProvider.autoDispose<MatchListNotifier, PagedMatches>(
  MatchListNotifier.new,
);

class MatchesScreen extends ConsumerStatefulWidget {
  const MatchesScreen({super.key});

  @override
  ConsumerState<MatchesScreen> createState() => _MatchesScreenState();
}

class _MatchesScreenState extends ConsumerState<MatchesScreen> {
  late final TextEditingController _keywordCtrl;
  late final ScrollController _scrollCtrl;
  Timer? _debounce;
  bool _filtersExpanded = false;

  @override
  void initState() {
    super.initState();
    _keywordCtrl = TextEditingController(text: ref.read(matchFilterProvider).keyword);
    _scrollCtrl = ScrollController()..addListener(_onScroll);
  }

  /// 关键词输入 500ms 防抖后触发搜索，避免每次击键都请求（MATCH-01）
  void _onKeywordChanged(String text) {
    _debounce?.cancel();
    _debounce = Timer(const Duration(milliseconds: 500), () {
      if (!mounted) return;
      ref.read(matchFilterProvider.notifier).setKeyword(text);
    });
  }

  void _onScroll() {
    if (!_scrollCtrl.hasClients) return;
    final pos = _scrollCtrl.position;
    if (pos.pixels >= pos.maxScrollExtent - 240) {
      ref.read(matchListProvider.notifier).loadMore();
    }
  }

  @override
  void dispose() {
    _debounce?.cancel();
    _scrollCtrl.dispose();
    _keywordCtrl.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final tab = ref.watch(matchTabProvider);
    final filter = ref.watch(matchFilterProvider);
    final asyncList = ref.watch(matchListProvider);
    final leaguesAsync = ref.watch(leaguesProvider);

    return PopScope(
      canPop: !_filtersExpanded,
      onPopInvokedWithResult: (didPop, _) {
        if (!didPop && _filtersExpanded) {
          setState(() => _filtersExpanded = false);
        }
      },
      child: Scaffold(
        appBar: AppBar(
          title: const Text('赛事'),
          actions: [
            IconButton(
              tooltip: _filtersExpanded ? '收起筛选' : '筛选',
              onPressed: () => setState(() => _filtersExpanded = !_filtersExpanded),
            icon: Badge(
              isLabelVisible: filter.hasActive,
              child: Icon(
                _filtersExpanded ? Icons.filter_alt : Icons.filter_alt_outlined,
              ),
            ),
          ),
        ],
      ),
      body: Column(
        children: [
          Padding(
            padding: const EdgeInsets.fromLTRB(16, 12, 16, 8),
            child: SegmentedButton<MatchTab>(
              segments: const [
                ButtonSegment(value: MatchTab.upcoming, label: Text('未赛')),
                ButtonSegment(value: MatchTab.finished, label: Text('已赛')),
              ],
              selected: {tab},
              onSelectionChanged: (s) {
                ref.read(matchTabProvider.notifier).setTab(s.first);
              },
            ),
          ),
          if (_filtersExpanded || filter.hasActive)
            _FilterPanel(
              filter: filter,
              keywordCtrl: _keywordCtrl,
              leagues: switch (leaguesAsync) {
                AsyncData(:final value) => value,
                _ => const <LeagueItem>[],
              },
              hasFollow: ref.watch(followedIdsProvider).value?.isNotEmpty ?? false,
              onLeague: (id) => ref.read(matchFilterProvider.notifier).setLeague(id),
              onKeywordChanged: _onKeywordChanged,
              onKeywordSubmit: (text) {
                _debounce?.cancel();
                ref.read(matchFilterProvider.notifier).setKeyword(text);
              },
              onPickDate: () async {
                final now = DateTime.now();
                final picked = await showDatePicker(
                  context: context,
                  initialDate: filter.matchDate ?? now,
                  firstDate: DateTime(now.year - 2),
                  lastDate: DateTime(now.year + 1),
                );
                if (picked != null) {
                  ref.read(matchFilterProvider.notifier).setDate(picked);
                }
              },
              onClearDate: () => ref.read(matchFilterProvider.notifier).setDate(null),
              onClearAll: () {
                _keywordCtrl.clear();
                ref.read(matchFilterProvider.notifier).clear();
              },
              onOnlyFollow: (v) => ref.read(matchFilterProvider.notifier).setOnlyFollow(v),
              onTimeRange: (v) => ref.read(matchFilterProvider.notifier).setTimeRange(v),
              onSortBy: (v) => ref.read(matchFilterProvider.notifier).setSortBy(v),
            ),
          Expanded(
            child: asyncList.when(
              loading: () => const SkeletonList(count: 6, cardHeight: 120),
              error: (e, _) => AsyncStatePane.error(
                error: e,
                onRetry: () => ref.read(matchListProvider.notifier).refresh(),
              ),
              data: (page) {
                if (page.matches.isEmpty) {
                  final onlyFollowEmpty = filter.onlyFollow && page.hasMore;
                  return AsyncStatePane.empty(
                    message: onlyFollowEmpty
                        ? '当前页无关注联赛赛事，尝试加载更多'
                        : (filter.hasActive ? '没有符合筛选条件的赛事' : '暂无赛事'),
                    onRetry: () => ref.read(matchListProvider.notifier).refresh(),
                    action: filter.hasActive
                        ? TextButton(
                            onPressed: () {
                              _keywordCtrl.clear();
                              ref.read(matchFilterProvider.notifier).clear();
                            },
                            child: const Text('清除所有筛选条件'),
                          )
                        : null,
                  );
                }
                final extra = page.loadingMore || page.hasMore ? 1 : 0;
                final sortHint = filter.sortBy == MatchSort.league
                    ? Padding(
                        padding: const EdgeInsets.fromLTRB(16, 8, 16, 0),
                        child: Text(
                          '排序仅对已加载内容生效',
                          style: TextStyle(
                              color: AppColors.textMuted, fontSize: 11),
                        ),
                      )
                    : const SizedBox.shrink();
                return Column(
                  children: [
                    sortHint,
                    Expanded(
                      child: RefreshIndicator(
                  onRefresh: () => ref.read(matchListProvider.notifier).refresh(),
                  child: ListView.separated(
                    controller: _scrollCtrl,
                    padding: const EdgeInsets.all(16),
                    itemCount: page.matches.length + extra,
                    separatorBuilder: (context, index) => const SizedBox(height: 10),
                    itemBuilder: (context, index) {
                      if (index >= page.matches.length) {
                        return Padding(
                          padding: const EdgeInsets.symmetric(vertical: 12),
                          child: Center(
                            child: page.loadingMore
                                ? const SizedBox(
                                    width: 24,
                                    height: 24,
                                    child: CircularProgressIndicator(strokeWidth: 2),
                                  )
                                : TextButton(
                                    onPressed: () =>
                                        ref.read(matchListProvider.notifier).loadMore(),
                                    child: const Text('加载更多'),
                                  ),
                          ),
                        );
                      }
                      final m = page.matches[index];
                      return _MatchCard(
                        match: m,
                        onTap: () => context.push('/match/${m.id}'),
                      );
                    },
                  ),
                ),
                    ),
                  ],
                );
              },
            ),
          ),
        ],
        ),
      ),
    );
  }
}

class _FilterPanel extends StatelessWidget {
  const _FilterPanel({
    required this.filter,
    required this.keywordCtrl,
    required this.leagues,
    required this.hasFollow,
    required this.onLeague,
    required this.onKeywordChanged,
    required this.onKeywordSubmit,
    required this.onPickDate,
    required this.onClearDate,
    required this.onClearAll,
    required this.onOnlyFollow,
    required this.onTimeRange,
    required this.onSortBy,
  });

  final MatchFilter filter;
  final TextEditingController keywordCtrl;
  final List<LeagueItem> leagues;
  final bool hasFollow;
  final ValueChanged<String?> onLeague;
  final ValueChanged<String> onKeywordChanged;
  final ValueChanged<String> onKeywordSubmit;
  final VoidCallback onPickDate;
  final VoidCallback onClearDate;
  final VoidCallback onClearAll;
  final ValueChanged<bool> onOnlyFollow;
  final ValueChanged<MatchTimeRange> onTimeRange;
  final ValueChanged<MatchSort> onSortBy;

  @override
  Widget build(BuildContext context) {
    final leagueValue = (filter.leagueId != null &&
            leagues.any((l) => l.id == filter.leagueId))
        ? filter.leagueId
        : null;

    return Padding(
      padding: const EdgeInsets.fromLTRB(16, 0, 16, 8),
      child: SingleChildScrollView(
        child: Card(
          child: Padding(
            padding: const EdgeInsets.all(12),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                // 联赛选择改为可搜索的底部抽屉，长列表更易用（MATCH-04）
                LeaguePickerField(
                  leagues: leagues,
                  value: leagueValue,
                  allowAll: true,
                  onChanged: onLeague,
                ),
                const SizedBox(height: 8),
              TextField(
                controller: keywordCtrl,
                textInputAction: TextInputAction.search,
                decoration: InputDecoration(
                  labelText: '关键词',
                  hintText: '球队名 / 赛事',
                  suffixIcon: IconButton(
                    tooltip: '立即搜索',
                    icon: const Icon(Icons.search),
                    onPressed: () => onKeywordSubmit(keywordCtrl.text),
                  ),
                ),
                onChanged: onKeywordChanged,
                onSubmitted: onKeywordSubmit,
              ),
              const SizedBox(height: 8),
              Row(
                children: [
                  Expanded(
                    child: OutlinedButton.icon(
                      onPressed: onPickDate,
                      icon: const Icon(Icons.calendar_today, size: 16),
                      label: Text(
                        filter.matchDateParam ?? '选择日期',
                        overflow: TextOverflow.ellipsis,
                      ),
                    ),
                  ),
                  if (filter.matchDate != null) ...[
                    const SizedBox(width: 8),
                    IconButton(
                      tooltip: '清除日期',
                      onPressed: onClearDate,
                      icon: const Icon(Icons.clear),
                    ),
                  ],
                  const SizedBox(width: 8),
                  TextButton(
                    onPressed: filter.hasActive ? onClearAll : null,
                    child: const Text('清空'),
                  ),
                ],
              ),
              const SizedBox(height: 8),
              Align(
                alignment: Alignment.centerLeft,
                child: Text(
                  '时间快捷',
                  style: TextStyle(color: AppColors.textMuted, fontSize: 12),
                ),
              ),
              const SizedBox(height: 6),
              Wrap(
                spacing: 8,
                children: [
                  ChoiceChip(
                    label: const Text('全部'),
                    selected: filter.timeRange == MatchTimeRange.all,
                    onSelected: (_) => onTimeRange(MatchTimeRange.all),
                  ),
                  ChoiceChip(
                    label: const Text('今天'),
                    selected: filter.timeRange == MatchTimeRange.today,
                    onSelected: (_) => onTimeRange(MatchTimeRange.today),
                  ),
                ],
              ),
              const SizedBox(height: 8),
              Align(
                alignment: Alignment.centerLeft,
                child: Text(
                  '排序',
                  style: TextStyle(color: AppColors.textMuted, fontSize: 12),
                ),
              ),
              const SizedBox(height: 6),
              SegmentedButton<MatchSort>(
                segments: const [
                  ButtonSegment(value: MatchSort.time, label: Text('开赛时间')),
                  ButtonSegment(value: MatchSort.league, label: Text('联赛')),
                ],
                selected: {filter.sortBy},
                onSelectionChanged: (s) => onSortBy(s.first),
                showSelectedIcon: false,
                style: SegmentedButton.styleFrom(
                  visualDensity: VisualDensity.compact,
                ),
              ),
              const SizedBox(height: 4),
              SwitchListTile(
                dense: true,
                contentPadding: EdgeInsets.zero,
                title: const Text('仅显示我关注的联赛'),
                value: filter.onlyFollow,
                onChanged: hasFollow ? onOnlyFollow : null,
                subtitle: hasFollow
                    ? null
                    : const Text(
                        '暂无关注联赛，请先在数据页添加关注',
                        style: TextStyle(fontSize: 11),
                      ),
              ),
            ],
          ),
        ),
      ),
      ),
    );
  }
}

class _MatchCard extends StatelessWidget {
  const _MatchCard({required this.match, required this.onTap});

  final MatchItem match;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final pred = match.prediction;
    final label =
        '${match.homeTeam.displayName} 对阵 ${match.awayTeam.displayName}，'
        '${match.league.name}，${match.whenText}，比分 ${match.scoreText}';
    return Semantics(
      button: true,
      label: label,
      child: Card(
        child: InkWell(
          borderRadius: BorderRadius.circular(10),
          onTap: onTap,
          child: Padding(
            padding: const EdgeInsets.all(14),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  children: [
                    if (match.league.logo != null &&
                        match.league.logo!.isNotEmpty) ...[
                      TeamLogo(
                        url: match.league.logo,
                        size: 18,
                        fallback: '🏆',
                        semanticLabel: '${match.league.name} 联赛标志',
                      ),
                      const SizedBox(width: 6),
                    ],
                    Expanded(
                      child: Text(
                        match.league.name,
                        style: const TextStyle(
                          color: AppColors.textMuted,
                          fontSize: 12,
                        ),
                      ),
                    ),
                    Text(
                      match.whenText,
                      style: const TextStyle(
                        color: AppColors.textMuted,
                        fontSize: 12,
                      ),
                    ),
                  ],
                ),
                const SizedBox(height: 10),
                Row(
                  children: [
                    TeamLogo(
                      url: match.homeTeam.logo,
                      size: 28,
                      semanticLabel: '${match.homeTeam.displayName} 队徽',
                    ),
                    const SizedBox(width: 8),
                    Expanded(
                      child: Text(
                        match.homeTeam.displayName,
                        style: const TextStyle(fontWeight: FontWeight.w600),
                      ),
                    ),
                    Text(
                      match.scoreText,
                      style: const TextStyle(
                        color: AppColors.gold,
                        fontWeight: FontWeight.bold,
                      ),
                    ),
                    Expanded(
                      child: Text(
                        match.awayTeam.displayName,
                        textAlign: TextAlign.right,
                        style: const TextStyle(fontWeight: FontWeight.w600),
                      ),
                    ),
                    const SizedBox(width: 8),
                    TeamLogo(
                      url: match.awayTeam.logo,
                      size: 28,
                      semanticLabel: '${match.awayTeam.displayName} 队徽',
                    ),
                  ],
                ),
                if (pred != null && pred.hasProbs) ...[
                  const SizedBox(height: 10),
                  WdlStackBar(
                    home: pred.homeWinProb ?? 0,
                    draw: pred.drawProb ?? 0,
                    away: pred.awayWinProb ?? 0,
                    height: 8,
                  ),
                  const SizedBox(height: 6),
                  Text(
                    '主 ${_pct(pred.homeWinProb)} · 平 ${_pct(pred.drawProb)} · 客 ${_pct(pred.awayWinProb)}'
                    '${pred.mainScore != null ? ' · ${pred.mainScore}' : ''}',
                    style: const TextStyle(
                      color: AppColors.textSecondary,
                      fontSize: 12,
                    ),
                  ),
                ] else if (pred?.mainScore != null) ...[
                  const SizedBox(height: 10),
                  Text(
                    '主线比分 ${pred!.mainScore}',
                    style: const TextStyle(
                      color: AppColors.textSecondary,
                      fontSize: 12,
                    ),
                  ),
                ],
              ],
            ),
          ),
        ),
      ),
    );
  }
}

String _pct(double? v) {
  if (v == null) return '-';
  return '${(v * 100).toStringAsFixed(1)}%';
}
