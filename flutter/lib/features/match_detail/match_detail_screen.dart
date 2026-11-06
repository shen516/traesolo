import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/config.dart';
import '../../core/network/api_exception.dart';
import '../../core/providers.dart';
import '../../core/theme.dart';
import '../../data/models/match.dart';
import '../../widgets/prediction_panel.dart';
import '../../widgets/team_logo.dart';
import '../auth/auth_state.dart';
import '../common/async_state_pane.dart';
import 'odds_snapshots_panel.dart';
import 'simulation_panel.dart';

@immutable
class MatchDetailData {
  const MatchDetailData({
    required this.match,
    this.prediction,
    this.fromCache = false,
    this.cachedAt,
    this.cacheStale = false,
  });

  final MatchItem match;
  final PredictionSummary? prediction;
  final bool fromCache;
  final DateTime? cachedAt;
  final bool cacheStale;
}

final matchDetailProvider =
    FutureProvider.autoDispose.family<MatchDetailData, String>(
  (ref, matchId) async {
    final repo = ref.watch(matchRepositoryProvider);
    final cache = ref.watch(matchDetailCacheProvider);

    try {
      final match = await repo.detail(matchId);
      PredictionSummary? prediction = match.prediction;
      try {
        prediction = await repo.prediction(matchId);
      } catch (_) {
        // 无预测权限或尚未产出时，保留详情里已有摘要
      }
      await cache.write(match: match, prediction: prediction);
      return MatchDetailData(match: match, prediction: prediction);
    } catch (e) {
      final cached = await cache.read(matchId);
      if (cached != null && cached.match.id.isNotEmpty) {
        final fresh = cached.isFresh(AppConfig.detailCacheTtl);
        return MatchDetailData(
          match: cached.match,
          prediction: cached.prediction ?? cached.match.prediction,
          fromCache: true,
          cachedAt: cached.savedAt,
          cacheStale: !fresh,
        );
      }
      rethrow;
    }
  },
);

final matchFavoriteProvider =
    FutureProvider.autoDispose.family<bool, String>((ref, matchId) async {
  final auth = ref.watch(authProvider);
  final userId = auth.user?.id;
  if (userId == null) return false;
  final ids = await ref.watch(favoriteRepositoryProvider).matchIds(
        userId is int ? userId : int.parse(userId.toString()),
      );
  return ids.contains(matchId);
});

class MatchDetailScreen extends ConsumerWidget {
  const MatchDetailScreen({super.key, required this.matchId});

  final String matchId;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final async = ref.watch(matchDetailProvider(matchId));
    final favAsync = ref.watch(matchFavoriteProvider(matchId));
    final isFav = switch (favAsync) {
      AsyncData(:final value) => value,
      _ => false,
    };

    return Scaffold(
      appBar: AppBar(
        title: const Text('赛事详情'),
        actions: [
          IconButton(
            tooltip: isFav ? '取消收藏' : '收藏赛事',
            onPressed: favAsync.isLoading
                ? null
                : () => _toggleFavorite(context, ref, currentlyFavorite: isFav),
            icon: Icon(
              isFav ? Icons.bookmark : Icons.bookmark_border,
              color: isFav ? AppColors.gold : null,
            ),
          ),
        ],
      ),
      body: async.when(
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (e, _) => AsyncStatePane.error(
          error: e,
          onRetry: () => ref.invalidate(matchDetailProvider(matchId)),
        ),
        data: (data) {
          final m = data.match;
          final p = data.prediction;
          return ListView(
            padding: const EdgeInsets.all(16),
            children: [
              if (data.fromCache) ...[
                _OfflineBanner(
                  stale: data.cacheStale,
                  cachedAt: data.cachedAt,
                  onRetry: () => ref.invalidate(matchDetailProvider(matchId)),
                ),
                const SizedBox(height: 12),
              ],
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
                        style: const TextStyle(
                          color: AppColors.textSecondary,
                          fontSize: 13,
                        ),
                      ),
                      const SizedBox(height: 16),
                      Row(
                        crossAxisAlignment: CrossAxisAlignment.center,
                        children: [
                          Expanded(
                            child: InkWell(
                              onTap: m.homeTeam.id.isEmpty
                                  ? null
                                  : () =>
                                      context.push('/teams/${m.homeTeam.id}'),
                              child: Column(
                                children: [
                                  TeamLogo(
                                    url: m.homeTeam.logo,
                                    size: 48,
                                    semanticLabel:
                                        '${m.homeTeam.displayName} 队徽',
                                  ),
                                  const SizedBox(height: 8),
                                  Text(
                                    m.homeTeam.displayName,
                                    textAlign: TextAlign.center,
                                    style: const TextStyle(
                                      fontSize: 16,
                                      fontWeight: FontWeight.w600,
                                    ),
                                  ),
                                ],
                              ),
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
                            child: InkWell(
                              onTap: m.awayTeam.id.isEmpty
                                  ? null
                                  : () =>
                                      context.push('/teams/${m.awayTeam.id}'),
                              child: Column(
                                children: [
                                  TeamLogo(
                                    url: m.awayTeam.logo,
                                    size: 48,
                                    semanticLabel:
                                        '${m.awayTeam.displayName} 队徽',
                                  ),
                                  const SizedBox(height: 8),
                                  Text(
                                    m.awayTeam.displayName,
                                    textAlign: TextAlign.center,
                                    style: const TextStyle(
                                      fontSize: 16,
                                      fontWeight: FontWeight.w600,
                                    ),
                                  ),
                                ],
                              ),
                            ),
                          ),
                        ],
                      ),
                    ],
                  ),
                ),
              ),
              const SizedBox(height: 12),
              PredictionPanel(prediction: p),
              const SizedBox(height: 12),
              OddsSnapshotsPanel(matchId: matchId, prediction: p),
              const SizedBox(height: 12),
              SimulationPanel(
                matchId: matchId,
                isUpcoming: m.status == 'upcoming',
              ),
            ],
          );
        },
      ),
    );
  }

  Future<void> _toggleFavorite(
    BuildContext context,
    WidgetRef ref, {
    required bool currentlyFavorite,
  }) async {
    final auth = ref.read(authProvider);
    final userId = auth.user?.id;
    if (userId == null) return;
    try {
      await ref.read(favoriteRepositoryProvider).toggleMatch(
            userId is int ? userId : int.parse(userId.toString()),
            matchId,
            currentlyFavorite: currentlyFavorite,
          );
      ref.invalidate(matchFavoriteProvider(matchId));
      if (context.mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text(currentlyFavorite ? '已取消收藏' : '已收藏赛事')),
        );
      }
    } catch (e) {
      if (!context.mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(e is ApiException ? e.message : e.toString())),
      );
    }
  }
}

class _OfflineBanner extends StatelessWidget {
  const _OfflineBanner({
    required this.stale,
    required this.cachedAt,
    required this.onRetry,
  });

  final bool stale;
  final DateTime? cachedAt;
  final VoidCallback onRetry;

  @override
  Widget build(BuildContext context) {
    final time = cachedAt;
    final timeText = time == null
        ? ''
        : ' · ${_two(time.month)}-${_two(time.day)} ${_two(time.hour)}:${_two(time.minute)}';
    return Semantics(
      liveRegion: true,
      child: Material(
        color: AppColors.bgSecondary,
        borderRadius: BorderRadius.circular(8),
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
          child: Row(
            children: [
              Icon(
                Icons.cloud_off_outlined,
                size: 18,
                color: stale ? AppColors.orange : AppColors.textMuted,
              ),
              const SizedBox(width: 8),
              Expanded(
                child: Text(
                  stale
                      ? '离线缓存（可能已过期）$timeText'
                      : '正在展示离线缓存$timeText',
                  style: TextStyle(
                    color: stale ? AppColors.orange : AppColors.textSecondary,
                    fontSize: 12,
                    height: 1.35,
                  ),
                ),
              ),
              TextButton(
                onPressed: onRetry,
                child: const Text('重试'),
              ),
            ],
          ),
        ),
      ),
    );
  }

  static String _two(int n) => n.toString().padLeft(2, '0');
}
