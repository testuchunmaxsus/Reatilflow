import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../auth/auth_providers.dart';
import '../auth/auth_repository.dart';
import 'finance_models.dart';
import 'finance_providers.dart';
import 'ledger_screen.dart';

/// Do'kon roli uchun moliya/balans ekrani.
///
/// Store foydalanuvchisi o'z do'konining balansini ko'radi.
/// storeId auth.user.branchId dan olinadi.
class StoreBalanceScreen extends ConsumerWidget {
  const StoreBalanceScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final authState = ref.watch(authNotifierProvider);
    final storeId = switch (authState) {
      AuthStateAuthenticated(:final user) => user.branchId,
      _ => null,
    };

    if (storeId == null) {
      return const _NoStoreIdBody();
    }

    return Scaffold(
      appBar: AppBar(
        title: const Text("Do'kon balansi"),
        actions: [
          IconButton(
            icon: const Icon(Icons.refresh),
            tooltip: 'Yangilash',
            onPressed: () =>
                ref.read(financeBalanceProvider(storeId).notifier).reload(),
          ),
        ],
      ),
      body: SingleChildScrollView(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            // Sana
            Text(
              _formattedDate(),
              style: Theme.of(context)
                  .textTheme
                  .bodyMedium
                  ?.copyWith(color: Colors.grey),
            ),

            const SizedBox(height: 20),

            // Balans kartasi
            _BalanceCard(storeId: storeId),

            const SizedBox(height: 16),

            // Ledger ga o'tish
            _LedgerCard(storeId: storeId),

            const SizedBox(height: 16),

            // Balans izohi
            _BalanceInfoCard(),
          ],
        ),
      ),
    );
  }

  String _formattedDate() {
    final now = DateTime.now();
    const months = [
      'yanvar', 'fevral', 'mart', 'aprel', 'may', 'iyun',
      'iyul', 'avgust', 'sentabr', 'oktabr', 'noyabr', 'dekabr',
    ];
    return '${now.day} ${months[now.month - 1]} ${now.year}';
  }
}

// ---------------------------------------------------------------------------

class _NoStoreIdBody extends StatelessWidget {
  const _NoStoreIdBody();

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text("Do'kon balansi")),
      body: Center(
        child: Padding(
          padding: const EdgeInsets.all(24),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Icon(Icons.store_mall_directory_outlined,
                  size: 64, color: Colors.grey.shade300),
              const SizedBox(height: 16),
              const Text(
                "Do'kon ID topilmadi",
                style: TextStyle(fontWeight: FontWeight.w600, fontSize: 16),
              ),
              const SizedBox(height: 8),
              const Text(
                'Akkauntga do\'kon biriktirilmagan. '
                'Administrator bilan bog\'laning.',
                textAlign: TextAlign.center,
                style: TextStyle(color: Colors.grey),
              ),
            ],
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
            padding: EdgeInsets.all(32),
            child: Center(child: CircularProgressIndicator()),
          ),
        ),
      FinanceBalanceError(:final message) => Card(
          color: Colors.red.withValues(alpha: 0.07),
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(12),
            side: BorderSide(color: Colors.red.withValues(alpha: 0.3)),
          ),
          child: Padding(
            padding: const EdgeInsets.all(16),
            child: Column(
              children: [
                const Icon(Icons.error_outline, color: Colors.red, size: 36),
                const SizedBox(height: 10),
                Text(
                  'Xatolik: $message',
                  style: const TextStyle(color: Colors.red, fontSize: 13),
                  textAlign: TextAlign.center,
                ),
                const SizedBox(height: 10),
                FilledButton.icon(
                  style:
                      FilledButton.styleFrom(backgroundColor: Colors.red),
                  onPressed: () => ref
                      .read(financeBalanceProvider(storeId).notifier)
                      .reload(),
                  icon: const Icon(Icons.refresh, size: 16),
                  label: const Text('Qayta urinish'),
                ),
              ],
            ),
          ),
        ),
      FinanceBalanceLoaded(:final balance) =>
        _BalanceLoadedCard(balance: balance),
    };
  }
}

class _BalanceLoadedCard extends StatelessWidget {
  const _BalanceLoadedCard({required this.balance});
  final FinanceBalance balance;

  @override
  Widget build(BuildContext context) {
    final color = balance.isDebt ? Colors.red : Colors.green;
    final statusLabel =
        balance.isDebt ? 'Qarzdorlik' : 'Kredit qoldiq';
    final statusIcon =
        balance.isDebt ? Icons.trending_up : Icons.savings_outlined;

    return Card(
      color: color.withValues(alpha: 0.07),
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(14),
        side: BorderSide(color: color.withValues(alpha: 0.35)),
      ),
      child: Padding(
        padding: const EdgeInsets.all(20),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Container(
                  width: 48,
                  height: 48,
                  decoration: BoxDecoration(
                    color: color.withValues(alpha: 0.14),
                    borderRadius: BorderRadius.circular(12),
                  ),
                  child: Icon(Icons.account_balance_wallet,
                      color: color, size: 26),
                ),
                const SizedBox(width: 14),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        'Moliyaviy balans',
                        style: Theme.of(context)
                            .textTheme
                            .titleMedium
                            ?.copyWith(fontWeight: FontWeight.w700),
                      ),
                      Row(
                        children: [
                          Icon(statusIcon, color: color, size: 14),
                          const SizedBox(width: 4),
                          Text(
                            statusLabel,
                            style: TextStyle(
                                color: color,
                                fontSize: 12,
                                fontWeight: FontWeight.w500),
                          ),
                        ],
                      ),
                    ],
                  ),
                ),
              ],
            ),
            const SizedBox(height: 20),
            Text(
              '${_fmt(balance.balanceAmount)} ${balance.currency}',
              style: Theme.of(context).textTheme.headlineMedium?.copyWith(
                    color: color,
                    fontWeight: FontWeight.bold,
                    letterSpacing: -0.5,
                  ),
            ),
            const SizedBox(height: 12),
            Divider(color: color.withValues(alpha: 0.2)),
            const SizedBox(height: 8),
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

class _LedgerCard extends StatelessWidget {
  const _LedgerCard({required this.storeId});
  final String storeId;

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
        child: const Padding(
          padding: EdgeInsets.symmetric(horizontal: 16, vertical: 14),
          child: Row(
            children: [
              Icon(Icons.receipt_long_outlined,
                  color: Colors.indigo, size: 28),
              SizedBox(width: 14),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      'Buxgalteriya yozuvlari',
                      style: TextStyle(fontWeight: FontWeight.w600),
                    ),
                    Text(
                      'Debet va kredit yozuvlarini ko\'rish',
                      style: TextStyle(fontSize: 12, color: Colors.grey),
                    ),
                  ],
                ),
              ),
              Icon(Icons.chevron_right, color: Colors.grey),
            ],
          ),
        ),
      ),
    );
  }
}

// ---------------------------------------------------------------------------

class _BalanceInfoCard extends StatelessWidget {
  @override
  Widget build(BuildContext context) {
    return Card(
      color: Colors.blue.withValues(alpha: 0.05),
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(10),
        side: BorderSide(color: Colors.blue.withValues(alpha: 0.2)),
      ),
      child: const Padding(
        padding: EdgeInsets.all(14),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Icon(Icons.info_outline, color: Colors.blue, size: 18),
            SizedBox(width: 10),
            Expanded(
              child: Text(
                'Balans server tomonida hisoblangan. '
                'Muammolar yuzaga kelganda administrator bilan bog\'laning.',
                style: TextStyle(fontSize: 12, color: Colors.blueGrey),
              ),
            ),
          ],
        ),
      ),
    );
  }
}
