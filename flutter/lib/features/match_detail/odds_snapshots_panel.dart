import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/network/api_exception.dart';
import '../../core/odds_math.dart';
import '../../core/providers.dart';
import '../../core/theme.dart';
import '../../data/models/match.dart';
import '../../data/models/odds_snapshot.dart';
import '../auth/auth_state.dart';
import '../common/async_state_pane.dart';

@immutable
class OddsSnapshotsState {
  const OddsSnapshotsState({
    this.snapshots = const [],
    this.locked = false,
    this.lockMessage,
  });

  final List<OddsSnapshot> snapshots;
  final bool locked;
  final String? lockMessage;
}

final oddsSnapshotsProvider =
    FutureProvider.autoDispose.family<OddsSnapshotsState, String>(
  (ref, matchId) async {
    final auth = ref.watch(authProvider);
    if (!auth.canOddsSnapshot) {
      return const OddsSnapshotsState(
        locked: true,
        lockMessage: '赔率时序快照需订阅权益 odds:snapshot 解锁（仅供学习分析）',
      );
    }
    try {
      final list =
          await ref.watch(matchRepositoryProvider).oddsSnapshots(matchId);
      return OddsSnapshotsState(snapshots: list);
    } on ApiException catch (e) {
      if (e.isFeatureLocked) {
        return OddsSnapshotsState(
          locked: true,
          lockMessage: e.message.isNotEmpty
              ? e.message
              : '该功能需要更高等级订阅，请升级后使用',
        );
      }
      rethrow;
    }
  },
);

class OddsSnapshotsPanel extends ConsumerWidget {
  const OddsSnapshotsPanel({
    super.key,
    required this.matchId,
    this.prediction,
  });

  final String matchId;
  final PredictionSummary? prediction;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final async = ref.watch(oddsSnapshotsProvider(matchId));

    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Text(
              '赔率快照',
              style: TextStyle(fontSize: 16, fontWeight: FontWeight.w600),
            ),
            const SizedBox(height: 6),
            const Text(
              '采集覆盖写赔率且发生变化时落库。仅供学习研究与数据分析，不构成投注建议。',
              style: TextStyle(
                color: AppColors.textMuted,
                fontSize: 12,
                height: 1.35,
              ),
            ),
            const SizedBox(height: 12),
            async.when(
              loading: () => const Padding(
                padding: EdgeInsets.symmetric(vertical: 12),
                child: Center(child: CircularProgressIndicator(strokeWidth: 2)),
              ),
              error: (e, _) => AsyncStatePane.error(
                error: e,
                onRetry: () => ref.invalidate(oddsSnapshotsProvider(matchId)),
              ),
              data: (state) {
                if (state.locked) {
                  return Text(
                    state.lockMessage ?? '暂无访问权限',
                    style: const TextStyle(
                      color: AppColors.orange,
                      height: 1.4,
                      fontSize: 13,
                    ),
                  );
                }
                if (state.snapshots.isEmpty) {
                  return const Text(
                    '暂无赔率快照',
                    style: TextStyle(color: AppColors.textMuted, fontSize: 13),
                  );
                }
                return Column(
                  children: state.snapshots
                      .map(
                        (s) => _SnapshotTile(
                          snapshot: s,
                          prediction: prediction,
                        ),
                      )
                      .toList(),
                );
              },
            ),
          ],
        ),
      ),
    );
  }
}

class _SnapshotTile extends StatelessWidget {
  const _SnapshotTile({
    required this.snapshot,
    this.prediction,
  });

  final OddsSnapshot snapshot;
  final PredictionSummary? prediction;

  @override
  Widget build(BuildContext context) {
    final implied = snapshot.implied;
    OddsVsModel? vs;
    if (implied != null &&
        prediction != null &&
        prediction!.hasProbs &&
        prediction!.homeWinProb != null &&
        prediction!.drawProb != null &&
        prediction!.awayWinProb != null) {
      vs = compareImpliedToModel(
        impliedHome: implied.home,
        impliedDraw: implied.draw,
        impliedAway: implied.away,
        modelHome: prediction!.homeWinProb!,
        modelDraw: prediction!.drawProb!,
        modelAway: prediction!.awayWinProb!,
      );
    }

    return Padding(
      padding: const EdgeInsets.only(bottom: 10),
      child: Container(
        width: double.infinity,
        padding: const EdgeInsets.all(12),
        decoration: BoxDecoration(
          color: AppColors.bgSecondary,
          borderRadius: BorderRadius.circular(8),
          border: Border.all(color: AppColors.border),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Expanded(
                  child: Text(
                    _formatTime(snapshot.capturedAt),
                    style: const TextStyle(
                      fontSize: 12,
                      color: AppColors.textMuted,
                    ),
                  ),
                ),
                if (snapshot.handicap != null)
                  Text(
                    '让球 ${snapshot.handicap}',
                    style: const TextStyle(
                      fontSize: 12,
                      color: AppColors.gold,
                    ),
                  ),
              ],
            ),
            const SizedBox(height: 6),
            Text(
              '市场参考 ${_fmtOdds(snapshot.win)} / '
              '${_fmtOdds(snapshot.draw)} / ${_fmtOdds(snapshot.lose)}',
              style: const TextStyle(fontSize: 13, fontWeight: FontWeight.w600),
            ),
            if (implied != null) ...[
              const SizedBox(height: 4),
              Text(
                '隐含 ${_pct(implied.home)} / ${_pct(implied.draw)} / ${_pct(implied.away)}'
                ' · 抽水 ${implied.overroundPct.toStringAsFixed(1)}%',
                style: const TextStyle(
                  fontSize: 12,
                  color: AppColors.textSecondary,
                ),
              ),
            ],
            if (vs != null) ...[
              const SizedBox(height: 4),
              Text(
                '相对模型 ${vs.maxAbsDeltaPct.toStringAsFixed(1)}pt'
                ' · ${vs.agreeTendency ? '同向' : '异向'}'
                ' · ${vs.level}',
                style: TextStyle(
                  fontSize: 12,
                  color: vs.agreeTendency ? AppColors.green : AppColors.orange,
                ),
              ),
            ],
            if (snapshot.source != null && snapshot.source!.isNotEmpty) ...[
              const SizedBox(height: 4),
              Text(
                '来源 ${snapshot.source}',
                style: const TextStyle(
                  fontSize: 11,
                  color: AppColors.textMuted,
                ),
              ),
            ],
          ],
        ),
      ),
    );
  }

  static String _fmtOdds(double? v) {
    if (v == null) return '-';
    return v.toStringAsFixed(2);
  }

  static String _pct(double v) => '${(v * 100).toStringAsFixed(1)}%';

  static String _formatTime(String? raw) {
    if (raw == null || raw.isEmpty) return '-';
    final dt = DateTime.tryParse(raw);
    if (dt == null) return raw;
    final local = dt.toLocal();
    String two(int n) => n.toString().padLeft(2, '0');
    return '${local.year}-${two(local.month)}-${two(local.day)} '
        '${two(local.hour)}:${two(local.minute)}';
  }
}
