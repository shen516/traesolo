import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../../core/config.dart';
import '../../core/theme.dart';
import '../../data/models/user.dart';
import 'auth_state.dart';

class LoginScreen extends ConsumerStatefulWidget {
  const LoginScreen({super.key});

  @override
  ConsumerState<LoginScreen> createState() => _LoginScreenState();
}

class _LoginScreenState extends ConsumerState<LoginScreen> {
  static const _rememberKey = 'login_remember_username';
  static const _savedUserKey = 'login_saved_username';

  final _userCtrl = TextEditingController();
  final _passCtrl = TextEditingController();
  final _captchaCtrl = TextEditingController();

  CaptchaPayload? _captcha;
  bool _loadingCaptcha = false;
  bool _obscure = true;
  bool _remember = false;

  @override
  void initState() {
    super.initState();
    Future.microtask(_refreshCaptcha);
    _loadSavedUsername();
  }

  @override
  void dispose() {
    _userCtrl.dispose();
    _passCtrl.dispose();
    _captchaCtrl.dispose();
    super.dispose();
  }

  /// 记住用户名：登录成功后按勾选状态写入本地（LOGIN-04）
  Future<void> _loadSavedUsername() async {
    final sp = await SharedPreferences.getInstance();
    final saved = sp.getString(_savedUserKey);
    final remember = sp.getBool(_rememberKey) ?? false;
    if (!mounted) return;
    setState(() {
      _remember = remember;
      if (remember && saved != null && saved.isNotEmpty) {
        _userCtrl.text = saved;
      }
    });
  }

  Future<void> _persistUsername() async {
    final sp = await SharedPreferences.getInstance();
    await sp.setBool(_rememberKey, _remember);
    if (_remember) {
      await sp.setString(_savedUserKey, _userCtrl.text.trim());
    } else {
      await sp.remove(_savedUserKey);
    }
  }

  /// 忘记密码引导：无自助找回接口，指向管理员重置与登录后修改（LOGIN-01）
  void _showForgotPasswordDialog() {
    showDialog<void>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('忘记密码'),
        content: const Text(
          '暂不支持自助找回密码。请联系管理员在后台重置；'
          '首次登录后可在「我的 → 修改密码」中自行修改。',
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(ctx).pop(),
            child: const Text('知道了'),
          ),
        ],
      ),
    );
  }

  void _clearAuthError() => ref.read(authProvider.notifier).clearError();

  Future<void> _refreshCaptcha() async {
    setState(() => _loadingCaptcha = true);
    try {
      final cap = await ref.read(authProvider.notifier).loadCaptcha();
      if (!mounted) return;
      setState(() {
        _captcha = cap;
        _captchaCtrl.clear();
      });
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('验证码加载失败：$e')),
      );
    } finally {
      if (mounted) setState(() => _loadingCaptcha = false);
    }
  }

  Future<void> _submit() async {
    final captcha = _captcha;
    if (captcha == null) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('请先获取验证码')),
      );
      return;
    }
    final ok = await ref.read(authProvider.notifier).login(
          username: _userCtrl.text.trim(),
          password: _passCtrl.text,
          captchaId: captcha.captchaId,
          captchaCode: _captchaCtrl.text.trim(),
        );
    if (ok) {
      await _persistUsername();
    } else {
      await _refreshCaptcha();
    }
  }

  @override
  Widget build(BuildContext context) {
    final auth = ref.watch(authProvider);

    return Scaffold(
      body: SafeArea(
        child: Center(
          child: ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: 420),
            child: SingleChildScrollView(
              padding: const EdgeInsets.all(24),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  const SizedBox(height: 24),
                  const Text(
                    AppConfig.appName,
                    textAlign: TextAlign.center,
                    style: TextStyle(
                      fontSize: 32,
                      fontWeight: FontWeight.bold,
                      color: AppColors.gold,
                    ),
                  ),
                  const SizedBox(height: 8),
                  const Text(
                    AppConfig.brandEn,
                    textAlign: TextAlign.center,
                    style: TextStyle(
                      fontSize: 14,
                      letterSpacing: 1.2,
                      color: AppColors.blue,
                    ),
                  ),
                  const SizedBox(height: 8),
                  const Text(
                    AppConfig.appTagline,
                    textAlign: TextAlign.center,
                    style: TextStyle(color: AppColors.textSecondary),
                  ),
                  const SizedBox(height: 8),
                  const Text(
                    AppConfig.disclaimer,
                    textAlign: TextAlign.center,
                    style: TextStyle(color: AppColors.textMuted, fontSize: 12),
                  ),
                  const SizedBox(height: 32),
                  TextField(
                    controller: _userCtrl,
                    autofocus: true, // 进入登录页自动聚焦用户名（LOGIN-03）
                    decoration: const InputDecoration(labelText: '用户名'),
                    textInputAction: TextInputAction.next,
                    onChanged: (_) => _clearAuthError(),
                  ),
                  const SizedBox(height: 12),
                  TextField(
                    controller: _passCtrl,
                    obscureText: _obscure,
                    decoration: InputDecoration(
                      labelText: '密码',
                      suffixIcon: IconButton(
                        onPressed: () => setState(() => _obscure = !_obscure),
                        icon: Icon(_obscure ? Icons.visibility : Icons.visibility_off),
                      ),
                    ),
                    textInputAction: TextInputAction.next,
                    onChanged: (_) => _clearAuthError(),
                  ),
                  const SizedBox(height: 12),
                  Row(
                    children: [
                      Expanded(
                        child: TextField(
                          controller: _captchaCtrl,
                          decoration: const InputDecoration(labelText: '验证码'),
                          textInputAction: TextInputAction.done,
                          onSubmitted: (_) => _submit(),
                          onChanged: (_) => _clearAuthError(),
                        ),
                      ),
                      const SizedBox(width: 12),
                      // 放大验证码点击热区至 56 高，并补充语义标签（LOGIN-02）
                      Semantics(
                        button: true,
                        label: '图形验证码，点按刷新',
                        child: Tooltip(
                          message: '点击刷新验证码',
                          child: InkWell(
                            onTap: _loadingCaptcha ? null : _refreshCaptcha,
                            borderRadius: BorderRadius.circular(8),
                            child: Container(
                              width: 140,
                              height: 56,
                              alignment: Alignment.center,
                              decoration: BoxDecoration(
                                color: AppColors.bgCard,
                                borderRadius: BorderRadius.circular(8),
                                border: Border.all(color: AppColors.border),
                              ),
                              child: _loadingCaptcha
                                  ? const SizedBox(
                                      width: 20,
                                      height: 20,
                                      child: CircularProgressIndicator(strokeWidth: 2),
                                    )
                                  : _captcha == null
                                      ? const Text(
                                          '点击刷新',
                                          style: TextStyle(fontSize: 12),
                                        )
                                      : Image.memory(
                                          Uint8List.fromList(
                                            _captcha!.imageBytes,
                                          ),
                                          fit: BoxFit.contain,
                                          gaplessPlayback: true,
                                        ),
                            ),
                          ),
                        ),
                      ),
                    ],
                  ),
                  const SizedBox(height: 4),
                  Row(
                    children: [
                      SizedBox(
                        width: 40,
                        height: 40,
                        child: Checkbox(
                          value: _remember,
                          onChanged: (v) =>
                              setState(() => _remember = v ?? false),
                        ),
                      ),
                      const Text(
                        '记住用户名',
                        style: TextStyle(color: AppColors.textSecondary),
                      ),
                      const Spacer(),
                      TextButton(
                        onPressed: _showForgotPasswordDialog,
                        child: const Text('忘记密码？'),
                      ),
                    ],
                  ),
                  if (auth.error != null) ...[
                    const SizedBox(height: 8),
                    Text(
                      auth.error!,
                      style: const TextStyle(color: AppColors.red),
                    ),
                  ],
                  const SizedBox(height: 24),
                  ElevatedButton(
                    onPressed: auth.isLoading ? null : _submit,
                    child: auth.isLoading
                        ? const SizedBox(
                            width: 22,
                            height: 22,
                            child: CircularProgressIndicator(strokeWidth: 2),
                          )
                        : const Text('登录'),
                  ),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }
}
