import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/theme/app_spacing.dart';
import '../../core/theme/app_theme.dart';
import '../../core/widgets/app_card.dart';
import '../../core/widgets/empty_state.dart';
import '../../core/widgets/section_header.dart';
import '../../core/widgets/status_badge.dart';
import 'pos_models.dart';
import 'pos_providers.dart';

/// POS Inventar ekrani — do'kon ombori holati.
///
/// Ko'rsatiladi:
/// - Mahsulot nomi, SKU, qty, narx
/// - Yaroqlilik muddati
/// - QIZIL: expired (muddati o'tgan) va near_expiry (muddat yaqin)
class PosInventoryScreen extends ConsumerStatefulWidget {
  const PosInventoryScreen({super.key});

  @override
  ConsumerState<PosInventoryScreen> createState() =>
      _PosInventoryScreenState();
}

class _PosInventoryScreenState extends ConsumerState<PosInventoryScreen> {
  final _searchCtrl = TextEditingController();

  @override
  void dispose() {
    _searchCtrl.dispose();
    ref.read(inventorySearchProvider.notifier).clear();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    final inventoryState = ref.watch(inventoryNotifierProvider);
    final filtered = ref.watch(filteredInventoryProvider);

    // Expiry statistika (faqat yuklangan holatda)
    final (expiredCount, nearExpiryCount) = switch (inventoryState) {
      InventoryLoaded(:final items) => (
          items.where((i) => i.isExpired).length,
          items.where((i) => i.isNearExpiry && !i.isExpired).length,
        ),
      _ => (0, 0),
    };

    return Scaffold(
      appBar: AppBar(
        title: const Text('Inventar'),
        actions: [
          IconButton(
            icon: const Icon(Icons.refresh),
            tooltip: 'Yangilash',
            onPressed: () =>
                ref.read(inventoryNotifierProvider.notifier).load(),
          ),
        ],
      ),
      body: Column(
        children: [
          // Statistika + ogohlantirish
          if (inventoryState is InventoryLoaded) ...[
            _InventoryStatsBanner(
              totalCount: inventoryState.items.length,
              expiredCount: expiredCount,
              nearExpiryCount: nearExpiryCount,
            ),
          ],

          // Qidiruv
          Padding(
            padding: const EdgeInsets.fromLTRB(
              AppSpacing.lg,
              AppSpacing.sm,
              AppSpacing.lg,
              AppSpacing.xs,
            ),
            child: TextField(
              controller: _searchCtrl,
              decoration: InputDecoration(
                hintText: 'Mahsulot nomi yoki SKU...',
                prefixIcon: const Icon(Icons.search),
                suffixIcon: _searchCtrl.text.isNotEmpty
                    ? IconButton(
                        icon: const Icon(Icons.clear),
                        onPressed: () {
                          _searchCtrl.clear();
                          ref
                              .read(inventorySearchProvider.notifier)
                              .clear();
                          setState(() {});
                        },
                      )
                    : null,
              ),
              onChanged: (v) {
                setState(() {});
                ref.read(inventorySearchProvider.notifier).setQuery(v);
              },
            ),
          ),

          // Ro'yxat
          Expanded(
            child: switch (inventoryState) {
              InventoryLoading() => const Center(
                  child: CircularProgressIndicator(),
                ),
              InventoryError(:final message) => _ErrorView(
                  message: message,
                  onRetry: () =>
                      ref.read(inventoryNotifierProvider.notifier).load(),
                ),
              InventoryLoaded() => filtered.isEmpty
                  ? EmptyState(
                      icon: Icons.search_off,
                      title: 'Mahsulot topilmadi',
                      message: _searchCtrl.text.isNotEmpty
                          ? '"${_searchCtrl.text}" bo\'yicha natija yo\'q'
                          : 'Inventar bo\'sh',
                      compact: true,
                    )
                  : ListView.builder(
                      padding: const EdgeInsets.symmetric(
                        horizontal: AppSpacing.lg,
                        vertical: AppSpacing.sm,
                      ),
                      itemCount: filtered.length,
                      itemBuilder: (ctx, i) =>
                          _InventoryCard(item: filtered[i]),
                    ),
            },
          ),
        ],
      ),
    );
  }
}

// ---------------------------------------------------------------------------
// Statistika banner

class _InventoryStatsBanner extends StatelessWidget {
  const _InventoryStatsBanner({
    required this.totalCount,
    required this.expiredCount,
    required this.nearExpiryCount,
  });
  final int totalCount;
  final int expiredCount;
  final int nearExpiryCount;

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    final tt = Theme.of(context).textTheme;
    final appColors = AppTheme.colorsOf(context);

    // Xavfsiz holat — ogohlantirish yo'q
    if (expiredCount == 0 && nearExpiryCount == 0) {
      return Container(
        margin: const EdgeInsets.fromLTRB(
          AppSpacing.lg,
          AppSpacing.md,
          AppSpacing.lg,
          0,
        ),
        padding: const EdgeInsets.symmetric(
          horizontal: AppSpacing.md,
          vertical: AppSpacing.sm,
        ),
        decoration: BoxDecoration(
          color: appColors.successContainer.withValues(alpha: 0.4),
          borderRadius: BorderRadius.circular(AppSpacing.radiusMd),
          border: Border.all(
            color: appColors.success.withValues(alpha: 0.3),
          ),
        ),
        child: Row(
          children: [
            Icon(Icons.check_circle_outline,
                size: AppSpacing.iconSm,
                color: appColors.success),
            const SizedBox(width: AppSpacing.sm),
            Text(
              'Jami $totalCount mahsulot — hammasi muddatda',
              style: tt.bodySmall?.copyWith(
                color: appColors.success,
                fontWeight: FontWeight.w600,
              ),
            ),
          ],
        ),
      );
    }

    // Ogohlantirish holati
    return Container(
      margin: const EdgeInsets.fromLTRB(
        AppSpacing.lg,
        AppSpacing.md,
        AppSpacing.lg,
        0,
      ),
      padding: const EdgeInsets.all(AppSpacing.md),
      decoration: BoxDecoration(
        color: appColors.dangerContainer.withValues(alpha: 0.35),
        borderRadius: BorderRadius.circular(AppSpacing.radiusMd),
        border: Border.all(
          color: appColors.danger.withValues(alpha: 0.4),
        ),
      ),
      child: Row(
        children: [
          Icon(Icons.warning_amber_rounded,
              size: AppSpacing.iconMd, color: appColors.danger),
          const SizedBox(width: AppSpacing.sm),
          Expanded(
            child: Wrap(
              spacing: AppSpacing.sm,
              runSpacing: AppSpacing.xs,
              children: [
                if (expiredCount > 0)
                  StatusBadge(
                    status: '$expiredCount ta muddati o\'tgan',
                    variant: StatusVariant.danger,
                    size: StatusBadgeSize.small,
                  ),
                if (nearExpiryCount > 0)
                  StatusBadge(
                    status: '$nearExpiryCount ta muddat yaqin',
                    variant: StatusVariant.warning,
                    size: StatusBadgeSize.small,
                  ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

// ---------------------------------------------------------------------------
// Inventar kartasi

class _InventoryCard extends StatelessWidget {
  const _InventoryCard({required this.item});
  final InventoryItem item;

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    final tt = Theme.of(context).textTheme;
    final appColors = AppTheme.colorsOf(context);

    Color? cardColor;
    Color? borderColor;

    if (item.isExpired) {
      cardColor = appColors.dangerContainer.withValues(alpha: 0.3);
      borderColor = appColors.danger.withValues(alpha: 0.35);
    } else if (item.isNearExpiry) {
      cardColor = appColors.warningContainer.withValues(alpha: 0.3);
      borderColor = appColors.warning.withValues(alpha: 0.35);
    }

    return Padding(
      padding: const EdgeInsets.only(bottom: AppSpacing.sm),
      child: AppCard(
        padding: const EdgeInsets.all(AppSpacing.md),
        color: cardColor,
        borderColor: borderColor,
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            // Icon
            Container(
              width: 44,
              height: 44,
              decoration: BoxDecoration(
                color: item.isExpired
                    ? appColors.dangerContainer
                    : item.isNearExpiry
                        ? appColors.warningContainer
                        : cs.primaryContainer,
                borderRadius:
                    BorderRadius.circular(AppSpacing.radiusSm),
              ),
              child: Icon(
                item.isExpired
                    ? Icons.block
                    : item.isNearExpiry
                        ? Icons.warning_amber_rounded
                        : Icons.inventory_2_outlined,
                size: AppSpacing.iconMd,
                color: item.isExpired
                    ? appColors.danger
                    : item.isNearExpiry
                        ? appColors.warning
                        : cs.primary,
              ),
            ),

            const SizedBox(width: AppSpacing.md),

            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  // Nomi + badge
                  Row(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Expanded(
                        child: Text(
                          item.productName,
                          style: tt.titleSmall?.copyWith(
                            color: item.isExpired
                                ? appColors.danger
                                : cs.onSurface,
                            fontWeight: FontWeight.w600,
                            decoration: item.isExpired
                                ? TextDecoration.lineThrough
                                : null,
                          ),
                        ),
                      ),
                      const SizedBox(width: AppSpacing.xs),
                      if (item.isExpired)
                        StatusBadge(
                          status: 'YAROQSIZ',
                          variant: StatusVariant.danger,
                          size: StatusBadgeSize.small,
                        )
                      else if (item.isNearExpiry)
                        StatusBadge(
                          status: item.daysToExpiry != null
                              ? '${item.daysToExpiry}K QOLDI'
                              : 'MUDDAT YAQIN',
                          variant: StatusVariant.warning,
                          size: StatusBadgeSize.small,
                        ),
                    ],
                  ),

                  // SKU + birlik
                  if (item.sku.isNotEmpty) ...[
                    const SizedBox(height: AppSpacing.xs),
                    Text(
                      'SKU: ${item.sku}  ·  ${item.unit}',
                      style: tt.labelSmall?.copyWith(
                        color: cs.onSurfaceVariant,
                      ),
                    ),
                  ],

                  const SizedBox(height: AppSpacing.sm),

                  // Miqdor + narxlar qatori
                  Wrap(
                    spacing: AppSpacing.md,
                    runSpacing: AppSpacing.xs,
                    children: [
                      _InfoChip(
                        label: 'Qoldiq',
                        value: '${_fmtQty(item.qty)} ${item.unit}',
                        accentColor: item.qty <= 0
                            ? appColors.danger
                            : cs.primary,
                      ),
                      _InfoChip(
                        label: 'Sotuv',
                        value: '${item.salePrice.toStringAsFixed(0)} so\'m',
                        accentColor: appColors.success,
                      ),
                      _InfoChip(
                        label: 'Tan narxi',
                        value: '${item.costPrice.toStringAsFixed(0)} so\'m',
                        accentColor: cs.onSurfaceVariant,
                      ),
                    ],
                  ),

                  // Muddat
                  if (item.expiryDate != null) ...[
                    const SizedBox(height: AppSpacing.xs),
                    Row(
                      children: [
                        Icon(
                          Icons.calendar_today,
                          size: 12,
                          color: item.isExpired
                              ? appColors.danger
                              : item.isNearExpiry
                                  ? appColors.warning
                                  : cs.onSurfaceVariant,
                        ),
                        const SizedBox(width: AppSpacing.xs),
                        Text(
                          'Muddat: ${_fmtDate(item.expiryDate!)}',
                          style: tt.labelSmall?.copyWith(
                            color: item.isExpired
                                ? appColors.danger
                                : item.isNearExpiry
                                    ? appColors.warning
                                    : cs.onSurfaceVariant,
                            fontWeight: item.hasExpiryWarning
                                ? FontWeight.w600
                                : FontWeight.normal,
                          ),
                        ),
                      ],
                    ),
                  ],
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }

  String _fmtQty(double qty) =>
      qty % 1 == 0 ? qty.toStringAsFixed(0) : qty.toStringAsFixed(2);

  String _fmtDate(DateTime dt) =>
      '${dt.day.toString().padLeft(2, '0')}.${dt.month.toString().padLeft(2, '0')}.${dt.year}';
}

class _InfoChip extends StatelessWidget {
  const _InfoChip({
    required this.label,
    required this.value,
    required this.accentColor,
  });
  final String label;
  final String value;
  final Color accentColor;

  @override
  Widget build(BuildContext context) {
    final tt = Theme.of(context).textTheme;
    final cs = Theme.of(context).colorScheme;

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          label,
          style: tt.labelSmall?.copyWith(color: cs.onSurfaceVariant),
        ),
        Text(
          value,
          style: tt.labelMedium?.copyWith(
            color: accentColor,
            fontWeight: FontWeight.w700,
          ),
        ),
      ],
    );
  }
}

// ---------------------------------------------------------------------------

class _ErrorView extends StatelessWidget {
  const _ErrorView({required this.message, required this.onRetry});
  final String message;
  final VoidCallback onRetry;

  @override
  Widget build(BuildContext context) {
    final appColors = AppTheme.colorsOf(context);

    return EmptyState(
      icon: Icons.error_outline,
      title: 'Xatolik yuz berdi',
      message: message,
      iconColor: appColors.danger,
      actionLabel: 'Qayta urinish',
      onAction: onRetry,
    );
  }
}
