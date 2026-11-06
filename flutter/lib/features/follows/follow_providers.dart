import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/providers.dart';
import '../../data/models/follow_summary.dart';

final followedIdsProvider = FutureProvider.autoDispose<Set<String>>((ref) async {
  final state = await ref.watch(followRepositoryProvider).list();
  return state.ids.toSet();
});

final followSummaryProvider = FutureProvider.autoDispose<FollowSummary>((ref) {
  return ref.watch(followRepositoryProvider).summary();
});
