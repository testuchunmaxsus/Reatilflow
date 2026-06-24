import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/theme/app_spacing.dart';
import '../../core/widgets/widgets.dart';
import '../../data/local/database.dart';
import '../auth/auth_providers.dart';
import '../auth/auth_repository.dart';
import 'stores_providers.dart';

/// Do'konlar ro'yxati ekrani — lokal Drift'dan (offline).
/// Agent faqat o'zi biriktirilgan do'konlarni ko'radi.
class StoreListScreen extends ConsumerWidget {
  const StoreListScreen({super.key});

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
        title: const Text("Do'konlar"),
        bottom: PreferredSize(
          preferredSize: const Size.fromHeight(64),
          child: Padding(
            padding: const EdgeInsets.fromLTRB(
                AppSpacing.lg, 0, AppSpacing.lg, AppSpacing.sm),
            child: _SearchBar(),
          ),
        ),
      ),
      body: _StoreList(agentId: user.id),
    );
  }
}

class _SearchBar extends ConsumerWidget {
  @override
  Widget build(BuildContext context, WidgetRef ref) {
    return TextField(
      decoration: const InputDecoration(
        hintText: "Do'kon qidirish...",
        prefixIcon: Icon(Icons.search_outlined),
      ),
      onChanged: ref.read(storeSearchProvider.notifier).setQuery,
    );
  }
}

class _StoreList extends ConsumerWidget {
  const _StoreList({required this.agentId});
  final String agentId;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final storesAsync = ref.watch(filteredStoresProvider(agentId));
    final cs = Theme.of(context).colorScheme;

    return storesAsync.when(
      data: (stores) {
        if (stores.isEmpty) {
          return const EmptyState(
            icon: Icons.store_mall_directory_outlined,
            title: "Do'konlar topilmadi",
            message: "Sync qilinmagan yoki qidiruv noto'g'ri",
          );
        }
        return RefreshIndicator(
          onRefresh: () async {},
          child: ListView.separated(
            padding: const EdgeInsets.all(AppSpacing.lg),
            itemCount: stores.length,
            separatorBuilder: (_, __) =>
                const SizedBox(height: AppSpacing.sm),
            itemBuilder: (ctx, i) => _StoreCard(store: stores[i]),
          ),
        );
      },
      loading: () =>
          Center(child: CircularProgressIndicator(color: cs.primary)),
      error: (e, _) => EmptyState(
        icon: Icons.error_outline,
        title: 'Xatolik yuz berdi',
        message: e.toString(),
      ),
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
      onTap: () => context.push('/home/stores/${store.id}'),
      padding: const EdgeInsets.all(AppSpacing.lg),
      child: Row(
        children: [
          Container(
            width: 48,
            height: 48,
            decoration: BoxDecoration(
              color: cs.primaryContainer,
              borderRadius: BorderRadius.circular(AppSpacing.radiusMd),
            ),
            child: Icon(Icons.store_outlined,
                color: cs.primary, size: AppSpacing.iconMd),
          ),
          const SizedBox(width: AppSpacing.lg),
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
