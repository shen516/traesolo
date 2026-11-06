import 'dart:convert';

import '../../core/network/api_client.dart';
import '../models/user.dart';

class AuthApi {
  AuthApi(this._client);

  final ApiClient _client;

  Future<CaptchaPayload> getCaptcha() async {
    final data = await _client.get<Map<String, dynamic>>(
      '/auth/captcha',
      parser: (raw) => Map<String, dynamic>.from(raw as Map),
    );
    final hex = (data['captcha_image'] ?? '').toString();
    if (hex.isEmpty) {
      throw StateError('验证码图片为空');
    }
    return CaptchaPayload(
      captchaId: (data['captcha_id'] ?? '').toString(),
      imageBytes: _hexToBytes(hex),
      expireSeconds: (data['expire_seconds'] as num?)?.toInt() ?? 120,
    );
  }

  Future<LoginResult> login({
    required String username,
    required String password,
    required String captchaId,
    required String captchaCode,
  }) async {
    final data = await _client.post<Map<String, dynamic>>(
      '/auth/login',
      data: {
        'username': username,
        'password': password,
        'captcha_id': captchaId,
        'captcha_code': captchaCode,
      },
      parser: (raw) => Map<String, dynamic>.from(raw as Map),
    );

    final userMap = Map<String, dynamic>.from(data['user'] as Map);
    return LoginResult(
      token: (data['token'] ?? '').toString(),
      user: UserProfile.fromJson(userMap),
      roles: _stringList(data['roles']),
      permissions: _stringList(data['permissions']),
      features: _stringList(data['features']),
    );
  }

  Future<void> logout() async {
    try {
      await _client.post<dynamic>('/auth/logout');
    } catch (_) {
      // 本地仍清理会话
    }
  }

  Future<void> changePassword({
    required String oldPassword,
    required String newPassword,
  }) async {
    await _client.post<dynamic>(
      '/auth/change-password',
      data: {
        'old_password': oldPassword,
        'new_password': newPassword,
      },
    );
  }

  List<String> _stringList(dynamic raw) {
    if (raw is! List) return const [];
    return raw.map((e) => e.toString()).toList();
  }

  List<int> _hexToBytes(String hex) {
    final cleaned = hex.trim();
    if (cleaned.length.isOdd) {
      throw const FormatException('验证码 hex 长度非法');
    }
    // 兼容后端直接返回 hex；若误传 base64 再兜底
    try {
      final out = <int>[];
      for (var i = 0; i < cleaned.length; i += 2) {
        out.add(int.parse(cleaned.substring(i, i + 2), radix: 16));
      }
      return out;
    } catch (_) {
      return base64Decode(cleaned);
    }
  }
}
