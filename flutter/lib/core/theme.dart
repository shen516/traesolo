import 'package:flutter/material.dart';

/// 对齐 Web `main.css` 深色职业分析色板。
class AppColors {
  AppColors._();

  static const bgPrimary = Color(0xFF0D1B30);
  static const bgSecondary = Color(0xFF132544);
  static const bgCard = Color(0xFF1A3358);
  static const bgHover = Color(0xFF23406A);
  static const border = Color(0xFF2D4F7A);

  static const textPrimary = Color(0xFFF4F8FD);
  static const textSecondary = Color(0xFFC5D2E6);
  static const textMuted = Color(0xFF9AADC8);

  static const gold = Color(0xFFFFD700);
  static const green = Color(0xFF3DFF9A);
  static const blue = Color(0xFF4DE0FF);
  static const red = Color(0xFFFF6B78);
  static const orange = Color(0xFFFFB14A);
}

ThemeData buildAppTheme() {
  final base = ThemeData(
    useMaterial3: true,
    brightness: Brightness.dark,
    scaffoldBackgroundColor: AppColors.bgPrimary,
    colorScheme: const ColorScheme.dark(
      primary: AppColors.blue,
      secondary: AppColors.gold,
      surface: AppColors.bgSecondary,
      error: AppColors.red,
      onPrimary: AppColors.bgPrimary,
      onSecondary: AppColors.bgPrimary,
      onSurface: AppColors.textPrimary,
      onError: AppColors.textPrimary,
    ),
  );

  return base.copyWith(
    appBarTheme: const AppBarTheme(
      backgroundColor: AppColors.bgSecondary,
      foregroundColor: AppColors.textPrimary,
      elevation: 0,
      centerTitle: true,
    ),
    cardTheme: CardThemeData(
      color: AppColors.bgCard,
      elevation: 0,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(10),
        side: const BorderSide(color: AppColors.border),
      ),
    ),
    inputDecorationTheme: InputDecorationTheme(
      filled: true,
      fillColor: AppColors.bgCard,
      labelStyle: const TextStyle(color: AppColors.textMuted),
      hintStyle: const TextStyle(color: AppColors.textMuted),
      border: OutlineInputBorder(
        borderRadius: BorderRadius.circular(10),
        borderSide: const BorderSide(color: AppColors.border),
      ),
      enabledBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(10),
        borderSide: const BorderSide(color: AppColors.border),
      ),
      focusedBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(10),
        borderSide: const BorderSide(color: AppColors.blue),
      ),
    ),
    elevatedButtonTheme: ElevatedButtonThemeData(
      style: ElevatedButton.styleFrom(
        backgroundColor: AppColors.blue,
        foregroundColor: AppColors.bgPrimary,
        minimumSize: const Size.fromHeight(48),
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(10)),
      ),
    ),
    navigationBarTheme: NavigationBarThemeData(
      backgroundColor: AppColors.bgSecondary,
      indicatorColor: AppColors.bgHover,
      labelTextStyle: WidgetStatePropertyAll(
        const TextStyle(color: AppColors.textSecondary, fontSize: 12),
      ),
    ),
    snackBarTheme: const SnackBarThemeData(
      backgroundColor: AppColors.bgCard,
      contentTextStyle: TextStyle(color: AppColors.textPrimary),
    ),
    dividerColor: AppColors.border,
    textTheme: base.textTheme.apply(
      bodyColor: AppColors.textPrimary,
      displayColor: AppColors.textPrimary,
    ),
  );
}
