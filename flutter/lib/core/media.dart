import 'config.dart';

/// 对齐 Web `frontend/src/utils/media.js`：绝对 URL 原样；`/static/` 拼 API 同源。
String? resolveMediaUrl(String? src) {
  final raw = src?.trim() ?? '';
  if (raw.isEmpty) return null;
  if (raw.startsWith('http://') || raw.startsWith('https://')) return raw;
  if (raw.startsWith('/static/')) return '${AppConfig.apiOrigin}$raw';
  return null;
}

bool isResolvableMedia(String? src) => resolveMediaUrl(src) != null;
