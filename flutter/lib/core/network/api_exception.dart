/// 将 FastAPI `detail`（string / map / 422 数组）统一成可读错误。
class ApiException implements Exception {
  ApiException(
    this.message, {
    this.statusCode,
    this.code,
    this.feature,
  });

  final String message;
  final int? statusCode;
  final String? code;
  final String? feature;

  bool get isUnauthorized => statusCode == 401;
  bool get isForbidden => statusCode == 403;

  factory ApiException.fromResponse(int? statusCode, dynamic data) {
    final detail = data is Map ? data['detail'] : data;
    if (detail is String) {
      return ApiException(detail, statusCode: statusCode);
    }
    if (detail is Map) {
      return ApiException(
        (detail['message'] ?? detail['msg'] ?? '请求失败').toString(),
        statusCode: statusCode,
        code: detail['code']?.toString(),
        feature: detail['feature']?.toString(),
      );
    }
    if (detail is List && detail.isNotEmpty) {
      final parts = <String>[];
      for (final item in detail) {
        if (item is Map) {
          parts.add((item['msg'] ?? item['message'] ?? item.toString()).toString());
        } else {
          parts.add(item.toString());
        }
      }
      return ApiException(parts.join('；'), statusCode: statusCode);
    }
    if (data is Map && data['message'] != null) {
      return ApiException(data['message'].toString(), statusCode: statusCode);
    }
    return ApiException('请求失败', statusCode: statusCode);
  }

  @override
  String toString() => message;
}
