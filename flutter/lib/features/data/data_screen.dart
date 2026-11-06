import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/network/api_exception.dart';
import '../../core/providers.dart';
import '../../core/theme.dart';
import '../../data/models/league.dart';
import '../../data/repositories/data_repository.dart';
import '../common/async_state_pane.dart';
import '../follows/follow_providers.dart';

enum DataBoardTab { standings, scorers }

class SelectedLeagueNotifier extends Notifier<String?> {
  @override
  String? build() => null;

  void setId(String? id) => state = id;
}

class DataBoardTabNotifier extends Notifier<DataBoardTab> {
  @override
  DataBoardTab build() => DataBoardTab.standings;

  void setTab(DataBoardTab tab) => state = tab;
}

final selectedLeagueIdProvider =
    NotifierProvider<SelectedLeagueNotifier, String?>(SelectedLeagueNotifier.new);

final dataBoardTabProvider =
    NotifierProvider<DataBoardTabNotifier, DataBoardTab>(DataBoardTabNotifier.new);

final leaguesProvider = FutureProvider.autoDispose<List<LeagueItem>>((ref) {
  return ref.watch(leagueRepositoryProvider).selectable();
});

final leagueBoardProvider =
    FutureProvider.autoDispose.family<LeagueBoardData, String>((ref, leagueId) {
  return ref.watch(dataRepositoryProvider).board(leagueId);
});

class DataScreen extends ConsumerWidget {
  const DataScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final leaguesAsync = ref.watch(leaguesProvider);
    final selectedId = ref.watch(selectedLeagueIdProvider);
    final tab = ref.watch(dataBoardTabProvider);
    final followedAsync = ref.watch(followedIdsProvider);

    return Scaffold(
      appBar: AppBar(title: const Text('数据')),
      body: leaguesAsync.when(
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (e, _) => AsyncStatePane.error(
          error: e,
          onRetry: () => ref.invalidate(leaguesProvider),
        ),
        data: (leagues) {
          if (leagues.isEmpty) {
            return AsyncStatePane.empty(
              message: '暂无联赛数据',
              onRetry: () => ref.invalidate(leaguesProvider),
            );
          }

          final String effectiveId;
          if (selectedId != null && leagues.any((l) => l.id == selectedId)) {
            effectiveId = selectedId;
          } else {
            effectiveId = leagues.first.id;
          }
          if (selectedId != effectiveId) {
            WidgetsBinding.instance.addPostFrameCallback((_) {
              ref.read(selectedLeagueIdProvider.notifier).setId(effectiveId);
            });
          }

          final boardAsync = ref.watch(leagueBoardProvider(effectiveId));
          final followed = switch (followedAsync) {
            AsyncData(:final value) => value,
            _ => <String>{},
          };
          final isFollowed = followed.contains(effectiveId);
          final current = leagues.firstWhere(
            (l) => l.id == effectiveId,
            orElse: () => leagues.first,
          );
          final season = switch (boardAsync) {
            AsyncData(:final value) => value.season,
            _ => null,
          };

          return Column(
            children: [
              Padding(
                padding: const EdgeInsets.fromLTRB(16, 12, 16, 8),
                child: Row(
                  children: [
                    Expanded(
                      child: InputDecorator(
                        decoration: const InputDecoration(
                          labelText: '联赛',
                          contentPadding:
                              EdgeInsets.symmetric(horizontal: 12, vertical: 4),
                        ),
                        child: DropdownButtonHideUnderline(
                          child: DropdownButton<String>(
                            value: effectiveId,
                            isExpanded: true,
                            items: leagues
                                .map(
                                  (l) => DropdownMenuItem(
                                    value: l.id,
                                    child: Text(
                                      l.name,
                                      overflow: TextOverflow.ellipsis,
                                    ),
                                  ),
                                )
                                .toList(),
                            onChanged: (v) {
                              if (v != null) {
                                ref
                                    .read(selectedLeagueIdProvider.notifier)
                                    .setId(v);
                              }
                            },
                          ),
                        ),
                      ),
                    ),
                    const SizedBox(width: 8),
                    IconButton(
                      tooltip: isFollowed ? '取消关注' : '关注联赛',
                      onPressed: () => _toggleFollow(
                        context,
                        ref,
                        leagueId: effectiveId,
                        currentlyFollowed: isFollowed,
                      ),
                      icon: Icon(
                        isFollowed ? Icons.star : Icons.star_border,
                        color:
                            isFollowed ? AppColors.gold : AppColors.textMuted,
                      ),
                    ),
                  ],
                ),
              ),
              Padding(
                padding: const EdgeInsets.symmetric(horizontal: 16),
                child: Row(
                  children: [
                    Expanded(
                      child: Text(
                        [
                          if (current.country != null &&
                              current.country!.isNotEmpty)
                            current.country!,
                          if (season != null && season.isNotEmpty) season,
                        ].join(' · '),
                        style: const TextStyle(
                          color: AppColors.textMuted,
                          fontSize: 12,
                        ),
                      ),
                    ),
                    TextButton(
                      onPressed: () => context.go('/matches'),
                      child: const Text('看赛事'),
                    ),
                  ],
                ),
              ),
              Padding(
                padding: const EdgeInsets.fromLTRB(16, 4, 16, 8),
                child: SegmentedButton<DataBoardTab>(
                  segments: const [
                    ButtonSegment(
                      value: DataBoardTab.standings,
                      label: Text('积分榜'),
                    ),
                    ButtonSegment(
                      value: DataBoardTab.scorers,
                      label: Text('射手榜'),
                    ),
                  ],
                  selected: {tab},
                  onSelectionChanged: (s) {
                    ref.read(dataBoardTabProvider.notifier).setTab(s.first);
                  },
                ),
              ),
              Expanded(
                child: boardAsync.when(
                  loading: () =>
                      const Center(child: CircularProgressIndicator()),
                  error: (e, _) => AsyncStatePane.error(
                    error: e,
                    onRetry: () =>
                        ref.invalidate(leagueBoardProvider(effectiveId)),
                  ),
                  data: (board) {
                    if (tab == DataBoardTab.standings) {
                      if (board.standings.isEmpty) {
                        return const AsyncStatePane.empty(message: '暂无积分榜');
                      }
                      return RefreshIndicator(
                        onRefresh: () async {
                          ref.invalidate(leagueBoardProvider(effectiveId));
                        },
                        child: ListView.separated(
                          padding: const EdgeInsets.fromLTRB(16, 0, 16, 16),
                          itemCount: board.standings.length + 1,
                          separatorBuilder: (context, index) =>
                              const Divider(height: 1),
                          itemBuilder: (context, index) {
                            if (index == 0) {
                              return const Padding(
                                padding: EdgeInsets.symmetric(vertical: 8),
                                child: Row(
                                  children: [
                                    SizedBox(
                                      width: 28,
                                      child: Text('#', style: _head),
                                    ),
                                    Expanded(child: Text('球队', style: _head)),
                                    SizedBox(
                                      width: 28,
                                      child: Text(
                                        '赛',
                                        style: _head,
                                        textAlign: TextAlign.right,
                                      ),
                                    ),
                                    SizedBox(
                                      width: 36,
                                      child: Text(
                                        '净',
                                        style: _head,
                                        textAlign: TextAlign.right,
                                      ),
                                    ),
                                    SizedBox(
                                      width: 36,
                                      child: Text(
                                        '分',
                                        style: _head,
                                        textAlign: TextAlign.right,
                                      ),
                                    ),
                                  ],
                                ),
                              );
                            }
                            final row = board.standings[index - 1];
                            return InkWell(
                              onTap: () => context.push('/teams/${row.teamId}'),
                              child: Padding(
                                padding:
                                    const EdgeInsets.symmetric(vertical: 10),
                                child: Row(
                                  children: [
                                    SizedBox(
                                      width: 28,
                                      child: Text(
                                        '${row.rank}',
                                        style: const TextStyle(
                                          color: AppColors.textMuted,
                                        ),
                                      ),
                                    ),
                                    Expanded(
                                      child: Text(
                                        row.displayName,
                                        style: const TextStyle(
                                          fontWeight: FontWeight.w600,
                                        ),
                                      ),
                                    ),
                                    SizedBox(
                                      width: 28,
                                      child: Text(
                                        '${row.played}',
                                        textAlign: TextAlign.right,
                                      ),
                                    ),
                                    SizedBox(
                                      width: 36,
                                      child: Text(
                                        '${row.goalDiff}',
                                        textAlign: TextAlign.right,
                                      ),
                                    ),
                                    SizedBox(
                                      width: 36,
                                      child: Text(
                                        '${row.points}',
                                        textAlign: TextAlign.right,
                                        style: const TextStyle(
                                          color: AppColors.gold,
                                          fontWeight: FontWeight.bold,
                                        ),
                                      ),
                                    ),
                                  ],
                                ),
                              ),
                            );
                          },
                        ),
                      );
                    }

                    if (board.scorers.isEmpty) {
                      return const AsyncStatePane.empty(message: '暂无射手榜');
                    }
                    return RefreshIndicator(
                      onRefresh: () async {
                        ref.invalidate(leagueBoardProvider(effectiveId));
                      },
                      child: ListView.separated(
                        padding: const EdgeInsets.all(16),
                        itemCount: board.scorers.length,
                        separatorBuilder: (context, index) =>
                            const SizedBox(height: 8),
                        itemBuilder: (context, index) {
                          final row = board.scorers[index];
                          return Card(
                            child: ListTile(
                              leading: CircleAvatar(
                                backgroundColor: AppColors.bgSecondary,
                                child: Text(
                                  '${row.rank > 0 ? row.rank : index + 1}',
                                  style: const TextStyle(fontSize: 13),
                                ),
                              ),
                              title: Text(row.playerName),
                              subtitle: Text(
                                row.teamLabel,
                                style: const TextStyle(
                                  color: AppColors.textMuted,
                                ),
                              ),
                              trailing: Text(
                                '${row.goals}球 · ${row.assists}助',
                                style: const TextStyle(color: AppColors.green),
                              ),
                              onTap: row.teamId == null || row.teamId!.isEmpty
                                  ? null
                                  : () => context.push('/teams/${row.teamId}'),
                            ),
                          );
                        },
                      ),
                    );
                  },
                ),
              ),
            ],
          );
        },
      ),
    );
  }

  Future<void> _toggleFollow(
    BuildContext context,
    WidgetRef ref, {
    required String leagueId,
    required bool currentlyFollowed,
  }) async {
    try {
      await ref.read(followRepositoryProvider).toggle(
            leagueId,
            currentlyFollowed: currentlyFollowed,
          );
      ref.invalidate(followedIdsProvider);
      ref.invalidate(followSummaryProvider);
      if (context.mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text(currentlyFollowed ? '已取消关注' : '已关注联赛'),
          ),
        );
      }
    } catch (e) {
      if (!context.mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(e is ApiException ? e.message : e.toString()),
        ),
      );
    }
  }
}

const _head = TextStyle(color: AppColors.textMuted, fontSize: 12);
