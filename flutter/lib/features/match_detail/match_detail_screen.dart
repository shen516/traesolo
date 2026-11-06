import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/config.dart';
import '../../core/network/api_exception.dart';
import '../../core/providers.dart';
import '../../core/theme.dart';
import '../../data/models/match.dart';

final matchDetailProvider =
    FutureProvider.autoDispose.family<({MatchItem match, PredictionSummary? prediction}), String>(
  (ref, matchId) async {
    final repo = ref.watch(matchRepositoryProvider);
    final match = await repo.detail(matchId);
    PredictionSummary? prediction = match.prediction;
    try {
      prediction = await repo.prediction(matchId);
    } catch (_) {
      // 无预测权限或尚未产出时，保留详情里已有摘要
    }
    return (match: match, prediction: prediction);
  },
);

class MatchDetailScreen extends ConsumerWidget {
  const MatchDetailScreen({super.key, required this.matchId});

  final String matchId;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final async = ref.watch(matchDetailProvider(matchId));

    return Scaffold(
      appBar: AppBar(title: const Text('赛事详情')),
      body: async.when(
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (e, _) => Center(
          child: Padding(
            padding: const EdgeInsets.all(24),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                Text(e is ApiException ? e.message : e.toString()),
                const SizedBox(height: 12),
                ElevatedButton(
                  onPressed: () => ref.invalidate(matchDetailProvider(matchId)),
                  child: const Text('重试'),
                ),
              ],
            ),
          ),
        ),
        data: (data) {
          final m = data.match;
          final p = data.prediction;
          return ListView(
            padding: const EdgeInsets.all(16),
            children: [
              Card(
                child: Padding(
                  padding: const EdgeInsets.all(16),
                  child: Column(
                    children: [
                      Text(
                        m.league.name,
                        style: const TextStyle(color: AppColors.textMuted),
                      ),
                      const SizedBox(height: 4),
                      Text(
                        m.whenText,
                        style: const TextStyle(color: AppColors.textSecondary, fontSize: 13),
                      ),
                      const SizedBox(height: 16),
                      Row(
                        children: [
                          Expanded(
                            child: Text(
                              m.homeTeam.displayName,
                              textAlign: TextAlign.center,
                              style: const TextStyle(fontSize: 18, fontWeight: FontWeight.w600),
                            ),
                          ),
                          Text(
                            m.scoreText,
                            style: const TextStyle(
                              fontSize: 22,
                              fontWeight: FontWeight.bold,
                              color: AppColors.gold,
                            ),
                          ),
                          Expanded(
                            child: Text(
                              m.awayTeam.displayName,
                              textAlign: TextAlign.center,
                              style: const TextStyle(fontSize: 18, fontWeight: FontWeight.w600),
                            ),
                          ),
                        ],
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
                        '模型预测（只读）',
                        style: TextStyle(fontSize: 16, fontWeight: FontWeight.w600),
                      ),
                      const SizedBox(height: 8),
                      const Text(
                        AppConfig.disclaimer,
                        style: TextStyle(color: AppColors.textMuted, fontSize: 12),
                      ),
                      const SizedBox(height: 16),
                      if (p == null || (!p.hasProbs && p.mainScore == null))
                        const Text('暂无预测数据', style: TextStyle(color: AppColors.textMuted))
                      else ...[
                        if (p.hasProbs) ...[
                          _ProbBar(label: '主胜', value: p.homeWinProb ?? 0, color: AppColors.blue),
                          const SizedBox(height: 8),
                          _ProbBar(label: '平局', value: p.drawProb ?? 0, color: AppColors.textMuted),
                          const SizedBox(height: 8),
                          _ProbBar(label: '客胜', value: p.awayWinProb ?? 0, color: AppColors.orange),
                          const SizedBox(height: 16),
                        ],
                        _kv('主线比分', p.mainScore ?? '-'),
                        _kv('倾向', p.tendency ?? '-'),
                        _kv('信心', p.confidence ?? '-'),
                        _kv('风险', p.riskLevel ?? '-'),
                        _kv('总进球', p.totalGoals?.toString() ?? '-'),
                        _kv('模型版本', p.modelVersion ?? '-'),
                        if (p.altScores.isNotEmpty)
                          _kv('备选比分', p.altScores.join('、')),
                        if (p.analysis != null && p.analysis!.isNotEmpty) ...[
                          const SizedBox(height: 12),
                          const Text('分析摘要', style: TextStyle(fontWeight: FontWeight.w600)),
                          const SizedBox(height: 6),
                          Text(
                            p.analysis!,
                            style: const TextStyle(color: AppColors.textSecondary, height: 1.4),
                          ),
                        ],
                      ],
                    ],
                  ),
                ),
              ),
            ],
          );
        },
      ),
    );
  }

  Widget _kv(String k, String v) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 6),
      child: Row(
        children: [
          SizedBox(
            width: 72,
            child: Text(k, style: const TextStyle(color: AppColors.textMuted)),
          ),
          Expanded(child: Text(v)),
        ],
      ),
    );
  }
}

class _ProbBar extends StatelessWidget {
  const _ProbBar({
    required this.label,
    required this.value,
    required this.color,
  });

  final String label;
  final double value;
  final Color color;

  @override
  Widget build(BuildContext context) {
    final pct = (value.clamp(0, 1) * 100);
    return Row(
      children: [
        SizedBox(width: 40, child: Text(label)),
        Expanded(
          child: ClipRRect(
            borderRadius: BorderRadius.circular(4),
            child: LinearProgressIndicator(
              value: value.clamp(0, 1),
              minHeight: 10,
              backgroundColor: AppColors.bgSecondary,
              color: color,
            ),
          ),
        ),
        const SizedBox(width: 8),
        SizedBox(
          width: 52,
          child: Text(
            '${pct.toStringAsFixed(1)}%',
            textAlign: TextAlign.right,
            style: const TextStyle(fontSize: 12, color: AppColors.textSecondary),
          ),
        ),
      ],
    );
  }
}
