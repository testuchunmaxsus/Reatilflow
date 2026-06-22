import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../data/sync/sync_notifier.dart';
import '../attendance/attendance_providers.dart';
import '../auth/auth_providers.dart';
import '../auth/auth_repository.dart';
import '../enterprise/enterprise_providers.dart';
import '../home/sync_providers.dart';
import '../orders/orders_providers.dart';

/// Agent uchun bosh ekran — dashboard.
///
/// Ko'rsatiladi:
/// - Bugungi davomat holati
/// - Tezkor harakatlar (buyurtma, do'konlar, katalog, davomat)
/// - Sync holati
class AgentDashboard extends ConsumerWidget {
  const AgentDashboard({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final authState = ref.watch(authNotifierProvider);
    final user = switch (authState) {
      AuthStateAuthenticated(:final user) => user,
      _ => null,
    };

    final syncState = ref.watch(syncNotifierProvider);
    final attendanceState = ref.watch(attendanceNotifierProvider);

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

          // Davomat kartasi
          _AttendanceCard(attendanceState: attendanceState),

          const SizedBox(height: 16),

          // Sync holat
          _SyncCard(syncState: syncState, ref: ref),

          const SizedBox(height: 20),

          Text('Tezkor harakatlar',
              style: Theme.of(context).textTheme.titleMedium?.copyWith(
                    fontWeight: FontWeight.w600,
                  )),

          const SizedBox(height: 12),

          // Tezkor harakatlar grid (modul-gating)
          _AgentQuickActions(),

          const SizedBox(height: 20),

          // Oxirgi buyurtmalar
          Text('So\'nggi buyurtmalar',
              style: Theme.of(context).textTheme.titleMedium?.copyWith(
                    fontWeight: FontWeight.w600,
                  )),

          const SizedBox(height: 8),

          _RecentOrders(),
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

class _AttendanceCard extends StatelessWidget {
  const _AttendanceCard({required this.attendanceState});
  final AttendanceState attendanceState;

  @override
  Widget build(BuildContext context) {
    final (icon, color, title, subtitle) = switch (attendanceState) {
      AttendanceCheckedIn(:final record) => (
          Icons.work,
          Colors.green,
          'Ish jarayonda',
          'Kirish: ${_fmt(record.checkInAt)}',
        ),
      AttendanceCheckedOut(:final record) => (
          Icons.work_off,
          Colors.grey,
          'Ish tugadi',
          'Chiqish: ${_fmt(record.checkOutAt!)}',
        ),
      AttendanceIdle() => (
          Icons.fingerprint,
          Colors.blue,
          'Davomat qayd etilmagan',
          'Boshlash uchun bosing',
        ),
      _ => (Icons.work_outline, Colors.orange, 'Davomat', ''),
    };

    return GestureDetector(
      onTap: () => Navigator.of(context).pushNamed('/home/attendance'),
      child: Card(
        color: color.withValues(alpha:0.08),
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(12),
          side: BorderSide(color: color.withValues(alpha:0.3)),
        ),
        child: Padding(
          padding: const EdgeInsets.all(16),
          child: Row(
            children: [
              Icon(icon, color: color, size: 36),
              const SizedBox(width: 16),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(title,
                        style: TextStyle(
                            color: color, fontWeight: FontWeight.bold)),
                    if (subtitle.isNotEmpty)
                      Text(subtitle,
                          style: const TextStyle(
                              fontSize: 12, color: Colors.grey)),
                  ],
                ),
              ),
              Icon(Icons.chevron_right, color: color),
            ],
          ),
        ),
      ),
    );
  }

  String _fmt(DateTime dt) =>
      '${dt.hour.toString().padLeft(2, '0')}:${dt.minute.toString().padLeft(2, '0')}';
}

class _SyncCard extends StatelessWidget {
  const _SyncCard({required this.syncState, required this.ref});
  final SyncState syncState;
  final WidgetRef ref;

  @override
  Widget build(BuildContext context) {
    final (icon, color, label) = switch (syncState) {
      SyncState.syncing => (Icons.sync, Colors.blue, 'Sync qilinmoqda...'),
      SyncState.success => (Icons.cloud_done, Colors.green, 'Sync muvaffaqiyatli'),
      SyncState.error => (Icons.sync_problem, Colors.red, 'Sync xatosi'),
      SyncState.offline => (Icons.cloud_off, Colors.orange, 'Offline rejim'),
      SyncState.idle => (Icons.cloud_queue, Colors.grey, 'Sync tayyorligida'),
    };

    return Card(
      child: ListTile(
        leading: Icon(icon, color: color),
        title: Text(label, style: TextStyle(color: color, fontSize: 14)),
        trailing: TextButton(
          onPressed: () => ref.read(syncNotifierProvider.notifier).triggerSync(),
          child: const Text('Sync'),
        ),
        dense: true,
      ),
    );
  }
}

/// Tezkor harakatlar grid — enabled_modules ga qarab ko'rsatiladi.
class _AgentQuickActions extends ConsumerWidget {
  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final hasCatalog = ref.watch(moduleEnabledProvider('catalog'));
    final hasOrders = ref.watch(moduleEnabledProvider('orders'));
    final hasAttendance = ref.watch(moduleEnabledProvider('attendance'));

    final actions = <Widget>[
      if (hasOrders)
        _QuickAction(
          icon: Icons.add_shopping_cart,
          label: 'Buyurtma',
          color: Colors.blue,
          onTap: () => context.push('/home/orders/create'),
        ),
      _QuickAction(
        icon: Icons.store_outlined,
        label: "Do'konlar",
        color: Colors.green,
        onTap: () => context.push('/home/stores'),
      ),
      if (hasCatalog)
        _QuickAction(
          icon: Icons.inventory_2_outlined,
          label: 'Katalog',
          color: Colors.orange,
          onTap: () => context.push('/home/catalog'),
        ),
      if (hasAttendance)
        _QuickAction(
          icon: Icons.fingerprint,
          label: 'Davomat',
          color: Colors.purple,
          onTap: () => context.push('/home/attendance'),
        ),
    ];

    if (actions.isEmpty) {
      return const SizedBox.shrink();
    }

    return GridView.count(
      crossAxisCount: 2,
      shrinkWrap: true,
      physics: const NeverScrollableScrollPhysics(),
      mainAxisSpacing: 12,
      crossAxisSpacing: 12,
      childAspectRatio: 1.4,
      children: actions,
    );
  }
}

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
                    color: color, fontWeight: FontWeight.w600, fontSize: 13),
                textAlign: TextAlign.center,
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _RecentOrders extends ConsumerWidget {
  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final ordersAsync = ref.watch(ordersStreamProvider);

    return ordersAsync.when(
      data: (orders) {
        final recent = orders.take(3).toList();
        if (recent.isEmpty) {
          return const Card(
            child: Padding(
              padding: EdgeInsets.all(16),
              child: Center(
                child: Text('Hali buyurtma yo\'q',
                    style: TextStyle(color: Colors.grey)),
              ),
            ),
          );
        }
        return Column(
          children: recent
              .map(
                (o) => Card(
                  child: ListTile(
                    leading: Icon(
                      o.syncStatus == 'synced'
                          ? Icons.check_circle_outline
                          : Icons.pending_outlined,
                      color: o.syncStatus == 'synced'
                          ? Colors.green
                          : Colors.orange,
                    ),
                    title: Text('${o.id.substring(0, 8)}...'),
                    subtitle: Text(_fmtDate(o.createdAt)),
                    trailing: _badge(o.syncStatus),
                    onTap: () => context.push('/home/orders'),
                    dense: true,
                  ),
                ),
              )
              .toList(),
        );
      },
      loading: () => const Center(child: CircularProgressIndicator()),
      error: (e, _) => Text('Xatolik: $e'),
    );
  }

  Widget _badge(String status) {
    final color = status == 'synced' ? Colors.green : Colors.orange;
    final label = status == 'synced' ? 'Yuborildi' : 'Kutilmoqda';
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
      decoration: BoxDecoration(
        color: color.withValues(alpha:0.1),
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: color.withValues(alpha:0.4)),
      ),
      child: Text(label,
          style: TextStyle(
              color: color, fontSize: 10, fontWeight: FontWeight.w600)),
    );
  }

  String _fmtDate(DateTime dt) =>
      '${dt.day.toString().padLeft(2, '0')}.${dt.month.toString().padLeft(2, '0')} '
      '${dt.hour.toString().padLeft(2, '0')}:${dt.minute.toString().padLeft(2, '0')}';
}
