import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/config.dart';
import '../../core/theme.dart';
import '../../data/models/user.dart';
import '../auth/auth_state.dart';

class ProfileScreen extends ConsumerWidget {
  const ProfileScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final auth = ref.watch(authProvider);
    final user = auth.user;

    return Scaffold(
      appBar: AppBar(title: const Text('我的')),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          Card(
            child: Padding(
              padding: const EdgeInsets.all(16),
              child: Row(
                children: [
                  // 头像视觉元素：取用户名首字母（PROFILE-01）
                  CircleAvatar(
                    radius: 26,
                    backgroundColor: AppColors.gold,
                    child: Text(
                      _initial(user?.username),
                      style: const TextStyle(
                        color: AppColors.bgPrimary,
                        fontSize: 20,
                        fontWeight: FontWeight.w700,
                      ),
                    ),
                  ),
                  const SizedBox(width: 14),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          user?.username ?? '-',
                          style: const TextStyle(
                            fontSize: 18,
                            fontWeight: FontWeight.w600,
                          ),
                        ),
                        const SizedBox(height: 4),
                        Text(
                          user?.email ?? '未设置邮箱',
                          style: const TextStyle(color: AppColors.textSecondary),
                        ),
                        if (auth.roles.isNotEmpty) ...[
                          const SizedBox(height: 4),
                          Text(
                            '角色：${auth.roles.join('、')}',
                            style: const TextStyle(
                              color: AppColors.textMuted,
                              fontSize: 12,
                            ),
                          ),
                        ],
                      ],
                    ),
                  ),
                ],
              ),
            ),
          ),
          const SizedBox(height: 12),
          Card(
            child: Column(
              children: [
                ListTile(
                  leading: const Icon(Icons.lock_outline, color: AppColors.blue),
                  title: const Text('修改密码'),
                  trailing: const Icon(Icons.chevron_right),
                  onTap: () => context.push('/change-password'),
                ),
                const Divider(height: 1),
                // 订阅方案入口：展示当前计划并说明升级渠道（PROFILE-02）
                ListTile(
                  leading: const Icon(Icons.workspace_premium, color: AppColors.gold),
                  title: const Text('订阅方案'),
                  subtitle: Text(
                    '当前：${user?.subscriptionPlan ?? 'free'}'
                    '${user?.subscriptionStatus != null ? ' · ${user!.subscriptionStatus}' : ''}',
                    style: const TextStyle(color: AppColors.textMuted, fontSize: 12),
                  ),
                  trailing: const Icon(Icons.chevron_right),
                  onTap: () => _showSubscriptionDialog(context, user),
                ),
                const Divider(height: 1),
                ListTile(
                  leading: const Icon(Icons.info_outline, color: AppColors.gold),
                  title: const Text('关于与免责声明'),
                  subtitle: Text(
                    '版本 ${AppConfig.appVersion}',
                    style: const TextStyle(color: AppColors.textMuted, fontSize: 12),
                  ),
                  trailing: const Icon(Icons.chevron_right),
                  onTap: () => context.push('/about'),
                ),
              ],
            ),
          ),
          const SizedBox(height: 12),
          const Card(
            child: Padding(
              padding: EdgeInsets.all(16),
              child: Text(
                AppConfig.disclaimer,
                style: TextStyle(color: AppColors.textMuted, fontSize: 12),
              ),
            ),
          ),
          const SizedBox(height: 24),
          // 退出登录改用描边红样式：弱化危险操作的视觉权重，不再整块红色填充（PROFILE-04）
          OutlinedButton(
            style: OutlinedButton.styleFrom(
              foregroundColor: AppColors.red,
              side: const BorderSide(color: AppColors.red),
            ),
            onPressed: auth.isLoading
                ? null
                : () async {
                    final confirm = await showDialog<bool>(
                      context: context,
                      builder: (ctx) => AlertDialog(
                        title: const Text('退出登录'),
                        content: const Text('确定退出当前账号？'),
                        actions: [
                          TextButton(
                            onPressed: () => Navigator.pop(ctx, false),
                            child: const Text('取消'),
                          ),
                          TextButton(
                            onPressed: () => Navigator.pop(ctx, true),
                            child: const Text(
                              '退出',
                              style: TextStyle(color: AppColors.red),
                            ),
                          ),
                        ],
                      ),
                    );
                    if (confirm == true) {
                      await ref.read(authProvider.notifier).logout();
                    }
                  },
            child: const Text('退出登录'),
          ),
        ],
      ),
    );
  }

  static String _initial(String? username) {
    final name = username?.trim();
    if (name == null || name.isEmpty) return '?';
    // 取首个 Unicode 码点，兼容中文用户名
    return String.fromCharCode(name.runes.first).toUpperCase();
  }

  void _showSubscriptionDialog(BuildContext context, UserProfile? user) {
    showDialog<void>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('订阅方案'),
        content: Text(
          '当前订阅：${user?.subscriptionPlan ?? 'free'}'
          '${user?.subscriptionStatus != null ? '（${user!.subscriptionStatus}）' : ''}。\n\n'
          '如需升级订阅，请登录 Web 端在「订阅管理」中操作，或联系管理员开通。',
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx),
            child: const Text('知道了'),
          ),
        ],
      ),
    );
  }
}
