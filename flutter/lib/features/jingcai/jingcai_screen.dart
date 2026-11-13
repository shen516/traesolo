import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/config.dart';
import '../../core/network/api_exception.dart';
import '../../core/providers.dart';
import '../../core/theme.dart';
import '../../data/models/match.dart';
import '../../widgets/skeleton.dart';
import '../../widgets/team_logo.dart';
import '../auth/auth_state.dart';
import '../common/async_state_pane.dart';
import '../common/paged_matches.dart';

enum JingcaiTab { live, history }

class JingcaiTabNotifier extends Notifier<JingcaiTab> {
  @override
  JingcaiTab build() => JingcaiTab.live;

  void setTab(JingcaiTab tab) => state = tab;
}

@immutable
class JingcaiFilter {
  const JingcaiFilter({
    this.keyword = '',
    this.matchDate,
    this.status,
    this.missingScoreOnly = false,
  });

  final String keyword;
  final DateTime? matchDate;
  final String? status;
  final bool missingScoreOnly;

  String? get matchDateParam {
    final d = matchDate;
    if (d == null) return null;
    final y = d.year.toString().padLeft(4, '0');
    final m = d.month.toString().padLeft(2, '0');
    final day = d.day.toString().padLeft(2, '0');
    return '$y-$m-$day';
  }

  JingcaiFilter copyWith({
    String? keyword,
    DateTime? matchDate,
    String? status,
    bool? missingScoreOnly,
    bool clearDate = false,
    bool clearStatus = false,
  }) {
    return JingcaiFilter(
      keyword: keyword ?? this.keyword,
      matchDate: clearDate ? null : (matchDate ?? this.matchDate),
      status: clearStatus ? null : (status ?? this.status),
      missingScoreOnly: missingScoreOnly ?? this.missingScoreOnly,
    );
  }

  /// 是否存在生效中的筛选条件，用于筛选按钮角标（JC-01）
  bool get hasActive =>
      keyword.trim().isNotEmpty ||
      matchDate != null ||
      (status != null && status!.isNotEmpty) ||
      missingScoreOnly;
}

class JingcaiFilterNotifier extends Notifier<JingcaiFilter> {
  @override
  JingcaiFilter build() => const JingcaiFilter();

  void setKeyword(String v) => state = state.copyWith(keyword: v);
  void setDate(DateTime? d) =>
      state = state.copyWith(matchDate: d, clearDate: d == null);
  void setStatus(String? s) =>
      state = state.copyWith(status: s, clearStatus: s == null || s.isEmpty);
  void setMissingOnly(bool v) => state = state.copyWith(missingScoreOnly: v);
  void clear() => state = const JingcaiFilter();
}

final jingcaiTabProvider =
    NotifierProvider<JingcaiTabNotifier, JingcaiTab>(JingcaiTabNotifier.new);

final jingcaiFilterProvider =
    NotifierProvider<JingcaiFilterNotifier, JingcaiFilter>(
  JingcaiFilterNotifier.new,
);

class JingcaiListNotifier extends AsyncNotifier<PagedMatches> {
  @override
  Future<PagedMatches> build() async {
    ref.watch(jingcaiTabProvider);
    ref.watch(jingcaiFilterProvider);
    return PagedMatches.fromPage(await _fetch(page: 1));
  }

  Future<MatchListPage> _fetch({required int page}) {
    final tab = ref.read(jingcaiTabProvider);
    final filter = ref.read(jingcaiFilterProvider);
    final repo = ref.read(jingcaiRepositoryProvider);
    final keyword = filter.keyword.trim();
    final date = filter.matchDateParam;
    if (tab == JingcaiTab.live) {
      return repo.bf(
        page: page,
        pageSize: AppConfig.pageSize,
        keyword: keyword.isEmpty ? null : keyword,
        matchDate: date,
        status: filter.status,
      );
    }
    return repo.bfHistory(
      page: page,
      pageSize: AppConfig.pageSize,
      keyword: keyword.isEmpty ? null : keyword,
      matchDate: date,
      missingScore: filter.missingScoreOnly,
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

final jingcaiListProvider =
    AsyncNotifierProvider.autoDispose<JingcaiListNotifier, PagedMatches>(
  JingcaiListNotifier.new,
);

class JingcaiScreen extends ConsumerStatefulWidget {
  const JingcaiScreen({super.key});

  @override
  ConsumerState<JingcaiScreen> createState() => _JingcaiScreenState();
}

class _JingcaiScreenState extends ConsumerState<JingcaiScreen> {
  late final TextEditingController _keywordCtrl;
  late final ScrollController _scrollCtrl;
  bool _filtersOpen = false;
  bool _disclaimerExpanded = false;

  @override
  void initState() {
    super.initState();
    _keywordCtrl =
        TextEditingController(text: ref.read(jingcaiFilterProvider).keyword);
    _scrollCtrl = ScrollController()..addListener(_onScroll);
  }

  void _onScroll() {
    if (!_scrollCtrl.hasClients) return;
    final pos = _scrollCtrl.position;
    if (pos.pixels >= pos.maxScrollExtent - 240) {
      ref.read(jingcaiListProvider.notifier).loadMore();
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
    final auth = ref.watch(authProvider);
    final tab = ref.watch(jingcaiTabProvider);
    final filter = ref.watch(jingcaiFilterProvider);
    final asyncList = ref.watch(jingcaiListProvider);

    return Scaffold(
      appBar: AppBar(
        title: const Text('竞彩分析'),
        actions: [
          IconButton(
            tooltip: '我的模拟投注',
            onPressed: () => context.push('/bets'),
            icon: const Icon(Icons.receipt_long),
          ),
          IconButton(
            tooltip: '筛选',
            onPressed: () => setState(() => _filtersOpen = !_filtersOpen),
            // 筛选生效时显示角标，提示有条件在起作用（JC-01）
            icon: Badge(
              isLabelVisible: filter.hasActive,
              child: Icon(
                _filtersOpen ? Icons.filter_alt : Icons.filter_alt_outlined,
              ),
            ),
          ),
        ],
      ),
      body: !auth.canJingcai
          ? AsyncStatePane.empty(
              message: '当前账号无竞彩分析权限。请联系管理员开通 match:jingcai_bf 等相关权限。',
              // 空态给出可操作出口，而非一句提示（JC-02）
              action: TextButton.icon(
                onPressed: () => context.push('/about'),
                icon: const Icon(Icons.info_outline, size: 18),
                label: const Text('查看关于与权限说明'),
              ),
            )
          : Column(
              children: [
                // 免责声明默认收起为一行，点按展开全文（JC-03）
                GestureDetector(
                  behavior: HitTestBehavior.opaque,
                  onTap: () =>
                      setState(() => _disclaimerExpanded = !_disclaimerExpanded),
                  child: Padding(
                    padding: const EdgeInsets.fromLTRB(16, 12, 16, 4),
                    child: Row(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Icon(
                          _disclaimerExpanded
                              ? Icons.expand_less
                              : Icons.info_outline,
                          size: 14,
                          color: AppColors.textMuted,
                        ),
                        const SizedBox(width: 6),
                        Expanded(
                          child: Text(
                            _disclaimerExpanded
                                ? AppConfig.disclaimer
                                : '仅供学习研究与数据分析，不构成任何投注建议。点按查看完整声明',
                            maxLines: _disclaimerExpanded ? null : 2,
                            overflow: _disclaimerExpanded
                                ? TextOverflow.visible
                                : TextOverflow.ellipsis,
                            style: const TextStyle(
                              color: AppColors.textMuted,
                              fontSize: 12,
                              height: 1.35,
                            ),
                          ),
                        ),
                      ],
                    ),
                  ),
                ),
                Padding(
                  padding: const EdgeInsets.fromLTRB(16, 8, 16, 8),
                  child: SegmentedButton<JingcaiTab>(
                    segments: const [
                      ButtonSegment(
                        value: JingcaiTab.live,
                        label: Text('在赛'),
                      ),
                      ButtonSegment(
                        value: JingcaiTab.history,
                        label: Text('历史'),
                      ),
                    ],
                    selected: {tab},
                    onSelectionChanged: (s) {
                      ref.read(jingcaiTabProvider.notifier).setTab(s.first);
                    },
                  ),
                ),
                if (_filtersOpen)
                  _FilterBar(
                    tab: tab,
                    filter: filter,
                    keywordCtrl: _keywordCtrl,
                    onKeyword: (t) =>
                        ref.read(jingcaiFilterProvider.notifier).setKeyword(t),
                    onStatus: (s) =>
                        ref.read(jingcaiFilterProvider.notifier).setStatus(s),
                    onMissing: (v) => ref
                        .read(jingcaiFilterProvider.notifier)
                        .setMissingOnly(v),
                    onPickDate: () async {
                      final now = DateTime.now();
                      final picked = await showDatePicker(
                        context: context,
                        initialDate: filter.matchDate ?? now,
                        firstDate: DateTime(now.year - 2),
                        lastDate: DateTime(now.year + 1),
                      );
                      if (picked != null) {
                        ref
                            .read(jingcaiFilterProvider.notifier)
                            .setDate(picked);
                      }
                    },
                    onClearDate: () =>
                        ref.read(jingcaiFilterProvider.notifier).setDate(null),
                    onClear: () {
                      _keywordCtrl.clear();
                      ref.read(jingcaiFilterProvider.notifier).clear();
                    },
                  ),
                Expanded(
                  child: asyncList.when(
                    loading: () => const SkeletonList(count: 6),
                    error: (e, _) {
                      if (e is ApiException && e.isForbidden) {
                        return AsyncStatePane.error(
                          error: ApiException(
                            '无权查看竞彩数据',
                            statusCode: 403,
                          ),
                          onRetry: () =>
                              ref.read(jingcaiListProvider.notifier).refresh(),
                        );
                      }
                      return AsyncStatePane.error(
                        error: e,
                        onRetry: () =>
                            ref.read(jingcaiListProvider.notifier).refresh(),
                      );
                    },
                    data: (page) {
                      if (page.matches.isEmpty) {
                        return AsyncStatePane.empty(
                          message: '暂无竞彩场次',
                          onRetry: () =>
                              ref.read(jingcaiListProvider.notifier).refresh(),
                        );
                      }
                      final footer = page.loadingMore || page.hasMore ? 1 : 0;
                      return RefreshIndicator(
                        onRefresh: () =>
                            ref.read(jingcaiListProvider.notifier).refresh(),
                        child: ListView.separated(
                          controller: _scrollCtrl,
                          padding: const EdgeInsets.all(16),
                          itemCount: page.matches.length + 1 + footer,
                          separatorBuilder: (_, index) =>
                              const SizedBox(height: 10),
                          itemBuilder: (context, index) {
                            if (index == 0) {
                              return Text(
                                '共 ${page.total} 场'
                                '${page.missingScoreTotal != null ? ' · 缺比分 ${page.missingScoreTotal}' : ''}'
                                ' · 仅供分析',
                                style: const TextStyle(
                                  color: AppColors.textMuted,
                                  fontSize: 12,
                                ),
                              );
                            }
                            final matchIndex = index - 1;
                            if (matchIndex >= page.matches.length) {
                              return Padding(
                                padding:
                                    const EdgeInsets.symmetric(vertical: 12),
                                child: Center(
                                  child: page.loadingMore
                                      ? const SizedBox(
                                          width: 24,
                                          height: 24,
                                          child: CircularProgressIndicator(
                                            strokeWidth: 2,
                                          ),
                                        )
                                      : TextButton(
                                          onPressed: () => ref
                                              .read(
                                                  jingcaiListProvider.notifier)
                                              .loadMore(),
                                          child: const Text('加载更多'),
                                        ),
                                ),
                              );
                            }
                            final m = page.matches[matchIndex];
                            return _JingcaiCard(
                              match: m,
                              onTap: () => context.push('/match/${m.id}'),
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

class _FilterBar extends StatelessWidget {
  const _FilterBar({
    required this.tab,
    required this.filter,
    required this.keywordCtrl,
    required this.onKeyword,
    required this.onStatus,
    required this.onMissing,
    required this.onPickDate,
    required this.onClearDate,
    required this.onClear,
  });

  final JingcaiTab tab;
  final JingcaiFilter filter;
  final TextEditingController keywordCtrl;
  final ValueChanged<String> onKeyword;
  final ValueChanged<String?> onStatus;
  final ValueChanged<bool> onMissing;
  final VoidCallback onPickDate;
  final VoidCallback onClearDate;
  final VoidCallback onClear;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(16, 0, 16, 8),
      child: Card(
        child: Padding(
          padding: const EdgeInsets.all(12),
          child: Column(
            children: [
              TextField(
                controller: keywordCtrl,
                textInputAction: TextInputAction.search,
                decoration: InputDecoration(
                  labelText: '球队关键词',
                  suffixIcon: IconButton(
                    icon: const Icon(Icons.search),
                    onPressed: () => onKeyword(keywordCtrl.text),
                  ),
                ),
                onSubmitted: onKeyword,
              ),
              const SizedBox(height: 8),
              if (tab == JingcaiTab.live)
                InputDecorator(
                  decoration: const InputDecoration(
                    labelText: '状态',
                    contentPadding:
                        EdgeInsets.symmetric(horizontal: 12, vertical: 4),
                  ),
                  child: DropdownButtonHideUnderline(
                    child: DropdownButton<String?>(
                      value: filter.status,
                      isExpanded: true,
                      items: const [
                        DropdownMenuItem(value: null, child: Text('全部')),
                        DropdownMenuItem(value: 'upcoming', child: Text('未开赛')),
                        DropdownMenuItem(value: 'live', child: Text('进行中')),
                        DropdownMenuItem(
                          value: 'finished',
                          child: Text('已完赛'),
                        ),
                      ],
                      onChanged: onStatus,
                    ),
                  ),
                )
              else
                SwitchListTile(
                  contentPadding: EdgeInsets.zero,
                  title: const Text('仅缺比分'),
                  value: filter.missingScoreOnly,
                  onChanged: onMissing,
                ),
              const SizedBox(height: 4),
              Row(
                children: [
                  Expanded(
                    child: OutlinedButton.icon(
                      onPressed: onPickDate,
                      icon: const Icon(Icons.calendar_today, size: 16),
                      label: Text(filter.matchDateParam ?? '选择日期'),
                    ),
                  ),
                  if (filter.matchDate != null)
                    IconButton(
                      onPressed: onClearDate,
                      icon: const Icon(Icons.clear),
                    ),
                  TextButton(onPressed: onClear, child: const Text('清空')),
                ],
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _JingcaiCard extends StatelessWidget {
  const _JingcaiCard({required this.match, required this.onTap});

  final MatchItem match;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final pred = match.prediction;
    final label =
        '${match.matchNo != null && match.matchNo!.isNotEmpty ? '${match.matchNo}，' : ''}'
        '${match.homeTeam.displayName} 对阵 ${match.awayTeam.displayName}，'
        '${match.league.name}，${match.whenText}';
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
                    if (match.matchNo != null && match.matchNo!.isNotEmpty) ...[
                      Container(
                        padding: const EdgeInsets.symmetric(
                          horizontal: 8,
                          vertical: 2,
                        ),
                        decoration: BoxDecoration(
                          color: AppColors.bgSecondary,
                          borderRadius: BorderRadius.circular(4),
                          border: Border.all(color: AppColors.border),
                        ),
                        child: Text(
                          match.matchNo!,
                          style: const TextStyle(
                            fontSize: 11,
                            color: AppColors.gold,
                          ),
                        ),
                      ),
                      const SizedBox(width: 8),
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
                      size: 26,
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
                      size: 26,
                      semanticLabel: '${match.awayTeam.displayName} 队徽',
                    ),
                  ],
                ),
                if (match.hasNspf) ...[
                  const SizedBox(height: 10),
                  Text(
                    '市场参考（胜平负） '
                    '${MatchItem.formatOdds(match.oddsNspfWin)} / '
                    '${MatchItem.formatOdds(match.oddsNspfDraw)} / '
                    '${MatchItem.formatOdds(match.oddsNspfLose)}'
                    '${match.handicap != null ? ' · 让球 ${match.handicap}' : ''}'
                    '${match.isSingle ? ' · 单关' : ''}',
                    style: const TextStyle(
                      color: AppColors.textSecondary,
                      fontSize: 12,
                    ),
                  ),
                ],
                if (pred != null &&
                    (pred.hasProbs || pred.mainScore != null)) ...[
                  const SizedBox(height: 6),
                  Text(
                    pred.hasProbs
                        ? '模型 '
                            '${_pct(pred.homeWinProb)} / '
                            '${_pct(pred.drawProb)} / '
                            '${_pct(pred.awayWinProb)}'
                            '${pred.mainScore != null ? ' · ${pred.mainScore}' : ''}'
                        : '模型主线 ${pred.mainScore}',
                    style: const TextStyle(
                      color: AppColors.textMuted,
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
  return '${(v * 100).toStringAsFixed(0)}%';
}
