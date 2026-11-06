import 'package:flutter/foundation.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../data/api/auth_api.dart';
import '../data/api/match_api.dart';
import '../data/repositories/auth_repository.dart';
import '../data/repositories/match_repository.dart';
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
