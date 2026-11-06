import 'package:flutter/material.dart';

import '../core/config.dart';
import '../core/theme.dart';
import '../data/models/match.dart';

/// 预测只读展示：堆叠胜平负条 + 主线比分 + 场景说明。
class PredictionPanel extends StatelessWidget {
  const PredictionPanel({super.key, required this.prediction});

  final PredictionSummary? prediction;

  @override
  Widget build(BuildContext context) {
    final p = prediction;
    return Card(
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
            if (p == null || !p.hasContent)
              const Text('暂无预测数据', style: TextStyle(color: AppColors.textMuted))
            else ...[
              if (p.hasProbs) ...[
                WdlStackBar(
                  home: p.homeWinProb ?? 0,
                  draw: p.drawProb ?? 0,
                  away: p.awayWinProb ?? 0,
                ),
                const SizedBox(height: 12),
                Row(
                  children: [
                    _Legend(color: AppColors.blue, label: '主 ${_pct(p.homeWinProb)}'),
                    const SizedBox(width: 12),
                    _Legend(color: AppColors.textMuted, label: '平 ${_pct(p.drawProb)}'),
                    const SizedBox(width: 12),
                    _Legend(color: AppColors.orange, label: '客 ${_pct(p.awayWinProb)}'),
                  ],
                ),
                const SizedBox(height: 16),
              ],
              if (p.mainScore != null && p.mainScore!.isNotEmpty)
                _HighlightScore(score: p.mainScore!),
              if (p.scenarioTitle.isNotEmpty ||
                  (p.scenarioReason != null && p.scenarioReason!.isNotEmpty) ||
                  (p.tendency != null && p.tendency!.isNotEmpty)) ...[
                const SizedBox(height: 14),
                const Text(
                  '场景说明',
                  style: TextStyle(fontWeight: FontWeight.w600),
                ),
                const SizedBox(height: 8),
                Wrap(
                  spacing: 8,
                  runSpacing: 8,
                  children: [
                    if (p.scenarioTitle.isNotEmpty)
                      _Chip(text: p.scenarioTitle, color: AppColors.blue),
                    if (p.tendency != null && p.tendency!.isNotEmpty)
                      _Chip(text: '倾向 ${p.tendency}', color: AppColors.gold),
                    if (p.confidence != null && p.confidence!.isNotEmpty)
                      _Chip(text: '信心 ${p.confidence}', color: AppColors.green),
                    if (p.riskLevel != null && p.riskLevel!.isNotEmpty)
                      _Chip(text: '风险 ${p.riskLevel}', color: AppColors.orange),
                  ],
                ),
                if (p.scenarioReason != null && p.scenarioReason!.isNotEmpty) ...[
                  const SizedBox(height: 8),
                  Text(
                    p.scenarioReason!,
                    style: const TextStyle(
                      color: AppColors.textSecondary,
                      height: 1.4,
                    ),
                  ),
                ],
              ],
              const SizedBox(height: 12),
              _kv('总进球', p.totalGoals?.toString() ?? '-'),
              _kv('模型版本', p.modelVersion ?? '-'),
              if (p.altScores.isNotEmpty) _kv('备选比分', p.altScores.join('、')),
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

class WdlStackBar extends StatelessWidget {
  const WdlStackBar({
    super.key,
    required this.home,
    required this.draw,
    required this.away,
    this.height = 14,
  });

  final double home;
  final double draw;
  final double away;
  final double height;

  @override
  Widget build(BuildContext context) {
    final h = home.clamp(0.0, 1.0);
    final d = draw.clamp(0.0, 1.0);
    final a = away.clamp(0.0, 1.0);
    final sum = h + d + a;
    final nh = sum > 0 ? h / sum : 0.0;
    final nd = sum > 0 ? d / sum : 0.0;
    final na = sum > 0 ? a / sum : 0.0;

    return ClipRRect(
      borderRadius: BorderRadius.circular(6),
      child: SizedBox(
        height: height,
        child: Row(
          children: [
            if (nh > 0)
              Expanded(
                flex: (nh * 1000).round().clamp(1, 1000),
                child: ColoredBox(color: AppColors.blue),
              ),
            if (nd > 0)
              Expanded(
                flex: (nd * 1000).round().clamp(1, 1000),
                child: ColoredBox(color: AppColors.textMuted),
              ),
            if (na > 0)
              Expanded(
                flex: (na * 1000).round().clamp(1, 1000),
                child: ColoredBox(color: AppColors.orange),
              ),
            if (sum <= 0)
              const Expanded(child: ColoredBox(color: AppColors.bgSecondary)),
          ],
        ),
      ),
    );
  }
}

class _HighlightScore extends StatelessWidget {
  const _HighlightScore({required this.score});

  final String score;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
      decoration: BoxDecoration(
        color: AppColors.bgSecondary,
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: AppColors.border),
      ),
      child: Row(
        children: [
          const Text('主线比分', style: TextStyle(color: AppColors.textMuted)),
          const Spacer(),
          Text(
            score,
            style: const TextStyle(
              fontSize: 22,
              fontWeight: FontWeight.bold,
              color: AppColors.gold,
            ),
          ),
        ],
      ),
    );
  }
}

class _Legend extends StatelessWidget {
  const _Legend({required this.color, required this.label});

  final Color color;
  final String label;

  @override
  Widget build(BuildContext context) {
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        Container(
          width: 10,
          height: 10,
          decoration: BoxDecoration(color: color, borderRadius: BorderRadius.circular(2)),
        ),
        const SizedBox(width: 4),
        Text(label, style: const TextStyle(fontSize: 12, color: AppColors.textSecondary)),
      ],
    );
  }
}

class _Chip extends StatelessWidget {
  const _Chip({required this.text, required this.color});

  final String text;
  final Color color;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.15),
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: color.withValues(alpha: 0.35)),
      ),
      child: Text(text, style: TextStyle(color: color, fontSize: 12)),
    );
  }
}

String _pct(double? v) {
  if (v == null) return '-';
  return '${(v * 100).toStringAsFixed(1)}%';
}
