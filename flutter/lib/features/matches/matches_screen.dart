import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/network/api_exception.dart';
import '../../core/providers.dart';
import '../../core/theme.dart';
import '../../data/models/match.dart';

enum MatchTab { upcoming, finished }

class MatchTabNotifier extends Notifier<MatchTab> {
  @override
  MatchTab build() => MatchTab.upcoming;

  void setTab(MatchTab tab) => state = tab;
}

final matchTabProvider =
    NotifierProvider<MatchTabNotifier, MatchTab>(MatchTabNotifier.new);

final matchListProvider = FutureProvider.autoDispose<MatchListPage>((ref) async {
  final tab = ref.watch(matchTabProvider);
  final repo = ref.watch(matchRepositoryProvider);
  if (tab == MatchTab.upcoming) {
    return repo.upcoming();
  }
  return repo.finished();
});

class MatchesScreen extends ConsumerWidget {
  const MatchesScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final tab = ref.watch(matchTabProvider);
    final asyncList = ref.watch(matchListProvider);

    return Scaffold(
      appBar: AppBar(title: const Text('赛事')),
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
          Expanded(
            child: asyncList.when(
              loading: () => const Center(child: CircularProgressIndicator()),
              error: (e, _) => _ErrorPane(
                message: e is ApiException ? e.message : e.toString(),
                onRetry: () => ref.invalidate(matchListProvider),
              ),
              data: (page) {
                if (page.matches.isEmpty) {
                  return const Center(
                    child: Text('暂无赛事', style: TextStyle(color: AppColors.textMuted)),
                  );
                }
                return RefreshIndicator(
                  onRefresh: () async => ref.invalidate(matchListProvider),
                  child: ListView.separated(
                    padding: const EdgeInsets.all(16),
                    itemCount: page.matches.length,
                    separatorBuilder: (context, index) => const SizedBox(height: 10),
                    itemBuilder: (context, index) {
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

class _MatchCard extends StatelessWidget {
  const _MatchCard({required this.match, required this.onTap});

  final MatchItem match;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final pred = match.prediction;
    return Card(
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
                  Expanded(
                    child: Text(
                      match.league.name,
                      style: const TextStyle(color: AppColors.textMuted, fontSize: 12),
                    ),
                  ),
                  Text(
                    match.whenText,
                    style: const TextStyle(color: AppColors.textMuted, fontSize: 12),
                  ),
                ],
              ),
              const SizedBox(height: 10),
              Row(
                children: [
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
                ],
              ),
              if (pred != null && pred.hasProbs) ...[
                const SizedBox(height: 10),
                Text(
                  '胜平负 ${_pct(pred.homeWinProb)}(主) / ${_pct(pred.drawProb)}(平) / ${_pct(pred.awayWinProb)}(客)',
                  style: const TextStyle(color: AppColors.textSecondary, fontSize: 12),
                ),
              ] else if (pred?.mainScore != null) ...[
                const SizedBox(height: 10),
                Text(
                  '主线比分 ${pred!.mainScore}',
                  style: const TextStyle(color: AppColors.textSecondary, fontSize: 12),
                ),
              ],
            ],
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

class _ErrorPane extends StatelessWidget {
  const _ErrorPane({required this.message, required this.onRetry});

  final String message;
  final VoidCallback onRetry;

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(24),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Text(message, textAlign: TextAlign.center),
            const SizedBox(height: 12),
            ElevatedButton(onPressed: onRetry, child: const Text('重试')),
          ],
        ),
      ),
    );
  }
}
