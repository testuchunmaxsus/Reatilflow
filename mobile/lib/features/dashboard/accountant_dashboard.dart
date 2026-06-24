import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../data/sync/sync_notifier.dart';
import '../auth/auth_providers.dart';
import '../auth/auth_repository.dart';
import '../home/sync_providers.dart';

/// Buxgalter uchun bosh ekran — dashboard.
///
/// Ko'rsatiladi:
///   - Salom (foydalanuvchi ismi)
///   - Tezkor harakatlar (moliya balans, ledger, davomat)
///   - Sync holati
class AccountantDashboard extends ConsumerWidget {
  const AccountantDashboard({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final authState = ref.watch(authNotifierProvider);
    final user = switch (authState) {
      AuthStateAuthenticated(:final user) => user,
      _ => null,
    };

    final syncState = ref.watch(syncNotifierProvider);

    return SingleChildScrollView(
      padding: const EdgeInsets.all(16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // Salom
          if (user != null) ...[
            Text(
              'Salom, ${user.fullName}',
              style: Theme.of(context).textTheme.headlineSmall?.copyWith(
                    fontWeight: FontWeight.bold,
                  ),
            ),
            const SizedBox(height: 4),
            Text(
              _formattedDate(),
              style: Theme.of(context)
                  .textTheme
                  .bodyMedium
                  ?.copyWith(color: Colors.grey),
            ),
          ],

          const SizedBox(height: 20),

          // Moliya qisqacha kartasi
          _FinanceSummaryCard(),

          const SizedBox(height: 12),

          // Sync holat
          _SyncCard(syncState: syncState, ref: ref),

          const SizedBox(height: 20),

          Text(
            'Tezkor harakatlar',
            style: Theme.of(context).textTheme.titleMedium?.copyWith(
                  fontWeight: FontWeight.w600,
                ),
          ),

          const SizedBox(height: 12),

          // Tezkor harakatlar grid
          GridView.count(
            crossAxisCount: 2,
            shrinkWrap: true,
            physics: const NeverScrollableScrollPhysics(),
            mainAxisSpacing: 12,
            crossAxisSpacing: 12,
            childAspectRatio: 1.4,
            children: [
              _QuickAction(
                icon: Icons.account_balance_wallet_outlined,
                label: 'Moliya',
                color: Colors.indigo,
                onTap: () => context.go('/home/accountant/finance'),
              ),
              _QuickAction(
                icon: Icons.receipt_long_outlined,
                label: 'Ledger',
                color: Colors.teal,
                onTap: () => context.go('/home/accountant/finance'),
              ),
              _QuickAction(
                icon: Icons.fingerprint,
                label: 'Davomat',
                color: Colors.purple,
                onTap: () => context.go('/home/attendance'),
              ),
              _QuickAction(
                icon: Icons.bar_chart_outlined,
                label: 'Hisobotlar',
                color: Colors.orange,
                onTap: () => context.go('/home/accountant/finance'),
              ),
            ],
          ),
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

/// Moliya qisqacha kartasi — balans va ledger-ga yo'naltirish.
class _FinanceSummaryCard extends StatelessWidget {
  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: () => context.go('/home/accountant/finance'),
      child: Card(
        color: Colors.indigo.withValues(alpha: 0.08),
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(12),
          side: BorderSide(color: Colors.indigo.withValues(alpha: 0.3)),
        ),
        child: Padding(
          padding: const EdgeInsets.all(16),
          child: Row(
            children: [
              Icon(Icons.account_balance,
                  color: Colors.indigo.shade600, size: 36),
              const SizedBox(width: 16),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      'Moliya moduli',
                      style: TextStyle(
                        color: Colors.indigo.shade700,
                        fontWeight: FontWeight.bold,
                        fontSize: 15,
                      ),
                    ),
                    const Text(
                      'Balans va buxgalteriya yozuvlari',
                      style: TextStyle(fontSize: 12, color: Colors.grey),
                    ),
                  ],
                ),
              ),
              Icon(Icons.chevron_right,
                  color: Colors.indigo.withValues(alpha: 0.6)),
            ],
          ),
        ),
      ),
    );
  }
}

// ---------------------------------------------------------------------------

class _SyncCard extends StatelessWidget {
  const _SyncCard({required this.syncState, required this.ref});
  final SyncState syncState;
  final WidgetRef ref;

  @override
  Widget build(BuildContext context) {
    final (icon, color, label) = switch (syncState) {
      SyncState.syncing => (Icons.sync, Colors.blue, 'Sync qilinmoqda...'),
      SyncState.success =>
        (Icons.cloud_done, Colors.green, 'Sync muvaffaqiyatli'),
      SyncState.error => (Icons.sync_problem, Colors.red, 'Sync xatosi'),
      SyncState.offline => (Icons.cloud_off, Colors.orange, 'Offline rejim'),
      SyncState.idle => (Icons.cloud_queue, Colors.grey, 'Sync tayyorligida'),
    };

    return Card(
      child: ListTile(
        leading: Icon(icon, color: color),
        title: Text(label, style: TextStyle(color: color, fontSize: 14)),
        trailing: TextButton(
          onPressed: () =>
              ref.read(syncNotifierProvider.notifier).triggerSync(),
          child: const Text('Sync'),
        ),
        dense: true,
      ),
    );
  }
}

// ---------------------------------------------------------------------------

class _QuickAction extends StatelessWidget {
  const _QuickAction({
    required this.icon,
    required this.label,
    required this.color,
    required this.onTap,
  });

  final IconData icon;
  final String label;
  final Color color;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return Card(
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
      child: InkWell(
        borderRadius: BorderRadius.circular(12),
        onTap: onTap,
        child: Padding(
          padding: const EdgeInsets.all(16),
          child: Column(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              Icon(icon, size: 32, color: color),
              const SizedBox(height: 8),
              Text(
                label,
                style: TextStyle(
                    color: color,
                    fontWeight: FontWeight.w600,
                    fontSize: 13),
                textAlign: TextAlign.center,
              ),
            ],
          ),
        ),
      ),
    );
  }
}
