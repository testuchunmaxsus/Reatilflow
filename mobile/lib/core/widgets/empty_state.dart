import 'package:flutter/material.dart';

import '../theme/app_spacing.dart';

/// Bo'sh holat ekrani — ikona + sarlavha + tavsif + ixtiyoriy tugma.
///
/// ListView, sahifa, modal ichida ishlatiladi.
///
/// ```dart
/// EmptyState(
///   icon: Icons.receipt_long_outlined,
///   title: 'Buyurtmalar yo\'q',
///   message: 'Yangi buyurtma qo\'shish uchun + tugmasini bosing.',
///   actionLabel: 'Buyurtma qo\'sh',
///   onAction: () => context.push('/orders/create'),
/// )
/// ```
class EmptyState extends StatelessWidget {
  const EmptyState({
    super.key,
    required this.icon,
    required this.title,
    this.message,
    this.actionLabel,
    this.onAction,
    this.iconSize = AppSpacing.iconXl * 1.2,
    this.iconColor,
    this.compact = false,
  });

  final IconData icon;
  final String title;
  final String? message;
  final String? actionLabel;
  final VoidCallback? onAction;

  /// Icon hajmi (default 58dp).
  final double iconSize;

  /// Icon rangi (null = onSurfaceVariant.withAlpha).
  final Color? iconColor;

  /// Ixcham variant — list ichida foydalanish uchun (kichik padding).
  final bool compact;

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    final tt = Theme.of(context).textTheme;
    final effectiveIconColor =
        iconColor ?? cs.onSurfaceVariant.withValues(alpha: 0.4);

    return Center(
      child: Padding(
        padding: EdgeInsets.symmetric(
          horizontal: AppSpacing.xxl,
          vertical: compact ? AppSpacing.xl : AppSpacing.xxxl,
        ),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            // Icon wrapper
            Container(
              width: iconSize + AppSpacing.xl,
              height: iconSize + AppSpacing.xl,
              decoration: BoxDecoration(
                color: cs.surfaceContainerHighest.withValues(alpha: 0.6),
                shape: BoxShape.circle,
              ),
              child: Icon(
                icon,
                size: iconSize,
                color: effectiveIconColor,
              ),
            ),

            SizedBox(height: compact ? AppSpacing.md : AppSpacing.lg),

            // Title
            Text(
              title,
              style: tt.titleMedium?.copyWith(
                color: cs.onSurface,
                fontWeight: FontWeight.w600,
              ),
              textAlign: TextAlign.center,
            ),

            if (message != null) ...[
              const SizedBox(height: AppSpacing.sm),
              Text(
                message!,
                style: tt.bodyMedium?.copyWith(
                  color: cs.onSurfaceVariant,
                  height: 1.5,
                ),
                textAlign: TextAlign.center,
              ),
            ],

            if (actionLabel != null && onAction != null) ...[
              SizedBox(height: compact ? AppSpacing.lg : AppSpacing.xl),
              FilledButton.icon(
                onPressed: onAction,
                icon: const Icon(Icons.add, size: AppSpacing.iconSm),
                label: Text(actionLabel!),
              ),
            ],
          ],
        ),
      ),
    );
  }
}
