import 'package:flutter/material.dart';

import '../theme/app_spacing.dart';

/// Bo'lim sarlavhasi — title + ixtiyoriy action (masalan "Barchasi" tugmasi).
///
/// ```dart
/// SectionHeader(
///   title: "So'nggi buyurtmalar",
///   actionLabel: 'Barchasi',
///   onAction: () => context.push('/orders'),
/// )
/// ```
class SectionHeader extends StatelessWidget {
  const SectionHeader({
    super.key,
    required this.title,
    this.actionLabel,
    this.onAction,
    this.padding,
    this.titleStyle,
    this.subtitle,
  });

  final String title;
  final String? subtitle;

  /// Action tugmasi matni (null bo'lsa tugma ko'rinmaydi).
  final String? actionLabel;
  final VoidCallback? onAction;

  /// Tashqi padding (null = EdgeInsets.zero).
  final EdgeInsetsGeometry? padding;

  /// Title uchun maxsus stil (null = titleMedium).
  final TextStyle? titleStyle;

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    final tt = Theme.of(context).textTheme;

    return Padding(
      padding: padding ?? EdgeInsets.zero,
      child: Row(
        children: [
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              mainAxisSize: MainAxisSize.min,
              children: [
                Text(
                  title,
                  style: titleStyle ??
                      tt.titleMedium?.copyWith(
                        fontWeight: FontWeight.w700,
                        color: cs.onSurface,
                      ),
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                ),
                if (subtitle != null) ...[
                  const SizedBox(height: 2),
                  Text(
                    subtitle!,
                    style: tt.bodySmall?.copyWith(color: cs.onSurfaceVariant),
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                  ),
                ],
              ],
            ),
          ),
          if (actionLabel != null && onAction != null) ...[
            const SizedBox(width: AppSpacing.sm),
            TextButton(
              onPressed: onAction,
              style: TextButton.styleFrom(
                padding: const EdgeInsets.symmetric(
                    horizontal: AppSpacing.sm, vertical: AppSpacing.xs),
                minimumSize: Size.zero,
                tapTargetSize: MaterialTapTargetSize.shrinkWrap,
                foregroundColor: cs.primary,
                textStyle: tt.labelMedium?.copyWith(fontWeight: FontWeight.w600),
              ),
              child: Row(
                mainAxisSize: MainAxisSize.min,
                children: [
                  Text(actionLabel!),
                  const SizedBox(width: 2),
                  const Icon(Icons.chevron_right, size: AppSpacing.iconSm),
                ],
              ),
            ),
          ],
        ],
      ),
    );
  }
}
