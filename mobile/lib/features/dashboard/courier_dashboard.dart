import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../data/sync/sync_notifier.dart';
import '../attendance/attendance_providers.dart';
import '../auth/auth_providers.dart';
import '../auth/auth_repository.dart';
import '../delivery/delivery_providers.dart';
import '../enterprise/enterprise_providers.dart';
import '../home/sync_providers.dart';

/// Kuryer uchun bosh ekran — dashboard.
///
/// Ko'rsatiladi:
/// - Salom (foydalanuvchi ismi)
/// - Bugungi davomat holati
/// - Tayinlangan yetkazishlar soni
/// - Sync holati
/// - Tezkor harakatlar (yetkazishlar, davomat)
class CourierDashboard extends ConsumerWidget {
  const CourierDashboard({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final authState = ref.watch(authNotifierProvider);
    final user = switch (authState) {
      AuthStateAuthenticated(:final user) => user,
      _ => null,
    };

    final syncState = ref.watch(syncNotifierProvider);
    final attendanceState = ref.watch(attendanceNotifierProvider);
    final activeCountAsync = ref.watch(activeDeliveriesCountProvider);
    final hasDelivery = ref.watch(moduleEnabledProvider('delivery'));
    final hasAttendance = ref.watch(moduleEnabledProvider('attendance'));

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

          // Yetkazishlar holat kartasi (delivery moduli yoqilganda)
          if (hasDelivery) ...[
            activeCountAsync.when(
              data: (count) => _DeliveriesCard(activeCount: count),
              loading: () => const _DeliveriesCard(activeCount: 0),
              error: (_, __) => const SizedBox.shrink(),
            ),
            const SizedBox(height: 12),
          ],

          // Davomat kartasi (attendance moduli yoqilganda)
          if (hasAttendance) ...[
            _AttendanceCard(attendanceState: attendanceState),
            const SizedBox(height: 12),
          ],

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

          // Tezkor harakatlar grid (modul-gating)
          GridView.count(
            crossAxisCount: 2,
            shrinkWrap: true,
            physics: const NeverScrollableScrollPhysics(),
            mainAxisSpacing: 12,
            crossAxisSpacing: 12,
            childAspectRatio: 1.4,
            children: [
              if (hasDelivery)
                _QuickAction(
                  icon: Icons.local_shipping,
                  label: 'Yetkazishlar',
                  color: Colors.blue,
                  onTap: () => context.go('/home/deliveries'),
                ),
              if (hasAttendance)
                _QuickAction(
                  icon: Icons.fingerprint,
                  label: 'Davomat',
                  color: Colors.purple,
                  onTap: () => context.go('/home/attendance'),
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

class _DeliveriesCard extends StatelessWidget {
  const _DeliveriesCard({required this.activeCount});

  final int activeCount;

  @override
  Widget build(BuildContext context) {
    final color = activeCount > 0 ? Colors.blue : Colors.grey;

    return GestureDetector(
      onTap: () => context.push('/home/deliveries'),
      child: Card(
        color: color.withValues(alpha: 0.08),
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(12),
          side: BorderSide(color: color.withValues(alpha: 0.3)),
        ),
        child: Padding(
          padding: const EdgeInsets.all(16),
          child: Row(
            children: [
              Icon(Icons.local_shipping, color: color, size: 36),
              const SizedBox(width: 16),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      activeCount > 0
                          ? '$activeCount ta faol yetkazish'
                          : 'Yetkazish yo\'q',
                      style: TextStyle(
                          color: color, fontWeight: FontWeight.bold),
                    ),
                    const Text(
                      'Ko\'rish uchun bosing',
                      style: TextStyle(
                          fontSize: 12, color: Colors.grey),
                    ),
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
      onTap: () => context.push('/home/attendance'),
      child: Card(
        color: color.withValues(alpha: 0.08),
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(12),
          side: BorderSide(color: color.withValues(alpha: 0.3)),
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
                    Text(
                      title,
                      style: TextStyle(
                          color: color, fontWeight: FontWeight.bold),
                    ),
                    if (subtitle.isNotEmpty)
                      Text(
                        subtitle,
                        style: const TextStyle(
                            fontSize: 12, color: Colors.grey),
                      ),
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
