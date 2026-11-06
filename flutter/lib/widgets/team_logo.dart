import 'package:cached_network_image/cached_network_image.dart';
import 'package:flutter/material.dart';

import '../core/media.dart';
import '../core/theme.dart';

class TeamLogo extends StatelessWidget {
  const TeamLogo({
    super.key,
    this.url,
    this.size = 28,
    this.fallback = '⚽',
    this.semanticLabel,
  });

  final String? url;
  final double size;
  final String fallback;
  final String? semanticLabel;

  @override
  Widget build(BuildContext context) {
    final resolved = resolveMediaUrl(url);
    final label = semanticLabel ?? '队徽';

    Widget child;
    if (resolved == null) {
      child = SizedBox(
        width: size,
        height: size,
        child: Center(
          child: Text(fallback, style: TextStyle(fontSize: size * 0.55)),
        ),
      );
    } else {
      final px = (size * MediaQuery.devicePixelRatioOf(context)).round();
      child = ClipRRect(
        borderRadius: BorderRadius.circular(size / 5),
        child: CachedNetworkImage(
          imageUrl: resolved,
          width: size,
          height: size,
          fit: BoxFit.cover,
          memCacheWidth: px,
          memCacheHeight: px,
          fadeInDuration: const Duration(milliseconds: 180),
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

    return Semantics(
      label: label,
      image: true,
      child: child,
    );
  }
}
