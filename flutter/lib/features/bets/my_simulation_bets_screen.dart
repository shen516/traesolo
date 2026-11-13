import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/providers.dart';
import '../../core/theme.dart';
import '../../data/models/simulation.dart';
import '../auth/auth_state.dart';

/// 我的模拟投注单列表（含统计卡、分组、筛选、作废）。
class MySimulationBetsScreen extends ConsumerStatefulWidget {
  const MySimulationBetsScreen({super.key});

  @override
  ConsumerState<MySimulationBetsScreen> createState() =>
      _MySimulationBetsScreenState();
}

class _MySimulationBetsScreenState
    extends ConsumerState<MySimulationBetsScreen> {
  String? _status;
  String? _playType;
  int _page = 1;
  final List<SimulationBet> _bets = [];
  bool _loading = false;
  bool _hasMore = true;
  String? _error;
  SimulationBetStats? _stats;

  @override
  void initState() {
    super.initState();
    _load(reset: true);
  }

  Future<void> _load({bool reset = false}) async {
    if (_loading) return;
    if (reset) {
      _page = 1;
      _bets.clear();
      _hasMore = true;
    }
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final repo = ref.read(simulationRepositoryProvider);
      final pageData = await repo.listBets(
        page: _page,
        pageSize: 20,
        status: _status,
        playType: _playType,
      );
      if (reset) {
        _bets.clear();
      }
      _bets.addAll(pageData.items);
      _hasMore = pageData.hasMore;
      final stats = await repo.betStats();
      if (mounted) setState(() => _stats = stats);
    } catch (e) {
      if (mounted) setState(() => _error = '$e');
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _voidBet(int betId) async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (c) => AlertDialog(
        title: const Text('作废投注单'),
        content: const Text('作废后该单整组不可恢复，且仅开赛前可作废。确认作废？'),
        actions: [
          TextButton(
              onPressed: () => Navigator.pop(c, false),
              child: const Text('取消')),
          FilledButton(
              onPressed: () => Navigator.pop(c, true),
              child: const Text('确认作废')),
        ],
      ),
    );
    if (confirmed != true) return;
    try {
      await ref.read(simulationRepositoryProvider).voidBet(betId);
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('已作废')),
        );
        await _load(reset: true);
      }
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('作废失败：$e')),
        );
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final auth = ref.watch(authProvider);
    return Scaffold(
      appBar: AppBar(title: const Text('我的模拟投注')),
      body: RefreshIndicator(
        onRefresh: () => _load(reset: true),
        child: ListView(
          physics: const AlwaysScrollableScrollPhysics(),
          padding: const EdgeInsets.all(12),
          children: [
            if (_stats != null) _StatsCard(stats: _stats!),
            const SizedBox(height: 12),
            _buildFilters(),
            const SizedBox(height: 8),
            if (_error != null)
              _ErrorPane(error: _error!, onRetry: () => _load(reset: true)),
            if (_bets.isEmpty && !_loading && _error == null)
              _EmptyPane(onGo: () => context.go('/matches')),
            ...[
              for (final group in _groupBets(_bets))
                _BetGroup(group: group, onVoid: _voidBet),
            ],
            if (_loading) const Padding(
              padding: EdgeInsets.all(16),
              child: Center(child: CircularProgressIndicator()),
            ),
            if (!_hasMore && _bets.isNotEmpty)
              const Padding(
                padding: EdgeInsets.all(12),
                child: Center(
                  child: Text('没有更多了',
                      style: TextStyle(color: AppColors.textMuted)),
                ),
              ),
          ],
        ),
      ),
      floatingActionButton: auth.canManageModel && _bets.isNotEmpty
          ? FloatingActionButton.extended(
              onPressed: () => _load(reset: true),
              icon: const Icon(Icons.refresh),
              label: const Text('刷新'),
            )
          : null,
    );
  }

  Widget _buildFilters() {
    return Row(
      children: [
        Expanded(
          child: DropdownButtonFormField<String?>(
            initialValue: _status,
            decoration: const InputDecoration(
              labelText: '状态',
              isDense: true,
            ),
            items: const [
              DropdownMenuItem(value: null, child: Text('全部')),
              DropdownMenuItem(value: 'pending', child: Text('待开赛')),
              DropdownMenuItem(value: 'won', child: Text('已中')),
              DropdownMenuItem(value: 'lost', child: Text('未中')),
              DropdownMenuItem(value: 'void', child: Text('作废')),
            ],
            onChanged: (v) {
              setState(() => _status = v);
              _load(reset: true);
            },
          ),
        ),
        const SizedBox(width: 8),
        Expanded(
          child: DropdownButtonFormField<String?>(
            initialValue: _playType,
            decoration: const InputDecoration(labelText: '玩法', isDense: true),
            items: const [
              DropdownMenuItem(value: null, child: Text('全部')),
              DropdownMenuItem(value: 'spf', child: Text('胜平负')),
              DropdownMenuItem(value: 'nspf', child: Text('让球')),
              DropdownMenuItem(value: 'hspf', child: Text('半场')),
              DropdownMenuItem(value: 'bf', child: Text('比分')),
              DropdownMenuItem(value: 'tg', child: Text('总进球')),
            ],
            onChanged: (v) {
              setState(() => _playType = v);
              _load(reset: true);
            },
          ),
        ),
      ],
    );
  }

  /// 按 combination_id 分组（串关组多行）。
  List<List<SimulationBet>> _groupBets(List<SimulationBet> bets) {
    final groups = <String, List<SimulationBet>>{};
    final singles = <List<SimulationBet>>[];
    for (final b in bets) {
      final cid = b.combinationId;
      if (cid != null && cid.isNotEmpty) {
        groups.putIfAbsent(cid, () => []).add(b);
      } else {
        singles.add([b]);
      }
    }
    final ordered = <List<SimulationBet>>[];
    ordered.addAll(singles);
    ordered.addAll(groups.values);
    return ordered;
  }
}

class _StatsCard extends StatelessWidget {
  const _StatsCard({required this.stats});

  final SimulationBetStats stats;

  @override
  Widget build(BuildContext context) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Text('累计模拟盈亏',
                style: TextStyle(
                    fontWeight: FontWeight.w600,
                    color: AppColors.textPrimary)),
            const SizedBox(height: 8),
            Row(
              children: [
                _StatItem(label: '投注额', value: stats.totalStake),
                _StatItem(label: '派奖', value: stats.totalPayout),
                _StatItem(
                  label: '盈亏',
                  value: stats.profit,
                  color: stats.profit >= 0 ? AppColors.green : AppColors.red,
                ),
                _StatItem(
                  label: '命中率',
                  value: (stats.hitRate ?? 0) * 100,
                  suffix: '%',
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }
}

class _StatItem extends StatelessWidget {
  const _StatItem(
      {required this.label, required this.value, this.suffix = '元', this.color});

  final String label;
  final double value;
  final String suffix;
  final Color? color;

  @override
  Widget build(BuildContext context) {
    return Expanded(
      child: Column(
        children: [
          Text(value.toStringAsFixed(suffix == '%' ? 1 : 2),
              style: TextStyle(
                  fontWeight: FontWeight.w700,
                  fontSize: 16,
                  color: color ?? AppColors.textPrimary)),
          const SizedBox(height: 2),
          Text(label,
              style: const TextStyle(color: AppColors.textMuted, fontSize: 12)),
        ],
      ),
    );
  }
}

class _BetGroup extends StatelessWidget {
  const _BetGroup({required this.group, required this.onVoid});

  final List<SimulationBet> group;
  final ValueChanged<int> onVoid;

  bool get isParlay => group.length > 1;

  String get _groupStatus {
    final st = group.map((e) => e.status).toSet();
    if (st.length == 1) return group.first.status;
    return st.contains('pending') ? 'pending' : 'lost';
  }

  double get _groupStake {
    final first = group.first;
    return (first.stake ?? 2.0) * first.multiple;
  }

  double get _groupPayout {
    return group.first.payout;
  }

  @override
  Widget build(BuildContext context) {
    final first = group.first;
    final status = _groupStatus;
    final statusColor = status == 'won'
        ? AppColors.green
        : status == 'lost'
            ? AppColors.red
            : status == 'void'
                ? AppColors.textMuted
                : AppColors.orange;
    final statusText = status == 'won'
        ? '已中'
        : status == 'lost'
            ? '未中'
            : status == 'void'
                ? '作废'
                : '待开赛';

    return Card(
      margin: const EdgeInsets.only(bottom: 8),
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                if (isParlay)
                  Container(
                    padding: const EdgeInsets.symmetric(
                        horizontal: 6, vertical: 2),
                    decoration: BoxDecoration(
                      color: AppColors.gold.withValues(alpha: 0.15),
                      borderRadius: BorderRadius.circular(4),
                    ),
                    child: Text('${group.length}串1',
                        style: const TextStyle(
                            color: AppColors.gold, fontSize: 11)),
                  ),
                const SizedBox(width: 8),
                Text(first.matchName ?? '',
                    style: const TextStyle(
                        fontWeight: FontWeight.w600,
                        color: AppColors.textPrimary)),
                const Spacer(),
                Container(
                  padding:
                      const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
                  decoration: BoxDecoration(
                    color: statusColor.withValues(alpha: 0.15),
                    borderRadius: BorderRadius.circular(4),
                  ),
                  child: Text(statusText,
                      style: TextStyle(color: statusColor, fontSize: 11)),
                ),
              ],
            ),
            const SizedBox(height: 8),
            for (final b in group)
              Padding(
                padding: const EdgeInsets.symmetric(vertical: 2),
                child: Row(
                  children: [
                    Text(_playLabel(b.playType),
                        style: const TextStyle(
                            color: AppColors.textMuted, fontSize: 12)),
                    const SizedBox(width: 6),
                    Expanded(
                      child: Text(
                        '${b.matchName ?? ''} · ${_selectionLabel(b)}',
                        style: const TextStyle(
                            color: AppColors.textSecondary, fontSize: 13),
                        overflow: TextOverflow.ellipsis,
                      ),
                    ),
                    Text('@${b.spAtCreate?.toStringAsFixed(2) ?? '-'}',
                        style: const TextStyle(
                            color: AppColors.gold, fontSize: 12)),
                  ],
                ),
              ),
            const Divider(height: 16),
            Row(
              children: [
                Text('金额 ${_groupStake.toStringAsFixed(2)}元',
                    style: const TextStyle(
                        color: AppColors.textMuted, fontSize: 12)),
                const Spacer(),
                Text('派奖 ${_groupPayout.toStringAsFixed(2)}元',
                    style: const TextStyle(
                        color: AppColors.gold, fontSize: 13)),
                if (first.isPending && first.id > 0) ...[
                  const SizedBox(width: 8),
                  TextButton(
                    onPressed: () => onVoid(first.id),
                    child: const Text('作废',
                        style: TextStyle(
                            color: AppColors.red, fontSize: 12)),
                  ),
                ],
              ],
            ),
          ],
        ),
      ),
    );
  }

  String _playLabel(String playType) {
    switch (playType) {
      case 'spf':
        return '胜平负';
      case 'nspf':
        return '让球';
      case 'hspf':
        return '半场';
      case 'bf':
        return '比分';
      case 'tg':
        return '总进球';
      default:
        return playType;
    }
  }

  String _selectionLabel(SimulationBet b) {
    if (b.playType == 'bf') return b.selection;
    if (b.playType == 'tg') {
      return '${b.selection}球';
    }
    switch (b.selection) {
      case 'win':
        return '主胜';
      case 'draw':
        return '平';
      case 'lose':
        return '客胜';
      default:
        return b.selection;
    }
  }
}

class _ErrorPane extends StatelessWidget {
  const _ErrorPane({required this.error, required this.onRetry});

  final String error;
  final VoidCallback onRetry;

  @override
  Widget build(BuildContext context) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          children: [
            Text(error,
                style: const TextStyle(color: AppColors.red), maxLines: 3),
            const SizedBox(height: 8),
            OutlinedButton(onPressed: onRetry, child: const Text('重试')),
          ],
        ),
      ),
    );
  }
}

class _EmptyPane extends StatelessWidget {
  const _EmptyPane({required this.onGo});

  final VoidCallback onGo;

  @override
  Widget build(BuildContext context) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(24),
        child: Column(
          children: [
            const Icon(Icons.receipt_long, color: AppColors.textMuted, size: 40),
            const SizedBox(height: 8),
            const Text('暂无模拟投注',
                style: TextStyle(color: AppColors.textSecondary)),
            const SizedBox(height: 12),
            FilledButton(onPressed: onGo, child: const Text('去模拟预测')),
          ],
        ),
      ),
    );
  }
}
