import 'package:flutter/material.dart';

import '../theme/app_spacing.dart';
import '../theme/app_theme.dart';

/// Holat ko'rsatuvchi badge (chip-style).
///
/// [StatusVariant] yoki maxsus [color]/[backgroundColor] orqali rang beriladi.
/// Retail tizimida buyurtma, yetkazma, to'lov holatlari uchun ishlatiladi.
///
/// ```dart
/// StatusBadge(status: 'synced')
/// StatusBadge(status: 'pending', variant: StatusVariant.warning)
/// StatusBadge(status: 'Xato', variant: StatusVariant.danger)
/// ```
enum StatusVariant { success, warning, danger, info, neutral }

class StatusBadge extends StatelessWidget {
  const StatusBadge({
    super.key,
    required this.status,
    this.variant,
    this.icon,
    this.size = StatusBadgeSize.medium,
    this.filled = false,
  });

  /// Ko'rsatiladigan matn.
  final String status;

  /// Rang varianti. Null bo'lsa [_variantFromStatus] orqali avtomatik aniqlanadi.
  final StatusVariant? variant;

  /// Ixtiyoriy kichik icon (textdan oldin).
  final IconData? icon;

  final StatusBadgeSize size;

  /// true = to'liq rangli fon; false = shaffof fon + chegarali (default).
  final bool filled;

  @override
  Widget build(BuildContext context) {
    final isDark = Theme.of(context).brightness == Brightness.dark;
    final cs = Theme.of(context).colorScheme;
    final appColors = AppTheme.colorsOf(context);
    final tt = Theme.of(context).textTheme;

    final effectiveVariant = variant ?? _variantFromStatus(status);
    final (fgColor, bgColor) = _resolveColors(
      effectiveVariant,
      appColors,
      cs,
      isDark,
      filled,
    );

    final textStyle = switch (size) {
      StatusBadgeSize.small => tt.labelSmall?.copyWith(
          color: fgColor,
          fontWeight: FontWeight.w600,
        ),
      StatusBadgeSize.medium => tt.labelMedium?.copyWith(
          color: fgColor,
          fontWeight: FontWeight.w600,
        ),
      StatusBadgeSize.large => tt.labelLarge?.copyWith(
          color: fgColor,
          fontWeight: FontWeight.w600,
        ),
    };

    final (hPad, vPad, iconSz) = switch (size) {
      StatusBadgeSize.small => (6.0, 2.0, 10.0),
      StatusBadgeSize.medium => (AppSpacing.sm, AppSpacing.xs, 12.0),
      StatusBadgeSize.large => (AppSpacing.md, 6.0, 14.0),
    };

    return Container(
      padding: EdgeInsets.symmetric(horizontal: hPad, vertical: vPad),
      decoration: BoxDecoration(
        color: bgColor,
        borderRadius: BorderRadius.circular(AppSpacing.radiusXs + 2),
        border: filled
            ? null
            : Border.all(color: fgColor.withValues(alpha: 0.3)),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          if (icon != null) ...[
            Icon(icon, size: iconSz, color: fgColor),
            const SizedBox(width: 3),
          ],
          Text(status, style: textStyle),
        ],
      ),
    );
  }

  static (Color fg, Color bg) _resolveColors(
    StatusVariant variant,
    AppColors appColors,
    ColorScheme cs,
    bool isDark,
    bool filled,
  ) {
    return switch (variant) {
      StatusVariant.success => (
          appColors.success,
          filled
              ? appColors.success
              : appColors.successContainer.withValues(alpha: isDark ? 0.3 : 0.5),
        ),
      StatusVariant.warning => (
          appColors.warning,
          filled
              ? appColors.warning
              : appColors.warningContainer.withValues(alpha: isDark ? 0.3 : 0.5),
        ),
      StatusVariant.danger => (
          appColors.danger,
          filled
              ? appColors.danger
              : appColors.dangerContainer.withValues(alpha: isDark ? 0.3 : 0.5),
        ),
      StatusVariant.info => (
          appColors.info,
          filled
              ? appColors.info
              : appColors.infoContainer.withValues(alpha: isDark ? 0.3 : 0.5),
        ),
      StatusVariant.neutral => (
          cs.onSurfaceVariant,
          filled
              ? cs.onSurfaceVariant
              : cs.surfaceContainerHighest,
        ),
    };
  }

  /// Matn asosida avtomatik variant aniqlaydi (uzbekcha + inglizcha).
  static StatusVariant _variantFromStatus(String status) {
    final s = status.toLowerCase();
    if (s == 'synced' ||
        s == 'delivered' ||
        s == 'yetkazildi' ||
        s == 'tasdiqlandi' ||
        s == 'paid' ||
        s == 'active' ||
        s == 'faol' ||
        s == 'completed') {
      return StatusVariant.success;
    }
    if (s == 'pending' ||
        s == 'kutilmoqda' ||
        s == 'in_transit' ||
        s == 'processing' ||
        s == 'partially') {
      return StatusVariant.warning;
    }
    if (s == 'error' ||
        s == 'failed' ||
        s == 'xato' ||
        s == 'cancelled' ||
        s == 'rejected' ||
        s == 'bekor') {
      return StatusVariant.danger;
    }
    if (s == 'info' || s == 'draft' || s == 'new' || s == 'yangi') {
      return StatusVariant.info;
    }
    return StatusVariant.neutral;
  }
}

enum StatusBadgeSize { small, medium, large }
