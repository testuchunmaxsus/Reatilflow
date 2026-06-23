import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

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
        title: const Text('Savat'),
        actions: [
          if (cartState.items.isNotEmpty)
            TextButton(
              onPressed: () => ref
                  .read(marketplaceCartProvider.notifier)
                  .clear(),
              child: const Text('Tozalash'),
            ),
        ],
      ),
      body: cartState.isEmpty
          ? const _EmptyCart()
          : _CartBody(cartState: cartState),
    );
  }
}

class _EmptyCart extends StatelessWidget {
  const _EmptyCart();

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(Icons.shopping_cart_outlined,
              size: 64, color: Colors.grey.shade300),
          const SizedBox(height: 12),
          Text(
            'Savat bo\'sh',
            style: Theme.of(context)
                .textTheme
                .titleMedium
                ?.copyWith(color: Colors.grey),
          ),
          const SizedBox(height: 8),
          FilledButton(
            onPressed: () => context.go('/home/marketplace'),
            child: const Text('Xaridga o\'tish'),
          ),
        ],
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
            padding: const EdgeInsets.all(12),
            itemCount: cartState.items.length,
            itemBuilder: (context, i) => _CartItemTile(
              item: cartState.items[i],
            ),
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
    return Card(
      margin: const EdgeInsets.only(bottom: 8),
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Row(
          children: [
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    item.product.name,
                    style: const TextStyle(
                      fontWeight: FontWeight.w600,
                      fontSize: 14,
                    ),
                  ),
                  const SizedBox(height: 2),
                  Text(
                    item.product.supplierEnterpriseName,
                    style: TextStyle(
                      fontSize: 12,
                      color: Colors.grey.shade600,
                    ),
                  ),
                ],
              ),
            ),
            const SizedBox(width: 8),

            // Qty boshqaruvi
            Row(
              children: [
                IconButton(
                  icon: const Icon(Icons.remove_circle_outline, size: 22),
                  onPressed: () => ref
                      .read(marketplaceCartProvider.notifier)
                      .updateQty(item.product.id, item.qty - 1),
                  padding: EdgeInsets.zero,
                  constraints: const BoxConstraints(),
                ),
                const SizedBox(width: 6),
                SizedBox(
                  width: 32,
                  child: Text(
                    item.qty.toStringAsFixed(
                        item.qty % 1 == 0 ? 0 : 1),
                    textAlign: TextAlign.center,
                    style: const TextStyle(
                        fontSize: 15, fontWeight: FontWeight.w600),
                  ),
                ),
                const SizedBox(width: 6),
                IconButton(
                  icon: const Icon(Icons.add_circle_outline, size: 22),
                  onPressed: () => ref
                      .read(marketplaceCartProvider.notifier)
                      .updateQty(item.product.id, item.qty + 1),
                  padding: EdgeInsets.zero,
                  constraints: const BoxConstraints(),
                ),
                const SizedBox(width: 4),
                IconButton(
                  icon: const Icon(Icons.delete_outline,
                      size: 20, color: Colors.red),
                  onPressed: () => ref
                      .read(marketplaceCartProvider.notifier)
                      .removeItem(item.product.id),
                  padding: EdgeInsets.zero,
                  constraints: const BoxConstraints(),
                ),
              ],
            ),
          ],
        ),
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
    return Container(
      padding: const EdgeInsets.fromLTRB(16, 12, 16, 16),
      decoration: BoxDecoration(
        color: Theme.of(context).scaffoldBackgroundColor,
        border: Border(top: BorderSide(color: Colors.grey.shade200)),
      ),
      child: Column(
        children: [
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              const Text('Taxminiy jami:',
                  style: TextStyle(fontWeight: FontWeight.w500)),
              Text(
                _fmtPrice(widget.cartState.estimatedTotal),
                style: const TextStyle(
                  fontWeight: FontWeight.bold,
                  fontSize: 16,
                ),
              ),
            ],
          ),
          const SizedBox(height: 4),
          Text(
            'Server-avtoritar: haqiqiy narx backend hisoblaydi.',
            style: TextStyle(fontSize: 11, color: Colors.grey.shade500),
          ),
          const SizedBox(height: 12),
          SizedBox(
            width: double.infinity,
            child: FilledButton(
              onPressed: _ordering ? null : _placeOrders,
              child: _ordering
                  ? const SizedBox(
                      height: 20,
                      width: 20,
                      child: CircularProgressIndicator(
                          strokeWidth: 2, color: Colors.white),
                    )
                  : const Text('Buyurtma berish'),
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

    for (final item in items) {
      try {
        await ref
            .read(createMarketplaceOrderProvider.notifier)
            .createOrder(
              productId: item.product.id,
              qty: item.qty,
            );
        final state = ref.read(createMarketplaceOrderProvider);
        if (state is CreateOrderSuccess) successCount++;
        if (state is CreateOrderFailure) errors.add(item.product.name);
        ref.read(createMarketplaceOrderProvider.notifier).reset();
      } catch (_) {
        errors.add(item.product.name);
      }
    }

    if (!mounted) return;

    setState(() => _ordering = false);

    if (errors.isEmpty) {
      ref.read(marketplaceCartProvider.notifier).clear();
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text('$successCount ta buyurtma muvaffaqiyatli yaratildi'),
          backgroundColor: Colors.green,
        ),
      );
      context.go('/home/marketplace/orders');
    } else {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(
            '$successCount ta muvaffaqiyatli. '
            'Xatolik: ${errors.join(', ')}',
          ),
          backgroundColor: Colors.orange,
        ),
      );
    }
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
