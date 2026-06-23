import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'pos_models.dart';
import 'pos_providers.dart';

/// POS sotuv ekrani — savat + checkout.
///
/// Qoida (server-avtoritar):
///   - Faqat product_id + qty yuboriladi.
///   - Narx YUBORILMAYDI — server hisoblaydi.
///   - Expired mahsulot savatga qo'shib bo'lmaydi.
///   - 422 pos.product_expired → qizil ogohlantirish.
class PosSaleScreen extends ConsumerWidget {
  const PosSaleScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final cart = ref.watch(cartProvider);
    final checkoutState = ref.watch(checkoutProvider);
    final isLoading = checkoutState is CheckoutLoading;

    // Muvaffaqiyatli sotuv → kvitansiya
    ref.listen(checkoutProvider, (_, next) {
      if (next is CheckoutSuccess) {
        ref.read(cartProvider.notifier).clear();
        // Inventarni yangilash
        ref.read(inventoryNotifierProvider.notifier).load();
        _showReceipt(context, next.response);
      } else if (next is CheckoutFailure) {
        _showError(context, next);
      }
    });

    return Scaffold(
      appBar: AppBar(
        title: const Text('POS Sotuv'),
        actions: [
          if (cart.items.isNotEmpty)
            TextButton.icon(
              onPressed: () => ref.read(cartProvider.notifier).clear(),
              icon: const Icon(Icons.delete_outline, size: 18),
              label: const Text('Tozalash'),
            ),
        ],
      ),
      body: Column(
        children: [
          // Savat bo'sh bo'lganda mahsulot tanlash hint
          if (cart.items.isEmpty)
            const Expanded(
              child: Center(
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Icon(Icons.shopping_cart_outlined,
                        size: 64, color: Colors.grey),
                    SizedBox(height: 16),
                    Text(
                      'Savat bo\'sh',
                      style: TextStyle(
                          color: Colors.grey,
                          fontSize: 18,
                          fontWeight: FontWeight.w500),
                    ),
                    SizedBox(height: 8),
                    Text(
                      'Mahsulot qo\'shish uchun pastdagi tugmani bosing',
                      style: TextStyle(color: Colors.grey, fontSize: 13),
                      textAlign: TextAlign.center,
                    ),
                  ],
                ),
              ),
            )
          else
            Expanded(
              child: Column(
                children: [
                  // Savat ro'yxati
                  Expanded(
                    child: ListView.builder(
                      padding: const EdgeInsets.fromLTRB(12, 8, 12, 0),
                      itemCount: cart.items.length,
                      itemBuilder: (context, i) =>
                          _CartItemRow(cartItem: cart.items[i]),
                    ),
                  ),

                  // To'lov usuli + jami
                  _CheckoutPanel(cart: cart, isLoading: isLoading),
                ],
              ),
            ),
        ],
      ),
      floatingActionButton: FloatingActionButton.extended(
        onPressed: isLoading ? null : () => _showProductPicker(context),
        icon: const Icon(Icons.add_shopping_cart),
        label: const Text('Mahsulot qo\'shish'),
      ),
    );
  }

  Future<void> _showProductPicker(BuildContext context) async {
    await showModalBottomSheet<void>(
      context: context,
      isScrollControlled: true,
      useSafeArea: true,
      builder: (_) => const _InventoryPickerSheet(),
    );
  }

  void _showReceipt(BuildContext context, PosSaleResponse response) {
    showDialog<void>(
      context: context,
      barrierDismissible: false,
      builder: (_) => _ReceiptDialog(response: response),
    );
  }

  void _showError(BuildContext context, CheckoutFailure failure) {
    final isExpired = failure.isExpiredError;
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Row(
          children: [
            Icon(
              isExpired ? Icons.warning_amber_rounded : Icons.error_outline,
              color: Colors.white,
              size: 20,
            ),
            const SizedBox(width: 8),
            Expanded(child: Text(failure.message)),
          ],
        ),
        backgroundColor: Colors.red.shade700,
        duration: const Duration(seconds: 5),
        behavior: SnackBarBehavior.floating,
      ),
    );
  }
}

// ---------------------------------------------------------------------------

class _CartItemRow extends ConsumerWidget {
  const _CartItemRow({required this.cartItem});
  final CartItem cartItem;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final item = cartItem.item;
    final isExpiredWarning = item.hasExpiryWarning;

    return Card(
      margin: const EdgeInsets.symmetric(vertical: 4),
      color: isExpiredWarning ? Colors.red.shade50 : null,
      shape: isExpiredWarning
          ? RoundedRectangleBorder(
              borderRadius: BorderRadius.circular(12),
              side: BorderSide(color: Colors.red.shade300),
            )
          : null,
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
        child: Row(
          children: [
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    children: [
                      Expanded(
                        child: Text(
                          item.productName,
                          style: const TextStyle(fontWeight: FontWeight.w600),
                        ),
                      ),
                      if (item.isExpired)
                        const _ExpiryBadge(label: 'Yaroqsiz', color: Colors.red)
                      else if (item.isNearExpiry)
                        _ExpiryBadge(
                            label: item.daysToExpiry != null
                                ? '${item.daysToExpiry}k qoldi'
                                : 'Muddat yaqin',
                            color: Colors.orange),
                    ],
                  ),
                  const SizedBox(height: 2),
                  Text(
                    // Narx display uchun (server hisoblaydi, lokal tahminy)
                    '${_fmt(item.salePrice)} so\'m / ${item.unit}  '
                    '·  Jami: ${_fmt(item.salePrice * cartItem.qty)} so\'m',
                    style: const TextStyle(fontSize: 11, color: Colors.grey),
                  ),
                ],
              ),
            ),
            // Miqdor boshqaruvi
            _QtyControl(
              qty: cartItem.qty,
              onDecrement: () => ref
                  .read(cartProvider.notifier)
                  .updateQty(item.productId, cartItem.qty - 1),
              onIncrement: () => ref
                  .read(cartProvider.notifier)
                  .updateQty(item.productId, cartItem.qty + 1),
              onRemove: () =>
                  ref.read(cartProvider.notifier).removeItem(item.productId),
            ),
          ],
        ),
      ),
    );
  }

  String _fmt(double v) {
    if (v == v.truncate()) return v.toStringAsFixed(0);
    return v.toStringAsFixed(2);
  }
}

class _ExpiryBadge extends StatelessWidget {
  const _ExpiryBadge({required this.label, required this.color});
  final String label;
  final Color color;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.15),
        borderRadius: BorderRadius.circular(6),
        border: Border.all(color: color.withValues(alpha: 0.5)),
      ),
      child: Text(
        label,
        style: TextStyle(
            color: color, fontSize: 10, fontWeight: FontWeight.w700),
      ),
    );
  }
}

class _QtyControl extends StatelessWidget {
  const _QtyControl({
    required this.qty,
    required this.onDecrement,
    required this.onIncrement,
    required this.onRemove,
  });
  final double qty;
  final VoidCallback onDecrement;
  final VoidCallback onIncrement;
  final VoidCallback onRemove;

  @override
  Widget build(BuildContext context) {
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        IconButton(
          icon: const Icon(Icons.remove_circle_outline),
          iconSize: 20,
          onPressed: onDecrement,
        ),
        SizedBox(
          width: 36,
          child: Text(
            qty % 1 == 0 ? qty.toStringAsFixed(0) : qty.toStringAsFixed(1),
            textAlign: TextAlign.center,
            style: const TextStyle(fontWeight: FontWeight.bold, fontSize: 16),
          ),
        ),
        IconButton(
          icon: const Icon(Icons.add_circle_outline),
          iconSize: 20,
          onPressed: onIncrement,
        ),
        IconButton(
          icon: const Icon(Icons.delete_outline, color: Colors.red),
          iconSize: 20,
          onPressed: onRemove,
        ),
      ],
    );
  }
}

// ---------------------------------------------------------------------------

class _CheckoutPanel extends ConsumerWidget {
  const _CheckoutPanel({required this.cart, required this.isLoading});
  final CartState cart;
  final bool isLoading;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    return Container(
      padding: const EdgeInsets.fromLTRB(16, 12, 16, 16),
      decoration: BoxDecoration(
        color: Theme.of(context).colorScheme.surface,
        boxShadow: [
          BoxShadow(
            color: Colors.black.withValues(alpha: 0.08),
            blurRadius: 8,
            offset: const Offset(0, -2),
          ),
        ],
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // To'lov usuli
          Row(
            children: [
              const Text('To\'lov:',
                  style: TextStyle(fontWeight: FontWeight.w500)),
              const SizedBox(width: 12),
              Expanded(
                child: SegmentedButton<String>(
                  segments: const [
                    ButtonSegment(value: 'cash', label: Text('Naqd')),
                    ButtonSegment(value: 'card', label: Text('Karta')),
                    ButtonSegment(value: 'transfer', label: Text('O\'tkazma')),
                  ],
                  selected: {cart.paymentMethod},
                  onSelectionChanged: (s) => ref
                      .read(cartProvider.notifier)
                      .setPaymentMethod(s.first),
                  style: const ButtonStyle(
                    tapTargetSize: MaterialTapTargetSize.shrinkWrap,
                  ),
                ),
              ),
            ],
          ),

          const SizedBox(height: 12),

          // Jami + Checkout tugmasi
          Row(
            children: [
              Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const Text('Jami (taxminiy)',
                      style: TextStyle(fontSize: 11, color: Colors.grey)),
                  Text(
                    '${_fmtAmount(cart.estimatedTotal)} so\'m',
                    style: const TextStyle(
                        fontWeight: FontWeight.bold, fontSize: 18),
                  ),
                  const Text(
                    'Server narxi hisoblanadi',
                    style: TextStyle(fontSize: 10, color: Colors.grey),
                  ),
                ],
              ),
              const Spacer(),
              ElevatedButton.icon(
                onPressed: isLoading
                    ? null
                    : () => ref
                        .read(checkoutProvider.notifier)
                        .checkout(cart),
                style: ElevatedButton.styleFrom(
                  backgroundColor: Colors.green,
                  foregroundColor: Colors.white,
                  padding: const EdgeInsets.symmetric(
                      horizontal: 24, vertical: 14),
                ),
                icon: isLoading
                    ? const SizedBox(
                        width: 16,
                        height: 16,
                        child: CircularProgressIndicator(
                            strokeWidth: 2, color: Colors.white),
                      )
                    : const Icon(Icons.check_circle_outline),
                label: Text(isLoading ? 'Yuborilmoqda...' : 'Sotish'),
              ),
            ],
          ),
        ],
      ),
    );
  }

  String _fmtAmount(double v) {
    final s = v.toStringAsFixed(0);
    // Minglablar uchun bo'sh joy
    final buf = StringBuffer();
    for (int i = 0; i < s.length; i++) {
      if (i > 0 && (s.length - i) % 3 == 0) buf.write(' ');
      buf.write(s[i]);
    }
    return buf.toString();
  }
}

// ---------------------------------------------------------------------------
// Mahsulot tanlash (inventar bottom sheet)

class _InventoryPickerSheet extends ConsumerStatefulWidget {
  const _InventoryPickerSheet();

  @override
  ConsumerState<_InventoryPickerSheet> createState() =>
      _InventoryPickerSheetState();
}

class _InventoryPickerSheetState extends ConsumerState<_InventoryPickerSheet> {
  final _controller = TextEditingController();

  @override
  void dispose() {
    _controller.dispose();
    ref.read(inventorySearchProvider.notifier).clear();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final inventoryState = ref.watch(inventoryNotifierProvider);
    final filtered = ref.watch(filteredInventoryProvider);

    return DraggableScrollableSheet(
      initialChildSize: 0.85,
      maxChildSize: 0.95,
      minChildSize: 0.5,
      expand: false,
      builder: (_, scrollCtrl) => Column(
        children: [
          // Handle
          Center(
            child: Container(
              width: 40,
              height: 4,
              margin: const EdgeInsets.only(top: 8, bottom: 12),
              decoration: BoxDecoration(
                color: Colors.grey.shade300,
                borderRadius: BorderRadius.circular(2),
              ),
            ),
          ),

          Padding(
            padding: const EdgeInsets.fromLTRB(16, 0, 16, 8),
            child: Row(
              children: [
                Text('Mahsulot tanlash',
                    style: Theme.of(context).textTheme.titleMedium),
                const Spacer(),
                // Yangilash tugmasi
                IconButton(
                  icon: const Icon(Icons.refresh),
                  iconSize: 20,
                  onPressed: () =>
                      ref.read(inventoryNotifierProvider.notifier).load(),
                ),
              ],
            ),
          ),

          // Qidiruv
          Padding(
            padding: const EdgeInsets.fromLTRB(16, 0, 16, 8),
            child: TextField(
              controller: _controller,
              decoration: InputDecoration(
                hintText: 'Mahsulot qidirish...',
                prefixIcon: const Icon(Icons.search),
                border:
                    OutlineInputBorder(borderRadius: BorderRadius.circular(8)),
                contentPadding: const EdgeInsets.symmetric(vertical: 8),
              ),
              onChanged:
                  ref.read(inventorySearchProvider.notifier).setQuery,
            ),
          ),

          // Ro'yxat
          Expanded(
            child: switch (inventoryState) {
              InventoryLoading() =>
                const Center(child: CircularProgressIndicator()),
              InventoryError(:final message) => Center(
                  child: Column(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      const Icon(Icons.error_outline,
                          color: Colors.red, size: 40),
                      const SizedBox(height: 8),
                      Text('Xatolik: $message',
                          textAlign: TextAlign.center,
                          style: const TextStyle(color: Colors.red)),
                      const SizedBox(height: 12),
                      TextButton(
                        onPressed: () => ref
                            .read(inventoryNotifierProvider.notifier)
                            .load(),
                        child: const Text('Qayta urinish'),
                      ),
                    ],
                  ),
                ),
              InventoryLoaded() => filtered.isEmpty
                  ? const Center(
                      child: Text('Mahsulot topilmadi',
                          style: TextStyle(color: Colors.grey)),
                    )
                  : ListView.builder(
                      controller: scrollCtrl,
                      itemCount: filtered.length,
                      itemBuilder: (ctx, i) =>
                          _InventoryListTile(item: filtered[i]),
                    ),
            },
          ),
        ],
      ),
    );
  }
}

class _InventoryListTile extends ConsumerWidget {
  const _InventoryListTile({required this.item});
  final InventoryItem item;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final isBlocked = item.isExpired;
    final isWarning = item.isNearExpiry && !item.isExpired;

    Color? tileColor;
    if (item.isExpired) {
      tileColor = Colors.red.shade50;
    } else if (item.isNearExpiry) {
      tileColor = Colors.orange.shade50;
    }

    return ListTile(
      tileColor: tileColor,
      leading: Icon(
        item.isExpired
            ? Icons.block
            : item.isNearExpiry
                ? Icons.warning_amber_rounded
                : Icons.inventory_2_outlined,
        color: item.isExpired
            ? Colors.red
            : item.isNearExpiry
                ? Colors.orange
                : null,
      ),
      title: Text(
        item.productName,
        style: TextStyle(
          fontWeight: FontWeight.w500,
          color: isBlocked ? Colors.red.shade700 : null,
          decoration: isBlocked ? TextDecoration.lineThrough : null,
        ),
      ),
      subtitle: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            '${item.qty % 1 == 0 ? item.qty.toStringAsFixed(0) : item.qty.toStringAsFixed(2)} ${item.unit}'
            '  ·  ${item.salePrice.toStringAsFixed(0)} so\'m',
            style: const TextStyle(fontSize: 12),
          ),
          if (item.isExpired)
            const Text(
              'Muddati o\'tgan — sotib bo\'lmaydi',
              style: TextStyle(
                  color: Colors.red,
                  fontSize: 11,
                  fontWeight: FontWeight.w600),
            )
          else if (item.isNearExpiry)
            Text(
              item.daysToExpiry != null
                  ? 'Muddat: ${item.daysToExpiry} kun qoldi'
                  : 'Muddat yaqinlashmoqda',
              style: TextStyle(
                  color: Colors.orange.shade700,
                  fontSize: 11,
                  fontWeight: FontWeight.w600),
            ),
        ],
      ),
      trailing: isBlocked
          ? Tooltip(
              message: 'Yaroqsiz mahsulot',
              child: Icon(Icons.not_interested, color: Colors.red.shade300),
            )
          : Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                if (isWarning)
                  Padding(
                    padding: const EdgeInsets.only(right: 4),
                    child: Icon(Icons.warning_amber_rounded,
                        color: Colors.orange.shade600, size: 18),
                  ),
                const Icon(Icons.add_circle_outline),
              ],
            ),
      onTap: isBlocked
          ? () => ScaffoldMessenger.of(context).showSnackBar(
                SnackBar(
                  content: const Row(
                    children: [
                      Icon(Icons.block, color: Colors.white, size: 18),
                      SizedBox(width: 8),
                      Expanded(
                        child: Text(
                          'Bu mahsulot muddati o\'tgan — savatga qo\'shib bo\'lmaydi',
                        ),
                      ),
                    ],
                  ),
                  backgroundColor: Colors.red.shade700,
                  behavior: SnackBarBehavior.floating,
                ),
              )
          : () {
              ref.read(cartProvider.notifier).addItem(item);
              Navigator.of(context).pop();
            },
    );
  }
}

// ---------------------------------------------------------------------------
// Kvitansiya dialog

class _ReceiptDialog extends StatelessWidget {
  const _ReceiptDialog({required this.response});
  final PosSaleResponse response;

  @override
  Widget build(BuildContext context) {
    return AlertDialog(
      title: const Row(
        children: [
          Icon(Icons.check_circle, color: Colors.green, size: 28),
          SizedBox(width: 8),
          Text('Sotuv muvaffaqiyatli'),
        ],
      ),
      content: SingleChildScrollView(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            _ReceiptRow('ID', response.saleId.length > 8
                ? '${response.saleId.substring(0, 8)}...'
                : response.saleId),
            _ReceiptRow(
                "To'lov", _paymentMethodLabel(response.paymentMethod)),
            const Divider(height: 16),
            // Mahsulotlar
            ...response.items.map((item) => Padding(
                  padding: const EdgeInsets.symmetric(vertical: 2),
                  child: Row(
                    children: [
                      Expanded(
                          child: Text(item.productName,
                              style: const TextStyle(fontSize: 13))),
                      Text(
                        '${_fmtQty(item.qty)}  ×  ${item.unitPrice.toStringAsFixed(0)}',
                        style: const TextStyle(
                            fontSize: 12, color: Colors.grey),
                      ),
                    ],
                  ),
                )),
            const Divider(height: 16),
            Row(
              children: [
                const Text('JAMI',
                    style: TextStyle(
                        fontWeight: FontWeight.bold, fontSize: 16)),
                const Spacer(),
                Text(
                  '${response.totalAmount.toStringAsFixed(0)} so\'m',
                  style: const TextStyle(
                      fontWeight: FontWeight.bold,
                      fontSize: 18,
                      color: Colors.green),
                ),
              ],
            ),
          ],
        ),
      ),
      actions: [
        ElevatedButton(
          onPressed: () => Navigator.of(context).pop(),
          child: const Text('Yopish'),
        ),
      ],
    );
  }

  String _paymentMethodLabel(String method) => switch (method) {
        'cash' => 'Naqd pul',
        'card' => 'Karta',
        'transfer' => "O'tkazma",
        _ => method,
      };

  String _fmtQty(double qty) =>
      qty % 1 == 0 ? qty.toStringAsFixed(0) : qty.toStringAsFixed(1);
}

class _ReceiptRow extends StatelessWidget {
  const _ReceiptRow(this.label, this.value);
  final String label;
  final String value;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 2),
      child: Row(
        children: [
          Text('$label: ',
              style: const TextStyle(color: Colors.grey, fontSize: 13)),
          Text(value,
              style: const TextStyle(
                  fontWeight: FontWeight.w500, fontSize: 13)),
        ],
      ),
    );
  }
}
