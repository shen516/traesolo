import 'package:flutter/material.dart';

import '../core/theme.dart';
import '../data/models/league.dart';

/// 联赛选择字段：点击弹出底部抽屉，支持按名称搜索（DATA-02 / MATCH-04）。
class LeaguePickerField extends StatelessWidget {
  const LeaguePickerField({
    super.key,
    required this.leagues,
    required this.onChanged,
    this.value,
    this.labelText = '联赛',
    this.allowAll = false,
    this.allLabel = '全部联赛',
  });

  final List<LeagueItem> leagues;
  final ValueChanged<String?> onChanged;
  final String? value;
  final String labelText;

  /// 为 true 时抽屉顶部提供「全部联赛」选项，返回 null 表示清空筛选。
  final bool allowAll;
  final String allLabel;

  String get _currentName {
    final v = value;
    if (v == null || v.isEmpty) {
      return allowAll ? allLabel : '请选择';
    }
    for (final l in leagues) {
      if (l.id == v) return l.name;
    }
    return allowAll ? allLabel : '请选择';
  }

  Future<void> _openPicker(BuildContext context) async {
    final selected = await showModalBottomSheet<String>(
      context: context,
      isScrollControlled: true,
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(16)),
      ),
      builder: (ctx) => _LeaguePickerSheet(
        leagues: leagues,
        current: value,
        allowAll: allowAll,
        allLabel: allLabel,
      ),
    );
    // 抽屉返回 null 表示直接关闭不做变更；空字符串表示「全部联赛」即清空。
    if (selected != null) {
      onChanged(selected.isEmpty ? null : selected);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Semantics(
      button: true,
      label: '$labelText，当前 $_currentName，点按打开选择列表',
      child: InkWell(
        borderRadius: BorderRadius.circular(8),
        onTap: () => _openPicker(context),
        child: InputDecorator(
          decoration: InputDecoration(
            labelText: labelText,
            contentPadding:
                const EdgeInsets.symmetric(horizontal: 12, vertical: 4),
            suffixIcon: const Icon(Icons.arrow_drop_down),
          ),
          child: Text(
            _currentName,
            overflow: TextOverflow.ellipsis,
          ),
        ),
      ),
    );
  }
}

class _LeaguePickerSheet extends StatefulWidget {
  const _LeaguePickerSheet({
    required this.leagues,
    required this.current,
    required this.allowAll,
    required this.allLabel,
  });

  final List<LeagueItem> leagues;
  final String? current;
  final bool allowAll;
  final String allLabel;

  @override
  State<_LeaguePickerSheet> createState() => _LeaguePickerSheetState();
}

class _LeaguePickerSheetState extends State<_LeaguePickerSheet> {
  String _keyword = '';

  List<LeagueItem> get _filtered {
    final kw = _keyword.trim().toLowerCase();
    if (kw.isEmpty) return widget.leagues;
    return widget.leagues
        .where(
          (l) =>
              l.name.toLowerCase().contains(kw) ||
              (l.country?.toLowerCase().contains(kw) ?? false),
        )
        .toList();
  }

  void _pick(String? id) => Navigator.of(context).pop(id ?? '');

  @override
  Widget build(BuildContext context) {
    final filtered = _filtered;
    return SafeArea(
      child: Padding(
        padding: EdgeInsets.only(
          bottom: MediaQuery.of(context).viewInsets.bottom,
        ),
        child: SizedBox(
          height: MediaQuery.of(context).size.height * 0.7,
          child: Column(
            children: [
              Padding(
                padding: const EdgeInsets.fromLTRB(16, 16, 16, 8),
                child: TextField(
                  autofocus: true,
                  decoration: InputDecoration(
                    hintText: '搜索联赛名称 / 国家',
                    prefixIcon: const Icon(Icons.search),
                    isDense: true,
                    border: const OutlineInputBorder(),
                    suffixIcon: _keyword.isEmpty
                        ? null
                        : IconButton(
                            tooltip: '清空搜索',
                            onPressed: () => setState(() => _keyword = ''),
                            icon: const Icon(Icons.clear, size: 20),
                          ),
                  ),
                  onChanged: (v) => setState(() => _keyword = v),
                ),
              ),
              Expanded(
                child: filtered.isEmpty
                    ? const Center(
                        child: Text(
                          '未找到匹配联赛',
                          style: TextStyle(color: AppColors.textMuted),
                        ),
                      )
                    : ListView.builder(
                        itemCount: filtered.length + (widget.allowAll ? 1 : 0),
                        itemBuilder: (context, index) {
                          if (widget.allowAll && index == 0) {
                            return ListTile(
                              leading: const Icon(Icons.filter_alt_off_outlined),
                              title: Text(widget.allLabel),
                              selected: widget.current == null,
                              onTap: () => _pick(null),
                            );
                          }
                          final l =
                              filtered[index - (widget.allowAll ? 1 : 0)];
                          return ListTile(
                            leading: const Icon(Icons.emoji_events_outlined),
                            title: Text(l.name),
                            subtitle: l.country == null || l.country!.isEmpty
                                ? null
                                : Text(l.country!),
                            trailing: l.id == widget.current
                                ? const Icon(
                                    Icons.check,
                                    color: AppColors.gold,
                                  )
                                : null,
                            onTap: () => _pick(l.id),
                          );
                        },
                      ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
