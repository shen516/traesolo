import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/providers.dart';
import '../../core/theme.dart';
import '../../data/models/match.dart';
import '../../widgets/team_logo.dart';

/// 今日赛事：当天开赛（后端 `match_date` 为精确日期，非近 24h）。
final todayMatchesProvider =
    FutureProvider.autoDispose<List<MatchItem>>((ref) async {
  final repo = ref.watch(matchRepositoryProvider);
  final now = DateTime.now();
  final y = now.year.toString().padLeft(4, '0');
  final m = now.month.toString().padLeft(2, '0');
  final d = now.day.toString().padLeft(2, '0');
  final date = '$y-$m-$d';
  final page = await repo.upcoming(page: 1, pageSize: 5, matchDate: date);
  return page.matches.take(5).toList();
});

/// 首页「今日赛事」卡片，最多 5 条；空态保留「查看全部」。
class TodayMatchesCard extends ConsumerWidget {
  const TodayMatchesCard({super.key, required this.onMore});

  final VoidCallback onMore;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final async = ref.watch(todayMatchesProvider);
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                const Expanded(
                  child: Text(
                    '今日赛事',
                    style: TextStyle(fontSize: 16, fontWeight: FontWeight.w600),
                  ),
                ),
                TextButton(onPressed: onMore, child: const Text('查看全部')),
              ],
            ),
            const SizedBox(height: 8),
            async.when(
              loading: () => const Padding(
                padding: EdgeInsets.symmetric(vertical: 12),
                child: Center(
                  child: SizedBox(
                    width: 24,
                    height: 24,
                    child: CircularProgressIndicator(strokeWidth: 2),
                  ),
                ),
              ),
              error: (e, _) => _TodayError(
                onRetry: () => ref.invalidate(todayMatchesProvider),
              ),
              data: (matches) {
                if (matches.isEmpty) {
                  return const Padding(
                    padding: EdgeInsets.symmetric(vertical: 8),
                    child: Text(
                      '今日暂无赛程',
                      style: TextStyle(color: AppColors.textMuted),
                    ),
                  );
                }
                return Column(
                  children: matches.map((m) => _TodayRow(match: m)).toList(),
                );
              },
            ),
          ],
        ),
      ),
    );
  }
}

class _TodayRow extends StatelessWidget {
  const _TodayRow({required this.match});

  final MatchItem match;

  @override
  Widget build(BuildContext context) {
    return InkWell(
      onTap: () => context.push('/matches/${match.id}'),
      borderRadius: BorderRadius.circular(8),
      child: Padding(
        padding: const EdgeInsets.symmetric(vertical: 6),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                if (match.league.logo != null && match.league.logo!.isNotEmpty) ...[
                  TeamLogo(
                    url: match.league.logo,
                    size: 14,
                    fallback: '🏆',
                    semanticLabel: '${match.league.name} 联赛标志',
                  ),
                  const SizedBox(width: 4),
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
            const SizedBox(height: 6),
            Row(
              children: [
                TeamLogo(
                  url: match.homeTeam.logo,
                  size: 22,
                  semanticLabel: '${match.homeTeam.displayName} 队徽',
                ),
                const SizedBox(width: 6),
                Expanded(
                  child: Text(
                    match.homeTeam.displayName,
                    overflow: TextOverflow.ellipsis,
                    style: const TextStyle(fontWeight: FontWeight.w600),
                  ),
                ),
                const Text(
                  'vs',
                  style: TextStyle(color: AppColors.textMuted, fontSize: 12),
                ),
                Expanded(
                  child: Text(
                    match.awayTeam.displayName,
                    textAlign: TextAlign.right,
                    overflow: TextOverflow.ellipsis,
                    style: const TextStyle(fontWeight: FontWeight.w600),
                  ),
                ),
                const SizedBox(width: 6),
                TeamLogo(
                  url: match.awayTeam.logo,
                  size: 22,
                  semanticLabel: '${match.awayTeam.displayName} 队徽',
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }
}

class _TodayError extends StatelessWidget {
  const _TodayError({required this.onRetry});

  final VoidCallback onRetry;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 8),
      child: Row(
        children: [
          const Expanded(
            child: Text(
              '今日赛事加载失败',
              style: TextStyle(color: AppColors.textMuted),
            ),
          ),
          TextButton(onPressed: onRetry, child: const Text('重试')),
        ],
      ),
    );
  }
}
