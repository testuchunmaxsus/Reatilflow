import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'finance_models.dart';
import 'finance_providers.dart';
import 'ledger_screen.dart';

/// Buxgalter moliya ekrani — do'kon balansi + ledger-ga o'tish.
///
/// Ekranda:
///   - Do'kon ID maydoni (buxgalter barcha do'konlarga kirish huquqiga ega).
///   - Tanlangan do'kon moliyaviy balansi.
///   - Ledger ro'yxatiga o'tish tugmasi.
class FinanceScreen extends ConsumerStatefulWidget {
  const FinanceScreen({super.key});

  @override
  ConsumerState<FinanceScreen> createState() => _FinanceScreenState();
}

class _FinanceScreenState extends ConsumerState<FinanceScreen> {
  final _storeIdController = TextEditingController();
  String? _activeStoreId;

  @override
  void dispose() {
    _storeIdController.dispose();
    super.dispose();
  }

  void _search() {
    final id = _storeIdController.text.trim();
    if (id.isEmpty) return;
    setState(() => _activeStoreId = id);
  }

  @override
  Widget build(BuildContext context) {
    return SingleChildScrollView(
      padding: const EdgeInsets.all(16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            'Moliya',
            style: Theme.of(context)
                .textTheme
                .headlineSmall
                ?.copyWith(fontWeight: FontWeight.bold),
          ),
          const SizedBox(height: 4),
          Text(
            _formattedDate(),
            style: Theme.of(context)
                .textTheme
                .bodyMedium
                ?.copyWith(color: Colors.grey),
          ),

          const SizedBox(height: 24),

          // Do'kon qidirish
          _StoreSearchField(
            controller: _storeIdController,
            onSearch: _search,
          ),

          const SizedBox(height: 20),

          // Balans kartasi
          if (_activeStoreId != null) ...[
            _BalanceCard(storeId: _activeStoreId!),
            const SizedBox(height: 16),
          ] else
            const _BalancePlaceholder(),

          const SizedBox(height: 8),

          // Ledger ro'yxatiga o'tish
          _LedgerNavigationCard(storeId: _activeStoreId),
        ],
      ),
    );
  }

  String _formattedDate() {
    final now = DateTime.now();
    const months = [
      'yanvar',
      'fevral',
      'mart',
      'aprel',
      'may',
      'iyun',
      'iyul',
      'avgust',
      'sentabr',
      'oktabr',
      'noyabr',
      'dekabr',
    ];
    return '${now.day} ${months[now.month - 1]} ${now.year}';
  }
}

// ---------------------------------------------------------------------------

class _StoreSearchField extends StatelessWidget {
  const _StoreSearchField({
    required this.controller,
    required this.onSearch,
  });

  final TextEditingController controller;
  final VoidCallback onSearch;

  @override
  Widget build(BuildContext context) {
    return Row(
      children: [
        Expanded(
          child: TextField(
            controller: controller,
            decoration: InputDecoration(
              labelText: "Do'kon UUID",
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
        FilledButton.icon(
          onPressed: onSearch,
          icon: const Icon(Icons.search, size: 18),
          label: const Text('Izla'),
          style: FilledButton.styleFrom(
            padding:
                const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
          ),
        ),
      ],
    );
  }
}

// ---------------------------------------------------------------------------

class _BalancePlaceholder extends StatelessWidget {
  const _BalancePlaceholder();

  @override
  Widget build(BuildContext context) {
    return Card(
      color: Colors.grey.withValues(alpha: 0.06),
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(12),
        side: BorderSide(color: Colors.grey.withValues(alpha: 0.2)),
      ),
      child: const Padding(
        padding: EdgeInsets.all(20),
        child: Center(
          child: Text(
            "Do'kon UUID ni kiriting va balansni ko'ring",
            textAlign: TextAlign.center,
            style: TextStyle(color: Colors.grey),
          ),
        ),
      ),
    );
  }
}

// ---------------------------------------------------------------------------

class _BalanceCard extends ConsumerWidget {
  const _BalanceCard({required this.storeId});
  final String storeId;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final state = ref.watch(financeBalanceProvider(storeId));

    return switch (state) {
      FinanceBalanceLoading() => const Card(
          child: Padding(
            padding: EdgeInsets.all(24),
            child: Center(child: CircularProgressIndicator()),
          ),
        ),
      FinanceBalanceError(:final message) => Card(
          color: Colors.red.withValues(alpha: 0.07),
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(12),
            side:
                BorderSide(color: Colors.red.withValues(alpha: 0.3)),
          ),
          child: Padding(
            padding: const EdgeInsets.all(16),
            child: Row(
              children: [
                const Icon(Icons.error_outline, color: Colors.red),
                const SizedBox(width: 12),
                Expanded(
                  child: Text(
                    'Xatolik: $message',
                    style: const TextStyle(color: Colors.red, fontSize: 13),
                  ),
                ),
                TextButton(
                  onPressed: () => ref
                      .read(financeBalanceProvider(storeId).notifier)
                      .reload(),
                  child: const Text('Qayta'),
                ),
              ],
            ),
          ),
        ),
      FinanceBalanceLoaded(:final balance) => _BalanceLoadedCard(
          balance: balance,
          onRefresh: () => ref
              .read(financeBalanceProvider(storeId).notifier)
              .reload(),
        ),
    };
  }
}

class _BalanceLoadedCard extends StatelessWidget {
  const _BalanceLoadedCard({
    required this.balance,
    required this.onRefresh,
  });

  final FinanceBalance balance;
  final VoidCallback onRefresh;

  @override
  Widget build(BuildContext context) {
    final color = balance.isDebt ? Colors.red : Colors.green;
    final statusLabel = balance.isDebt ? 'Qarzdorlik' : 'Kredit qoldiq';
    final statusIcon = balance.isDebt ? Icons.trending_up : Icons.trending_down;

    return Card(
      color: color.withValues(alpha: 0.07),
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(12),
        side: BorderSide(color: color.withValues(alpha: 0.3)),
      ),
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Icon(Icons.account_balance_wallet, color: color, size: 28),
                const SizedBox(width: 12),
                Expanded(
                  child: Text(
                    'Moliyaviy balans',
                    style: Theme.of(context)
                        .textTheme
                        .titleMedium
                        ?.copyWith(fontWeight: FontWeight.w600),
                  ),
                ),
                IconButton(
                  icon: const Icon(Icons.refresh, size: 20),
                  tooltip: 'Yangilash',
                  onPressed: onRefresh,
                  padding: EdgeInsets.zero,
                  constraints: const BoxConstraints(),
                ),
              ],
            ),
            const SizedBox(height: 16),
            Row(
              crossAxisAlignment: CrossAxisAlignment.end,
              children: [
                Icon(statusIcon, color: color, size: 18),
                const SizedBox(width: 6),
                Text(
                  statusLabel,
                  style: TextStyle(color: color, fontSize: 13),
                ),
              ],
            ),
            const SizedBox(height: 6),
            Text(
              '${_fmt(balance.balanceAmount)} ${balance.currency}',
              style: Theme.of(context).textTheme.headlineMedium?.copyWith(
                    color: color,
                    fontWeight: FontWeight.bold,
                  ),
            ),
            const SizedBox(height: 12),
            Text(
              "Do'kon: ${balance.storeId}",
              style: const TextStyle(fontSize: 11, color: Colors.grey),
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
            ),
            Text(
              'Yangilangan: ${_fmtDate(balance.lastRecalcAt)}',
              style: const TextStyle(fontSize: 11, color: Colors.grey),
            ),
          ],
        ),
      ),
    );
  }

  String _fmt(double amount) {
    // Minglik ajratuvchi bilan (masalan: 500 000.00)
    final abs = amount.abs();
    final formatted = abs.toStringAsFixed(2);
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

// ---------------------------------------------------------------------------

class _LedgerNavigationCard extends StatelessWidget {
  const _LedgerNavigationCard({this.storeId});
  final String? storeId;

  @override
  Widget build(BuildContext context) {
    return Card(
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
      child: InkWell(
        borderRadius: BorderRadius.circular(12),
        onTap: () {
          Navigator.of(context).push(
            MaterialPageRoute<void>(
              builder: (_) => LedgerScreen(initialStoreId: storeId),
            ),
          );
        },
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
          child: Row(
            children: [
              const Icon(
                Icons.receipt_long_outlined,
                color: Colors.indigo,
                size: 28,
              ),
              const SizedBox(width: 14),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      'Buxgalteriya yozuvlari',
                      style: Theme.of(context)
                          .textTheme
                          .titleSmall
                          ?.copyWith(fontWeight: FontWeight.w600),
                    ),
                    const Text(
                      'Debet va kredit yozuvlarini ko\'rish',
                      style: TextStyle(fontSize: 12, color: Colors.grey),
                    ),
                  ],
                ),
              ),
              const Icon(Icons.chevron_right, color: Colors.grey),
            ],
          ),
        ),
      ),
    );
  }
}
