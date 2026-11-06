import 'package:cached_network_image/cached_network_image.dart';
import 'package:flutter/material.dart';

import '../core/theme.dart';

class TeamLogo extends StatelessWidget {
  const TeamLogo({
    super.key,
    this.url,
    this.size = 28,
    this.fallback = '⚽',
  });

  final String? url;
  final double size;
  final String fallback;

  @override
  Widget build(BuildContext context) {
    final src = url?.trim() ?? '';
    if (src.isEmpty || !(src.startsWith('http://') || src.startsWith('https://') || src.startsWith('/'))) {
      return SizedBox(
        width: size,
        height: size,
        child: Center(
          child: Text(fallback, style: TextStyle(fontSize: size * 0.55)),
        ),
      );
    }

    // 相对路径时交给后端静态资源：调用方应传完整 URL；此处兜底显示占位。
    if (src.startsWith('/')) {
      return SizedBox(
        width: size,
        height: size,
        child: Center(
          child: Text(fallback, style: TextStyle(fontSize: size * 0.55)),
        ),
      );
    }

    return ClipRRect(
      borderRadius: BorderRadius.circular(size / 5),
      child: CachedNetworkImage(
        imageUrl: src,
        width: size,
        height: size,
        fit: BoxFit.cover,
        placeholder: (context, _) => Container(
          width: size,
          height: size,
          color: AppColors.bgSecondary,
        ),
        errorWidget: (context, url, error) => SizedBox(
          width: size,
          height: size,
          child: Center(
            child: Text(fallback, style: TextStyle(fontSize: size * 0.55)),
          ),
        ),
      ),
    );
  }
}
