import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/providers.dart';
import '../../core/theme.dart';
import '../../data/models/league.dart';
import '../../data/models/match.dart';
import '../../data/models/standing.dart';
import '../../data/models/team.dart';
import '../../widgets/team_logo.dart';
import '../common/async_state_pane.dart';
import '../data/data_screen.dart';

class TeamDetailBundle {
  const TeamDetailBundle({
    required this.team,
    this.league,
    this.standing,
    this.recent = const [],
  });

  final TeamDetail team;
  final LeagueItem? league;
  final StandingRow? standing;
  final List<MatchItem> recent;
}

final teamDetailProvider =
    FutureProvider.autoDispose.family<TeamDetailBundle, String>((ref, teamId) async {
  final teamRepo = ref.watch(teamRepositoryProvider);
  final matchRepo = ref.watch(matchRepositoryProvider);
  final leagueRepo = ref.watch(leagueRepositoryProvider);
  final dataRepo = ref.watch(dataRepositoryProvider);

  final team = await teamRepo.detail(teamId);
  LeagueItem? league;
  StandingRow? standing;
  if (team.leagueId != null && team.leagueId!.isNotEmpty) {
    try {
      league = await leagueRepo.byId(team.leagueId!);
    } catch (_) {}
    try {
      final board = await dataRepo.board(team.leagueId!);
      for (final row in board.standings) {
        if (row.teamId == team.id) {
          standing = row;
          break;
        }
      }
    } catch (_) {}
  }

  List<MatchItem> recent = const [];
  try {
    final page = await matchRepo.finished(
      pageSize: 8,
      leagueId: team.leagueId,
      keyword: team.name,
    );
    recent = page.matches
        .where(
          (m) => m.homeTeam.id == team.id || m.awayTeam.id == team.id,
        )
        .take(5)
        .toList();
  } catch (_) {}

  return TeamDetailBundle(
    team: team,
    league: league,
    standing: standing,
    recent: recent,
  );
});

class TeamDetailScreen extends ConsumerWidget {
  const TeamDetailScreen({super.key, required this.teamId});

  final String teamId;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final async = ref.watch(teamDetailProvider(teamId));

    return Scaffold(
      appBar: AppBar(title: const Text('球队详情')),
      body: async.when(
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (e, _) => AsyncStatePane.error(
          error: e,
          onRetry: () => ref.invalidate(teamDetailProvider(teamId)),
        ),
        data: (data) {
          final t = data.team;
          final s = data.standing;
          return RefreshIndicator(
            onRefresh: () async => ref.invalidate(teamDetailProvider(teamId)),
            child: ListView(
              padding: const EdgeInsets.all(16),
              children: [
                Card(
                  child: Padding(
                    padding: const EdgeInsets.all(16),
                    child: Row(
                      children: [
                        TeamLogo(url: t.logo, size: 56),
                        const SizedBox(width: 14),
                        Expanded(
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              Text(
                                t.name,
                                style: const TextStyle(
                                  fontSize: 20,
                                  fontWeight: FontWeight.w600,
                                ),
                              ),
                              const SizedBox(height: 4),
                              Text(
                                [
                                  if (data.league != null) data.league!.name,
                                  if (t.country != null && t.country!.isNotEmpty)
                                    t.country!,
                                ].join(' · '),
                                style: const TextStyle(color: AppColors.textMuted),
                              ),
                            ],
                          ),
                        ),
                      ],
                    ),
                  ),
                ),
                const SizedBox(height: 12),
                Card(
                  child: Padding(
                    padding: const EdgeInsets.all(16),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        const Text(
                          '简介',
                          style: TextStyle(fontSize: 16, fontWeight: FontWeight.w600),
                        ),
                        const SizedBox(height: 12),
                        Wrap(
                          spacing: 12,
                          runSpacing: 12,
                          children: [
                            _StatChip(label: 'ELO', value: '${t.eloRating}'),
                            _StatChip(
                              label: '进攻',
                              value: t.attackStrength.toStringAsFixed(2),
                            ),
                            _StatChip(
                              label: '防守',
                              value: t.defenseStrength.toStringAsFixed(2),
                            ),
                            if (t.foundedYear != null)
                              _StatChip(label: '成立', value: '${t.foundedYear}'),
                          ],
                        ),
                        if (t.homeGround != null && t.homeGround!.isNotEmpty) ...[
                          const SizedBox(height: 12),
                          Text(
                            '主场：${t.homeGround}',
                            style: const TextStyle(color: AppColors.textSecondary),
                          ),
                        ],
                        if (s != null) ...[
                          const SizedBox(height: 12),
                          Text(
                            '积分榜：第 ${s.rank} 名 · ${s.points} 分'
                            '（${s.played} 场 ${s.won}胜${s.drawn}平${s.lost}负）',
                            style: const TextStyle(color: AppColors.textSecondary),
                          ),
                        ],
                      ],
                    ),
                  ),
                ),
                const SizedBox(height: 12),
                Card(
                  child: Padding(
                    padding: const EdgeInsets.all(16),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Row(
                          children: [
                            const Expanded(
                              child: Text(
                                '近期战绩',
                                style: TextStyle(
                                  fontSize: 16,
                                  fontWeight: FontWeight.w600,
                                ),
                              ),
                            ),
                            if (t.leagueId != null)
                              TextButton(
                                onPressed: () {
                                  ref
                                      .read(selectedLeagueIdProvider.notifier)
                                      .setId(t.leagueId);
                                  context.go('/data');
                                },
                                child: const Text('联赛数据'),
                              ),
                          ],
                        ),
                        const SizedBox(height: 8),
                        if (data.recent.isEmpty)
                          const Text(
                            '暂无近期完赛记录',
                            style: TextStyle(color: AppColors.textMuted),
                          )
                        else
                          ...data.recent.map(
                            (m) => ListTile(
                              contentPadding: EdgeInsets.zero,
                              title: Text(
                                '${m.homeTeam.displayName} ${m.scoreText} ${m.awayTeam.displayName}',
                              ),
                              subtitle: Text(
                                '${m.league.name} · ${m.whenText}',
                                style: const TextStyle(color: AppColors.textMuted),
                              ),
                              trailing: const Icon(Icons.chevron_right),
                              onTap: () => context.push('/matches/${m.id}'),
                            ),
                          ),
                      ],
                    ),
                  ),
                ),
              ],
            ),
          );
        },
      ),
    );
  }
}

class _StatChip extends StatelessWidget {
  const _StatChip({required this.label, required this.value});

  final String label;
  final String value;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
      decoration: BoxDecoration(
        color: AppColors.bgSecondary,
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: AppColors.border),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(label, style: const TextStyle(color: AppColors.textMuted, fontSize: 12)),
          const SizedBox(height: 4),
          Text(value, style: const TextStyle(fontWeight: FontWeight.w600)),
        ],
      ),
    );
  }
}
