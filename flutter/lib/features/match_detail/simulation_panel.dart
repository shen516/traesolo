import 'dart:async';

import 'package:dio/dio.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/config.dart';
import '../../core/network/api_exception.dart';
import '../../core/providers.dart';
import '../../core/theme.dart';
import '../../data/models/sensitivity.dart';
import '../../data/models/simulation.dart';
import '../../widgets/prediction_panel.dart';
import 'bet_builder_panel.dart';
import '../auth/auth_state.dart';

final simHistoryProvider =
    FutureProvider.autoDispose.family<List<SimulationHistoryItem>, String>(
  (ref, matchId) async {
    final auth = ref.watch(authProvider);
    if (!auth.canSimulate) return const [];
    try {
      return await ref.watch(simulationRepositoryProvider).history(
            matchId: matchId,
            limit: 8,
          );
    } on ApiException catch (e) {
      if (e.isForbidden) return const [];
      rethrow;
    }
  },
);

class SimulationPanel extends ConsumerStatefulWidget {
  const SimulationPanel({
    super.key,
    required this.matchId,
    required this.isUpcoming,
  });

  final String matchId;
  final bool isUpcoming;

  @override
  ConsumerState<SimulationPanel> createState() => _SimulationPanelState();
}

class _SimulationPanelState extends ConsumerState<SimulationPanel> {
  int _simulations = AppConfig.defaultSimulations;
  final _seedCtrl = TextEditingController();
  bool _running = false;
  bool _sensRunning = false;
  String? _error;
  SimulationResult? _result;
  SensitivityResult? _sensitivity;
  CancelToken? _cancelToken;
  Timer? _progressTimer;
  int _progressStage = 0;

  static const _simOptions = [3000, 5000, 10000, 20000];

  static const _simStages = [
    '正在生成随机样本…',
    '正在计算泊松概率…',
    '正在运行蒙特卡洛模拟…',
    '正在汇总结果…',
  ];

  static const _sensStages = [
    '正在扫描 λ 参数空间…',
    '正在逐点计算模拟…',
    '正在汇总敏感性结果…',
  ];

  bool get _busy => _running || _sensRunning;

  @override
  void dispose() {
    _progressTimer?.cancel();
    _cancelToken?.cancel();
    _seedCtrl.dispose();
    super.dispose();
  }

  void _startProgressTimer(bool isSensitivity) {
    _progressStage = 0;
    _progressTimer?.cancel();
    final stages = isSensitivity ? _sensStages : _simStages;
    _progressTimer = Timer.periodic(const Duration(seconds: 4), (t) {
      if (!mounted) {
        t.cancel();
        return;
      }
      setState(() {
        _progressStage = (_progressStage + 1) % stages.length;
      });
    });
  }

  void _stopProgressTimer() {
    _progressTimer?.cancel();
    _progressTimer = null;
  }

  void _cancel() {
    _cancelToken?.cancel();
  }

  static bool _isCancelled(Object e) =>
      e is DioException && e.type == DioExceptionType.cancel;

  int? _parseSeed() {
    final seedText = _seedCtrl.text.trim();
    if (seedText.isEmpty) return null;
    final seed = int.tryParse(seedText);
    if (seed == null) {
      throw ApiException('随机种子须为非负整数');
    }
    return seed;
  }

  Future<void> _run() async {
    if (_busy) return;
    final token = CancelToken();
    _cancelToken = token;
    setState(() {
      _running = true;
      _error = null;
    });
    _startProgressTimer(false);
    try {
      final result = await ref.read(simulationRepositoryProvider).simulate(
            matchId: widget.matchId,
            simulations: _simulations,
            seed: _parseSeed(),
            cancelToken: token,
          );
      if (!mounted) return;
      setState(() => _result = result);
      ref.invalidate(simHistoryProvider(widget.matchId));
    } catch (e) {
      if (!mounted) return;
      // 用户主动取消：静默处理，不显示错误
      if (_isCancelled(e)) return;
      setState(() {
        _error = e is ApiException ? e.message : e.toString();
      });
    } finally {
      _stopProgressTimer();
      if (mounted) setState(() => _running = false);
      _cancelToken = null;
    }
  }

  Future<void> _runSensitivity() async {
    if (_busy) return;
    final token = CancelToken();
    _cancelToken = token;
    setState(() {
      _sensRunning = true;
      _error = null;
    });
    _startProgressTimer(true);
    try {
      final result = await ref.read(simulationRepositoryProvider).sensitivity(
            matchId: widget.matchId,
            simulations: AppConfig.defaultSensitivitySimulations,
            seed: _parseSeed(),
            cancelToken: token,
          );
      if (!mounted) return;
      setState(() => _sensitivity = result);
    } catch (e) {
      if (!mounted) return;
      // 用户主动取消：静默处理，不显示错误
      if (_isCancelled(e)) return;
      setState(() {
        _error = e is ApiException ? e.message : e.toString();
      });
    } finally {
      _stopProgressTimer();
      if (mounted) setState(() => _sensRunning = false);
      _cancelToken = null;
    }
  }

  @override
  Widget build(BuildContext context) {
    final auth = ref.watch(authProvider);
    final historyAsync = ref.watch(simHistoryProvider(widget.matchId));

    if (!widget.isUpcoming) {
      return const Card(
        child: Padding(
          padding: EdgeInsets.all(16),
          child: Text(
            '模拟推演仅适用于未赛场次',
            style: TextStyle(color: AppColors.textMuted),
          ),
        ),
      );
    }

    if (!auth.canSimulate) {
      return Card(
        child: Padding(
          padding: const EdgeInsets.all(16),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const Text(
                '只读模拟推演',
                style: TextStyle(fontSize: 16, fontWeight: FontWeight.w600),
              ),
              const SizedBox(height: 8),
              const Text(
                '当前账号无模拟权限（需要 simulation:view）。请联系管理员开通后使用。',
                style: TextStyle(color: AppColors.textMuted, height: 1.4),
              ),
            ],
          ),
        ),
      );
    }

    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Text(
              '只读模拟推演',
              style: TextStyle(fontSize: 16, fontWeight: FontWeight.w600),
            ),
            const SizedBox(height: 8),
            const Text(
              '结果仅写入模拟历史，不覆盖正式预测。仅供学习研究与数据分析，不构成任何投注建议。',
              style: TextStyle(color: AppColors.textMuted, fontSize: 12, height: 1.4),
            ),
            const SizedBox(height: 14),
            const Text('模拟次数', style: TextStyle(color: AppColors.textSecondary, fontSize: 13)),
            const SizedBox(height: 8),
            Wrap(
              spacing: 8,
              children: _simOptions.map((n) {
                final selected = _simulations == n;
                return ChoiceChip(
                  label: Text('$n'),
                  selected: selected,
                  onSelected: _busy
                      ? null
                      : (v) {
                          if (v) setState(() => _simulations = n);
                        },
                );
              }).toList(),
            ),
            // 次数与耗时提示：帮助用户理解大样本的代价（SIM-05）
            Padding(
              padding: const EdgeInsets.only(top: 6),
              child: Text(
                _simulations >= 10000
                    ? '当前 $_simulations 次：结果更稳定，但耗时明显增加（上限 ${AppConfig.maxAppSimulations}）'
                    : '可选 $_simulations 次，耗时较短；次数越多结果越稳定（上限 ${AppConfig.maxAppSimulations}）',
                style: const TextStyle(
                  color: AppColors.textMuted,
                  fontSize: 11,
                ),
              ),
            ),
            const SizedBox(height: 12),
            TextField(
              controller: _seedCtrl,
              enabled: !_busy,
              keyboardType: TextInputType.number,
              inputFormatters: [FilteringTextInputFormatter.digitsOnly],
              decoration: const InputDecoration(
                labelText: '随机种子（可选）',
                hintText: '留空则不固定',
              ),
            ),
            const SizedBox(height: 12),
            Row(
              children: [
                Expanded(
                  child: ElevatedButton(
                    onPressed: _busy ? null : _run,
                    child: Text(_running ? '模拟中…' : '开始模拟'),
                  ),
                ),
                const SizedBox(width: 8),
                Expanded(
                  child: OutlinedButton(
                    onPressed: _busy ? null : _runSensitivity,
                    child: Text(_sensRunning ? '扫描中…' : 'λ 敏感性'),
                  ),
                ),
              ],
            ),
            if (_busy) ...[
              const SizedBox(height: 12),
              const LinearProgressIndicator(),
              const SizedBox(height: 6),
              Text(
                _sensRunning
                    ? '${_sensStages[_progressStage]}（共约 14 个扫描点）'
                    : _simStages[_progressStage],
                style: const TextStyle(color: AppColors.textMuted, fontSize: 12),
              ),
              const SizedBox(height: 10),
              SizedBox(
                width: double.infinity,
                child: OutlinedButton(
                  onPressed: _cancel,
                  style: OutlinedButton.styleFrom(
                    foregroundColor: AppColors.red,
                    side: const BorderSide(color: AppColors.red),
                  ),
                  child: const Text('取消本次计算'),
                ),
              ),
            ],
            if (_error != null) ...[
              const SizedBox(height: 12),
              Text(_error!, style: const TextStyle(color: AppColors.red)),
            ],
            if (_result != null) ...[
              const SizedBox(height: 16),
              const Divider(),
              const SizedBox(height: 8),
              _ResultView(result: _result!),
              const SizedBox(height: 8),
              SimulationBetPanel(result: _result!),
            ],
            if (_sensitivity != null) ...[
              const SizedBox(height: 16),
              const Divider(),
              const SizedBox(height: 8),
              _SensitivityView(result: _sensitivity!),
            ],
            const SizedBox(height: 16),
            const Text(
              '本场模拟历史',
              style: TextStyle(fontWeight: FontWeight.w600),
            ),
            const SizedBox(height: 8),
            historyAsync.when(
              loading: () => const Padding(
                padding: EdgeInsets.symmetric(vertical: 8),
                child: Center(child: CircularProgressIndicator(strokeWidth: 2)),
              ),
              error: (e, _) => Text(
                e is ApiException ? e.message : e.toString(),
                style: const TextStyle(color: AppColors.textMuted, fontSize: 12),
              ),
              data: (items) {
                if (items.isEmpty) {
                  return const Text(
                    '暂无历史记录',
                    style: TextStyle(color: AppColors.textMuted, fontSize: 13),
                  );
                }
                return Column(
                  children: items
                      .map(
                        (h) => ListTile(
                          contentPadding: EdgeInsets.zero,
                          dense: true,
                          title: Text(
                            h.mainScore != null
                                ? '主线 ${h.mainScore}'
                                : (h.matchName ?? '模拟 #${h.id}'),
                            style: const TextStyle(fontSize: 14),
                          ),
                          subtitle: Text(
                            [
                              if (h.simulations != null) '${h.simulations} 次',
                              if (h.homeWinProb != null)
                                '主 ${_pct(h.homeWinProb)} / 平 ${_pct(h.drawProb)} / 客 ${_pct(h.awayWinProb)}',
                              if (h.createdAt != null) h.createdAt!,
                            ].join(' · '),
                            style: const TextStyle(
                              color: AppColors.textMuted,
                              fontSize: 12,
                            ),
                          ),
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

class _ResultView extends StatelessWidget {
  const _ResultView({required this.result});

  final SimulationResult result;

  @override
  Widget build(BuildContext context) {
    final sim = result.simulated;
    final base = result.baseline;
    final meta = result.meta;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          '模拟结果'
          '${meta.simulations != null ? ' · ${meta.simulations} 次' : ''}'
          '${meta.elapsedMs != null ? ' · ${meta.elapsedMs} ms' : ''}'
          '${meta.cacheHit ? ' · 缓存' : ''}',
          style: const TextStyle(fontWeight: FontWeight.w600),
        ),
        if (meta.warnings.isNotEmpty) ...[
          const SizedBox(height: 6),
          Text(
            meta.warnings.join('；'),
            style: const TextStyle(color: AppColors.orange, fontSize: 12),
          ),
        ],
        const SizedBox(height: 12),
        if (sim.hasProbs) ...[
          const Text('模拟胜平负', style: TextStyle(fontSize: 13, color: AppColors.textSecondary)),
          const SizedBox(height: 6),
          WdlStackBar(
            home: sim.homeWinProb ?? 0,
            draw: sim.drawProb ?? 0,
            away: sim.awayWinProb ?? 0,
          ),
          const SizedBox(height: 6),
          Text(
            '主 ${_pct(sim.homeWinProb)} · 平 ${_pct(sim.drawProb)} · 客 ${_pct(sim.awayWinProb)}',
            style: const TextStyle(color: AppColors.textSecondary, fontSize: 12),
          ),
        ],
        if (base.hasProbs) ...[
          const SizedBox(height: 12),
          const Text('基线对照', style: TextStyle(fontSize: 13, color: AppColors.textSecondary)),
          const SizedBox(height: 6),
          WdlStackBar(
            home: base.homeWinProb ?? 0,
            draw: base.drawProb ?? 0,
            away: base.awayWinProb ?? 0,
            height: 10,
          ),
          const SizedBox(height: 6),
          Text(
            '主 ${_pct(base.homeWinProb)} · 平 ${_pct(base.drawProb)} · 客 ${_pct(base.awayWinProb)}',
            style: const TextStyle(color: AppColors.textMuted, fontSize: 12),
          ),
        ],
        const SizedBox(height: 12),
        _kv('主线比分', sim.mainScore ?? '-'),
        _kv(
          'λ',
          '${_fmt(sim.lambdaHome)} / ${_fmt(sim.lambdaAway)}',
        ),
        if (sim.altScores.isNotEmpty) _kv('备选比分', sim.altScores.join('、')),
        if (sim.topScores.isNotEmpty)
          _kv('高频比分', sim.topScores.take(5).join('、')),
        if (sim.over25 != null || sim.btts != null) ...[
          _kv('大 2.5', _pct(sim.over25)),
          _kv('双方进球', _pct(sim.btts)),
          if (sim.totalGoalsAvg != null) _kv('总进球均值', _fmt(sim.totalGoalsAvg)),
        ],
        if (sim.weightSource != null && sim.weightSource!.isNotEmpty)
          _kv('权重来源', sim.weightSource!),
      ],
    );
  }

  Widget _kv(String k, String v) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 4),
      child: Row(
        children: [
          SizedBox(
            width: 80,
            child: Text(k, style: const TextStyle(color: AppColors.textMuted, fontSize: 13)),
          ),
          Expanded(child: Text(v, style: const TextStyle(fontSize: 13))),
        ],
      ),
    );
  }
}

class _SensitivityView extends StatelessWidget {
  const _SensitivityView({required this.result});

  final SensitivityResult result;

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          'λ 敏感性'
          '${result.simulations != null ? ' · ${result.simulations} 次/点' : ''}'
          '${result.range != null ? ' · ±${result.range}' : ''}'
          '${result.step != null ? ' 步长 ${result.step}' : ''}',
          style: const TextStyle(fontWeight: FontWeight.w600),
        ),
        const SizedBox(height: 4),
        Text(
          '${result.homeTeam ?? '主队'} vs ${result.awayTeam ?? '客队'}'
          ' · 基准 λ ${_fmt(result.lambdaHome.base)} / ${_fmt(result.lambdaAway.base)}',
          style: const TextStyle(color: AppColors.textMuted, fontSize: 12),
        ),
        const SizedBox(height: 4),
        const Text(
          '仅供研究模型对期望进球的敏感度，不构成投注建议。',
          style: TextStyle(color: AppColors.textMuted, fontSize: 11),
        ),
        const SizedBox(height: 12),
        _SensitivitySeriesBlock(
          title: '主队 λ 扫描',
          series: result.lambdaHome,
        ),
        const SizedBox(height: 12),
        _SensitivitySeriesBlock(
          title: '客队 λ 扫描',
          series: result.lambdaAway,
        ),
      ],
    );
  }
}

class _SensitivitySeriesBlock extends StatelessWidget {
  const _SensitivitySeriesBlock({
    required this.title,
    required this.series,
  });

  final String title;
  final SensitivitySeries series;

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          title,
          style: const TextStyle(
            fontSize: 13,
            color: AppColors.textSecondary,
            fontWeight: FontWeight.w600,
          ),
        ),
        const SizedBox(height: 6),
        if (series.points.length >= 2) ...[
          _SensitivityLineChart(series: series),
          const SizedBox(height: 8),
        ],
        ...series.points.map((p) {
          final isBase = p.delta.abs() < 1e-9;
          return Padding(
            padding: const EdgeInsets.only(bottom: 8),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  children: [
                    Text(
                      'Δ ${p.delta >= 0 ? '+' : ''}${p.delta.toStringAsFixed(1)}'
                      ' · λ ${_fmt(p.lambda)}'
                      '${isBase ? ' · 基准' : ''}',
                      style: TextStyle(
                        fontSize: 12,
                        color: isBase ? AppColors.gold : AppColors.textMuted,
                        fontWeight: isBase ? FontWeight.w600 : FontWeight.normal,
                      ),
                    ),
                    const Spacer(),
                    Text(
                      '主 ${_pct(p.homeWinProb)} / 平 ${_pct(p.drawProb)} / 客 ${_pct(p.awayWinProb)}',
                      style: const TextStyle(
                        fontSize: 11,
                        color: AppColors.textSecondary,
                      ),
                    ),
                  ],
                ),
                const SizedBox(height: 4),
                WdlStackBar(
                  home: p.homeWinProb ?? 0,
                  draw: p.drawProb ?? 0,
                  away: p.awayWinProb ?? 0,
                  height: 7,
                ),
              ],
            ),
          );
        }),
      ],
    );
  }
}

/// 简易折线图：展示 λ 扫描下胜平负概率变化趋势。
class _SensitivityLineChart extends StatelessWidget {
  const _SensitivityLineChart({required this.series});

  final SensitivitySeries series;

  @override
  Widget build(BuildContext context) {
    // 为图表补充语义摘要，读屏用户可获知趋势（A11Y-02）
    final pts = series.points;
    final base = pts
        .where((p) => p.delta.abs() < 1e-9)
        .toList();
    String summary = 'λ 敏感性折线图，共 ${pts.length} 个扫描点';
    if (base.isNotEmpty) {
      final p = base.first;
      summary =
          'λ 敏感性折线图，共 ${pts.length} 个扫描点；'
          '基准点主胜 ${_pct(p.homeWinProb)}、平局 ${_pct(p.drawProb)}、客胜 ${_pct(p.awayWinProb)}，'
          '下方文字列出各点数值';
    }
    return Semantics(
      label: summary,
      child: SizedBox(
        height: 120,
        child: CustomPaint(
          size: Size.infinite,
          painter: _LineChartPainter(series: series),
        ),
      ),
    );
  }
}

class _LineChartPainter extends CustomPainter {
  _LineChartPainter({required this.series});

  final SensitivitySeries series;

  @override
  void paint(Canvas canvas, Size size) {
    final pts = series.points;
    if (pts.length < 2) return;

    final w = size.width;
    final h = size.height;
    const padLeft = 28.0;
    const padRight = 8.0;
    const padTop = 8.0;
    const padBottom = 16.0;
    final chartW = w - padLeft - padRight;
    final chartH = h - padTop - padBottom;

    // X 范围：lambda 值
    final xMin = pts.map((p) => p.lambda).reduce((a, b) => a < b ? a : b);
    final xMax = pts.map((p) => p.lambda).reduce((a, b) => a > b ? a : b);
    final xRange = (xMax - xMin).abs() < 1e-9 ? 1.0 : xMax - xMin;

    double toX(double lambda) =>
        padLeft + (lambda - xMin) / xRange * chartW;
    double toY(double prob) =>
        padTop + (1 - prob) * chartH;

    // 背景网格
    final gridPaint = Paint()
      ..color = AppColors.bgCard
      ..strokeWidth = 0.5;
    for (var i = 0; i <= 4; i++) {
      final y = padTop + chartH * i / 4;
      canvas.drawLine(Offset(padLeft, y), Offset(w - padRight, y), gridPaint);
    }

    // Y 轴标签
    final labelStyle = TextStyle(color: AppColors.textMuted, fontSize: 9);
    for (var i = 0; i <= 4; i++) {
      final prob = 1 - i / 4.0;
      final y = padTop + chartH * i / 4;
      final tp = TextPainter(
        text: TextSpan(text: '${(prob * 100).round()}', style: labelStyle),
        textDirection: TextDirection.ltr,
      )..layout();
      tp.paint(canvas, Offset(2, y - tp.height / 2));
    }

    // X 轴标签（首尾）
    final xLabelStyle = TextStyle(color: AppColors.textMuted, fontSize: 9);
    for (final lambda in [xMin, xMax]) {
      final tp = TextPainter(
        text: TextSpan(
            text: lambda.toStringAsFixed(1), style: xLabelStyle),
        textDirection: TextDirection.ltr,
      )..layout();
      tp.paint(canvas, Offset(toX(lambda) - tp.width / 2, h - padBottom + 2));
    }

    // 三条折线
    final lines = <(List<double?>, Color)>[
      (pts.map((p) => p.homeWinProb).toList(), AppColors.gold),
      (pts.map((p) => p.drawProb).toList(), AppColors.textMuted),
      (pts.map((p) => p.awayWinProb).toList(), const Color(0xFF4FC3F7)),
    ];

    for (final (probs, color) in lines) {
      final path = Path();
      var first = true;
      for (var i = 0; i < pts.length; i++) {
        final prob = probs[i];
        if (prob == null) continue;
        final x = toX(pts[i].lambda);
        final y = toY(prob);
        if (first) {
          path.moveTo(x, y);
          first = false;
        } else {
          path.lineTo(x, y);
        }
      }
      canvas.drawPath(
        path,
        Paint()
          ..color = color
          ..style = PaintingStyle.stroke
          ..strokeWidth = 1.5,
      );
    }

    // 基准竖线
    final baseX = toX(series.base);
    final basePaint = Paint()
      ..color = AppColors.gold.withValues(alpha: 0.3)
      ..strokeWidth = 0.8;
    canvas.drawLine(
      Offset(baseX, padTop),
      Offset(baseX, padTop + chartH),
      basePaint,
    );
  }

  @override
  bool shouldRepaint(covariant _LineChartPainter oldDelegate) =>
      oldDelegate.series != series;
}

String _pct(double? v) {
  if (v == null) return '-';
  return '${(v * 100).toStringAsFixed(1)}%';
}

String _fmt(double? v) {
  if (v == null) return '-';
  return v.toStringAsFixed(2);
}
