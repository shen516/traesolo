import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/config.dart';
import '../../core/theme.dart';
import '../../widgets/team_logo.dart';
import '../auth/auth_state.dart';
import '../common/async_state_pane.dart';
import '../data/data_screen.dart';
import '../follows/follow_providers.dart';

class HomeScreen extends ConsumerWidget {
  const HomeScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final auth = ref.watch(authProvider);
    final name = auth.user?.username ?? '用户';
    final summaryAsync = ref.watch(followSummaryProvider);

    return Scaffold(
      appBar: AppBar(title: const Text('首页')),
      body: RefreshIndicator(
        onRefresh: () async => ref.invalidate(followSummaryProvider),
        child: ListView(
          padding: const EdgeInsets.all(16),
          children: [
            Card(
              child: Padding(
                padding: const EdgeInsets.all(16),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      '你好，$name',
                      style: const TextStyle(fontSize: 20, fontWeight: FontWeight.w600),
                    ),
                    const SizedBox(height: 8),
                    const Text(
                      '${AppConfig.appName} · ${AppConfig.appTagline}',
                      style: TextStyle(color: AppColors.textSecondary),
                    ),
                    const SizedBox(height: 12),
                    Container(
                      width: double.infinity,
                      padding: const EdgeInsets.all(12),
                      decoration: BoxDecoration(
                        color: AppColors.bgSecondary,
                        borderRadius: BorderRadius.circular(8),
                        border: Border.all(color: AppColors.border),
                      ),
                      child: const Text(
                        AppConfig.disclaimer,
                        style: TextStyle(color: AppColors.textMuted, fontSize: 12),
                      ),
                    ),
                  ],
                ),
              ),
            ),
            const SizedBox(height: 12),
            Row(
              children: [
                Expanded(
                  child: _QuickTile(
                    icon: Icons.sports_soccer,
                    color: AppColors.blue,
                    title: '赛事',
                    onTap: () => context.go('/matches'),
                  ),
                ),
                const SizedBox(width: 8),
                Expanded(
                  child: _QuickTile(
                    icon: Icons.table_chart_outlined,
                    color: AppColors.gold,
                    title: '数据',
                    onTap: () => context.go('/data'),
                  ),
                ),
                const SizedBox(width: 8),
                Expanded(
                  child: _QuickTile(
                    icon: Icons.analytics_outlined,
                    color: AppColors.green,
                    title: '竞彩',
                    onTap: () => context.go('/jingcai'),
                  ),
                ),
              ],
            ),
            const SizedBox(height: 16),
            summaryAsync.when(
              loading: () => const Padding(
                padding: EdgeInsets.symmetric(vertical: 24),
                child: Center(child: CircularProgressIndicator()),
              ),
              error: (e, _) => AsyncStatePane.error(
                error: e,
                onRetry: () => ref.invalidate(followSummaryProvider),
              ),
              data: (summary) {
                if (summary.state.ids.isEmpty) {
                  return Card(
                    child: Padding(
                      padding: const EdgeInsets.all(16),
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          const Text(
                            '关注联赛',
                            style: TextStyle(fontSize: 16, fontWeight: FontWeight.w600),
                          ),
                          const SizedBox(height: 8),
                          const Text(
                            '还没有关注联赛。去「数据」页点星标，首页会展示未赛与积分摘要。',
                            style: TextStyle(color: AppColors.textMuted),
                          ),
                          const SizedBox(height: 12),
                          ElevatedButton(
                            onPressed: () => context.go('/data'),
                            child: const Text('去关注联赛'),
                          ),
                        ],
                      ),
                    ),
                  );
                }

                return Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(
                      children: [
                        const Expanded(
                          child: Text(
                            '我的关注',
                            style: TextStyle(fontSize: 16, fontWeight: FontWeight.w600),
                          ),
                        ),
                        TextButton(
                          onPressed: () => context.go('/data'),
                          child: const Text('管理'),
                        ),
                      ],
                    ),
                    const SizedBox(height: 4),
                    Wrap(
                      spacing: 8,
                      runSpacing: 8,
                      children: summary.state.leagues
                          .map(
                            (l) => ActionChip(
                              label: Text(l.name),
                              onPressed: () {
                                ref
                                    .read(selectedLeagueIdProvider.notifier)
                                    .setId(l.id);
                                context.go('/data');
                              },
                            ),
                          )
                          .toList(),
                    ),
                    const SizedBox(height: 16),
                    const Text(
                      '关注联赛未赛',
                      style: TextStyle(fontSize: 16, fontWeight: FontWeight.w600),
                    ),
                    const SizedBox(height: 8),
                    if (summary.matches.isEmpty)
                      const Text(
                        '暂无未赛',
                        style: TextStyle(color: AppColors.textMuted),
                      )
                    else
                      ...summary.matches.map(
                        (m) => Padding(
                          padding: const EdgeInsets.only(bottom: 8),
                          child: Card(
                            child: ListTile(
                              contentPadding: const EdgeInsets.symmetric(
                                horizontal: 14,
                                vertical: 6,
                              ),
                              leading: SizedBox(
                                width: 56,
                                child: Row(
                                  children: [
                                    TeamLogo(
                                      url: m.homeTeam.logo,
                                      size: 24,
                                      semanticLabel:
                                          '${m.homeTeam.displayName} 队徽',
                                    ),
                                    const SizedBox(width: 4),
                                    TeamLogo(
                                      url: m.awayTeam.logo,
                                      size: 24,
                                      semanticLabel:
                                          '${m.awayTeam.displayName} 队徽',
                                    ),
                                  ],
                                ),
                              ),
                              title: Text(
                                '${m.homeTeam.displayName} vs ${m.awayTeam.displayName}',
                              ),
                              subtitle: Text(
                                '${m.league.name} · ${m.whenText}',
                                style: const TextStyle(
                                  color: AppColors.textMuted,
                                ),
                              ),
                              trailing: const Icon(Icons.chevron_right),
                              onTap: () => context.push('/matches/${m.id}'),
                            ),
                          ),
                        ),
                      ),
                    if (summary.boards.isNotEmpty) ...[
                      const SizedBox(height: 8),
                      const Text(
                        '积分摘要',
                        style: TextStyle(fontSize: 16, fontWeight: FontWeight.w600),
                      ),
                      const SizedBox(height: 8),
                      ...summary.boards.map((board) {
                        final top = board.standings.take(3).toList();
                        return Padding(
                          padding: const EdgeInsets.only(bottom: 8),
                          child: Card(
                            child: Padding(
                              padding: const EdgeInsets.all(14),
                              child: Column(
                                crossAxisAlignment: CrossAxisAlignment.start,
                                children: [
                                  Text(
                                    board.leagueName,
                                    style: const TextStyle(fontWeight: FontWeight.w600),
                                  ),
                                  if (board.season != null) ...[
                                    const SizedBox(height: 2),
                                    Text(
                                      board.season!,
                                      style: const TextStyle(
                                        color: AppColors.textMuted,
                                        fontSize: 12,
                                      ),
                                    ),
                                  ],
                                  const SizedBox(height: 8),
                                  if (top.isEmpty)
                                    const Text(
                                      '暂无积分榜',
                                      style: TextStyle(color: AppColors.textMuted),
                                    )
                                  else
                                    ...top.map(
                                      (row) => Padding(
                                        padding: const EdgeInsets.only(bottom: 4),
                                        child: Row(
                                          children: [
                                            SizedBox(
                                              width: 24,
                                              child: Text(
                                                '${row.rank}',
                                                style: const TextStyle(
                                                  color: AppColors.textMuted,
                                                ),
                                              ),
                                            ),
                                            Expanded(child: Text(row.displayName)),
                                            Text(
                                              '${row.points}分',
                                              style: const TextStyle(color: AppColors.gold),
                                            ),
                                          ],
                                        ),
                                      ),
                                    ),
                                  Align(
                                    alignment: Alignment.centerRight,
                                    child: TextButton(
                                      onPressed: () {
                                        ref
                                            .read(selectedLeagueIdProvider.notifier)
                                            .setId(board.leagueId);
                                        context.go('/data');
                                      },
                                      child: const Text('查看完整'),
                                    ),
                                  ),
                                ],
                              ),
                            ),
                          ),
                        );
                      }),
                    ],
                  ],
                );
              },
            ),
          ],
        ),
      ),
    );
  }
}

class _QuickTile extends StatelessWidget {
  const _QuickTile({
    required this.icon,
    required this.color,
    required this.title,
    required this.onTap,
  });

  final IconData icon;
  final Color color;
  final String title;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return Card(
      child: InkWell(
        borderRadius: BorderRadius.circular(10),
        onTap: onTap,
        child: Padding(
          padding: const EdgeInsets.symmetric(vertical: 16),
          child: Column(
            children: [
              Icon(icon, color: color),
              const SizedBox(height: 8),
              Text(title, style: const TextStyle(fontWeight: FontWeight.w600)),
            ],
          ),
        ),
      ),
    );
  }
}
