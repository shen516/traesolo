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

  @override
  Widget build(BuildContext context) {
    final text = empty
        ? (message ?? '暂无数据')
        : (error is ApiException ? (error as ApiException).message : error.toString());

    return Center(
      child: Padding(
        padding: const EdgeInsets.all(24),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(
              empty ? Icons.inbox_outlined : Icons.error_outline,
              color: AppColors.textMuted,
              size: 36,
            ),
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
