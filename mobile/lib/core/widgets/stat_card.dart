import 'package:flutter/material.dart';

import '../theme/app_spacing.dart';
import 'app_card.dart';

/// Statistika kartasi — ikona + label + qiymat + ixtiyoriy trend indikatori.
///
/// Retail dashboardlari uchun: sotuv, yetkazish, davomat va boshqa
/// ko'rsatkichlarni vizual aks ettirish.
///
/// ```dart
/// StatCard(
///   icon: Icons.receipt_long,
///   label: 'Buyurtmalar',
///   value: '142',
///   trendValue: '+12%',
///   trendUp: true,
///   accentColor: Colors.blue,
/// )
/// ```
class StatCard extends StatelessWidget {
  const StatCard({
    super.key,
    required this.icon,
    required this.label,
    required this.value,
    this.trendValue,
    this.trendUp,
    this.accentColor,
    this.subtitle,
    this.onTap,
    this.isLoading = false,
    this.iconSize = AppSpacing.iconLg,
  });

  /// Material icon.
  final IconData icon;

  /// Pastki qisqdacha tavsif (masalan: "Bugungi buyurtmalar").
  final String label;

  /// Asosiy raqam/qiymat (masalan: "1 250 000").
  final String value;

  /// Trend matni — ixtiyoriy (masalan: "+8%", "-3").
  final String? trendValue;

  /// Trend yo'nalishi: true = ko'tarilmoqda, false = tushmoqda, null = neytral.
  final bool? trendUp;

  /// Ixtiyoriy aksent rang (icon, trend rangi uchun asos).
  /// Null bo'lsa [ColorScheme.primary] ishlatiladi.
  final Color? accentColor;

  /// Qo'shimcha kichik matn (pastda).
  final String? subtitle;

  final VoidCallback? onTap;

  /// Skeleton loading holati.
  final bool isLoading;

  final double iconSize;

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    final tt = Theme.of(context).textTheme;
    final accent = accentColor ?? cs.primary;

    if (isLoading) {
      return AppCard(child: _Skeleton());
    }

    return AppCard(
      onTap: onTap,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        mainAxisSize: MainAxisSize.min,
        children: [
          // Icon + trend (top row)
          Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Container(
                width: iconSize + AppSpacing.md,
                height: iconSize + AppSpacing.md,
                decoration: BoxDecoration(
                  color: accent.withValues(alpha: 0.1),
                  borderRadius: BorderRadius.circular(AppSpacing.radiusSm),
                ),
                child: Icon(icon, color: accent, size: iconSize),
              ),
              const Spacer(),
              if (trendValue != null) _TrendBadge(value: trendValue!, up: trendUp),
            ],
          ),

          const SizedBox(height: AppSpacing.md),

          // Qiymat
          Text(
            value,
            style: tt.headlineSmall?.copyWith(
              fontWeight: FontWeight.w700,
              color: cs.onSurface,
              letterSpacing: -0.5,
            ),
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
          ),

          const SizedBox(height: AppSpacing.xs),

          // Label
          Text(
            label,
            style: tt.bodySmall?.copyWith(color: cs.onSurfaceVariant),
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
          ),

          if (subtitle != null) ...[
            const SizedBox(height: AppSpacing.xs),
            Text(
              subtitle!,
              style: tt.labelSmall?.copyWith(
                color: cs.onSurfaceVariant.withValues(alpha: 0.7),
              ),
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
            ),
          ],
        ],
      ),
    );
  }
}

class _TrendBadge extends StatelessWidget {
  const _TrendBadge({required this.value, this.up});
  final String value;
  final bool? up;

  @override
  Widget build(BuildContext context) {
    final isDark = Theme.of(context).brightness == Brightness.dark;
    Color color;
    IconData iconData;

    if (up == null) {
      color = Theme.of(context).colorScheme.onSurfaceVariant;
      iconData = Icons.remove;
    } else if (up!) {
      color = isDark ? const Color(0xFF4ADE80) : const Color(0xFF15803D);
      iconData = Icons.trending_up;
    } else {
      color = isDark ? const Color(0xFFF87171) : const Color(0xFFDC2626);
      iconData = Icons.trending_down;
    }

    return Container(
      padding: const EdgeInsets.symmetric(
          horizontal: AppSpacing.sm, vertical: AppSpacing.xs),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.1),
        borderRadius: BorderRadius.circular(AppSpacing.radiusXs),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(iconData, size: 12, color: color),
          const SizedBox(width: 2),
          Text(
            value,
            style: TextStyle(
              fontSize: 11,
              fontWeight: FontWeight.w600,
              color: color,
            ),
          ),
        ],
      ),
    );
  }
}

class _Skeleton extends StatelessWidget {
  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    final base = cs.surfaceContainerHighest;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      mainAxisSize: MainAxisSize.min,
      children: [
        Container(
          width: 44,
          height: 44,
          decoration: BoxDecoration(
            color: base,
            borderRadius: BorderRadius.circular(AppSpacing.radiusSm),
          ),
        ),
        const SizedBox(height: AppSpacing.md),
        Container(
          width: 80,
          height: 28,
          decoration: BoxDecoration(
            color: base,
            borderRadius: BorderRadius.circular(AppSpacing.radiusXs),
          ),
        ),
        const SizedBox(height: AppSpacing.xs),
        Container(
          width: 120,
          height: 14,
          decoration: BoxDecoration(
            color: base.withValues(alpha: 0.6),
            borderRadius: BorderRadius.circular(AppSpacing.radiusXs),
          ),
        ),
      ],
    );
  }
}
