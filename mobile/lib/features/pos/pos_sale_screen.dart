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

/// POS sotuv ekrani — chiroyli kassa interfeysi.
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
        ref.read(inventoryNotifierProvider.notifier).load();
        _showReceipt(context, next.response);
      } else if (next is CheckoutFailure) {
        _showError(context, next);
      }
    });

    return Scaffold(
      appBar: AppBar(
        title: Row(
          children: [
            const Text('Kassa'),
            if (cart.items.isNotEmpty) ...[
              const SizedBox(width: AppSpacing.sm),
              _CartCountBadge(count: cart.items.length),
            ],
          ],
        ),
        actions: [
          if (cart.items.isNotEmpty)
            TextButton.icon(
              onPressed: () => ref.read(cartProvider.notifier).clear(),
              icon: const Icon(Icons.delete_sweep_outlined,
                  size: AppSpacing.iconSm),
              label: const Text('Tozalash'),
              style: TextButton.styleFrom(
                foregroundColor: Theme.of(context).colorScheme.error,
              ),
            ),
        ],
      ),
      body: Column(
        children: [
          if (cart.items.isEmpty)
            Expanded(
              child: EmptyState(
                icon: Icons.point_of_sale_outlined,
                title: 'Savat bo\'sh',
                message:
                    'Mahsulot qo\'shish uchun pastdagi tugmani bosing',
                actionLabel: 'Mahsulot qo\'shish',
                onAction: isLoading
                    ? null
                    : () => _showProductPicker(context),
              ),
            )
          else
            Expanded(
              child: Column(
                children: [
                  // Savat ro'yxati
                  Expanded(
                    child: ListView.builder(
                      padding: const EdgeInsets.fromLTRB(
                        AppSpacing.lg,
                        AppSpacing.md,
                        AppSpacing.lg,
                        AppSpacing.sm,
                      ),
                      itemCount: cart.items.length,
                      itemBuilder: (context, i) =>
                          _CartItemCard(cartItem: cart.items[i]),
                    ),
                  ),
                  // To'lov usuli + jami
                  _CheckoutPanel(cart: cart, isLoading: isLoading),
                ],
              ),
            ),
        ],
      ),
      floatingActionButton: cart.items.isEmpty
          ? null
          : FloatingActionButton.extended(
              onPressed: isLoading
                  ? null
                  : () => _showProductPicker(context),
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
    final cs = Theme.of(context).colorScheme;
    final appColors = AppTheme.colorsOf(context);
    final isExpired = failure.isExpiredError;
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Row(
          children: [
            Icon(
              isExpired
                  ? Icons.warning_amber_rounded
                  : Icons.error_outline,
              color: appColors.onDanger,
              size: AppSpacing.iconSm,
            ),
            const SizedBox(width: AppSpacing.sm),
            Expanded(child: Text(failure.message)),
          ],
        ),
        backgroundColor: appColors.danger,
        duration: const Duration(seconds: 5),
        behavior: SnackBarBehavior.floating,
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(AppSpacing.radiusMd),
        ),
      ),
    );
  }
}

// ---------------------------------------------------------------------------
// Savat elementi kartasi

class _CartCountBadge extends StatelessWidget {
  const _CartCountBadge({required this.count});
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

class _CartItemCard extends ConsumerWidget {
  const _CartItemCard({required this.cartItem});
  final CartItem cartItem;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final cs = Theme.of(context).colorScheme;
    final tt = Theme.of(context).textTheme;
    final appColors = AppTheme.colorsOf(context);
    final item = cartItem.item;
    final isExpiredWarning = item.hasExpiryWarning;

    return Padding(
      padding: const EdgeInsets.only(bottom: AppSpacing.sm),
      child: AppCard(
        padding: const EdgeInsets.all(AppSpacing.md),
        color: item.isExpired
            ? appColors.dangerContainer.withValues(alpha: 0.35)
            : item.isNearExpiry
                ? appColors.warningContainer.withValues(alpha: 0.35)
                : null,
        borderColor: item.isExpired
            ? appColors.danger.withValues(alpha: 0.4)
            : item.isNearExpiry
                ? appColors.warning.withValues(alpha: 0.4)
                : null,
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            // Mahsulot ikonasi
            Container(
              width: 40,
              height: 40,
              decoration: BoxDecoration(
                color: isExpiredWarning
                    ? (item.isExpired
                        ? appColors.dangerContainer
                        : appColors.warningContainer)
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
                size: AppSpacing.iconSm,
                color: item.isExpired
                    ? appColors.danger
                    : item.isNearExpiry
                        ? appColors.warning
                        : cs.primary,
              ),
            ),

            const SizedBox(width: AppSpacing.md),

            // Matn qismi
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
                            decoration: item.isExpired
                                ? TextDecoration.lineThrough
                                : null,
                          ),
                        ),
                      ),
                      const SizedBox(width: AppSpacing.xs),
                      if (item.isExpired)
                        StatusBadge(
                          status: 'Yaroqsiz',
                          variant: StatusVariant.danger,
                          size: StatusBadgeSize.small,
                        )
                      else if (item.isNearExpiry)
                        StatusBadge(
                          status: item.daysToExpiry != null
                              ? '${item.daysToExpiry}k qoldi'
                              : 'Muddat yaqin',
                          variant: StatusVariant.warning,
                          size: StatusBadgeSize.small,
                        ),
                    ],
                  ),
                  const SizedBox(height: AppSpacing.xs),
                  // Narx
                  Text(
                    '${_fmt(item.salePrice)} so\'m/${item.unit}'
                    '  ·  Jami: ${_fmt(item.salePrice * cartItem.qty)} so\'m',
                    style: tt.bodySmall?.copyWith(
                      color: cs.onSurfaceVariant,
                    ),
                  ),
                ],
              ),
            ),

            const SizedBox(width: AppSpacing.xs),

            // Miqdor boshqaruvi
            _QtyControl(
              qty: cartItem.qty,
              onDecrement: () => ref
                  .read(cartProvider.notifier)
                  .updateQty(item.productId, cartItem.qty - 1),
              onIncrement: () => ref
                  .read(cartProvider.notifier)
                  .updateQty(item.productId, cartItem.qty + 1),
              onRemove: () => ref
                  .read(cartProvider.notifier)
                  .removeItem(item.productId),
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
    final cs = Theme.of(context).colorScheme;
    final appColors = AppTheme.colorsOf(context);

    return Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        // Qty row
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
                onPressed: onDecrement,
                color: cs.onSurfaceVariant,
              ),
              SizedBox(
                width: 32,
                child: Text(
                  qty % 1 == 0
                      ? qty.toStringAsFixed(0)
                      : qty.toStringAsFixed(1),
                  textAlign: TextAlign.center,
                  style: Theme.of(context).textTheme.titleSmall?.copyWith(
                        fontWeight: FontWeight.w700,
                      ),
                ),
              ),
              _QtyBtn(
                icon: Icons.add,
                onPressed: onIncrement,
                color: cs.primary,
              ),
            ],
          ),
        ),
        const SizedBox(height: AppSpacing.xs),
        // O'chirish
        GestureDetector(
          onTap: onRemove,
          child: Icon(
            Icons.delete_outline,
            size: AppSpacing.iconSm,
            color: appColors.danger,
          ),
        ),
      ],
    );
  }
}

class _QtyBtn extends StatelessWidget {
  const _QtyBtn({
    required this.icon,
    required this.onPressed,
    required this.color,
  });
  final IconData icon;
  final VoidCallback onPressed;
  final Color color;

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
// Checkout paneli

class _CheckoutPanel extends ConsumerWidget {
  const _CheckoutPanel({required this.cart, required this.isLoading});
  final CartState cart;
  final bool isLoading;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final cs = Theme.of(context).colorScheme;
    final tt = Theme.of(context).textTheme;

    return Container(
      padding: const EdgeInsets.fromLTRB(
        AppSpacing.lg,
        AppSpacing.md,
        AppSpacing.lg,
        AppSpacing.lg,
      ),
      decoration: BoxDecoration(
        color: cs.surface,
        border: Border(
          top: BorderSide(color: cs.outlineVariant),
        ),
        boxShadow: [
          BoxShadow(
            color: cs.shadow.withValues(alpha: 0.06),
            blurRadius: 12,
            offset: const Offset(0, -4),
          ),
        ],
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        mainAxisSize: MainAxisSize.min,
        children: [
          // To'lov usuli
          Row(
            children: [
              Text(
                'To\'lov usuli',
                style: tt.labelMedium?.copyWith(
                  color: cs.onSurfaceVariant,
                  fontWeight: FontWeight.w600,
                ),
              ),
              const SizedBox(width: AppSpacing.md),
              Expanded(
                child: SegmentedButton<String>(
                  segments: const [
                    ButtonSegment(
                      value: 'cash',
                      label: Text('Naqd'),
                      icon: Icon(Icons.money, size: 14),
                    ),
                    ButtonSegment(
                      value: 'card',
                      label: Text('Karta'),
                      icon: Icon(Icons.credit_card, size: 14),
                    ),
                    ButtonSegment(
                      value: 'transfer',
                      label: Text("O'tkazma"),
                      icon:
                          Icon(Icons.account_balance, size: 14),
                    ),
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

          const SizedBox(height: AppSpacing.md),
          Divider(color: cs.outlineVariant, height: 1),
          const SizedBox(height: AppSpacing.md),

          // Jami + Checkout
          Row(
            crossAxisAlignment: CrossAxisAlignment.end,
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
                    const SizedBox(height: 2),
                    Text(
                      '${_fmtAmount(cart.estimatedTotal)} so\'m',
                      style: tt.headlineSmall?.copyWith(
                        fontWeight: FontWeight.w800,
                        color: cs.onSurface,
                        letterSpacing: -0.5,
                      ),
                    ),
                    Text(
                      'Server narxi hisoblanadi',
                      style: tt.labelSmall?.copyWith(
                        color: cs.onSurfaceVariant.withValues(alpha: 0.6),
                      ),
                    ),
                  ],
                ),
              ),
              const SizedBox(width: AppSpacing.md),
              FilledButton.icon(
                onPressed: isLoading
                    ? null
                    : () => ref
                        .read(checkoutProvider.notifier)
                        .checkout(cart),
                style: FilledButton.styleFrom(
                  backgroundColor: AppTheme.colorsOf(context).success,
                  foregroundColor:
                      AppTheme.colorsOf(context).onSuccess,
                  padding: const EdgeInsets.symmetric(
                    horizontal: AppSpacing.xl,
                    vertical: AppSpacing.md,
                  ),
                ),
                icon: isLoading
                    ? SizedBox(
                        width: 18,
                        height: 18,
                        child: CircularProgressIndicator(
                          strokeWidth: 2,
                          color: AppTheme.colorsOf(context).onSuccess,
                        ),
                      )
                    : const Icon(Icons.check_circle_outline),
                label: Text(
                  isLoading ? 'Yuborilmoqda...' : 'Sotish',
                  style: const TextStyle(fontWeight: FontWeight.w700),
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }

  String _fmtAmount(double v) {
    final s = v.toStringAsFixed(0);
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

class _InventoryPickerSheetState
    extends ConsumerState<_InventoryPickerSheet> {
  final _controller = TextEditingController();

  @override
  void dispose() {
    _controller.dispose();
    ref.read(inventorySearchProvider.notifier).clear();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
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
              width: 32,
              height: 4,
              margin: const EdgeInsets.only(
                  top: AppSpacing.sm, bottom: AppSpacing.md),
              decoration: BoxDecoration(
                color: cs.outlineVariant,
                borderRadius:
                    BorderRadius.circular(AppSpacing.radiusFull),
              ),
            ),
          ),

          Padding(
            padding: const EdgeInsets.fromLTRB(
              AppSpacing.lg,
              0,
              AppSpacing.md,
              AppSpacing.sm,
            ),
            child: SectionHeader(
              title: 'Mahsulot tanlash',
              actionLabel: 'Yangilash',
              onAction: () =>
                  ref.read(inventoryNotifierProvider.notifier).load(),
            ),
          ),

          // Qidiruv
          Padding(
            padding: const EdgeInsets.fromLTRB(
              AppSpacing.lg,
              0,
              AppSpacing.lg,
              AppSpacing.sm,
            ),
            child: TextField(
              controller: _controller,
              decoration: const InputDecoration(
                hintText: 'Mahsulot qidirish...',
                prefixIcon: Icon(Icons.search),
              ),
              onChanged: (v) {
                setState(() {});
                ref
                    .read(inventorySearchProvider.notifier)
                    .setQuery(v);
              },
            ),
          ),

          // Ro'yxat
          Expanded(
            child: switch (inventoryState) {
              InventoryLoading() => const Center(
                  child: CircularProgressIndicator(),
                ),
              InventoryError(:final message) => _PickerError(
                  message: message,
                  onRetry: () =>
                      ref.read(inventoryNotifierProvider.notifier).load(),
                ),
              InventoryLoaded() => filtered.isEmpty
                  ? EmptyState(
                      icon: Icons.search_off,
                      title: 'Mahsulot topilmadi',
                      compact: true,
                    )
                  : ListView.builder(
                      controller: scrollCtrl,
                      padding: const EdgeInsets.symmetric(
                          horizontal: AppSpacing.lg),
                      itemCount: filtered.length,
                      itemBuilder: (ctx, i) =>
                          _InventoryPickerItem(item: filtered[i]),
                    ),
            },
          ),
        ],
      ),
    );
  }
}

class _PickerError extends StatelessWidget {
  const _PickerError({required this.message, required this.onRetry});
  final String message;
  final VoidCallback onRetry;

  @override
  Widget build(BuildContext context) {
    final appColors = AppTheme.colorsOf(context);
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(AppSpacing.xl),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(Icons.error_outline,
                color: appColors.danger, size: AppSpacing.iconXl),
            const SizedBox(height: AppSpacing.md),
            Text(
              'Xatolik: $message',
              textAlign: TextAlign.center,
              style: TextStyle(color: appColors.danger),
            ),
            const SizedBox(height: AppSpacing.lg),
            OutlinedButton.icon(
              onPressed: onRetry,
              icon: const Icon(Icons.refresh),
              label: const Text('Qayta urinish'),
            ),
          ],
        ),
      ),
    );
  }
}

class _InventoryPickerItem extends ConsumerWidget {
  const _InventoryPickerItem({required this.item});
  final InventoryItem item;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final cs = Theme.of(context).colorScheme;
    final tt = Theme.of(context).textTheme;
    final appColors = AppTheme.colorsOf(context);
    final isBlocked = item.isExpired;

    return Padding(
      padding: const EdgeInsets.only(bottom: AppSpacing.sm),
      child: AppCard(
        padding: const EdgeInsets.symmetric(
          horizontal: AppSpacing.md,
          vertical: AppSpacing.sm,
        ),
        color: item.isExpired
            ? appColors.dangerContainer.withValues(alpha: 0.2)
            : item.isNearExpiry
                ? appColors.warningContainer.withValues(alpha: 0.2)
                : null,
        borderColor: item.isExpired
            ? appColors.danger.withValues(alpha: 0.3)
            : item.isNearExpiry
                ? appColors.warning.withValues(alpha: 0.3)
                : null,
        onTap: isBlocked
            ? () => _showBlockedSnack(context)
            : () {
                ref.read(cartProvider.notifier).addItem(item);
                Navigator.of(context).pop();
              },
        child: Row(
          children: [
            // Icon
            Container(
              width: 40,
              height: 40,
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
                size: AppSpacing.iconSm,
                color: item.isExpired
                    ? appColors.danger
                    : item.isNearExpiry
                        ? appColors.warning
                        : cs.primary,
              ),
            ),

            const SizedBox(width: AppSpacing.md),

            // Matn
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    children: [
                      Expanded(
                        child: Text(
                          item.productName,
                          style: tt.titleSmall?.copyWith(
                            color: isBlocked
                                ? appColors.danger
                                : cs.onSurface,
                            decoration: isBlocked
                                ? TextDecoration.lineThrough
                                : null,
                          ),
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                        ),
                      ),
                      if (item.isExpired)
                        StatusBadge(
                          status: 'Yaroqsiz',
                          variant: StatusVariant.danger,
                          size: StatusBadgeSize.small,
                        )
                      else if (item.isNearExpiry)
                        StatusBadge(
                          status: item.daysToExpiry != null
                              ? '${item.daysToExpiry}k'
                              : 'Muddat yaqin',
                          variant: StatusVariant.warning,
                          size: StatusBadgeSize.small,
                        ),
                    ],
                  ),
                  const SizedBox(height: 2),
                  Text(
                    '${_fmtQty(item.qty)} ${item.unit}  ·  '
                    '${item.salePrice.toStringAsFixed(0)} so\'m',
                    style: tt.bodySmall?.copyWith(
                      color: cs.onSurfaceVariant,
                    ),
                  ),
                  if (item.isExpired)
                    Text(
                      'Muddati o\'tgan — sotib bo\'lmaydi',
                      style: tt.labelSmall?.copyWith(
                        color: appColors.danger,
                        fontWeight: FontWeight.w600,
                      ),
                    )
                  else if (item.isNearExpiry && item.daysToExpiry != null)
                    Text(
                      'Muddat: ${item.daysToExpiry} kun qoldi',
                      style: tt.labelSmall?.copyWith(
                        color: appColors.warning,
                        fontWeight: FontWeight.w600,
                      ),
                    ),
                ],
              ),
            ),

            const SizedBox(width: AppSpacing.sm),

            // Trailing
            if (isBlocked)
              Icon(Icons.not_interested,
                  color: appColors.danger.withValues(alpha: 0.5),
                  size: AppSpacing.iconSm)
            else
              Icon(Icons.add_circle_outline,
                  color: cs.primary, size: AppSpacing.iconMd),
          ],
        ),
      ),
    );
  }

  void _showBlockedSnack(BuildContext context) {
    final appColors = AppTheme.colorsOf(context);
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: const Row(
          children: [
            Icon(Icons.block, color: Colors.white, size: AppSpacing.iconSm),
            SizedBox(width: AppSpacing.sm),
            Expanded(
              child: Text(
                'Bu mahsulot muddati o\'tgan — savatga qo\'shib bo\'lmaydi',
              ),
            ),
          ],
        ),
        backgroundColor: appColors.danger,
        behavior: SnackBarBehavior.floating,
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(AppSpacing.radiusMd),
        ),
      ),
    );
  }

  String _fmtQty(double qty) =>
      qty % 1 == 0 ? qty.toStringAsFixed(0) : qty.toStringAsFixed(2);
}

// ---------------------------------------------------------------------------
// Kvitansiya dialog

class _ReceiptDialog extends StatelessWidget {
  const _ReceiptDialog({required this.response});
  final PosSaleResponse response;

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    final tt = Theme.of(context).textTheme;
    final appColors = AppTheme.colorsOf(context);

    return AlertDialog(
      title: Row(
        children: [
          Container(
            width: 40,
            height: 40,
            decoration: BoxDecoration(
              color: appColors.successContainer,
              shape: BoxShape.circle,
            ),
            child: Icon(Icons.check,
                color: appColors.success, size: AppSpacing.iconMd),
          ),
          const SizedBox(width: AppSpacing.md),
          Expanded(
            child: Text(
              'Sotuv muvaffaqiyatli',
              style: tt.titleMedium?.copyWith(fontWeight: FontWeight.w700),
            ),
          ),
        ],
      ),
      content: SingleChildScrollView(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            _ReceiptRow(
                'ID',
                response.saleId.length > 8
                    ? '${response.saleId.substring(0, 8)}...'
                    : response.saleId),
            _ReceiptRow(
                "To'lov", _paymentMethodLabel(response.paymentMethod)),
            Divider(color: cs.outlineVariant, height: AppSpacing.lg),
            // Mahsulotlar
            ...response.items.map((item) => Padding(
                  padding: const EdgeInsets.symmetric(
                      vertical: AppSpacing.xs),
                  child: Row(
                    children: [
                      Expanded(
                        child: Text(
                          item.productName,
                          style: tt.bodySmall,
                        ),
                      ),
                      Text(
                        '${_fmtQty(item.qty)} × '
                        '${item.unitPrice.toStringAsFixed(0)}',
                        style: tt.bodySmall?.copyWith(
                          color: cs.onSurfaceVariant,
                        ),
                      ),
                    ],
                  ),
                )),
            Divider(color: cs.outlineVariant, height: AppSpacing.lg),
            Row(
              children: [
                Text(
                  'JAMI',
                  style: tt.titleSmall?.copyWith(
                    fontWeight: FontWeight.w700,
                  ),
                ),
                const Spacer(),
                Text(
                  '${response.totalAmount.toStringAsFixed(0)} so\'m',
                  style: tt.titleMedium?.copyWith(
                    fontWeight: FontWeight.w800,
                    color: appColors.success,
                    letterSpacing: -0.5,
                  ),
                ),
              ],
            ),
          ],
        ),
      ),
      actions: [
        FilledButton(
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
    final cs = Theme.of(context).colorScheme;
    final tt = Theme.of(context).textTheme;
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: AppSpacing.xs),
      child: Row(
        children: [
          Text(
            '$label: ',
            style: tt.bodySmall?.copyWith(color: cs.onSurfaceVariant),
          ),
          Text(
            value,
            style: tt.bodySmall?.copyWith(fontWeight: FontWeight.w600),
          ),
        ],
      ),
    );
  }
}
