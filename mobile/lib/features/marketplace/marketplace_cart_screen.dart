import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/theme/app_spacing.dart';
import '../../core/theme/app_theme.dart';
import '../../core/widgets/app_card.dart';
import '../../core/widgets/empty_state.dart';
import '../../core/widgets/section_header.dart';
import 'marketplace_providers.dart';

/// Marketplace savat ekrani — buyurtma tasdiqlash.
///
/// Bitta supplier = bitta buyurtma (backend qoidasi).
/// Har bir mahsulot uchun alohida buyurtma yaratiladi.
class MarketplaceCartScreen extends ConsumerWidget {
  const MarketplaceCartScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final cartState = ref.watch(marketplaceCartProvider);

    return Scaffold(
      appBar: AppBar(
        title: Row(
          children: [
            const Text('Savat'),
            if (cartState.items.isNotEmpty) ...[
              const SizedBox(width: AppSpacing.sm),
              _CartBadge(count: cartState.items.length),
            ],
          ],
        ),
        actions: [
          if (cartState.items.isNotEmpty)
            TextButton.icon(
              onPressed: () =>
                  ref.read(marketplaceCartProvider.notifier).clear(),
              icon: const Icon(Icons.delete_sweep_outlined,
                  size: AppSpacing.iconSm),
              label: const Text('Tozalash'),
              style: TextButton.styleFrom(
                foregroundColor: Theme.of(context).colorScheme.error,
              ),
            ),
        ],
      ),
      body: cartState.isEmpty
          ? EmptyState(
              icon: Icons.shopping_cart_outlined,
              title: 'Savat bo\'sh',
              message:
                  'Marketplacega o\'tib mahsulot qo\'shing',
              actionLabel: 'Marketplacega o\'tish',
              onAction: () => context.go('/home/marketplace'),
            )
          : _CartBody(cartState: cartState),
    );
  }
}

class _CartBadge extends StatelessWidget {
  const _CartBadge({required this.count});
  final int count;

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    return Container(
      padding: const EdgeInsets.symmetric(
        horizontal: AppSpacing.sm,
        vertical: 2,
      ),
      decoration: BoxDecoration(
        color: cs.primary,
        borderRadius: BorderRadius.circular(AppSpacing.radiusFull),
      ),
      child: Text(
        '$count',
        style: Theme.of(context).textTheme.labelSmall?.copyWith(
              color: cs.onPrimary,
              fontWeight: FontWeight.w700,
            ),
      ),
    );
  }
}

class _CartBody extends ConsumerWidget {
  const _CartBody({required this.cartState});
  final MarketplaceCartState cartState;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    return Column(
      children: [
        Expanded(
          child: ListView.builder(
            padding: const EdgeInsets.fromLTRB(
              AppSpacing.lg,
              AppSpacing.md,
              AppSpacing.lg,
              AppSpacing.sm,
            ),
            itemCount: cartState.items.length + 1,
            itemBuilder: (context, i) {
              // Sarlavha
              if (i == 0) {
                return Padding(
                  padding:
                      const EdgeInsets.only(bottom: AppSpacing.md),
                  child: SectionHeader(
                    title: 'Savatdagi mahsulotlar',
                    subtitle: '${cartState.items.length} ta element',
                  ),
                );
              }
              return _CartItemTile(item: cartState.items[i - 1]);
            },
          ),
        ),

        // Jami va buyurtma berish
        _CartFooter(cartState: cartState),
      ],
    );
  }
}

class _CartItemTile extends ConsumerWidget {
  const _CartItemTile({required this.item});
  final MarketplaceCartItem item;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final cs = Theme.of(context).colorScheme;
    final tt = Theme.of(context).textTheme;
    final appColors = AppTheme.colorsOf(context);

    return Padding(
      padding: const EdgeInsets.only(bottom: AppSpacing.sm),
      child: AppCard(
        padding: const EdgeInsets.all(AppSpacing.md),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            // Mahsulot icon
            Container(
              width: 44,
              height: 44,
              decoration: BoxDecoration(
                color: cs.primaryContainer,
                borderRadius:
                    BorderRadius.circular(AppSpacing.radiusSm),
              ),
              child: Icon(
                Icons.inventory_2_outlined,
                size: AppSpacing.iconSm,
                color: cs.primary,
              ),
            ),

            const SizedBox(width: AppSpacing.md),

            // Matn
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    item.product.name,
                    style: tt.titleSmall?.copyWith(
                      fontWeight: FontWeight.w600,
                    ),
                    maxLines: 2,
                    overflow: TextOverflow.ellipsis,
                  ),
                  const SizedBox(height: 2),
                  Text(
                    item.product.supplierEnterpriseName,
                    style: tt.bodySmall?.copyWith(
                      color: cs.onSurfaceVariant,
                    ),
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                  ),
                  const SizedBox(height: AppSpacing.xs),
                  Text(
                    '${_fmtPrice(item.product.price)} so\'m / ${item.product.unit}',
                    style: tt.labelMedium?.copyWith(
                      color: cs.primary,
                      fontWeight: FontWeight.w600,
                    ),
                  ),
                ],
              ),
            ),

            const SizedBox(width: AppSpacing.sm),

            // Qty boshqaruvi
            Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.end,
              children: [
                Container(
                  decoration: BoxDecoration(
                    color: cs.surfaceContainerHighest,
                    borderRadius:
                        BorderRadius.circular(AppSpacing.radiusSm),
                  ),
                  child: Row(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      _QtyBtn(
                        icon: Icons.remove,
                        color: cs.onSurfaceVariant,
                        onPressed: () => ref
                            .read(marketplaceCartProvider.notifier)
                            .updateQty(
                                item.product.id, item.qty - 1),
                      ),
                      SizedBox(
                        width: 36,
                        child: Text(
                          item.qty.toStringAsFixed(
                              item.qty % 1 == 0 ? 0 : 1),
                          textAlign: TextAlign.center,
                          style: tt.titleSmall?.copyWith(
                            fontWeight: FontWeight.w700,
                          ),
                        ),
                      ),
                      _QtyBtn(
                        icon: Icons.add,
                        color: cs.primary,
                        onPressed: () => ref
                            .read(marketplaceCartProvider.notifier)
                            .updateQty(
                                item.product.id, item.qty + 1),
                      ),
                    ],
                  ),
                ),
                const SizedBox(height: AppSpacing.xs),
                GestureDetector(
                  onTap: () => ref
                      .read(marketplaceCartProvider.notifier)
                      .removeItem(item.product.id),
                  child: Icon(
                    Icons.delete_outline,
                    size: AppSpacing.iconSm,
                    color: appColors.danger,
                  ),
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }

  String _fmtPrice(double v) {
    if (v >= 1000000) return '${(v / 1000000).toStringAsFixed(1)} mln';
    if (v >= 1000) return '${(v / 1000).toStringAsFixed(0)} ming';
    return v.toStringAsFixed(0);
  }
}

class _QtyBtn extends StatelessWidget {
  const _QtyBtn({
    required this.icon,
    required this.color,
    required this.onPressed,
  });
  final IconData icon;
  final Color color;
  final VoidCallback onPressed;

  @override
  Widget build(BuildContext context) {
    return InkWell(
      onTap: onPressed,
      borderRadius: BorderRadius.circular(AppSpacing.radiusSm),
      child: Padding(
        padding: const EdgeInsets.all(AppSpacing.sm),
        child: Icon(icon, size: 16, color: color),
      ),
    );
  }
}

class _CartFooter extends ConsumerStatefulWidget {
  const _CartFooter({required this.cartState});
  final MarketplaceCartState cartState;

  @override
  ConsumerState<_CartFooter> createState() => _CartFooterState();
}

class _CartFooterState extends ConsumerState<_CartFooter> {
  bool _ordering = false;

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    final tt = Theme.of(context).textTheme;
    final appColors = AppTheme.colorsOf(context);

    return Container(
      padding: const EdgeInsets.fromLTRB(
        AppSpacing.lg,
        AppSpacing.md,
        AppSpacing.lg,
        AppSpacing.lg,
      ),
      decoration: BoxDecoration(
        color: cs.surface,
        border: Border(top: BorderSide(color: cs.outlineVariant)),
        boxShadow: [
          BoxShadow(
            color: cs.shadow.withValues(alpha: 0.06),
            blurRadius: 12,
            offset: const Offset(0, -4),
          ),
        ],
      ),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          // Jami satr
          AppCard(
            padding: const EdgeInsets.symmetric(
              horizontal: AppSpacing.lg,
              vertical: AppSpacing.md,
            ),
            color: cs.surfaceContainerHighest,
            outlined: false,
            child: Row(
              children: [
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        'Taxminiy jami',
                        style: tt.labelSmall?.copyWith(
                          color: cs.onSurfaceVariant,
                        ),
                      ),
                      Text(
                        _fmtPrice(widget.cartState.estimatedTotal),
                        style: tt.headlineSmall?.copyWith(
                          fontWeight: FontWeight.w800,
                          color: cs.onSurface,
                          letterSpacing: -0.5,
                        ),
                      ),
                    ],
                  ),
                ),
                Container(
                  padding: const EdgeInsets.symmetric(
                    horizontal: AppSpacing.sm,
                    vertical: AppSpacing.xs,
                  ),
                  decoration: BoxDecoration(
                    color: cs.primaryContainer,
                    borderRadius:
                        BorderRadius.circular(AppSpacing.radiusXs),
                  ),
                  child: Text(
                    '${widget.cartState.items.length} ta',
                    style: tt.labelSmall?.copyWith(
                      color: cs.primary,
                      fontWeight: FontWeight.w600,
                    ),
                  ),
                ),
              ],
            ),
          ),

          const SizedBox(height: AppSpacing.xs),
          Text(
            'Server-avtoritar: haqiqiy narx backend hisoblaydi.',
            style: tt.labelSmall?.copyWith(
              color: cs.onSurfaceVariant.withValues(alpha: 0.6),
            ),
          ),
          const SizedBox(height: AppSpacing.md),

          // Buyurtma berish tugmasi
          SizedBox(
            width: double.infinity,
            child: FilledButton.icon(
              onPressed: _ordering ? null : _placeOrders,
              style: FilledButton.styleFrom(
                backgroundColor: appColors.success,
                foregroundColor: appColors.onSuccess,
                minimumSize: const Size.fromHeight(AppSpacing.buttonHeight),
              ),
              icon: _ordering
                  ? SizedBox(
                      height: 18,
                      width: 18,
                      child: CircularProgressIndicator(
                          strokeWidth: 2,
                          color: appColors.onSuccess),
                    )
                  : const Icon(Icons.shopping_bag_outlined),
              label: Text(
                _ordering ? 'Yuborilmoqda...' : 'Buyurtma berish',
                style: const TextStyle(fontWeight: FontWeight.w700),
              ),
            ),
          ),
        ],
      ),
    );
  }

  Future<void> _placeOrders() async {
    final items = widget.cartState.items;
    if (items.isEmpty) return;

    setState(() => _ordering = true);

    int successCount = 0;
    final errors = <String>[];
    // GATE: shartnoma talab qilingan korxonalar
    final contractRequired = <String>[];

    for (final item in items) {
      try {
        await ref
            .read(createMarketplaceOrderProvider.notifier)
            .createOrder(
              productId: item.product.id,
              qty: item.qty,
              supplierEnterpriseName: item.product.supplierEnterpriseName,
            );
        final orderState = ref.read(createMarketplaceOrderProvider);
        if (orderState is CreateOrderSuccess) {
          successCount++;
        } else if (orderState is CreateOrderContractRequired) {
          contractRequired.add(item.product.supplierEnterpriseName);
        } else if (orderState is CreateOrderFailure) {
          errors.add(item.product.name);
        }
        ref.read(createMarketplaceOrderProvider.notifier).reset();
      } catch (_) {
        errors.add(item.product.name);
      }
    }

    if (!mounted) return;

    setState(() => _ordering = false);

    // GATE dialog — shartnoma talab qilinsa, avval ko'rsatamiz
    if (contractRequired.isNotEmpty && mounted) {
      await _showContractRequiredDialog(contractRequired);
    }

    if (!mounted) return;

    final appColors = AppTheme.colorsOf(context);

    if (errors.isEmpty && contractRequired.isEmpty) {
      ref.read(marketplaceCartProvider.notifier).clear();
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content:
              Text('$successCount ta buyurtma muvaffaqiyatli yaratildi'),
          backgroundColor: appColors.success,
          behavior: SnackBarBehavior.floating,
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(AppSpacing.radiusMd),
          ),
        ),
      );
      context.go('/home/marketplace/orders');
    } else if (successCount > 0 && contractRequired.isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(
            '$successCount ta muvaffaqiyatli. '
            'Xatolik: ${errors.join(', ')}',
          ),
          backgroundColor: appColors.warning,
          behavior: SnackBarBehavior.floating,
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(AppSpacing.radiusMd),
          ),
        ),
      );
    }
    // GATE + qisman muvaffaqiyat: dialog ko'rsatildi, snackbar mos kerak emas
  }

  /// 409 marketplace.contract_required — GATE dialog.
  Future<void> _showContractRequiredDialog(
      List<String> supplierNames) async {
    final uniqueSuppliers = supplierNames.toSet().toList();
    final supplierList = uniqueSuppliers.join(', ');

    await showDialog<void>(
      context: context,
      builder: (ctx) => AlertDialog(
        icon: const Icon(Icons.handshake_outlined, size: 40),
        title: const Text('Shartnoma talab qilinadi'),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              'Quyidagi korxona(lar) bilan shartnomangiz yo\'q:',
              style: Theme.of(ctx).textTheme.bodyMedium,
            ),
            const SizedBox(height: 8),
            Text(
              supplierList,
              style: Theme.of(ctx).textTheme.bodyMedium?.copyWith(
                    fontWeight: FontWeight.w700,
                    color: Theme.of(ctx).colorScheme.primary,
                  ),
            ),
            const SizedBox(height: 12),
            Text(
              'Buyurtma berish uchun korxona bilan shartnoma tuzilishi kerak. '
              'Iltimos, agentingiz bilan bog\'laning.',
              style: Theme.of(ctx).textTheme.bodySmall?.copyWith(
                    color: Theme.of(ctx).colorScheme.onSurfaceVariant,
                  ),
            ),
          ],
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(ctx).pop(),
            child: const Text('Tushunarli'),
          ),
        ],
      ),
    );
  }

  String _fmtPrice(double v) {
    if (v >= 1000000) {
      return "${(v / 1000000).toStringAsFixed(2)} mln so'm";
    }
    if (v >= 1000) {
      return "${(v / 1000).toStringAsFixed(0)} ming so'm";
    }
    return "${v.toStringAsFixed(0)} so'm";
  }
}
