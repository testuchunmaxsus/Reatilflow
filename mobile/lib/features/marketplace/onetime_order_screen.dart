import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:uuid/uuid.dart';

import '../../core/theme/app_spacing.dart';
import '../../core/theme/app_theme.dart';
import '../../core/widgets/widgets.dart';
import '../home/sync_providers.dart';
import '../stores/stores_providers.dart';
import 'marketplace_models.dart';
import 'marketplace_providers.dart';
import 'onetime_order_providers.dart';

/// Agent bir martalik buyurtma ekrani.
///
/// Agent do'kon nomidan shartnomasiz katalogdan buyurtma beradi.
/// [is_onetime=true] + [store_id] outbox payloadda yuboriladi.
/// Narx/supplier YUBORILMAYDI — server-avtoritar.
///
/// URL: /home/marketplace/onetime?storeId=...
class OnetimeOrderScreen extends ConsumerStatefulWidget {
  const OnetimeOrderScreen({super.key, required this.storeId});
  final String storeId;

  @override
  ConsumerState<OnetimeOrderScreen> createState() =>
      _OnetimeOrderScreenState();
}

class _OnetimeOrderScreenState extends ConsumerState<OnetimeOrderScreen> {
  bool _ordering = false;

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    final cartState = ref.watch(marketplaceCartProvider);
    final storeAsync = ref.watch(storeByIdProvider(widget.storeId));

    final storeName = storeAsync.whenOrNull(
      data: (s) => s?.name,
    );

    return Scaffold(
      appBar: AppBar(
        title: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          mainAxisSize: MainAxisSize.min,
          children: [
            const Text('Bir martalik buyurtma'),
            if (storeName != null)
              Text(
                storeName,
                style: Theme.of(context).textTheme.bodySmall?.copyWith(
                      color: cs.onSurfaceVariant,
                    ),
              ),
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
                foregroundColor: cs.error,
              ),
            ),
        ],
      ),
      body: Column(
        children: [
          // Do'kon banneri
          _StoreBanner(storeId: widget.storeId),

          // Mahsulotlar yoki savat
          Expanded(
            child: DefaultTabController(
              length: 2,
              child: Column(
                children: [
                  TabBar(
                    tabs: [
                      Tab(
                        child: Row(
                          mainAxisSize: MainAxisSize.min,
                          children: [
                            const Text('Katalog'),
                          ],
                        ),
                      ),
                      Tab(
                        child: Row(
                          mainAxisSize: MainAxisSize.min,
                          children: [
                            const Text('Savat'),
                            if (cartState.items.isNotEmpty) ...[
                              const SizedBox(width: AppSpacing.xs),
                              _Badge(count: cartState.items.length),
                            ],
                          ],
                        ),
                      ),
                    ],
                  ),
                  Expanded(
                    child: TabBarView(
                      children: [
                        _CatalogTab(),
                        _CartTab(storeId: widget.storeId),
                      ],
                    ),
                  ),
                ],
              ),
            ),
          ),

          // Footer — buyurtma berish
          if (cartState.items.isNotEmpty)
            _OnetimeOrderFooter(
              storeId: widget.storeId,
              cartState: cartState,
              ordering: _ordering,
              onOrder: _placeOrder,
            ),
        ],
      ),
    );
  }

  Future<void> _placeOrder() async {
    final cartState = ref.read(marketplaceCartProvider);
    if (cartState.items.isEmpty) return;

    setState(() => _ordering = true);

    int successCount = 0;
    final errors = <String>[];
    const uuid = Uuid();

    for (final item in cartState.items) {
      try {
        final clientUuid = uuid.v4();
        await ref
            .read(onetimeOrderProvider(widget.storeId).notifier)
            .placeOrder(
              productId: item.product.id,
              qty: item.qty,
              storeId: widget.storeId,
              clientUuid: clientUuid,
            );
        final state =
            ref.read(onetimeOrderProvider(widget.storeId));
        if (state is OnetimeOrderSuccess) successCount++;
        if (state is OnetimeOrderFailure) errors.add(item.product.name);
        ref.read(onetimeOrderProvider(widget.storeId).notifier).reset();
      } catch (_) {
        errors.add(item.product.name);
      }
    }

    // Sync trigger
    unawaited(ref.read(syncNotifierProvider.notifier).triggerSync());

    if (!mounted) return;
    setState(() => _ordering = false);

    final appColors = AppTheme.colorsOf(context);

    if (errors.isEmpty) {
      ref.read(marketplaceCartProvider.notifier).clear();
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(
              '$successCount ta buyurtma yuborildi (bir martalik)'),
          backgroundColor: appColors.success,
          behavior: SnackBarBehavior.floating,
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(AppSpacing.radiusMd),
          ),
        ),
      );
      context.pop();
    } else {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(
            '$successCount ta muvaffaqiyatli. '
            'Xatolik: ${errors.join(', ')}',
          ),
          backgroundColor: appColors.warning,
          behavior: SnackBarBehavior.floating,
        ),
      );
    }
  }
}

// ---------------------------------------------------------------------------

class _StoreBanner extends ConsumerWidget {
  const _StoreBanner({required this.storeId});
  final String storeId;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final cs = Theme.of(context).colorScheme;
    final tt = Theme.of(context).textTheme;
    final storeAsync = ref.watch(storeByIdProvider(storeId));

    return storeAsync.whenOrNull(
          data: (store) {
            if (store == null) return null;
            return Container(
              padding: const EdgeInsets.symmetric(
                horizontal: AppSpacing.lg,
                vertical: AppSpacing.sm,
              ),
              color: cs.primaryContainer.withValues(alpha: 0.3),
              child: Row(
                children: [
                  Icon(Icons.store_outlined,
                      size: AppSpacing.iconSm, color: cs.primary),
                  const SizedBox(width: AppSpacing.sm),
                  Expanded(
                    child: Text(
                      store.name,
                      style: tt.labelMedium?.copyWith(
                        color: cs.primary,
                        fontWeight: FontWeight.w600,
                      ),
                    ),
                  ),
                  Container(
                    padding: const EdgeInsets.symmetric(
                      horizontal: AppSpacing.sm,
                      vertical: AppSpacing.xs,
                    ),
                    decoration: BoxDecoration(
                      color: cs.tertiaryContainer,
                      borderRadius: BorderRadius.circular(AppSpacing.radiusXs),
                    ),
                    child: Text(
                      'Bir martalik',
                      style: tt.labelSmall?.copyWith(
                        color: cs.tertiary,
                        fontWeight: FontWeight.w600,
                      ),
                    ),
                  ),
                ],
              ),
            );
          },
        ) ??
        const SizedBox.shrink();
  }
}

class _Badge extends StatelessWidget {
  const _Badge({required this.count});
  final int count;

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    return Container(
      padding: const EdgeInsets.symmetric(
        horizontal: AppSpacing.xs + 2,
        vertical: 1,
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
              fontSize: 10,
            ),
      ),
    );
  }
}

// ---------------------------------------------------------------------------
// Katalog tab

class _CatalogTab extends ConsumerStatefulWidget {
  @override
  ConsumerState<_CatalogTab> createState() => _CatalogTabState();
}

class _CatalogTabState extends ConsumerState<_CatalogTab> {
  final _searchController = TextEditingController();

  @override
  void dispose() {
    _searchController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    final productsState = ref.watch(productsNotifierProvider);

    return Column(
      children: [
        Padding(
          padding: const EdgeInsets.fromLTRB(
            AppSpacing.lg,
            AppSpacing.sm,
            AppSpacing.lg,
            AppSpacing.xs,
          ),
          child: TextField(
            controller: _searchController,
            decoration: InputDecoration(
              hintText: 'Mahsulot qidirish...',
              prefixIcon: const Icon(Icons.search_outlined),
              suffixIcon: _searchController.text.isNotEmpty
                  ? IconButton(
                      icon: const Icon(Icons.clear),
                      onPressed: () {
                        _searchController.clear();
                        ref.read(marketplaceSearchProvider.notifier).clear();
                      },
                    )
                  : null,
              isDense: true,
            ),
            onChanged: (v) =>
                ref.read(marketplaceSearchProvider.notifier).set(v),
          ),
        ),

        Expanded(
          child: switch (productsState) {
            ProductsLoading() =>
              Center(child: CircularProgressIndicator(color: cs.primary)),
            ProductsError(:final message) => EmptyState(
                icon: Icons.error_outline,
                title: 'Yuklanmadi',
                message: message,
                compact: true,
              ),
            ProductsLoaded(:final products) => products.isEmpty
                ? const EmptyState(
                    icon: Icons.inventory_2_outlined,
                    title: 'Mahsulot topilmadi',
                    message: 'Qidiruv so\'zini o\'zgartiring',
                    compact: true,
                  )
                : ListView.builder(
                    padding: const EdgeInsets.fromLTRB(
                      AppSpacing.lg,
                      AppSpacing.xs,
                      AppSpacing.lg,
                      AppSpacing.lg,
                    ),
                    itemCount: products.length,
                    itemBuilder: (context, i) =>
                        _ProductTile(product: products[i]),
                  ),
          },
        ),
      ],
    );
  }
}

class _ProductTile extends ConsumerWidget {
  const _ProductTile({required this.product});
  final MarketplaceProduct product;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final cs = Theme.of(context).colorScheme;
    final tt = Theme.of(context).textTheme;
    final cartState = ref.watch(marketplaceCartProvider);
    final inCart = cartState.items.any((e) => e.product.id == product.id);

    return Padding(
      padding: const EdgeInsets.only(bottom: AppSpacing.sm),
      child: AppCard(
        padding: const EdgeInsets.all(AppSpacing.md),
        child: Row(
          children: [
            Container(
              width: 44,
              height: 44,
              decoration: BoxDecoration(
                color: cs.primaryContainer,
                borderRadius: BorderRadius.circular(AppSpacing.radiusSm),
              ),
              child: Icon(Icons.inventory_2_outlined,
                  size: AppSpacing.iconSm, color: cs.primary),
            ),
            const SizedBox(width: AppSpacing.md),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    product.name,
                    style: tt.titleSmall
                        ?.copyWith(fontWeight: FontWeight.w600),
                    maxLines: 2,
                    overflow: TextOverflow.ellipsis,
                  ),
                  Text(
                    product.supplierEnterpriseName,
                    style:
                        tt.bodySmall?.copyWith(color: cs.onSurfaceVariant),
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                  ),
                  Text(
                    '${_fmt(product.price)} so\'m / ${product.unit}',
                    style: tt.labelMedium?.copyWith(
                      color: cs.primary,
                      fontWeight: FontWeight.w600,
                    ),
                  ),
                ],
              ),
            ),
            const SizedBox(width: AppSpacing.sm),
            inCart
                ? IconButton.filledTonal(
                    icon: const Icon(Icons.check),
                    onPressed: () => ref
                        .read(marketplaceCartProvider.notifier)
                        .removeItem(product.id),
                    tooltip: "Savatdan olib tashlash",
                    style: IconButton.styleFrom(
                      backgroundColor: cs.secondaryContainer,
                      foregroundColor: cs.secondary,
                    ),
                  )
                : IconButton.filled(
                    icon: const Icon(Icons.add),
                    onPressed: () => ref
                        .read(marketplaceCartProvider.notifier)
                        .addItem(product),
                    tooltip: "Savatga qo'shish",
                  ),
          ],
        ),
      ),
    );
  }

  String _fmt(double v) {
    if (v >= 1000000) return '${(v / 1000000).toStringAsFixed(1)} mln';
    if (v >= 1000) return '${(v / 1000).toStringAsFixed(0)} ming';
    return v.toStringAsFixed(0);
  }
}

// ---------------------------------------------------------------------------
// Savat tab

class _CartTab extends ConsumerWidget {
  const _CartTab({required this.storeId});
  final String storeId;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final cartState = ref.watch(marketplaceCartProvider);

    if (cartState.isEmpty) {
      return const EmptyState(
        icon: Icons.shopping_cart_outlined,
        title: 'Savat bo\'sh',
        message: 'Katalog tabidan mahsulot qo\'shing',
        compact: true,
      );
    }

    return ListView.builder(
      padding: const EdgeInsets.all(AppSpacing.lg),
      itemCount: cartState.items.length,
      itemBuilder: (context, i) {
        final item = cartState.items[i];
        return _OnetimeCartItem(item: item);
      },
    );
  }
}

class _OnetimeCartItem extends ConsumerWidget {
  const _OnetimeCartItem({required this.item});
  final MarketplaceCartItem item;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final cs = Theme.of(context).colorScheme;
    final tt = Theme.of(context).textTheme;

    return Padding(
      padding: const EdgeInsets.only(bottom: AppSpacing.sm),
      child: AppCard(
        padding: const EdgeInsets.all(AppSpacing.md),
        child: Row(
          children: [
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    item.product.name,
                    style: tt.titleSmall
                        ?.copyWith(fontWeight: FontWeight.w600),
                    maxLines: 2,
                    overflow: TextOverflow.ellipsis,
                  ),
                  Text(
                    item.product.supplierEnterpriseName,
                    style:
                        tt.bodySmall?.copyWith(color: cs.onSurfaceVariant),
                  ),
                ],
              ),
            ),
            const SizedBox(width: AppSpacing.sm),
            // Qty boshqaruvi
            Container(
              decoration: BoxDecoration(
                color: cs.surfaceContainerHighest,
                borderRadius: BorderRadius.circular(AppSpacing.radiusSm),
              ),
              child: Row(
                mainAxisSize: MainAxisSize.min,
                children: [
                  _QtyBtn(
                    icon: Icons.remove,
                    color: cs.onSurfaceVariant,
                    onPressed: () => ref
                        .read(marketplaceCartProvider.notifier)
                        .updateQty(item.product.id, item.qty - 1),
                  ),
                  SizedBox(
                    width: 36,
                    child: Text(
                      item.qty.toStringAsFixed(
                          item.qty % 1 == 0 ? 0 : 1),
                      textAlign: TextAlign.center,
                      style: tt.titleSmall
                          ?.copyWith(fontWeight: FontWeight.w700),
                    ),
                  ),
                  _QtyBtn(
                    icon: Icons.add,
                    color: cs.primary,
                    onPressed: () => ref
                        .read(marketplaceCartProvider.notifier)
                        .updateQty(item.product.id, item.qty + 1),
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
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

// ---------------------------------------------------------------------------
// Footer

class _OnetimeOrderFooter extends StatelessWidget {
  const _OnetimeOrderFooter({
    required this.storeId,
    required this.cartState,
    required this.ordering,
    required this.onOrder,
  });

  final String storeId;
  final MarketplaceCartState cartState;
  final bool ordering;
  final VoidCallback onOrder;

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
          // Taxminiy jami
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              Text(
                'Taxminiy jami',
                style: tt.labelMedium?.copyWith(color: cs.onSurfaceVariant),
              ),
              Text(
                _fmtTotal(cartState.estimatedTotal),
                style: tt.titleMedium?.copyWith(
                  fontWeight: FontWeight.w700,
                  color: cs.onSurface,
                ),
              ),
            ],
          ),
          const SizedBox(height: AppSpacing.xs),
          Text(
            'Narx server tomonidan aniqlanadi.',
            style: tt.labelSmall?.copyWith(
                color: cs.onSurfaceVariant.withValues(alpha: 0.6)),
          ),
          const SizedBox(height: AppSpacing.md),
          SizedBox(
            width: double.infinity,
            child: FilledButton.icon(
              onPressed: ordering ? null : onOrder,
              style: FilledButton.styleFrom(
                backgroundColor: appColors.warning,
                foregroundColor: appColors.onWarning,
                minimumSize:
                    const Size.fromHeight(AppSpacing.buttonHeight),
              ),
              icon: ordering
                  ? SizedBox(
                      height: 18,
                      width: 18,
                      child: CircularProgressIndicator(
                          strokeWidth: 2, color: appColors.onWarning),
                    )
                  : const Icon(Icons.bolt_outlined),
              label: Text(
                ordering ? 'Yuborilmoqda...' : 'Bir martalik buyurtma berish',
                style: const TextStyle(fontWeight: FontWeight.w700),
              ),
            ),
          ),
        ],
      ),
    );
  }

  String _fmtTotal(double v) {
    if (v >= 1000000) return "${(v / 1000000).toStringAsFixed(2)} mln so'm";
    if (v >= 1000) return "${(v / 1000).toStringAsFixed(0)} ming so'm";
    return "${v.toStringAsFixed(0)} so'm";
  }
}

/// Fire-and-forget helper
void unawaited(Future<void> future) => future.ignore();
