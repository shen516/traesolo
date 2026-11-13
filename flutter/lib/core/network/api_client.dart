import 'package:dio/dio.dart';

import '../config.dart';
import 'api_exception.dart';

typedef TokenReader = Future<String?> Function();
typedef UnauthorizedHandler = Future<void> Function();

/// Dio 封装：自动挂 Bearer，统一解析 FastAPI 错误。
class ApiClient {
  ApiClient({
    required this._readToken,
    required this._onUnauthorized,
    String? baseUrl,
  }) {
    _dio = Dio(
      BaseOptions(
        baseUrl: (baseUrl ?? AppConfig.apiBaseUrl).replaceAll(RegExp(r'/+$'), ''),
        connectTimeout: AppConfig.connectTimeout,
        receiveTimeout: AppConfig.receiveTimeout,
        headers: const {'Content-Type': 'application/json', 'Accept': 'application/json'},
      ),
    );

    _dio.interceptors.add(
      InterceptorsWrapper(
        onRequest: (options, handler) async {
          final token = await _readToken();
          if (token != null && token.isNotEmpty) {
            options.headers['Authorization'] = 'Bearer $token';
          }
          handler.next(options);
        },
        onError: (error, handler) async {
          final response = error.response;
          if (response != null) {
            final ex = ApiException.fromResponse(response.statusCode, response.data);
            final path = error.requestOptions.path;
            final isAuthEndpoint =
                path.contains('/auth/login') || path.contains('/auth/captcha');
            if (ex.isUnauthorized && !isAuthEndpoint) {
              await _onUnauthorized();
            }
            handler.reject(
              DioException(
                requestOptions: error.requestOptions,
                response: response,
                type: error.type,
                error: ex,
                message: ex.message,
              ),
            );
            return;
          }
          handler.reject(
            DioException(
              requestOptions: error.requestOptions,
              type: error.type,
              error: ApiException(error.message ?? '网络异常'),
              message: error.message,
            ),
          );
        },
      ),
    );
  }

  late final Dio _dio;
  final TokenReader _readToken;
  final UnauthorizedHandler _onUnauthorized;

  Dio get dio => _dio;

  Future<T> get<T>(
    String path, {
    Map<String, dynamic>? queryParameters,
    T Function(dynamic data)? parser,
  }) async {
    try {
      final res = await _dio.get<dynamic>(path, queryParameters: queryParameters);
      final data = res.data;
      if (parser != null) return parser(data);
      return data as T;
    } on DioException catch (e) {
      throw _unwrap(e);
    }
  }

  Future<T> post<T>(
    String path, {
    Object? data,
    Map<String, dynamic>? queryParameters,
    T Function(dynamic data)? parser,
    Duration? receiveTimeout,
    CancelToken? cancelToken,
  }) async {
    try {
      final res = await _dio.post<dynamic>(
        path,
        data: data,
        queryParameters: queryParameters,
        cancelToken: cancelToken,
        options: receiveTimeout == null
            ? null
            : Options(receiveTimeout: receiveTimeout),
      );
      final body = res.data;
      if (parser != null) return parser(body);
      return body as T;
    } on DioException catch (e) {
      // 用户主动取消：保持 DioException 原样抛出，交由调用方静默处理
      if (e.type == DioExceptionType.cancel) rethrow;
      throw _unwrap(e);
    }
  }

  Future<T> put<T>(
    String path, {
    Object? data,
    Map<String, dynamic>? queryParameters,
    T Function(dynamic data)? parser,
  }) async {
    try {
      final res = await _dio.put<dynamic>(
        path,
        data: data,
        queryParameters: queryParameters,
      );
      final body = res.data;
      if (parser != null) return parser(body);
      return body as T;
    } on DioException catch (e) {
      throw _unwrap(e);
    }
  }

  Future<T> delete<T>(
    String path, {
    Object? data,
    Map<String, dynamic>? queryParameters,
    T Function(dynamic data)? parser,
  }) async {
    try {
      final res = await _dio.delete<dynamic>(
        path,
        data: data,
        queryParameters: queryParameters,
      );
      final body = res.data;
      if (parser != null) return parser(body);
      return body as T;
    } on DioException catch (e) {
      throw _unwrap(e);
    }
  }

  ApiException _unwrap(DioException e) {
    final err = e.error;
    if (err is ApiException) return err;
    return ApiException(e.message ?? '网络异常', statusCode: e.response?.statusCode);
  }
}
