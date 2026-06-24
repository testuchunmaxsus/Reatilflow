import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../data/local/database.dart';
import '../../data/remote/models/auth_models.dart';
import '../auth/auth_providers.dart';
import '../auth/auth_repository.dart';
import '../enterprise/enterprise_providers.dart';
import '../stores/stores_providers.dart';

/// Agent kabineti ekrani — profil + biriktirilgan do'konlar.
///
/// Faqat `agent` roli ko'rishi mumkin.
/// moduleEnabledProvider gating qo'llanilmaydi — kabinet asosiy funksiya.
class AgentCabinetScreen extends ConsumerWidget {
  const AgentCabinetScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final authState = ref.watch(authNotifierProvider);
    final user = switch (authState) {
      AuthStateAuthenticated(:final user) => user,
      _ => null,
    };

    if (user == null) {
      return const Scaffold(
        body: Center(child: CircularProgressIndicator()),
      );
    }

    return Scaffold(
      appBar: AppBar(
        title: const Text('Mening kabinetim'),
        actions: [
          IconButton(
            icon: const Icon(Icons.logout),
            tooltip: 'Chiqish',
            onPressed: () async {
              await ref.read(authNotifierProvider.notifier).logout();
            },
          ),
        ],
      ),
      body: RefreshIndicator(
        onRefresh: () async {
          // Enterprise ma'lumotlarini yangilash
          await ref.read(enterpriseNotifierProvider.notifier).refresh();
        },
        child: SingleChildScrollView(
          physics: const AlwaysScrollableScrollPhysics(),
          padding: const EdgeInsets.all(16),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              // Profil kartasi
              _ProfileCard(user: user),

              const SizedBox(height: 20),

              // Modul holati
              _ModulesCard(),

              const SizedBox(height: 20),

              // Biriktirilgan do'konlar
              _AttachedStoresSection(agentId: user.id),

              const SizedBox(height: 24),
            ],
          ),
        ),
      ),
    );
  }
}

// ---------------------------------------------------------------------------

class _ProfileCard extends StatelessWidget {
  const _ProfileCard({required this.user});
  final MeResponse user;

  @override
  Widget build(BuildContext context) {
    return Card(
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(14)),
      child: Padding(
        padding: const EdgeInsets.all(20),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            // Avatar
            Container(
              width: 64,
              height: 64,
              decoration: BoxDecoration(
                color: Colors.blue.shade100,
                shape: BoxShape.circle,
              ),
              child: Center(
                child: Text(
                  _initials(user.fullName),
                  style: TextStyle(
                    color: Colors.blue.shade700,
                    fontWeight: FontWeight.bold,
                    fontSize: 22,
                  ),
                ),
              ),
            ),
            const SizedBox(width: 16),

            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    user.fullName,
                    style: Theme.of(context)
                        .textTheme
                        .titleLarge
                        ?.copyWith(fontWeight: FontWeight.bold),
                  ),
                  const SizedBox(height: 4),
                  _InfoRow(
                    icon: Icons.phone_outlined,
                    value: user.phone,
                  ),
                  _InfoRow(
                    icon: Icons.badge_outlined,
                    value: _roleLabel(user.role),
                  ),
                  if (user.branchId != null)
                    _InfoRow(
                      icon: Icons.business_outlined,
                      value: 'Filial: ${user.branchId!.substring(0, 8)}...',
                    ),
                  const SizedBox(height: 4),
                  Row(
                    children: [
                      Container(
                        padding: const EdgeInsets.symmetric(
                            horizontal: 8, vertical: 2),
                        decoration: BoxDecoration(
                          color: user.isActive
                              ? Colors.green.withValues(alpha: 0.12)
                              : Colors.red.withValues(alpha: 0.12),
                          borderRadius: BorderRadius.circular(8),
                        ),
                        child: Text(
                          user.isActive ? 'Faol' : 'Nofaol',
                          style: TextStyle(
                            color: user.isActive ? Colors.green : Colors.red,
                            fontSize: 11,
                            fontWeight: FontWeight.w600,
                          ),
                        ),
                      ),
                      if (user.biometricEnrolled) ...[
                        const SizedBox(width: 8),
                        Container(
                          padding: const EdgeInsets.symmetric(
                              horizontal: 8, vertical: 2),
                          decoration: BoxDecoration(
                            color: Colors.purple.withValues(alpha: 0.1),
                            borderRadius: BorderRadius.circular(8),
                          ),
                          child: const Row(
                            mainAxisSize: MainAxisSize.min,
                            children: [
                              Icon(Icons.fingerprint,
                                  size: 12, color: Colors.purple),
                              SizedBox(width: 3),
                              Text(
                                'Biometrik',
                                style: TextStyle(
                                    color: Colors.purple,
                                    fontSize: 11,
                                    fontWeight: FontWeight.w600),
                              ),
                            ],
                          ),
                        ),
                      ],
                    ],
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }

  String _initials(String fullName) {
    final parts = fullName.trim().split(' ');
    if (parts.isEmpty) return '?';
    if (parts.length == 1) return parts.first[0].toUpperCase();
    return '${parts.first[0]}${parts[1][0]}'.toUpperCase();
  }

  String _roleLabel(String role) => switch (role) {
        'agent' => 'Agent',
        'courier' => 'Kuryer',
        'store' => "Do'kon",
        'accountant' => 'Buxgalter',
        'administrator' => 'Administrator',
        _ => role,
      };
}

class _InfoRow extends StatelessWidget {
  const _InfoRow({required this.icon, required this.value});
  final IconData icon;
  final String value;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 2),
      child: Row(
        children: [
          Icon(icon, size: 14, color: Colors.grey),
          const SizedBox(width: 6),
          Expanded(
            child: Text(
              value,
              style: const TextStyle(fontSize: 13, color: Colors.grey),
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
            ),
          ),
        ],
      ),
    );
  }
}

// ---------------------------------------------------------------------------

class _ModulesCard extends ConsumerWidget {
  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final modules = ref.watch(enabledModulesProvider);

    return Card(
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              'Faol modullar',
              style: Theme.of(context)
                  .textTheme
                  .titleSmall
                  ?.copyWith(fontWeight: FontWeight.bold),
            ),
            const SizedBox(height: 12),
            if (modules.isEmpty)
              const Text(
                'Modul faollashtirilinmagan',
                style: TextStyle(color: Colors.grey, fontSize: 13),
              )
            else
              Wrap(
                spacing: 8,
                runSpacing: 8,
                children: modules.map((m) => _ModuleChip(module: m)).toList(),
              ),
          ],
        ),
      ),
    );
  }
}

class _ModuleChip extends StatelessWidget {
  const _ModuleChip({required this.module});
  final String module;

  @override
  Widget build(BuildContext context) {
    final (icon, color) = _moduleInfo(module);
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 5),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.1),
        borderRadius: BorderRadius.circular(20),
        border: Border.all(color: color.withValues(alpha: 0.35)),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(icon, size: 13, color: color),
          const SizedBox(width: 5),
          Text(
            _moduleLabel(module),
            style: TextStyle(
                color: color, fontSize: 12, fontWeight: FontWeight.w500),
          ),
        ],
      ),
    );
  }

  (IconData, Color) _moduleInfo(String module) => switch (module) {
        'catalog' => (Icons.inventory_2_outlined, Colors.orange),
        'orders' => (Icons.receipt_long, Colors.blue),
        'attendance' => (Icons.fingerprint, Colors.purple),
        'delivery' => (Icons.local_shipping_outlined, Colors.teal),
        'pos' => (Icons.point_of_sale, Colors.indigo),
        'marketplace' => (Icons.storefront_outlined, Colors.pink),
        'finance' => (Icons.account_balance_wallet_outlined, Colors.green),
        _ => (Icons.extension_outlined, Colors.grey),
      };

  String _moduleLabel(String module) => switch (module) {
        'catalog' => 'Katalog',
        'orders' => 'Buyurtmalar',
        'attendance' => 'Davomat',
        'delivery' => 'Yetkazish',
        'pos' => 'POS',
        'marketplace' => 'Marketplace',
        'finance' => 'Moliya',
        _ => module,
      };
}

// ---------------------------------------------------------------------------

class _AttachedStoresSection extends ConsumerWidget {
  const _AttachedStoresSection({required this.agentId});
  final String agentId;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final storesAsync = ref.watch(filteredStoresProvider(agentId));

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          children: [
            Text(
              'Biriktirilgan do\'konlar',
              style: Theme.of(context)
                  .textTheme
                  .titleSmall
                  ?.copyWith(fontWeight: FontWeight.bold),
            ),
            const Spacer(),
            TextButton.icon(
              onPressed: () => context.push('/home/stores'),
              icon: const Icon(Icons.arrow_forward, size: 16),
              label: const Text('Hammasi', style: TextStyle(fontSize: 12)),
            ),
          ],
        ),
        const SizedBox(height: 8),
        storesAsync.when(
          loading: () => const Center(child: CircularProgressIndicator()),
          error: (e, _) => Text(
            'Xatolik: $e',
            style: const TextStyle(color: Colors.red, fontSize: 13),
          ),
          data: (stores) {
            if (stores.isEmpty) {
              return const Card(
                child: Padding(
                  padding: EdgeInsets.all(16),
                  child: Center(
                    child: Text(
                      'Biriktirilgan do\'konlar topilmadi',
                      style: TextStyle(color: Colors.grey),
                    ),
                  ),
                ),
              );
            }
            return Column(
              children: stores
                  .take(5)
                  .map((s) => _StoreCard(store: s))
                  .toList(),
            );
          },
        ),
      ],
    );
  }
}

class _StoreCard extends StatelessWidget {
  const _StoreCard({required this.store});
  final Store store;

  @override
  Widget build(BuildContext context) {
    return Card(
      margin: const EdgeInsets.only(bottom: 6),
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(10)),
      child: ListTile(
        leading: CircleAvatar(
          backgroundColor: Colors.blue.shade50,
          child: Icon(Icons.store, color: Colors.blue.shade400, size: 20),
        ),
        title: Text(
          store.name,
          style: const TextStyle(fontWeight: FontWeight.w600, fontSize: 14),
        ),
        subtitle: store.address != null
            ? Text(
                store.address!,
                style: const TextStyle(fontSize: 12),
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
              )
            : null,
        trailing: const Icon(Icons.chevron_right, size: 18, color: Colors.grey),
        dense: true,
        onTap: () => context.push('/home/stores/${store.id}'),
      ),
    );
  }
}
