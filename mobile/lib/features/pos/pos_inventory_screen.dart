import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

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
          // Ogohlantirish paneli (expired / near_expiry bo'lsa)
          if (expiredCount > 0 || nearExpiryCount > 0)
            _ExpiryWarningBanner(
              expiredCount: expiredCount,
              nearExpiryCount: nearExpiryCount,
            ),

          // Qidiruv
          Padding(
            padding: const EdgeInsets.fromLTRB(12, 8, 12, 4),
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
                        },
                      )
                    : null,
                border: OutlineInputBorder(
                    borderRadius: BorderRadius.circular(8)),
                contentPadding: const EdgeInsets.symmetric(vertical: 8),
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
              InventoryLoading() =>
                const Center(child: CircularProgressIndicator()),
              InventoryError(:final message) => _ErrorView(
                  message: message,
                  onRetry: () =>
                      ref.read(inventoryNotifierProvider.notifier).load(),
                ),
              InventoryLoaded() => filtered.isEmpty
                  ? const Center(
                      child: Text('Mahsulot topilmadi',
                          style: TextStyle(color: Colors.grey)),
                    )
                  : ListView.builder(
                      padding: const EdgeInsets.symmetric(horizontal: 8),
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

class _ExpiryWarningBanner extends StatelessWidget {
  const _ExpiryWarningBanner({
    required this.expiredCount,
    required this.nearExpiryCount,
  });
  final int expiredCount;
  final int nearExpiryCount;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 10),
      color: Colors.red.shade50,
      child: Row(
        children: [
          const Icon(Icons.warning_amber_rounded, color: Colors.red, size: 20),
          const SizedBox(width: 8),
          Expanded(
            child: Text.rich(
              TextSpan(
                children: [
                  if (expiredCount > 0)
                    TextSpan(
                      text: '$expiredCount ta muddati o\'tgan',
                      style: const TextStyle(
                          color: Colors.red,
                          fontWeight: FontWeight.w700,
                          fontSize: 13),
                    ),
                  if (expiredCount > 0 && nearExpiryCount > 0)
                    const TextSpan(text: '  ·  '),
                  if (nearExpiryCount > 0)
                    TextSpan(
                      text: '$nearExpiryCount ta muddat yaqin',
                      style: TextStyle(
                          color: Colors.orange.shade700,
                          fontWeight: FontWeight.w600,
                          fontSize: 13),
                    ),
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }
}

class _InventoryCard extends StatelessWidget {
  const _InventoryCard({required this.item});
  final InventoryItem item;

  @override
  Widget build(BuildContext context) {
    Color? cardColor;
    Color borderColor = Colors.transparent;
    IconData leadIcon = Icons.inventory_2_outlined;
    Color leadColor = Colors.grey;

    if (item.isExpired) {
      cardColor = Colors.red.shade50;
      borderColor = Colors.red.shade300;
      leadIcon = Icons.block;
      leadColor = Colors.red;
    } else if (item.isNearExpiry) {
      cardColor = Colors.orange.shade50;
      borderColor = Colors.orange.shade300;
      leadIcon = Icons.warning_amber_rounded;
      leadColor = Colors.orange.shade700;
    }

    return Card(
      margin: const EdgeInsets.symmetric(vertical: 4, horizontal: 4),
      color: cardColor,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(10),
        side: BorderSide(
            color: borderColor,
            width: item.hasExpiryWarning ? 1.0 : 0.0),
      ),
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Icon(leadIcon, color: leadColor, size: 28),
            const SizedBox(width: 12),
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
                          style: TextStyle(
                            fontWeight: FontWeight.w600,
                            fontSize: 14,
                            color: item.isExpired
                                ? Colors.red.shade700
                                : null,
                            decoration: item.isExpired
                                ? TextDecoration.lineThrough
                                : null,
                          ),
                        ),
                      ),
                      if (item.isExpired)
                        const _Badge(
                            label: 'YAROQSIZ',
                            color: Colors.red)
                      else if (item.isNearExpiry)
                        _Badge(
                            label: item.daysToExpiry != null
                                ? '${item.daysToExpiry}K QOLDI'
                                : 'MUDDAT YAQIN',
                            color: Colors.orange),
                    ],
                  ),

                  const SizedBox(height: 4),

                  // SKU + birlik
                  if (item.sku.isNotEmpty)
                    Text(
                      'SKU: ${item.sku}  ·  Birlik: ${item.unit}',
                      style: const TextStyle(
                          fontSize: 11, color: Colors.grey),
                    ),

                  const SizedBox(height: 6),

                  // Miqdor + narx
                  Wrap(
                    spacing: 16,
                    children: [
                      _InfoChip(
                        label: 'Qoldiq',
                        value:
                            '${_fmtQty(item.qty)} ${item.unit}',
                        color: item.qty <= 0
                            ? Colors.red
                            : Colors.blue,
                      ),
                      _InfoChip(
                        label: 'Sotuv narxi',
                        value:
                            '${item.salePrice.toStringAsFixed(0)} so\'m',
                        color: Colors.green,
                      ),
                      _InfoChip(
                        label: 'Tan narxi',
                        value:
                            '${item.costPrice.toStringAsFixed(0)} so\'m',
                        color: Colors.grey,
                      ),
                    ],
                  ),

                  // Muddat
                  if (item.expiryDate != null) ...[
                    const SizedBox(height: 4),
                    Text(
                      'Muddat: ${_fmtDate(item.expiryDate!)}',
                      style: TextStyle(
                        fontSize: 12,
                        color: item.isExpired
                            ? Colors.red
                            : item.isNearExpiry
                                ? Colors.orange.shade700
                                : Colors.grey,
                        fontWeight: item.hasExpiryWarning
                            ? FontWeight.w600
                            : FontWeight.normal,
                      ),
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

class _Badge extends StatelessWidget {
  const _Badge({required this.label, required this.color});
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
            color: color, fontSize: 9, fontWeight: FontWeight.w800,
            letterSpacing: 0.5),
      ),
    );
  }
}

class _InfoChip extends StatelessWidget {
  const _InfoChip(
      {required this.label, required this.value, required this.color});
  final String label;
  final String value;
  final Color color;

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(label,
            style: const TextStyle(fontSize: 10, color: Colors.grey)),
        Text(value,
            style: TextStyle(
                fontSize: 13,
                color: color,
                fontWeight: FontWeight.w600)),
      ],
    );
  }
}

class _ErrorView extends StatelessWidget {
  const _ErrorView({required this.message, required this.onRetry});
  final String message;
  final VoidCallback onRetry;

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(24),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            const Icon(Icons.error_outline, color: Colors.red, size: 48),
            const SizedBox(height: 12),
            Text('Xatolik: $message',
                textAlign: TextAlign.center,
                style: const TextStyle(color: Colors.red)),
            const SizedBox(height: 16),
            ElevatedButton.icon(
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
