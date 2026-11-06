import '../api/favorite_api.dart';

class FavoriteRepository {
  FavoriteRepository(this._api);

  final FavoriteApi _api;

  Future<Set<String>> matchIds(int userId) => _api.matchIds(userId);

  Future<void> addMatch(int userId, String matchId) =>
      _api.addMatch(userId, matchId);

  Future<void> removeMatch(int userId, String matchId) =>
      _api.removeMatch(userId, matchId);

  Future<bool> toggleMatch(
    int userId,
    String matchId, {
    required bool currentlyFavorite,
  }) async {
    if (currentlyFavorite) {
      await removeMatch(userId, matchId);
      return false;
    }
    await addMatch(userId, matchId);
    return true;
  }
}
