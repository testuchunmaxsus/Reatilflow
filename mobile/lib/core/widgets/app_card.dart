import 'package:flutter/material.dart';

import '../theme/app_spacing.dart';

/// Temadan rang va shakl oladigan asosiy karta konteyneri.
///
/// [AppCard] faqat vizual konteyner; ichida ixtiyoriy content joylashadi.
/// [outlined] true bo'lsa — chegara bilan (default), false bo'lsa — subtle shadow.
/// [padding] null bo'lsa standart [AppSpacing.lg] ishlatiladi.
class AppCard extends StatelessWidget {
  const AppCard({
    super.key,
    required this.child,
    this.padding,
    this.outlined = true,
    this.color,
    this.borderColor,
    this.borderRadius,
    this.onTap,
    this.clipBehavior = Clip.antiAlias,
    this.margin,
  });

  final Widget child;
  final EdgeInsetsGeometry? padding;
  final bool outlined;
  final Color? color;
  final Color? borderColor;
  final BorderRadius? borderRadius;
  final VoidCallback? onTap;
  final Clip clipBehavior;
  final EdgeInsetsGeometry? margin;

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    final effectiveRadius =
        borderRadius ?? BorderRadius.circular(AppSpacing.radiusLg);

    return Padding(
      padding: margin ?? EdgeInsets.zero,
      child: Material(
        color: color ?? cs.surface,
        surfaceTintColor: Colors.transparent,
        borderRadius: effectiveRadius,
        clipBehavior: clipBehavior,
        child: _wrapBorder(
          child: InkWell(
            onTap: onTap,
            borderRadius: effectiveRadius,
            splashColor: cs.primary.withValues(alpha: 0.06),
            highlightColor: cs.primary.withValues(alpha: 0.03),
            child: Padding(
              padding: padding ?? const EdgeInsets.all(AppSpacing.lg),
              child: child,
            ),
          ),
          cs: cs,
          radius: effectiveRadius,
        ),
      ),
    );
  }

  Widget _wrapBorder({
    required Widget child,
    required ColorScheme cs,
    required BorderRadius radius,
  }) {
    if (!outlined) return child;
    return DecoratedBox(
      decoration: BoxDecoration(
        borderRadius: radius,
        border: Border.all(
          color: borderColor ?? cs.outlineVariant,
        ),
      ),
      child: child,
    );
  }
}
