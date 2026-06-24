import 'package:flutter/material.dart';

import '../theme/app_spacing.dart';

/// Dashboard yuqori qismi — salom + ism + avatar/ikona + gradient fon.
///
/// Har bir rol (agent, courier, store, accountant) dashboardida
/// bir xil pattern bilan ishlatiladig uniform header widget.
///
/// ```dart
/// DashboardHeader(
///   greeting: 'Salom,',
///   name: 'Bobur Karimov',
///   subtitle: '24 iyun 2026',
///   avatarInitials: 'BK',
///   role: 'Agent',
/// )
/// ```
class DashboardHeader extends StatelessWidget {
  const DashboardHeader({
    super.key,
    required this.greeting,
    required this.name,
    this.subtitle,
    this.role,
    this.avatarInitials,
    this.avatarIcon,
    this.trailing,
    this.useGradient = true,
    this.padding,
  }) : assert(
          avatarInitials != null || avatarIcon != null,
          'avatarInitials yoki avatarIcon kerak',
        );

  final String greeting;
  final String name;
  final String? subtitle;

  /// Rol tegi — top-right chip sifatida ko'rinadi.
  final String? role;

  /// Avatar harflari (masalan: "BK"). avatarIcon'dan ustunlik qiladi.
  final String? avatarInitials;

  /// avatarInitials null bo'lganda ko'rsatiladigan icon.
  final IconData? avatarIcon;

  /// O'ng tomonga qo'yiladigan ixtiyoriy widget (masalan notification bell).
  final Widget? trailing;

  /// Gradient fon (true — default).
  final bool useGradient;

  final EdgeInsetsGeometry? padding;

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    final tt = Theme.of(context).textTheme;

    final bgDecoration = useGradient
        ? BoxDecoration(
            gradient: LinearGradient(
              colors: [
                cs.primary,
                cs.primary.withValues(alpha: 0.85),
              ],
              begin: Alignment.topLeft,
              end: Alignment.bottomRight,
            ),
            borderRadius: BorderRadius.circular(AppSpacing.radiusXl),
          )
        : BoxDecoration(
            color: cs.primaryContainer,
            borderRadius: BorderRadius.circular(AppSpacing.radiusXl),
          );

    final onBg = useGradient ? cs.onPrimary : cs.onPrimaryContainer;
    final onBgMuted = onBg.withValues(alpha: 0.75);

    return Container(
      width: double.infinity,
      padding: padding ??
          const EdgeInsets.symmetric(
              horizontal: AppSpacing.lg, vertical: AppSpacing.lg),
      decoration: bgDecoration,
      child: Row(
        children: [
          // Sol: matn
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              mainAxisSize: MainAxisSize.min,
              children: [
                if (role != null)
                  Container(
                    padding: const EdgeInsets.symmetric(
                        horizontal: AppSpacing.sm, vertical: 2),
                    decoration: BoxDecoration(
                      color: onBg.withValues(alpha: 0.15),
                      borderRadius:
                          BorderRadius.circular(AppSpacing.radiusXs),
                    ),
                    child: Text(
                      role!,
                      style: tt.labelSmall?.copyWith(
                        color: onBgMuted,
                        fontWeight: FontWeight.w600,
                        letterSpacing: 0.8,
                      ),
                    ),
                  ),
                if (role != null) const SizedBox(height: AppSpacing.xs),
                RichText(
                  text: TextSpan(
                    children: [
                      TextSpan(
                        text: '$greeting ',
                        style: tt.bodyMedium?.copyWith(color: onBgMuted),
                      ),
                      TextSpan(
                        text: name,
                        style: tt.titleLarge?.copyWith(
                          color: onBg,
                          fontWeight: FontWeight.w700,
                        ),
                      ),
                    ],
                  ),
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                ),
                if (subtitle != null) ...[
                  const SizedBox(height: 2),
                  Text(
                    subtitle!,
                    style: tt.bodySmall?.copyWith(color: onBgMuted),
                  ),
                ],
              ],
            ),
          ),

          const SizedBox(width: AppSpacing.md),

          // O'ng: avatar + trailing
          Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              if (trailing != null) ...[
                trailing!,
                const SizedBox(width: AppSpacing.sm),
              ],
              _Avatar(
                initials: avatarInitials,
                icon: avatarIcon,
                onBg: onBg,
                onBgMuted: onBgMuted,
                bgColor: onBg.withValues(alpha: 0.2),
              ),
            ],
          ),
        ],
      ),
    );
  }
}

class _Avatar extends StatelessWidget {
  const _Avatar({
    this.initials,
    this.icon,
    required this.onBg,
    required this.onBgMuted,
    required this.bgColor,
  });

  final String? initials;
  final IconData? icon;
  final Color onBg;
  final Color onBgMuted;
  final Color bgColor;

  @override
  Widget build(BuildContext context) {
    final tt = Theme.of(context).textTheme;
    return Container(
      width: 46,
      height: 46,
      decoration: BoxDecoration(
        color: bgColor,
        shape: BoxShape.circle,
      ),
      child: Center(
        child: initials != null
            ? Text(
                initials!.toUpperCase(),
                style: tt.titleSmall?.copyWith(
                  color: onBg,
                  fontWeight: FontWeight.w700,
                ),
              )
            : Icon(icon, color: onBg, size: AppSpacing.iconMd),
      ),
    );
  }
}
