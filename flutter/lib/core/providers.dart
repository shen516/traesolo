import 'package:flutter/foundation.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../data/api/auth_api.dart';
import '../data/api/favorite_api.dart';
import '../data/api/follow_api.dart';
import '../data/api/jingcai_api.dart';
import '../data/api/league_api.dart';
import '../data/api/match_api.dart';
import '../data/api/scorer_api.dart';
import '../data/api/simulation_api.dart';
import '../data/api/standing_api.dart';
import '../data/api/team_api.dart';
import '../data/repositories/auth_repository.dart';
import '../data/repositories/data_repository.dart';
import '../data/repositories/favorite_repository.dart';
import '../data/repositories/follow_repository.dart';
import '../data/repositories/jingcai_repository.dart';
import '../data/repositories/league_repository.dart';
import '../data/match_detail_cache.dart';
import '../data/repositories/match_repository.dart';
import '../data/repositories/simulation_repository.dart';
import '../data/repositories/team_repository.dart';
import '../data/session_store.dart';
import 'network/api_client.dart';

/// 401 时递增，供 AuthNotifier 清空内存会话。
final unauthorizedTickProvider = Provider<ValueNotifier<int>>((ref) {
  final tick = ValueNotifier<int>(0);
  ref.onDispose(tick.dispose);
  return tick;
});

final sessionStoreProvider = Provider<SessionStore>((ref) => SessionStore());

final apiClientProvider = Provider<ApiClient>((ref) {
  final store = ref.watch(sessionStoreProvider);
  final tick = ref.watch(unauthorizedTickProvider);
  return ApiClient(
    readToken: store.readToken,
    onUnauthorized: () async {
      await store.clear();
      tick.value++;
    },
  );
});

final authRepositoryProvider = Provider<AuthRepository>((ref) {
  return AuthRepository(
    api: AuthApi(ref.watch(apiClientProvider)),
    sessionStore: ref.watch(sessionStoreProvider),
  );
});

final matchRepositoryProvider = Provider<MatchRepository>((ref) {
  return MatchRepository(MatchApi(ref.watch(apiClientProvider)));
});

final matchDetailCacheProvider = Provider<MatchDetailCache>((ref) {
  return MatchDetailCache();
});

final leagueRepositoryProvider = Provider<LeagueRepository>((ref) {
  return LeagueRepository(LeagueApi(ref.watch(apiClientProvider)));
});

final teamRepositoryProvider = Provider<TeamRepository>((ref) {
  return TeamRepository(TeamApi(ref.watch(apiClientProvider)));
});

final dataRepositoryProvider = Provider<DataRepository>((ref) {
  final client = ref.watch(apiClientProvider);
  return DataRepository(
    StandingApi(client),
    ScorerApi(client),
    ref.watch(teamRepositoryProvider),
  );
});

final followRepositoryProvider = Provider<FollowRepository>((ref) {
  return FollowRepository(FollowApi(ref.watch(apiClientProvider)));
});

final favoriteRepositoryProvider = Provider<FavoriteRepository>((ref) {
  return FavoriteRepository(FavoriteApi(ref.watch(apiClientProvider)));
});

final simulationRepositoryProvider = Provider<SimulationRepository>((ref) {
  return SimulationRepository(SimulationApi(ref.watch(apiClientProvider)));
});

final jingcaiRepositoryProvider = Provider<JingcaiRepository>((ref) {
  return JingcaiRepository(JingcaiApi(ref.watch(apiClientProvider)));
});
