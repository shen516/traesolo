import 'dart:convert';

import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'models/user.dart';

class SessionSnapshot {
  const SessionSnapshot({
    required this.token,
    required this.user,
    required this.roles,
    required this.permissions,
    required this.features,
  });

  final String token;
  final UserProfile user;
  final List<String> roles;
  final List<String> permissions;
  final List<String> features;
}

class SessionStore {
  SessionStore({
    FlutterSecureStorage? secureStorage,
  }) : _secure = secureStorage ?? const FlutterSecureStorage();

  static const _tokenKey = 'traesolo_token';
  static const _userKey = 'traesolo_user';
  static const _rolesKey = 'traesolo_roles';
  static const _permsKey = 'traesolo_permissions';
  static const _featuresKey = 'traesolo_features';

  final FlutterSecureStorage _secure;

  Future<String?> readToken() => _secure.read(key: _tokenKey);

  Future<SessionSnapshot?> load() async {
    final token = await readToken();
    if (token == null || token.isEmpty) return null;

    final prefs = await SharedPreferences.getInstance();
    final userRaw = prefs.getString(_userKey);
    if (userRaw == null || userRaw.isEmpty) return null;

    try {
      final user = UserProfile.fromJson(
        Map<String, dynamic>.from(jsonDecode(userRaw) as Map),
      );
      return SessionSnapshot(
        token: token,
        user: user,
        roles: prefs.getStringList(_rolesKey) ?? const [],
        permissions: prefs.getStringList(_permsKey) ?? const [],
        features: prefs.getStringList(_featuresKey) ?? const [],
      );
    } catch (_) {
      await clear();
      return null;
    }
  }

  Future<void> save(LoginResult result) async {
    await _secure.write(key: _tokenKey, value: result.token);
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(_userKey, jsonEncode(result.user.toJson()));
    await prefs.setStringList(_rolesKey, result.roles);
    await prefs.setStringList(_permsKey, result.permissions);
    await prefs.setStringList(_featuresKey, result.features);
  }

  Future<void> updateUser(UserProfile user) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(_userKey, jsonEncode(user.toJson()));
  }

  Future<void> clear() async {
    await _secure.delete(key: _tokenKey);
    final prefs = await SharedPreferences.getInstance();
    await prefs.remove(_userKey);
    await prefs.remove(_rolesKey);
    await prefs.remove(_permsKey);
    await prefs.remove(_featuresKey);
  }
}
