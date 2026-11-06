import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/config.dart';
import '../../core/providers.dart';
import '../../core/theme.dart';
import '../../data/models/league.dart';
import '../../data/models/match.dart';
import '../../widgets/prediction_panel.dart';
import '../../widgets/team_logo.dart';
import '../common/async_state_pane.dart';
import '../common/paged_matches.dart';
import '../data/data_screen.dart' show leaguesProvider;

enum MatchTab { upcoming, finished }

@immutable
class MatchFilter {
  const MatchFilter({
    this.leagueId,
    this.keyword = '',
    this.matchDate,
  });

  final String? leagueId;
  final String keyword;
  final DateTime? matchDate;

  bool get hasActive =>
      (leagueId != null && leagueId!.isNotEmpty) ||
      keyword.trim().isNotEmpty ||
      matchDate != null;

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
    bool clearLeague = false,
    bool clearDate = false,
  }) {
    return MatchFilter(
      leagueId: clearLeague ? null : (leagueId ?? this.leagueId),
      keyword: keyword ?? this.keyword,
      matchDate: clearDate ? null : (matchDate ?? this.matchDate),
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
    return PagedMatches.fromPage(await _fetch(page: 1));
  }

  Future<MatchListPage> _fetch({required int page}) {
    final tab = ref.read(matchTabProvider);
    final filter = ref.read(matchFilterProvider);
    final repo = ref.read(matchRepositoryProvider);
    final keyword = filter.keyword.trim();
    final date = filter.matchDateParam;
    if (tab == MatchTab.upcoming) {
      return repo.upcoming(
        page: page,
        pageSize: AppConfig.pageSize,
        leagueId: filter.leagueId,
        keyword: keyword.isEmpty ? null : keyword,
        matchDate: date,
      );
    }
    return repo.finished(
      page: page,
      pageSize: AppConfig.pageSize,
      leagueId: filter.leagueId,
      keyword: keyword.isEmpty ? null : keyword,
      matchDate: date,
    );
  }

  Future<void> refresh() async {
    state = const AsyncLoading();
    state = await AsyncValue.guard(
      () async => PagedMatches.fromPage(await _fetch(page: 1)),
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
      final next = await _fetch(page: current.page + 1);
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
  bool _filtersExpanded = false;

  @override
  void initState() {
    super.initState();
    _keywordCtrl = TextEditingController(text: ref.read(matchFilterProvider).keyword);
    _scrollCtrl = ScrollController()..addListener(_onScroll);
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

    return Scaffold(
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
              onLeague: (id) => ref.read(matchFilterProvider.notifier).setLeague(id),
              onKeywordSubmit: (text) {
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
            ),
          Expanded(
            child: asyncList.when(
              loading: () => const Center(child: CircularProgressIndicator()),
              error: (e, _) => AsyncStatePane.error(
                error: e,
                onRetry: () => ref.read(matchListProvider.notifier).refresh(),
              ),
              data: (page) {
                if (page.matches.isEmpty) {
                  return AsyncStatePane.empty(
                    message: filter.hasActive ? '没有符合筛选条件的赛事' : '暂无赛事',
                    onRetry: () => ref.read(matchListProvider.notifier).refresh(),
                  );
                }
                final extra = page.loadingMore || page.hasMore ? 1 : 0;
                return RefreshIndicator(
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
                        onTap: () => context.push('/matches/${m.id}'),
                      );
                    },
                  ),
                );
              },
            ),
          ),
        ],
      ),
    );
  }
}

class _FilterPanel extends StatelessWidget {
  const _FilterPanel({
    required this.filter,
    required this.keywordCtrl,
    required this.leagues,
    required this.onLeague,
    required this.onKeywordSubmit,
    required this.onPickDate,
    required this.onClearDate,
    required this.onClearAll,
  });

  final MatchFilter filter;
  final TextEditingController keywordCtrl;
  final List<LeagueItem> leagues;
  final ValueChanged<String?> onLeague;
  final ValueChanged<String> onKeywordSubmit;
  final VoidCallback onPickDate;
  final VoidCallback onClearDate;
  final VoidCallback onClearAll;

  @override
  Widget build(BuildContext context) {
    final leagueValue = (filter.leagueId != null &&
            leagues.any((l) => l.id == filter.leagueId))
        ? filter.leagueId
        : null;

    return Padding(
      padding: const EdgeInsets.fromLTRB(16, 0, 16, 8),
      child: Card(
        child: Padding(
          padding: const EdgeInsets.all(12),
          child: Column(
            children: [
              InputDecorator(
                decoration: const InputDecoration(
                  labelText: '联赛',
                  contentPadding: EdgeInsets.symmetric(horizontal: 12, vertical: 4),
                ),
                child: DropdownButtonHideUnderline(
                  child: DropdownButton<String?>(
                    value: leagueValue,
                    isExpanded: true,
                    hint: const Text('全部联赛'),
                    items: [
                      const DropdownMenuItem<String?>(
                        value: null,
                        child: Text('全部联赛'),
                      ),
                      ...leagues.map(
                        (l) => DropdownMenuItem<String?>(
                          value: l.id,
                          child: Text(l.name, overflow: TextOverflow.ellipsis),
                        ),
                      ),
                    ],
                    onChanged: onLeague,
                  ),
                ),
              ),
              const SizedBox(height: 8),
              TextField(
                controller: keywordCtrl,
                textInputAction: TextInputAction.search,
                decoration: InputDecoration(
                  labelText: '关键词',
                  hintText: '球队名 / 赛事',
                  suffixIcon: IconButton(
                    icon: const Icon(Icons.search),
                    onPressed: () => onKeywordSubmit(keywordCtrl.text),
                  ),
                ),
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
            ],
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
