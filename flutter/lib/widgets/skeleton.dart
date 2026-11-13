import 'package:flutter/material.dart';

import '../core/theme.dart';

/// 骨架占位块，用于列表/卡片加载态，替代旋转指示器。
class SkeletonBox extends StatelessWidget {
  const SkeletonBox({
    super.key,
    this.width,
    this.height = 12,
    this.radius = 6,
  });

  final double? width;
  final double height;
  final double radius;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: width,
      height: height,
      decoration: BoxDecoration(
        color: AppColors.bgSecondary,
        borderRadius: BorderRadius.circular(radius),
      ),
    );
  }
}

/// 卡片式骨架，模拟一张内容卡片的排版。
class SkeletonCard extends StatelessWidget {
  const SkeletonCard({super.key, this.height = 96, this.showTitle = true});

  final double height;
  final bool showTitle;

  @override
  Widget build(BuildContext context) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(14),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            if (showTitle) ...[
              const SkeletonBox(width: 140, height: 16),
              const SizedBox(height: 10),
            ],
            SkeletonBox(
              width: double.infinity,
              height: showTitle ? height - 40 : height,
            ),
          ],
        ),
      ),
    );
  }
}

/// 纵向一列骨架卡片，用于页面级加载态。
class SkeletonList extends StatelessWidget {
  const SkeletonList({super.key, this.count = 6, this.cardHeight = 96});

  final int count;
  final double cardHeight;

  @override
  Widget build(BuildContext context) {
    return ListView.separated(
      padding: const EdgeInsets.all(16),
      itemCount: count,
      itemBuilder: (_, _) => SkeletonCard(height: cardHeight),
      separatorBuilder: (_, _) => const SizedBox(height: 10),
    );
  }
}
