import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'finance_models.dart';
import 'finance_providers.dart';

/// Ledger yozuvlari ro'yxati ekrani.
///
/// Filtrlar: do'kon UUID, yozuv turi (debit | credit | hammasi).
/// Backend: GET /finance/ledger (STOCK_FINANCE.md §2.5).
class LedgerScreen extends ConsumerStatefulWidget {
  const LedgerScreen({super.key, this.initialStoreId});
  final String? initialStoreId;

  @override
  ConsumerState<LedgerScreen> createState() => _LedgerScreenState();
}

class _LedgerScreenState extends ConsumerState<LedgerScreen> {
  late final TextEditingController _storeIdController;
  String? _typeFilter; // null = hammasi, 'debit', 'credit'

  @override
  void initState() {
    super.initState();
    _storeIdController =
        TextEditingController(text: widget.initialStoreId ?? '');
    // Dastlabki yuklanish — initialStoreId bilan.
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (widget.initialStoreId != null && widget.initialStoreId!.isNotEmpty) {
        ref
            .read(ledgerNotifierProvider.notifier)
            .load(storeId: widget.initialStoreId);
      }
    });
  }

  @override
  void dispose() {
    _storeIdController.dispose();
    super.dispose();
  }

  void _applyFilters() {
    final storeId = _storeIdController.text.trim();
    ref.read(ledgerNotifierProvider.notifier).load(
          storeId: storeId.isEmpty ? null : storeId,
          entryType: _typeFilter,
        );
  }

  @override
  Widget build(BuildContext context) {
    final ledgerState = ref.watch(ledgerNotifierProvider);

    return Scaffold(
      appBar: AppBar(
        title: const Text('Buxgalteriya yozuvlari'),
        actions: [
          IconButton(
            icon: const Icon(Icons.refresh),
            tooltip: 'Yangilash',
            onPressed: () =>
                ref.read(ledgerNotifierProvider.notifier).reload(),
          ),
        ],
      ),
      body: Column(
        children: [
          // Filtr paneli
          _FilterPanel(
            controller: _storeIdController,
            typeFilter: _typeFilter,
            onTypeChanged: (v) {
              setState(() => _typeFilter = v);
              _applyFilters();
            },
            onSearch: _applyFilters,
          ),

          const Divider(height: 1),

          // Ro'yxat
          Expanded(
            child: _LedgerBody(state: ledgerState),
          ),
        ],
      ),
    );
  }
}

// ---------------------------------------------------------------------------

class _FilterPanel extends StatelessWidget {
  const _FilterPanel({
    required this.controller,
    required this.typeFilter,
    required this.onTypeChanged,
    required this.onSearch,
  });

  final TextEditingController controller;
  final String? typeFilter;
  final ValueChanged<String?> onTypeChanged;
  final VoidCallback onSearch;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(12, 10, 12, 8),
      child: Column(
        children: [
          // Do'kon UUID maydoni
          Row(
            children: [
              Expanded(
                child: TextField(
                  controller: controller,
                  decoration: InputDecoration(
                    labelText: "Do'kon UUID (ixtiyoriy)",
                    hintText: '019012ab-...',
                    border: OutlineInputBorder(
                      borderRadius: BorderRadius.circular(10),
                    ),
                    isDense: true,
                    prefixIcon: const Icon(Icons.store_outlined, size: 20),
                  ),
                  onSubmitted: (_) => onSearch(),
                ),
              ),
              const SizedBox(width: 8),
              FilledButton(
                onPressed: onSearch,
                style: FilledButton.styleFrom(
                  padding: const EdgeInsets.symmetric(
                      horizontal: 16, vertical: 12),
                ),
                child: const Text('Filtr'),
              ),
            ],
          ),
          const SizedBox(height: 8),
          // Tur filtri
          Row(
            children: [
              const Text('Tur:', style: TextStyle(fontSize: 13)),
              const SizedBox(width: 8),
              _TypeChip(
                label: 'Hammasi',
                selected: typeFilter == null,
                onTap: () => onTypeChanged(null),
              ),
              const SizedBox(width: 6),
              _TypeChip(
                label: 'Debet',
                selected: typeFilter == 'debit',
                color: Colors.red,
                onTap: () => onTypeChanged('debit'),
              ),
              const SizedBox(width: 6),
              _TypeChip(
                label: 'Kredit',
                selected: typeFilter == 'credit',
                color: Colors.green,
                onTap: () => onTypeChanged('credit'),
              ),
            ],
          ),
        ],
      ),
    );
  }
}

class _TypeChip extends StatelessWidget {
  const _TypeChip({
    required this.label,
    required this.selected,
    required this.onTap,
    this.color,
  });

  final String label;
  final bool selected;
  final VoidCallback onTap;
  final Color? color;

  @override
  Widget build(BuildContext context) {
    final activeColor = color ?? Theme.of(context).colorScheme.primary;
    return GestureDetector(
      onTap: onTap,
      child: AnimatedContainer(
        duration: const Duration(milliseconds: 150),
        padding:
            const EdgeInsets.symmetric(horizontal: 12, vertical: 5),
        decoration: BoxDecoration(
          color: selected
              ? activeColor.withValues(alpha: 0.12)
              : Colors.grey.withValues(alpha: 0.08),
          borderRadius: BorderRadius.circular(16),
          border: Border.all(
            color: selected ? activeColor : Colors.grey.withValues(alpha: 0.3),
          ),
        ),
        child: Text(
          label,
          style: TextStyle(
            fontSize: 12,
            fontWeight: selected ? FontWeight.w600 : FontWeight.normal,
            color: selected ? activeColor : Colors.grey.shade700,
          ),
        ),
      ),
    );
  }
}

// ---------------------------------------------------------------------------

class _LedgerBody extends StatelessWidget {
  const _LedgerBody({required this.state});
  final LedgerState state;

  @override
  Widget build(BuildContext context) {
    return switch (state) {
      LedgerLoading() => const Center(child: CircularProgressIndicator()),
      LedgerError(:final message) => _ErrorView(message: message),
      LedgerLoaded(:final page) => page.items.isEmpty
          ? const _EmptyView()
          : _LedgerList(page: page),
    };
  }
}

class _ErrorView extends StatelessWidget {
  const _ErrorView({required this.message});
  final String message;

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(24),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            const Icon(Icons.error_outline, size: 48, color: Colors.red),
            const SizedBox(height: 12),
            Text('Xatolik: $message',
                textAlign: TextAlign.center,
                style: const TextStyle(color: Colors.red)),
          ],
        ),
      ),
    );
  }
}

class _EmptyView extends StatelessWidget {
  const _EmptyView();

  @override
  Widget build(BuildContext context) {
    return const Center(
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(Icons.receipt_long, size: 48, color: Colors.grey),
          SizedBox(height: 12),
          Text('Yozuvlar topilmadi',
              style: TextStyle(color: Colors.grey)),
        ],
      ),
    );
  }
}

class _LedgerList extends StatelessWidget {
  const _LedgerList({required this.page});
  final LedgerPage page;

  @override
  Widget build(BuildContext context) {
    return Column(
      children: [
        // Jami ma'lumot
        Padding(
          padding: const EdgeInsets.fromLTRB(16, 6, 16, 4),
          child: Row(
            children: [
              Text(
                'Jami: ${page.total} yozuv',
                style: const TextStyle(fontSize: 12, color: Colors.grey),
              ),
            ],
          ),
        ),
        Expanded(
          child: ListView.separated(
            padding: const EdgeInsets.fromLTRB(12, 0, 12, 16),
            itemCount: page.items.length,
            separatorBuilder: (_, __) => const SizedBox(height: 6),
            itemBuilder: (context, index) {
              return _LedgerEntryTile(entry: page.items[index]);
            },
          ),
        ),
      ],
    );
  }
}

class _LedgerEntryTile extends StatelessWidget {
  const _LedgerEntryTile({required this.entry});
  final LedgerEntry entry;

  @override
  Widget build(BuildContext context) {
    final isDebit = entry.type == LedgerEntryType.debit;
    final color = isDebit ? Colors.red : Colors.green;
    final icon = isDebit ? Icons.arrow_upward : Icons.arrow_downward;
    final sign = isDebit ? '+' : '-';

    return Card(
      margin: EdgeInsets.zero,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(10),
      ),
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
        child: Row(
          children: [
            // Tur belgisi
            Container(
              width: 36,
              height: 36,
              decoration: BoxDecoration(
                color: color.withValues(alpha: 0.1),
                borderRadius: BorderRadius.circular(8),
              ),
              child: Icon(icon, color: color, size: 18),
            ),
            const SizedBox(width: 12),
            // Ma'lumotlar
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    children: [
                      _TypeBadge(type: entry.type),
                      if (entry.refType != null) ...[
                        const SizedBox(width: 6),
                        Text(
                          entry.refType!,
                          style: const TextStyle(
                              fontSize: 11, color: Colors.grey),
                        ),
                      ],
                    ],
                  ),
                  const SizedBox(height: 2),
                  Text(
                    _fmtDate(entry.entryDate),
                    style: const TextStyle(fontSize: 11, color: Colors.grey),
                  ),
                ],
              ),
            ),
            // Miqdor
            Column(
              crossAxisAlignment: CrossAxisAlignment.end,
              children: [
                Text(
                  '$sign${_fmtAmount(entry.amountValue)} ${entry.currency}',
                  style: TextStyle(
                    color: color,
                    fontWeight: FontWeight.bold,
                    fontSize: 15,
                  ),
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }

  String _fmtAmount(double amount) {
    final formatted = amount.toStringAsFixed(2);
    final parts = formatted.split('.');
    final intPart = parts[0];
    final decPart = parts[1];
    final buffer = StringBuffer();
    for (int i = 0; i < intPart.length; i++) {
      if (i > 0 && (intPart.length - i) % 3 == 0) buffer.write(' ');
      buffer.write(intPart[i]);
    }
    return '$buffer.$decPart';
  }

  String _fmtDate(DateTime dt) =>
      '${dt.day.toString().padLeft(2, '0')}.${dt.month.toString().padLeft(2, '0')}.${dt.year} '
      '${dt.hour.toString().padLeft(2, '0')}:${dt.minute.toString().padLeft(2, '0')}';
}

class _TypeBadge extends StatelessWidget {
  const _TypeBadge({required this.type});
  final LedgerEntryType type;

  @override
  Widget build(BuildContext context) {
    final isDebit = type == LedgerEntryType.debit;
    final color = isDebit ? Colors.red : Colors.green;
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 7, vertical: 2),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.1),
        borderRadius: BorderRadius.circular(6),
        border: Border.all(color: color.withValues(alpha: 0.4)),
      ),
      child: Text(
        type.label,
        style: TextStyle(
          color: color,
          fontSize: 11,
          fontWeight: FontWeight.w600,
        ),
      ),
    );
  }
}
