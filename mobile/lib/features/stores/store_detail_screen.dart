import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/router/app_router.dart';
import '../../core/theme/app_spacing.dart';
import '../../core/theme/app_theme.dart';
import '../../core/widgets/widgets.dart';
import '../../data/local/database.dart';
import '../auth/auth_providers.dart';
import '../auth/auth_repository.dart';
import '../enterprise/enterprise_providers.dart';
import 'stores_providers.dart';

/// Do'kon detail ekrani — lokal Drift'dan (offline).
class StoreDetailScreen extends ConsumerWidget {
  const StoreDetailScreen({super.key, required this.storeId});
  final String storeId;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final storeAsync = ref.watch(storeByIdProvider(storeId));
    final cs = Theme.of(context).colorScheme;

    // Joriy foydalanuvchi
    final authState = ref.watch(authNotifierProvider);
    final currentUser = switch (authState) {
      AuthStateAuthenticated(:final user) => user,
      _ => null,
    };
    final isAgent = currentUser?.role == 'agent';

    // Modul gating
    final hasContracts = ref.watch(moduleEnabledProvider('contracts'));
    final hasMarketplace = ref.watch(moduleEnabledProvider('marketplace'));

    return Scaffold(
      appBar: AppBar(
        title: const Text("Do'kon"),
        actions: [
          // Tahrirlash — agent o'zi yaratgan do'konni tuzata oladi
          storeAsync.whenOrNull(
                data: (store) {
                  if (store != null &&
                      isAgent &&
                      currentUser != null &&
                      store.agentId == currentUser.id) {
                    return IconButton(
                      icon: const Icon(Icons.edit_outlined),
                      tooltip: 'Tahrirlash',
                      onPressed: () => context
                          .push('$routeStores/$storeId/edit'),
                    );
                  }
                  return null;
                },
              ) ??
              const SizedBox.shrink(),
          if (!isAgent)
            IconButton(
              icon: const Icon(Icons.shopping_cart_outlined),
              tooltip: 'Buyurtma',
              onPressed: () =>
                  context.push('/home/orders/create?storeId=$storeId'),
            ),
        ],
      ),
      body: storeAsync.when(
        data: (store) {
          if (store == null) {
            return const EmptyState(
              icon: Icons.store_mall_directory_outlined,
              title: "Do'kon topilmadi",
              message: "Bu do'kon mavjud emas yoki o'chirilgan.",
            );
          }
          return _StoreDetailBody(
            store: store,
            isAgent: isAgent,
            hasContracts: hasContracts,
            hasMarketplace: hasMarketplace,
          );
        },
        loading: () =>
            Center(child: CircularProgressIndicator(color: cs.primary)),
        error: (e, _) => EmptyState(
          icon: Icons.error_outline,
          title: 'Xatolik yuz berdi',
          message: e.toString(),
        ),
      ),
    );
  }
}

class _StoreDetailBody extends StatelessWidget {
  const _StoreDetailBody({
    required this.store,
    required this.isAgent,
    required this.hasContracts,
    required this.hasMarketplace,
  });
  final Store store;
  final bool isAgent;
  final bool hasContracts;
  final bool hasMarketplace;

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    final tt = Theme.of(context).textTheme;

    return SingleChildScrollView(
      padding: const EdgeInsets.all(AppSpacing.lg),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // Sarlavha kartasi — do'kon nomi + avatar
          AppCard(
            padding: const EdgeInsets.all(AppSpacing.lg),
            child: Row(
              children: [
                Container(
                  width: 60,
                  height: 60,
                  decoration: BoxDecoration(
                    color: cs.primaryContainer,
                    borderRadius: BorderRadius.circular(AppSpacing.radiusMd),
                  ),
                  child: Icon(Icons.store_outlined,
                      size: AppSpacing.iconLg, color: cs.primary),
                ),
                const SizedBox(width: AppSpacing.lg),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        store.name,
                        style: tt.titleLarge
                            ?.copyWith(fontWeight: FontWeight.w700),
                      ),
                      if (store.address != null) ...[
                        const SizedBox(height: AppSpacing.xs),
                        Row(
                          children: [
                            Icon(Icons.location_on_outlined,
                                size: AppSpacing.iconXs,
                                color: cs.onSurfaceVariant),
                            const SizedBox(width: AppSpacing.xs),
                            Expanded(
                              child: Text(
                                store.address!,
                                style: tt.bodySmall
                                    ?.copyWith(color: cs.onSurfaceVariant),
                              ),
                            ),
                          ],
                        ),
                      ],
                    ],
                  ),
                ),
              ],
            ),
          ),

          const SizedBox(height: AppSpacing.lg),

          // Ma'lumot kartasi
          AppCard(
            padding: const EdgeInsets.all(AppSpacing.lg),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const SectionHeader(title: "Ma'lumot"),
                const SizedBox(height: AppSpacing.md),
                if (store.gpsLat != null && store.gpsLng != null)
                  _InfoRow(
                    icon: Icons.location_on_outlined,
                    label: 'GPS',
                    value:
                        '${store.gpsLat!.toStringAsFixed(6)}, ${store.gpsLng!.toStringAsFixed(6)}',
                    valueColor: cs.primary,
                  ),
                if (store.phone != null)
                  _InfoRow(
                    icon: Icons.phone_outlined,
                    label: 'Telefon',
                    value: store.phone!,
                  ),
                if (store.inn != null)
                  _InfoRow(
                    icon: Icons.badge_outlined,
                    label: 'INN',
                    value: store.inn!,
                  ),
                if (store.creditLimit != null)
                  _InfoRow(
                    icon: Icons.account_balance_wallet_outlined,
                    label: 'Kredit limiti',
                    value: '${_formatAmount(store.creditLimit!)} UZS',
                    valueColor: Theme.of(context).colorScheme.secondary,
                  ),
                if (store.gpsLat == null &&
                    store.phone == null &&
                    store.inn == null &&
                    store.creditLimit == null)
                  Text(
                    "Qo'shimcha ma'lumot mavjud emas",
                    style: tt.bodyMedium
                        ?.copyWith(color: cs.onSurfaceVariant),
                  ),
              ],
            ),
          ),

          const SizedBox(height: AppSpacing.xl),

          // Agent uchun amallar
          if (isAgent) ...[
            _AgentActionButtons(
              store: store,
              hasContracts: hasContracts,
              hasMarketplace: hasMarketplace,
            ),
          ] else ...[
            // Do'kon rolida (yoki boshqa) odatiy buyurtma
            SizedBox(
              width: double.infinity,
              child: FilledButton.icon(
                onPressed: () => context
                    .push('/home/orders/create?storeId=${store.id}'),
                icon: const Icon(Icons.add_shopping_cart_outlined),
                label: const Text('Buyurtma berish'),
              ),
            ),
          ],
        ],
      ),
    );
  }

  String _formatAmount(double amount) {
    final parts = amount.toStringAsFixed(0).split('');
    final buffer = StringBuffer();
    for (var i = 0; i < parts.length; i++) {
      if (i > 0 && (parts.length - i) % 3 == 0) buffer.write(' ');
      buffer.write(parts[i]);
    }
    return buffer.toString();
  }
}

// ---------------------------------------------------------------------------
// Agent amallar tugmalari

class _AgentActionButtons extends StatelessWidget {
  const _AgentActionButtons({
    required this.store,
    required this.hasContracts,
    required this.hasMarketplace,
  });
  final Store store;
  final bool hasContracts;
  final bool hasMarketplace;

  @override
  Widget build(BuildContext context) {
    final appColors = AppTheme.colorsOf(context);

    return Column(
      children: [
        // Onboarding
        SizedBox(
          width: double.infinity,
          child: FilledButton.icon(
            onPressed: () =>
                context.push('/home/stores/${store.id}/onboarding'),
            icon: const Icon(Icons.how_to_reg_outlined),
            label: const Text('Onboarding'),
            style: FilledButton.styleFrom(
              minimumSize: const Size.fromHeight(AppSpacing.buttonHeight),
            ),
          ),
        ),

        const SizedBox(height: AppSpacing.sm),

        // Shartnoma (modul-gated)
        if (hasContracts) ...[
          Row(
            children: [
              Expanded(
                child: OutlinedButton.icon(
                  onPressed: () =>
                      context.push('/home/stores/${store.id}/contracts'),
                  icon: const Icon(Icons.handshake_outlined),
                  label: const Text('Shartnomalar'),
                  style: OutlinedButton.styleFrom(
                    minimumSize:
                        const Size.fromHeight(AppSpacing.buttonHeight),
                  ),
                ),
              ),
              const SizedBox(width: AppSpacing.sm),
              Expanded(
                child: OutlinedButton.icon(
                  onPressed: () =>
                      context.push('/home/stores/${store.id}/contracts/create'),
                  icon: const Icon(Icons.add),
                  label: const Text("Shartnoma tuzish"),
                  style: OutlinedButton.styleFrom(
                    minimumSize:
                        const Size.fromHeight(AppSpacing.buttonHeight),
                    foregroundColor: appColors.success,
                    side: BorderSide(color: appColors.success),
                  ),
                ),
              ),
            ],
          ),
          const SizedBox(height: AppSpacing.sm),
        ],

        // Bir martalik buyurtma (modul-gated marketplace)
        if (hasMarketplace)
          SizedBox(
            width: double.infinity,
            child: FilledButton.icon(
              onPressed: () => context.push(
                '/home/marketplace/onetime?storeId=${store.id}',
              ),
              icon: const Icon(Icons.bolt_outlined),
              label: const Text('Bir martalik buyurtma'),
              style: FilledButton.styleFrom(
                backgroundColor: appColors.warning,
                foregroundColor: appColors.onWarning,
                minimumSize: const Size.fromHeight(AppSpacing.buttonHeight),
              ),
            ),
          ),

        // Odatiy buyurtma (katalogdan)
        const SizedBox(height: AppSpacing.sm),
        SizedBox(
          width: double.infinity,
          child: OutlinedButton.icon(
            onPressed: () =>
                context.push('/home/orders/create?storeId=${store.id}'),
            icon: const Icon(Icons.add_shopping_cart_outlined),
            label: const Text('Buyurtma berish'),
            style: OutlinedButton.styleFrom(
              minimumSize: const Size.fromHeight(AppSpacing.buttonHeight),
            ),
          ),
        ),
      ],
    );
  }
}

// ---------------------------------------------------------------------------

class _InfoRow extends StatelessWidget {
  const _InfoRow({
    required this.icon,
    required this.label,
    required this.value,
    this.valueColor,
  });
  final IconData icon;
  final String label;
  final String value;
  final Color? valueColor;

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    final tt = Theme.of(context).textTheme;

    return Padding(
      padding: const EdgeInsets.symmetric(vertical: AppSpacing.xs),
      child: Row(
        children: [
          Icon(icon, size: AppSpacing.iconXs, color: cs.onSurfaceVariant),
          const SizedBox(width: AppSpacing.sm),
          SizedBox(
            width: 96,
            child: Text(
              '$label:',
              style: tt.bodySmall?.copyWith(color: cs.onSurfaceVariant),
            ),
          ),
          Expanded(
            child: Text(
              value,
              style: tt.bodyMedium?.copyWith(
                fontWeight: FontWeight.w600,
                color: valueColor ?? cs.onSurface,
              ),
            ),
          ),
        ],
      ),
    );
  }
}
