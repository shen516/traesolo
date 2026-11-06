/// API 与运行配置。
///
/// 真机调试请传局域网后端地址，例如：
/// `flutter run --dart-define=API_BASE_URL=http://192.168.1.8:8000/api/v1`
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

  /// 默认指向联调/部署机；可用 --dart-define=API_BASE_URL=... 覆盖
  static const String apiBaseUrl = String.fromEnvironment(
    'API_BASE_URL',
    defaultValue: 'http://14.118.168.216:5173/api/v1',
  );

  static const String disclaimer =
      '仅供学习研究与数据分析，不构成任何投注建议。';

  static const Duration connectTimeout = Duration(seconds: 15);
  static const Duration receiveTimeout = Duration(seconds: 30);
}
