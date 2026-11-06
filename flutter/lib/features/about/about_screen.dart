import 'package:flutter/material.dart';

import '../../core/config.dart';
import '../../core/theme.dart';

class AboutScreen extends StatelessWidget {
  const AboutScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('关于')),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          Card(
            child: Padding(
              padding: const EdgeInsets.all(20),
              child: Column(
                children: [
                  const Icon(Icons.sports_soccer, size: 48, color: AppColors.gold),
                  const SizedBox(height: 12),
                  Text(
                    AppConfig.appName,
                    style: const TextStyle(fontSize: 22, fontWeight: FontWeight.w700),
                  ),
                  const SizedBox(height: 4),
                  Text(
                    AppConfig.brandEn,
                    style: const TextStyle(color: AppColors.textMuted),
                  ),
                  const SizedBox(height: 8),
                  Text(
                    '版本 ${AppConfig.appVersion}',
                    style: const TextStyle(color: AppColors.textSecondary, fontSize: 13),
                  ),
                  const SizedBox(height: 4),
                  Text(
                    '环境 ${AppConfig.appEnv}'
                    '${AppConfig.isProd ? '' : ' · 非生产'}',
                    style: const TextStyle(color: AppColors.textMuted, fontSize: 12),
                  ),
                  const SizedBox(height: 8),
                  const Text(
                    AppConfig.appTagline,
                    textAlign: TextAlign.center,
                    style: TextStyle(color: AppColors.textSecondary),
                  ),
                ],
              ),
            ),
          ),
          const SizedBox(height: 12),
          const Card(
            child: Padding(
              padding: EdgeInsets.all(16),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    '产品说明',
                    style: TextStyle(fontSize: 16, fontWeight: FontWeight.w600),
                  ),
                  SizedBox(height: 8),
                  Text(
                    '欢哥竞球是足球竞技量化分析的消费端客户端，用于浏览赛事、联赛数据与模型预测结果。'
                    '模型训练、数据采集与权限配置请在 Web 运营端完成。',
                    style: TextStyle(color: AppColors.textSecondary, height: 1.45),
                  ),
                ],
              ),
            ),
          ),
          const SizedBox(height: 12),
          Card(
            child: Padding(
              padding: const EdgeInsets.all(16),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const Text(
                    '免责声明',
                    style: TextStyle(fontSize: 16, fontWeight: FontWeight.w600),
                  ),
                  const SizedBox(height: 8),
                  const Text(
                    AppConfig.disclaimer,
                    style: TextStyle(color: AppColors.textMuted, height: 1.45),
                  ),
                  const SizedBox(height: 10),
                  Text(
                    '本应用不提供投注建议，不引导任何形式的赌博行为。',
                    style: TextStyle(
                      color: AppColors.orange.withValues(alpha: 0.95),
                      height: 1.4,
                      fontSize: 13,
                    ),
                  ),
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }
}
