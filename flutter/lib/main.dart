import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'app.dart';
import 'core/config.dart';

void main() {
  WidgetsFlutterBinding.ensureInitialized();
  if (AppConfig.isProd && !AppConfig.apiUsesHttps) {
    debugPrint(
      '警告: APP_ENV=prod 但 API_BASE_URL 非 HTTPS，请用 dart-define 修正。',
    );
  }
  runApp(const ProviderScope(child: TraeSoloApp()));
}
