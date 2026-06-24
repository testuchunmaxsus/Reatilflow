import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/theme/app_spacing.dart';
import '../../core/theme/app_theme.dart';
import '../../core/widgets/widgets.dart';
import '../../data/local/database.dart';
import '../../data/remote/models/auth_models.dart';
import '../auth/auth_providers.dart';
import '../auth/auth_repository.dart';
import '../enterprise/enterprise_providers.dart';
import '../stores/stores_providers.dart';

/// Agent kabineti ekrani — profil + biriktirilgan do'konlar.
///
/// Faqat `agent` roli ko'rishi mumkin.
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
            icon: const Icon(Icons.logout_outlined),
            tooltip: 'Chiqish',
            onPressed: () async {
              await ref.read(authNotifierProvider.notifier).logout();
            },
          ),
        ],
      ),
      body: RefreshIndicator(
        onRefresh: () async {
          await ref.read(enterpriseNotifierProvider.notifier).refresh();
        },
        child: SingleChildScrollView(
          physics: const AlwaysScrollableScrollPhysics(),
          padding: const EdgeInsets.all(AppSpacing.lg),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              _ProfileCard(user: user),

              const SizedBox(height: AppSpacing.lg),

              _ModulesCard(),

              const SizedBox(height: AppSpacing.lg),

              _AttachedStoresSection(agentId: user.id),

              const SizedBox(height: AppSpacing.xl),
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
    final cs = Theme.of(context).colorScheme;
    final tt = Theme.of(context).textTheme;
    final appColors = AppTheme.colorsOf(context);

    return AppCard(
      padding: const EdgeInsets.all(AppSpacing.lg),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // Avatar
          Container(
            width: 64,
            height: 64,
            decoration: BoxDecoration(
              gradient: LinearGradient(
                colors: [cs.primary, cs.primary.withValues(alpha: 0.8)],
                begin: Alignment.topLeft,
                end: Alignment.bottomRight,
              ),
              shape: BoxShape.circle,
            ),
            child: Center(
              child: Text(
                _initials(user.fullName),
                style: tt.titleMedium?.copyWith(
                  color: cs.onPrimary,
                  fontWeight: FontWeight.w700,
                ),
              ),
            ),
          ),
          const SizedBox(width: AppSpacing.lg),

          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  user.fullName,
                  style: tt.titleLarge?.copyWith(fontWeight: FontWeight.w700),
                ),
                const SizedBox(height: AppSpacing.xs),
                _InfoLine(icon: Icons.phone_outlined, value: user.phone),
                _InfoLine(
                    icon: Icons.badge_outlined,
                    value: _roleLabel(user.role)),
                if (user.branchId != null)
                  _InfoLine(
                    icon: Icons.business_outlined,
                    value: 'Filial: ${user.branchId!.substring(0, 8)}...',
                  ),
                const SizedBox(height: AppSpacing.sm),
                Wrap(
                  spacing: AppSpacing.xs,
                  runSpacing: AppSpacing.xs,
                  children: [
                    StatusBadge(
                      status: user.isActive ? 'Faol' : 'Nofaol',
                      variant: user.isActive
                          ? StatusVariant.success
                          : StatusVariant.danger,
                    ),
                    if (user.biometricEnrolled)
                      StatusBadge(
                        status: 'Biometrik',
                        variant: StatusVariant.info,
                        icon: Icons.fingerprint,
                      ),
                  ],
                ),
              ],
            ),
          ),
        ],
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

class _InfoLine extends StatelessWidget {
  const _InfoLine({required this.icon, required this.value});
  final IconData icon;
  final String value;

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    final tt = Theme.of(context).textTheme;
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 2),
      child: Row(
        children: [
          Icon(icon, size: AppSpacing.iconXs, color: cs.onSurfaceVariant),
          const SizedBox(width: AppSpacing.xs),
          Expanded(
            child: Text(
              value,
              style: tt.bodySmall?.copyWith(color: cs.onSurfaceVariant),
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
    final cs = Theme.of(context).colorScheme;

    return AppCard(
      padding: const EdgeInsets.all(AppSpacing.lg),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const SectionHeader(title: 'Faol modullar'),
          const SizedBox(height: AppSpacing.md),
          if (modules.isEmpty)
            Text(
              'Modul faollashtirilinmagan',
              style: Theme.of(context)
                  .textTheme
                  .bodyMedium
                  ?.copyWith(color: cs.onSurfaceVariant),
            )
          else
            Wrap(
              spacing: AppSpacing.sm,
              runSpacing: AppSpacing.sm,
              children: modules.map((m) => _ModuleChip(module: m)).toList(),
            ),
        ],
      ),
    );
  }
}

class _ModuleChip extends StatelessWidget {
  const _ModuleChip({required this.module});
  final String module;

  @override
  Widget build(BuildContext context) {
    final (icon, variant) = _moduleInfo(module);
    return StatusBadge(
      status: _moduleLabel(module),
      variant: variant,
      icon: icon,
      size: StatusBadgeSize.medium,
    );
  }

  (IconData, StatusVariant) _moduleInfo(String module) => switch (module) {
        'catalog' => (Icons.inventory_2_outlined, StatusVariant.warning),
        'orders' => (Icons.receipt_long_outlined, StatusVariant.info),
        'attendance' => (Icons.fingerprint, StatusVariant.neutral),
        'delivery' => (Icons.local_shipping_outlined, StatusVariant.success),
        'pos' => (Icons.point_of_sale_outlined, StatusVariant.info),
        'marketplace' => (Icons.storefront_outlined, StatusVariant.neutral),
        'finance' => (Icons.account_balance_wallet_outlined, StatusVariant.success),
        _ => (Icons.extension_outlined, StatusVariant.neutral),
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
        SectionHeader(
          title: "Biriktirilgan do'konlar",
          actionLabel: 'Hammasi',
          onAction: () => context.push('/home/stores'),
        ),
        const SizedBox(height: AppSpacing.md),
        storesAsync.when(
          loading: () => const Center(child: CircularProgressIndicator()),
          error: (e, _) => EmptyState(
            icon: Icons.error_outline,
            title: 'Xatolik',
            message: e.toString(),
            compact: true,
          ),
          data: (stores) {
            if (stores.isEmpty) {
              return const EmptyState(
                icon: Icons.store_outlined,
                title: "Biriktirilgan do'konlar topilmadi",
                compact: true,
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
    final cs = Theme.of(context).colorScheme;
    final tt = Theme.of(context).textTheme;

    return AppCard(
      margin: const EdgeInsets.only(bottom: AppSpacing.sm),
      padding: const EdgeInsets.symmetric(
          horizontal: AppSpacing.lg, vertical: AppSpacing.md),
      onTap: () => context.push('/home/stores/${store.id}'),
      child: Row(
        children: [
          Container(
            width: 40,
            height: 40,
            decoration: BoxDecoration(
              color: cs.primaryContainer,
              borderRadius: BorderRadius.circular(AppSpacing.radiusSm),
            ),
            child: Icon(Icons.store_outlined,
                color: cs.primary, size: AppSpacing.iconSm),
          ),
          const SizedBox(width: AppSpacing.md),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  store.name,
                  style: tt.titleSmall?.copyWith(fontWeight: FontWeight.w600),
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                ),
                if (store.address != null)
                  Text(
                    store.address!,
                    style: tt.bodySmall?.copyWith(color: cs.onSurfaceVariant),
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                  ),
              ],
            ),
          ),
          Icon(Icons.chevron_right,
              size: AppSpacing.iconSm, color: cs.onSurfaceVariant),
        ],
      ),
    );
  }
}
