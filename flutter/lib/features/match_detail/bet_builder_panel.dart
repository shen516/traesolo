import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/theme.dart';
import '../../data/api/simulation_api.dart';
import '../../data/models/simulation.dart';
import '../../data/repositories/simulation_repository.dart';
import '../../core/providers.dart';
import '../auth/auth_state.dart';

/// 串关篮中的一条腿。
class ParlayCartLeg {
  const ParlayCartLeg({
    required this.matchId,
    required this.matchName,
    required this.playType,
    required this.selection,
    required this.selectionLabel,
    required this.sp,
    required this.spSource,
    this.multiple = 1,
  });

  final String matchId;
  final String matchName;
  final String playType;
  final String selection;
  final String selectionLabel;
  final double sp;
  final String spSource;
  final int multiple;

  /// 同场次同玩法同选项视为同一条腿。
  String get key => '$matchId|$playType|$selection';

  @override
  bool operator ==(Object other) =>
      other is ParlayCartLeg && other.key == key;

  @override
  int get hashCode => key.hashCode;
}

class ParlayCart extends Notifier<List<ParlayCartLeg>> {
  @override
  List<ParlayCartLeg> build() => const [];

  void add(ParlayCartLeg leg) {
    if (state.any((e) => e.key == leg.key)) return;
    if (state.length >= 8) return;
    state = [...state, leg];
  }

  void remove(String key) {
    state = state.where((e) => e.key != key).toList();
  }

  void clear() => state = const [];
}

final parlayCartProvider =
    NotifierProvider<ParlayCart, List<ParlayCartLeg>>(ParlayCart.new);

/// 玩法选项的展示元数据。
class _PlayMeta {
  const _PlayMeta(this.label, this.playType, this.options);

  final String label;
  final String playType;
  final List<({String key, String text})> options;
}

const _spfOptions = [
  (key: 'win', text: '主胜'),
  (key: 'draw', text: '平'),
  (key: 'lose', text: '客胜'),
];

const _hspfOptions = [
  (key: 'win', text: '主胜'),
  (key: 'draw', text: '平'),
  (key: 'lose', text: '客胜'),
];

const _tgOptions = [
  (key: '0', text: '0球'),
  (key: '1', text: '1球'),
  (key: '2', text: '2球'),
  (key: '3', text: '3球'),
  (key: '4', text: '4球'),
  (key: '5', text: '5球'),
  (key: '6', text: '6球'),
  (key: '7+', text: '7+球'),
];

/// 模拟结果页的投注落单区：玩法选项选择 + 加入单关 / 加入串关篮。
class SimulationBetPanel extends ConsumerStatefulWidget {
  const SimulationBetPanel({
    super.key,
    required this.result,
  });

  final SimulationResult result;

  @override
  ConsumerState<SimulationBetPanel> createState() =>
      _SimulationBetPanelState();
}

class _SimulationBetPanelState extends ConsumerState<SimulationBetPanel> {
  String? _selectedPlayType;
  String? _selectedSelection;
  int _multiple = 1;
  bool _submitting = false;
  String? _toast;

  SimulationPrize get _prize => widget.result.prize;

  List<_PlayMeta> get _playMetas {
    final metas = <_PlayMeta>[];
    final p = _prize;
    if (p.spf.hasAny) metas.add(_PlayMeta('胜平负', 'spf', _spfOptions));
    if (p.nspf.hasAny) metas.add(_PlayMeta('让球胜平负', 'nspf', _spfOptions));
    if (p.hspf.hasAny) metas.add(_PlayMeta('半场胜平负', 'hspf', _hspfOptions));
    if (p.bf.hasAny) metas.add(_PlayMeta('比分', 'bf', _bfOptions(p.bf)));
    if (p.tg.hasAny) metas.add(_PlayMeta('总进球', 'tg', _tgOptions));
    return metas;
  }

  List<({String key, String text})> _bfOptions(PrizeOptionBlock bf) {
    // 取前 12 个高频比分 + 三个其它
    final keys = bf.sp.keys.toList();
    final main = keys
        .where((k) => !k.endsWith('_other'))
        .take(12)
        .map((k) => (key: k, text: k))
        .toList();
    final others = keys
        .where((k) => k.endsWith('_other'))
        .map((k) => (key: k, text: _otherLabel(k)))
        .toList();
    return [...main, ...others];
  }

  String _otherLabel(String key) {
    switch (key) {
      case 'win_other':
        return '胜其它';
      case 'draw_other':
        return '平其它';
      case 'lose_other':
        return '负其它';
      default:
        return key;
    }
  }

  String _selectionText(String playType, String selection) {
    if (playType == 'bf') return selection;
    if (playType == 'tg') {
      return _tgOptions.firstWhere((e) => e.key == selection,
          orElse: () => (key: selection, text: selection)).text;
    }
    return _spfOptions
        .firstWhere((e) => e.key == selection,
            orElse: () => (key: selection, text: selection))
        .text;
  }

  double? _spFor(String playType, String selection) {
    return _prize.blockOf(playType).sp[selection];
  }

  String _sourceFor(String playType) {
    final s = _prize.spSource[playType];
    return s == null || s.isEmpty ? 'synthetic' : s;
  }

  bool get _canCreate {
    if (_selectedPlayType == null || _selectedSelection == null) return false;
    final sp = _spFor(_selectedPlayType!, _selectedSelection!);
    return sp != null && sp >= 1.01;
  }

  void _select(String playType, String selection) {
    if (_selectedPlayType == playType && _selectedSelection == selection) {
      setState(() {
        _selectedPlayType = null;
        _selectedSelection = null;
      });
      return;
    }
    setState(() {
      _selectedPlayType = playType;
      _selectedSelection = selection;
    });
  }

  Future<void> _addSingle() async {
    if (!_canCreate) return;
    final auth = ref.read(authProvider);
    if (!auth.canManageModel) {
      _showToast('无 model:manage 权限，无法创建模拟投注单');
      return;
    }
    setState(() => _submitting = true);
    try {
      final repo = ref.read(simulationRepositoryProvider);
      await repo.createBet(
        matchId: widget.result.matchId,
        playType: _selectedPlayType!,
        selection: _selectedSelection!,
        sp: _spFor(_selectedPlayType!, _selectedSelection!)!,
        spSource: _sourceFor(_selectedPlayType!),
        multiple: _multiple,
      );
      // 落单成功轻触反馈（A11Y-04）
      await HapticFeedback.lightImpact();
      if (!mounted) return;
      setState(() {
        _selectedPlayType = null;
        _selectedSelection = null;
        _multiple = 1;
      });
      _showToast('已加入模拟投注单（单关）');
    } catch (e) {
      _showToast('创建失败：$e');
    } finally {
      if (mounted) setState(() => _submitting = false);
    }
  }

  Future<void> _addParlay() async {
    if (!_canCreate) return;
    final auth = ref.read(authProvider);
    if (!auth.canManageModel) {
      _showToast('无 model:manage 权限，无法加入串关');
      return;
    }
    final sp = _spFor(_selectedPlayType!, _selectedSelection!);
    if (sp == null || sp < 1.01) return;
    final cart = ref.read(parlayCartProvider.notifier);
    final currentCart = ref.read(parlayCartProvider);
    if (currentCart.length >= 8) {
      _showToast('串关最多 8 关，已达上限');
      return;
    }
    cart.add(ParlayCartLeg(
      matchId: widget.result.matchId,
      matchName: widget.result.matchName,
      playType: _selectedPlayType!,
      selection: _selectedSelection!,
      selectionLabel: _selectionText(_selectedPlayType!, _selectedSelection!),
      sp: sp,
      spSource: _sourceFor(_selectedPlayType!),
      multiple: _multiple,
    ));
    // 加入串关篮轻触反馈（A11Y-04）
    await HapticFeedback.selectionClick();
    setState(() {
      _selectedPlayType = null;
      _selectedSelection = null;
    });
    _showToast('已加入串关篮（${ref.read(parlayCartProvider).length}/8）');
  }

  void _showToast(String msg) {
    if (!mounted) return;
    setState(() => _toast = msg);
    Future.delayed(const Duration(seconds: 2), () {
      if (mounted) setState(() => _toast = null);
    });
  }

  @override
  Widget build(BuildContext context) {
    final metas = _playMetas;
    if (metas.isEmpty) return const SizedBox.shrink();
    final auth = ref.watch(authProvider);
    final canCreate = auth.canManageModel;
    final inCart = ref.watch(parlayCartProvider).any((e) =>
        e.matchId == widget.result.matchId &&
        e.playType == _selectedPlayType &&
        e.selection == _selectedSelection);

    return Card(
      margin: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                const Icon(Icons.receipt_long,
                    color: AppColors.gold, size: 18),
                const SizedBox(width: 6),
                Text('模拟投注落单',
                    style: Theme.of(context)
                        .textTheme
                        .titleSmall
                        ?.copyWith(color: AppColors.textPrimary)),
                const Spacer(),
                if (!canCreate)
                  const Text('仅管理员可创建',
                      style: TextStyle(color: AppColors.textMuted, fontSize: 12)),
              ],
            ),
            const SizedBox(height: 8),
            for (final meta in metas) ...[
              _buildPlaySection(meta, canCreate),
              const SizedBox(height: 10),
            ],
            const SizedBox(height: 4),
            Row(
              children: [
                _MultipleStepper(
                  value: _multiple,
                  onChanged: (v) => setState(() => _multiple = v),
                ),
                const Spacer(),
                const SizedBox(width: 8),
                OutlinedButton.icon(
                  onPressed: canCreate && !_submitting ? _addParlay : null,
                  icon: const Icon(Icons.playlist_add, size: 16),
                  label: Text(inCart ? '已在串关篮' : '加串关篮'),
                ),
                const SizedBox(width: 8),
                FilledButton.icon(
                  onPressed: canCreate && !_submitting ? _addSingle : null,
                  icon: const Icon(Icons.add_shopping_cart, size: 16),
                  label: const Text('加单关'),
                ),
              ],
            ),
            if (_toast != null) ...[
              const SizedBox(height: 8),
              Text(_toast!,
                  style: const TextStyle(color: AppColors.orange, fontSize: 12)),
            ],
          ],
        ),
      ),
    );
  }

  Widget _buildPlaySection(_PlayMeta meta, bool canCreate) {
    final block = _prize.blockOf(meta.playType);
    final source = _sourceFor(meta.playType);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          children: [
            Text(meta.label,
                style: const TextStyle(
                    color: AppColors.textSecondary,
                    fontSize: 13,
                    fontWeight: FontWeight.w600)),
            const SizedBox(width: 6),
            _SourceTag(source: source),
          ],
        ),
        const SizedBox(height: 6),
        Wrap(
          spacing: 6,
          runSpacing: 6,
          children: meta.options.map((o) {
            final sp = block.sp[o.key];
            final prob = block.probs[o.key];
            final selected = _selectedPlayType == meta.playType &&
                _selectedSelection == o.key;
            return Semantics(
              button: true,
              selected: selected,
              label: '${meta.label} ${o.text}'
                  '${sp != null ? '，赔率 ${sp.toStringAsFixed(2)}' : ''}'
                  '${prob != null ? '，模拟概率 ${(prob * 100).toStringAsFixed(1)}%' : ''}',
              child: InkWell(
              onTap: () => _select(meta.playType, o.key),
              borderRadius: BorderRadius.circular(6),
              child: Container(
                padding:
                    const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
                decoration: BoxDecoration(
                  color: selected ? AppColors.blue : AppColors.bgCard,
                  borderRadius: BorderRadius.circular(6),
                  border: Border.all(
                    color: selected ? AppColors.blue : AppColors.border,
                  ),
                ),
                child: Column(
                  children: [
                    Text(o.text,
                        style: TextStyle(
                            color: selected
                                ? AppColors.bgPrimary
                                : AppColors.textPrimary,
                            fontSize: 13,
                            fontWeight: FontWeight.w600)),
                    if (sp != null)
                      Text(sp.toStringAsFixed(2),
                          style: TextStyle(
                              color: selected
                                  ? AppColors.bgPrimary
                                  : AppColors.gold,
                              fontSize: 12)),
                    if (prob != null)
                      Text('${(prob * 100).toStringAsFixed(1)}%',
                          style: TextStyle(
                              color: selected
                                  ? AppColors.bgPrimary
                                  : AppColors.textMuted,
                              fontSize: 11)),
                  ],
                ),
              ),
              ),
            );
          }).toList(),
        ),
      ],
    );
  }
}

class _SourceTag extends StatelessWidget {
  const _SourceTag({required this.source});

  final String source;

  @override
  Widget build(BuildContext context) {
    final color = source == 'snapshot'
        ? AppColors.green
        : source == 'real'
            ? AppColors.blue
            : source == 'manual'
                ? AppColors.gold
                : AppColors.orange;
    final text = source == 'snapshot'
        ? '快照'
        : source == 'real'
            ? '真实SP'
            : source == 'manual'
                ? '手动'
                : '合成';
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.15),
        borderRadius: BorderRadius.circular(4),
      ),
      child: Text(text,
          style: TextStyle(color: color, fontSize: 11)),
    );
  }
}

class _MultipleStepper extends StatelessWidget {
  const _MultipleStepper({required this.value, required this.onChanged});

  final int value;
  final ValueChanged<int> onChanged;

  @override
  Widget build(BuildContext context) {
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        IconButton(
          tooltip: '减少倍数',
          icon: const Icon(Icons.remove_circle_outline, size: 20),
          color: AppColors.textMuted,
          onPressed: value > 1 ? () => onChanged(value - 1) : null,
        ),
        Text('$value倍',
            style: const TextStyle(color: AppColors.textPrimary)),
        IconButton(
          tooltip: '增加倍数',
          icon: const Icon(Icons.add_circle_outline, size: 20),
          color: AppColors.textMuted,
          onPressed: value < 999 ? () => onChanged(value + 1) : null,
        ),
      ],
    );
  }
}

/// 底部串关篮浮动条（挂载于赛事详情页）。
class ParlayCartBar extends ConsumerStatefulWidget {
  const ParlayCartBar({
    super.key,
    required this.repository,
    this.currentMatchId,
  });

  final SimulationRepository repository;

  /// 当前所在详情页的赛事 ID，用于区分串关篮中的跨场腿（DETAIL-03）。
  final String? currentMatchId;

  @override
  ConsumerState<ParlayCartBar> createState() => _ParlayCartBarState();
}

class _ParlayCartBarState extends ConsumerState<ParlayCartBar> {
  int _parlayMultiple = 1;

  @override
  Widget build(BuildContext context) {
    final cart = ref.watch(parlayCartProvider);
    if (cart.isEmpty) return const SizedBox.shrink();

    double totalSp = cart.fold(1.0, (acc, e) => acc * e.sp);
    final payout = totalSp * 2 * _parlayMultiple;
    final currentId = widget.currentMatchId;

    return Material(
      elevation: 8,
      color: AppColors.bgSecondary,
      child: SafeArea(
        top: false,
        child: Padding(
          padding: const EdgeInsets.all(12),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Row(
                children: [
                  const Icon(Icons.layers, color: AppColors.gold, size: 18),
                  const SizedBox(width: 6),
                  Text('串关篮 ${cart.length}关',
                      style: const TextStyle(color: AppColors.textPrimary)),
                  const Spacer(),
                  TextButton(
                    onPressed: () =>
                        ref.read(parlayCartProvider.notifier).clear(),
                    child: const Text('清空',
                        style: TextStyle(color: AppColors.textMuted)),
                  ),
                ],
              ),
              // 说明串关篮是跨赛事购物篮，避免用户误以为只属于当前场次（DETAIL-03）
              const Align(
                alignment: Alignment.centerLeft,
                child: Text(
                  '跨赛事串关篮：可从其他场次继续添加投注项',
                  style: TextStyle(color: AppColors.textMuted, fontSize: 11),
                ),
              ),
              const SizedBox(height: 4),
              for (final leg in cart)
                Row(
                  children: [
                    // 非当前场次的投注项标记为「他场」，降低误认（DETAIL-03）
                    if (currentId != null && leg.matchId != currentId)
                      Container(
                        margin: const EdgeInsets.only(right: 6),
                        padding: const EdgeInsets.symmetric(
                          horizontal: 4,
                          vertical: 1,
                        ),
                        decoration: BoxDecoration(
                          color: AppColors.textMuted.withValues(alpha: 0.15),
                          borderRadius: BorderRadius.circular(3),
                        ),
                        child: const Text(
                          '他场',
                          style: TextStyle(
                            color: AppColors.textMuted,
                            fontSize: 10,
                          ),
                        ),
                      ),
                    Expanded(
                      child: Text(
                        '${leg.matchName}  ${leg.selectionLabel}  @${leg.sp.toStringAsFixed(2)}',
                        style: const TextStyle(
                            color: AppColors.textSecondary, fontSize: 12),
                        overflow: TextOverflow.ellipsis,
                      ),
                    ),
                    IconButton(
                      tooltip: '移除该投注项',
                      icon: const Icon(Icons.close, size: 16),
                      color: AppColors.textMuted,
                      onPressed: () => ref
                          .read(parlayCartProvider.notifier)
                          .remove(leg.key),
                    ),
                  ],
                ),
              const SizedBox(height: 4),
              Row(
                children: [
                  Text('预计 ${cart.length}串1',
                      style: const TextStyle(
                          color: AppColors.textMuted, fontSize: 12)),
                  const Spacer(),
                  _MultipleStepper(
                    value: _parlayMultiple,
                    onChanged: (v) => setState(() => _parlayMultiple = v),
                  ),
                ],
              ),
              const SizedBox(height: 4),
              Row(
                children: [
                  const Spacer(),
                  Text('参考奖金 ${payout.toStringAsFixed(2)}元',
                      style: const TextStyle(
                          color: AppColors.gold, fontSize: 13)),
                ],
              ),
              const SizedBox(height: 8),
              SizedBox(
                width: double.infinity,
                child: FilledButton(
                  onPressed: cart.length >= 2 ? () => _submit(context) : null,
                  child: Text(cart.length < 2
                      ? '至少 2 关才可提交'
                      : '提交 ${cart.length}串1 模拟投注单'),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }

  Future<void> _submit(BuildContext context) async {
    final cart = ref.read(parlayCartProvider);
    final auth = ref.read(authProvider);
    if (!auth.canManageModel) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('无 model:manage 权限，无法提交串关')),
      );
      return;
    }
    final repo = ref.read(simulationRepositoryProvider);
    try {
      await repo.createParlay(
        legs: cart
            .map((e) => CreateParlayLeg(
                  matchId: e.matchId,
                  playType: e.playType,
                  selection: e.selection,
                  sp: e.sp,
                  spSource: e.spSource,
                ))
            .toList(),
        multiple: _parlayMultiple,
      );
      ref.read(parlayCartProvider.notifier).clear();
      setState(() => _parlayMultiple = 1);
      if (context.mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('串关模拟投注单已创建')),
        );
      }
    } catch (e) {
      if (context.mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('提交失败：$e')),
        );
      }
    }
  }
}
