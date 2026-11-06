import '../api/auth_api.dart';
import '../models/user.dart';
import '../session_store.dart';

class AuthRepository {
  AuthRepository({
    required this._api,
    required SessionStore sessionStore,
  }) : _session = sessionStore;

  final AuthApi _api;
  final SessionStore _session;

  Future<String?> readToken() => _session.readToken();

  Future<SessionSnapshot?> restore() => _session.load();

  Future<CaptchaPayload> getCaptcha() => _api.getCaptcha();

  Future<LoginResult> login({
    required String username,
    required String password,
    required String captchaId,
    required String captchaCode,
  }) async {
    final result = await _api.login(
      username: username,
      password: password,
      captchaId: captchaId,
      captchaCode: captchaCode,
    );
    await _session.save(result);
    return result;
  }

  Future<void> changePassword({
    required String oldPassword,
    required String newPassword,
  }) async {
    await _api.changePassword(oldPassword: oldPassword, newPassword: newPassword);
  }

  Future<void> markPasswordChanged(UserProfile user) async {
    await _session.updateUser(user.copyWith(mustChangePassword: false));
  }

  Future<void> logout({bool callServer = true}) async {
    if (callServer) {
      await _api.logout();
    }
    await _session.clear();
  }

  Future<void> clearLocal() => _session.clear();
}
