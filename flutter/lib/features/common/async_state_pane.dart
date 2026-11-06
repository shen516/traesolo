import 'package:flutter/material.dart';

import '../../core/network/api_exception.dart';
import '../../core/theme.dart';

class AsyncStatePane extends StatelessWidget {
  const AsyncStatePane.error({
    super.key,
    required this.error,
    required this.onRetry,
  })  : message = null,
        empty = false;

  const AsyncStatePane.empty({
    super.key,
    required this.message,
    this.onRetry,
  })  : error = null,
        empty = true;

  final Object? error;
  final String? message;
  final VoidCallback? onRetry;
  final bool empty;

  static String describeError(Object? error) {
    if (error is ApiException) {
      if (error.isUnauthorized) {
        return '登录已失效，请重新登录';
      }
      if (error.isForbidden) {
        return error.message.isNotEmpty
            ? error.message
            : '当前账号无权查看该内容';
      }
      if (error.statusCode == null) {
        return '网络异常，请检查连接后重试';
      }
      return error.message;
    }
    final text = error?.toString() ?? '请求失败';
    if (text.contains('SocketException') ||
        text.contains('Connection') ||
        text.contains('网络')) {
      return '网络异常，请检查连接后重试';
    }
    return text;
  }

  @override
  Widget build(BuildContext context) {
    final text = empty ? (message ?? '暂无数据') : describeError(error);
    final icon = empty
        ? Icons.inbox_outlined
        : (error is ApiException && (error as ApiException).isForbidden
            ? Icons.lock_outline
            : Icons.error_outline);

    return Center(
      child: Padding(
        padding: const EdgeInsets.all(24),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(icon, color: AppColors.textMuted, size: 36),
            const SizedBox(height: 12),
            Text(
              text,
              textAlign: TextAlign.center,
              style: const TextStyle(color: AppColors.textSecondary),
            ),
            if (onRetry != null) ...[
              const SizedBox(height: 12),
              ElevatedButton(
                onPressed: onRetry,
                child: Text(empty ? '刷新' : '重试'),
              ),
            ],
          ],
        ),
      ),
    );
  }
}
