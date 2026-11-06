/// API 与运行配置。
///
/// 环境示例：
/// ```
/// flutter run --dart-define=APP_ENV=dev --dart-define=API_BASE_URL=http://10.0.2.2:8000/api/v1
/// flutter build apk --release --dart-define=APP_ENV=prod --dart-define=API_BASE_URL=https://api.example.com/api/v1
/// ```
class AppConfig {
  AppConfig._();

  /// 品牌英文名（代码 / 包名沿用 TraeSolo）
  static const String brandEn = 'TraeSolo';

  /// 应用显示名
  static const String appName = '欢哥竞球';

  /// 副标题
  static const String appTagline = '足球 · 篮球竞技量化分析';

  /// 系统任务栏 / 多任务标题
  static const String appTitle = appName;

  /// `dev` | `staging` | `prod`
  static const String appEnv = String.fromEnvironment(
    'APP_ENV',
    defaultValue: 'dev',
  );

  static bool get isProd => appEnv == 'prod';

  /// 默认指向联调/部署机；生产必须用 HTTPS 的 `--dart-define=API_BASE_URL=...`
  static const String apiBaseUrl = String.fromEnvironment(
    'API_BASE_URL',
    defaultValue: 'http://14.118.168.216:5173/api/v1',
  );

  /// API 同源根（去掉 `/api/v1`），用于 `/static/` 队徽等静态资源。
  static String get apiOrigin {
    var base = apiBaseUrl.trim();
    while (base.endsWith('/')) {
      base = base.substring(0, base.length - 1);
    }
    const suffix = '/api/v1';
    if (base.endsWith(suffix)) {
      return base.substring(0, base.length - suffix.length);
    }
    return base;
  }

  /// 生产构建若误用明文 HTTP，启动时可告警（不阻断调试）。
  static bool get apiUsesHttps =>
      apiBaseUrl.startsWith('https://') || apiBaseUrl.startsWith('https:');

  static const String disclaimer =
      '仅供学习研究与数据分析，不构成任何投注建议。';

  /// 与 pubspec.yaml version 对齐（关于页展示）
  static const String appVersion = '1.0.0+1';

  static const Duration connectTimeout = Duration(seconds: 15);
  static const Duration receiveTimeout = Duration(seconds: 30);

  /// 单场模拟（蒙特卡洛）可能较慢
  static const Duration simulateReceiveTimeout = Duration(seconds: 120);

  /// App 侧默认模拟次数（后端允许 1000～50000）
  static const int defaultSimulations = 5000;

  /// App 侧可选上限，避免手机端过长等待
  static const int maxAppSimulations = 20000;

  /// λ 敏感性默认模拟次数（后端默认 2000，上限 10000）
  static const int defaultSensitivitySimulations = 2000;

  /// App 侧敏感性扫描上限，避免手机端过久
  static const int maxSensitivitySimulations = 5000;

  /// 列表分页默认每页条数
  static const int pageSize = 20;

  /// 赛事详情离线缓存保留条数（LRU）
  static const int detailCacheMaxEntries = 20;

  /// 赛事详情离线缓存有效期；过期仍可作兜底展示
  static const Duration detailCacheTtl = Duration(hours: 24);
}
