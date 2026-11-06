import '../api/follow_api.dart';
import '../models/follow_summary.dart';

class FollowRepository {
  FollowRepository(this._api);

  final FollowApi _api;

  Future<FollowState> list() => _api.list();

  Future<FollowSummary> summary() => _api.summary(
        matchLimit: 12,
        standingsLimit: 5,
        scorersLimit: 3,
      );

  Future<void> follow(String leagueId) => _api.follow(leagueId);

  Future<void> unfollow(String leagueId) => _api.unfollow(leagueId);

  Future<bool> toggle(String leagueId, {required bool currentlyFollowed}) async {
    if (currentlyFollowed) {
      await unfollow(leagueId);
      return false;
    }
    await follow(leagueId);
    return true;
  }
}
