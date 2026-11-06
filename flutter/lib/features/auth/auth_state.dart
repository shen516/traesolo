import 'package:flutter/foundation.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/network/api_exception.dart';
import '../../core/providers.dart';
import '../../data/models/user.dart';
import '../../data/repositories/auth_repository.dart';

@immutable
class AuthState {
  const AuthState({
    required this.initialized,
    required this.isLoading,
    this.token,
    this.user,
    this.roles = const [],
    this.permissions = const [],
    this.features = const [],
    this.error,
  });

  final bool initialized;
  final bool isLoading;
  final String? token;
  final UserProfile? user;
  final List<String> roles;
  final List<String> permissions;
  final List<String> features;
  final String? error;

  bool get isAuthenticated => token != null && token!.isNotEmpty;
  bool get mustChangePassword => user?.mustChangePassword == true;

  /// 与后端 RequireSimulation 对齐：simulation:view 或 model:manage
  bool get canSimulate =>
      permissions.contains('simulation:view') ||
      permissions.contains('model:manage');

  /// 竞彩只读：与 Web Jingcai 页权限大致对齐（后端 RequireMatchRead 更宽）
  bool get canJingcai =>
      permissions.contains('match:jingcai_bf') ||
      permissions.contains('match:jingcai_bf_history') ||
      permissions.contains('match:upcoming') ||
      permissions.contains('match:finished') ||
      permissions.contains('match:manage') ||
      permissions.contains('jingcai:manage');

  /// 赔率快照：订阅权益 `odds:snapshot`
  bool get canOddsSnapshot => features.contains('odds:snapshot');

  AuthState copyWith({
    bool? initialized,
    bool? isLoading,
    String? token,
    UserProfile? user,
    List<String>? roles,
    List<String>? permissions,
    List<String>? features,
    String? error,
    bool clearError = false,
    bool clearSession = false,
  }) {
    return AuthState(
      initialized: initialized ?? this.initialized,
      isLoading: isLoading ?? this.isLoading,
      token: clearSession ? null : (token ?? this.token),
      user: clearSession ? null : (user ?? this.user),
      roles: clearSession ? const [] : (roles ?? this.roles),
      permissions: clearSession ? const [] : (permissions ?? this.permissions),
      features: clearSession ? const [] : (features ?? this.features),
      error: clearError ? null : (error ?? this.error),
    );
  }

  static const initial = AuthState(initialized: false, isLoading: true);
}

class AuthNotifier extends Notifier<AuthState> {
  late final AuthRepository _repo;

  /// 供 go_router refreshListenable
  final authListenable = ValueNotifier<int>(0);

  @override
  AuthState build() {
    _repo = ref.read(authRepositoryProvider);
    final tick = ref.read(unauthorizedTickProvider);

    void onUnauthorized() {
      state = const AuthState(initialized: true, isLoading: false);
      authListenable.value++;
    }

    tick.addListener(onUnauthorized);
    ref.onDispose(() {
      tick.removeListener(onUnauthorized);
      authListenable.dispose();
    });

    Future.microtask(restore);
    return AuthState.initial;
  }

  void _bump() => authListenable.value++;

  Future<void> restore() async {
    state = state.copyWith(isLoading: true, clearError: true);
    try {
      final snap = await _repo.restore();
      if (snap == null) {
        state = const AuthState(initialized: true, isLoading: false);
      } else {
        state = AuthState(
          initialized: true,
          isLoading: false,
          token: snap.token,
          user: snap.user,
          roles: snap.roles,
          permissions: snap.permissions,
          features: snap.features,
        );
      }
    } catch (e) {
      state = AuthState(
        initialized: true,
        isLoading: false,
        error: e.toString(),
      );
    }
    _bump();
  }

  Future<CaptchaPayload> loadCaptcha() => _repo.getCaptcha();

  Future<bool> login({
    required String username,
    required String password,
    required String captchaId,
    required String captchaCode,
  }) async {
    state = state.copyWith(isLoading: true, clearError: true);
    try {
      final result = await _repo.login(
        username: username,
        password: password,
        captchaId: captchaId,
        captchaCode: captchaCode,
      );
      state = AuthState(
        initialized: true,
        isLoading: false,
        token: result.token,
        user: result.user,
        roles: result.roles,
        permissions: result.permissions,
        features: result.features,
      );
      _bump();
      return true;
    } catch (e) {
      state = state.copyWith(
        isLoading: false,
        error: e is ApiException ? e.message : e.toString(),
      );
      _bump();
      return false;
    }
  }

  Future<bool> changePassword({
    required String oldPassword,
    required String newPassword,
  }) async {
    state = state.copyWith(isLoading: true, clearError: true);
    try {
      await _repo.changePassword(oldPassword: oldPassword, newPassword: newPassword);
      await _repo.clearLocal();
      state = const AuthState(
        initialized: true,
        isLoading: false,
        error: '密码已修改，请重新登录',
      );
      _bump();
      return true;
    } catch (e) {
      state = state.copyWith(
        isLoading: false,
        error: e is ApiException ? e.message : e.toString(),
      );
      return false;
    }
  }

  Future<void> logout() async {
    state = state.copyWith(isLoading: true, clearError: true);
    await _repo.logout(callServer: true);
    state = const AuthState(initialized: true, isLoading: false);
    _bump();
  }
}

final authProvider = NotifierProvider<AuthNotifier, AuthState>(AuthNotifier.new);
