class UserProfile {
  const UserProfile({
    required this.id,
    required this.username,
    this.email,
    this.avatar,
    this.level,
    this.subscriptionPlan,
    this.subscriptionStatus,
    this.subscriptionExpire,
    this.mustChangePassword = false,
  });

  final dynamic id;
  final String username;
  final String? email;
  final String? avatar;
  final dynamic level;
  final String? subscriptionPlan;
  final String? subscriptionStatus;
  final String? subscriptionExpire;
  final bool mustChangePassword;

  factory UserProfile.fromJson(Map<String, dynamic> json) {
    return UserProfile(
      id: json['id'],
      username: (json['username'] ?? '').toString(),
      email: json['email']?.toString(),
      avatar: json['avatar']?.toString(),
      level: json['level'],
      subscriptionPlan: json['subscription_plan']?.toString(),
      subscriptionStatus: json['subscription_status']?.toString(),
      subscriptionExpire: json['subscription_expire']?.toString(),
      mustChangePassword: json['must_change_password'] == true,
    );
  }

  Map<String, dynamic> toJson() => {
        'id': id,
        'username': username,
        'email': email,
        'avatar': avatar,
        'level': level,
        'subscription_plan': subscriptionPlan,
        'subscription_status': subscriptionStatus,
        'subscription_expire': subscriptionExpire,
        'must_change_password': mustChangePassword,
      };

  UserProfile copyWith({bool? mustChangePassword}) {
    return UserProfile(
      id: id,
      username: username,
      email: email,
      avatar: avatar,
      level: level,
      subscriptionPlan: subscriptionPlan,
      subscriptionStatus: subscriptionStatus,
      subscriptionExpire: subscriptionExpire,
      mustChangePassword: mustChangePassword ?? this.mustChangePassword,
    );
  }
}

class CaptchaPayload {
  const CaptchaPayload({
    required this.captchaId,
    required this.imageBytes,
    required this.expireSeconds,
  });

  final String captchaId;
  final List<int> imageBytes;
  final int expireSeconds;
}

class LoginResult {
  const LoginResult({
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
