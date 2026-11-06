import 'dart:convert';

import 'package:flutter/foundation.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../core/config.dart';
import 'models/match.dart';

@immutable
class CachedMatchDetail {
  const CachedMatchDetail({
    required this.match,
    this.prediction,
    required this.savedAt,
  });

  final MatchItem match;
  final PredictionSummary? prediction;
  final DateTime savedAt;

  bool isFresh([Duration ttl = AppConfig.detailCacheTtl]) =>
      DateTime.now().difference(savedAt) <= ttl;

  Map<String, dynamic> toJson() => {
        'saved_at': savedAt.toIso8601String(),
        'match': match.toJson(),
        if (prediction != null) 'prediction': prediction!.toJson(),
      };

  factory CachedMatchDetail.fromJson(Map<String, dynamic> json) {
    final matchRaw = json['match'];
    final predRaw = json['prediction'];
    return CachedMatchDetail(
      match: MatchItem.fromJson(
        matchRaw is Map
            ? Map<String, dynamic>.from(matchRaw)
            : <String, dynamic>{},
      ),
      prediction: predRaw is Map
          ? PredictionSummary.fromJson(Map<String, dynamic>.from(predRaw))
          : null,
      savedAt: DateTime.tryParse(json['saved_at']?.toString() ?? '') ??
          DateTime.fromMillisecondsSinceEpoch(0),
    );
  }
}

/// 最近赛事详情本地缓存（SharedPreferences JSON，LRU 裁剪）。
class MatchDetailCache {
  MatchDetailCache({
    Future<SharedPreferences> Function()? prefsFactory,
    this.maxEntries = AppConfig.detailCacheMaxEntries,
  }) : _prefsFactory = prefsFactory ?? SharedPreferences.getInstance;

  static const _storageKey = 'traesolo_match_detail_cache_v1';

  final Future<SharedPreferences> Function() _prefsFactory;
  final int maxEntries;

  Future<CachedMatchDetail?> read(String matchId) async {
    final all = await _loadAll();
    return all[matchId];
  }

  Future<void> write({
    required MatchItem match,
    PredictionSummary? prediction,
    DateTime? savedAt,
  }) async {
    if (match.id.isEmpty) return;
    final all = await _loadAll();
    all[match.id] = CachedMatchDetail(
      match: match,
      prediction: prediction ?? match.prediction,
      savedAt: savedAt ?? DateTime.now(),
    );
    await _persist(_prune(all, maxEntries));
  }

  Future<void> remove(String matchId) async {
    final all = await _loadAll();
    if (all.remove(matchId) == null) return;
    await _persist(all);
  }

  Future<void> clear() async {
    final prefs = await _prefsFactory();
    await prefs.remove(_storageKey);
  }

  Future<Map<String, CachedMatchDetail>> _loadAll() async {
    final prefs = await _prefsFactory();
    final raw = prefs.getString(_storageKey);
    if (raw == null || raw.isEmpty) return {};
    try {
      final decoded = jsonDecode(raw);
      if (decoded is! Map) return {};
      final out = <String, CachedMatchDetail>{};
      decoded.forEach((key, value) {
        if (value is Map) {
          out[key.toString()] = CachedMatchDetail.fromJson(
            Map<String, dynamic>.from(value),
          );
        }
      });
      return out;
    } catch (_) {
      await prefs.remove(_storageKey);
      return {};
    }
  }

  Future<void> _persist(Map<String, CachedMatchDetail> all) async {
    final prefs = await _prefsFactory();
    final encoded = <String, dynamic>{
      for (final e in all.entries) e.key: e.value.toJson(),
    };
    await prefs.setString(_storageKey, jsonEncode(encoded));
  }

  /// 按 savedAt 保留最近 [limit] 条（可单测）。
  static Map<String, CachedMatchDetail> pruneToLimit(
    Map<String, CachedMatchDetail> input,
    int limit,
  ) =>
      _prune(input, limit);

  static Map<String, CachedMatchDetail> _prune(
    Map<String, CachedMatchDetail> input,
    int limit,
  ) {
    if (limit <= 0 || input.length <= limit) {
      return Map<String, CachedMatchDetail>.from(input);
    }
    final sorted = input.entries.toList()
      ..sort((a, b) => b.value.savedAt.compareTo(a.value.savedAt));
    return {
      for (final e in sorted.take(limit)) e.key: e.value,
    };
  }
}
