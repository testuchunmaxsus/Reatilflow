import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../auth/auth_providers.dart';
import '../auth/auth_repository.dart';
import '../enterprise/enterprise_providers.dart';

/// Do'kon roli uchun bosh ekran — dashboard.
///
/// Tezkor harakatlar:
/// - POS Sotuv (pos moduli yoqilganda)
/// - Inventar (pos moduli yoqilganda)
/// - Kunlik hisobot (pos moduli yoqilganda)
class StoreDashboard extends ConsumerWidget {
  const StoreDashboard({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final authState = ref.watch(authNotifierProvider);
    final user = switch (authState) {
      AuthStateAuthenticated(:final user) => user,
      _ => null,
    };

    final hasPos = ref.watch(moduleEnabledProvider('pos'));

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

          // POS moduli yo'q bo'lsa — xabar
          if (!hasPos)
            const _ModuleDisabledCard(
              icon: Icons.point_of_sale,
              title: 'POS moduli faollashtirilmagan',
              subtitle:
                  'Administrator POS modulini yoqishi kerak. '
                  'Iltimos, administrator bilan bog\'laning.',
            )
          else ...[
            Text(
              'Tezkor harakatlar',
              style: Theme.of(context).textTheme.titleMedium?.copyWith(
                    fontWeight: FontWeight.w600,
                  ),
            ),

            const SizedBox(height: 12),

            GridView.count(
              crossAxisCount: 2,
              shrinkWrap: true,
              physics: const NeverScrollableScrollPhysics(),
              mainAxisSpacing: 12,
              crossAxisSpacing: 12,
              childAspectRatio: 1.4,
              children: [
                _QuickAction(
                  icon: Icons.point_of_sale,
                  label: 'Sotuv',
                  color: Colors.blue,
                  onTap: () => context.go('/home/pos/sale'),
                ),
                _QuickAction(
                  icon: Icons.inventory_2_outlined,
                  label: 'Inventar',
                  color: Colors.orange,
                  onTap: () => context.go('/home/pos/inventory'),
                ),
                _QuickAction(
                  icon: Icons.bar_chart,
                  label: 'Hisobot',
                  color: Colors.green,
                  onTap: () => context.go('/home/pos/summary'),
                ),
              ],
            ),
          ],
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

class _ModuleDisabledCard extends StatelessWidget {
  const _ModuleDisabledCard({
    required this.icon,
    required this.title,
    required this.subtitle,
  });
  final IconData icon;
  final String title;
  final String subtitle;

  @override
  Widget build(BuildContext context) {
    return Card(
      color: Colors.grey.shade50,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(12),
        side: BorderSide(color: Colors.grey.shade300),
      ),
      child: Padding(
        padding: const EdgeInsets.all(20),
        child: Column(
          children: [
            Icon(icon, size: 48, color: Colors.grey.shade400),
            const SizedBox(height: 12),
            Text(
              title,
              style: TextStyle(
                  fontWeight: FontWeight.w600,
                  color: Colors.grey.shade600,
                  fontSize: 15),
              textAlign: TextAlign.center,
            ),
            const SizedBox(height: 6),
            Text(
              subtitle,
              style: TextStyle(color: Colors.grey.shade500, fontSize: 13),
              textAlign: TextAlign.center,
            ),
          ],
        ),
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
