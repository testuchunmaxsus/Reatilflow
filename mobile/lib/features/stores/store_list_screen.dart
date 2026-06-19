import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

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
          preferredSize: const Size.fromHeight(56),
          child: Padding(
            padding: const EdgeInsets.fromLTRB(12, 0, 12, 8),
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
      decoration: InputDecoration(
        hintText: "Do'kon qidirish...",
        prefixIcon: const Icon(Icons.search),
        border: OutlineInputBorder(borderRadius: BorderRadius.circular(8)),
        filled: true,
        fillColor: Theme.of(context).colorScheme.surface,
        contentPadding: const EdgeInsets.symmetric(vertical: 8),
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

    return storesAsync.when(
      data: (stores) {
        if (stores.isEmpty) {
          return const Center(
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                Icon(Icons.store_mall_directory_outlined,
                    size: 64, color: Colors.grey),
                SizedBox(height: 12),
                Text("Do'konlar topilmadi",
                    style: TextStyle(color: Colors.grey)),
                SizedBox(height: 6),
                Text(
                  'Sync qilinmagan bo\'lishi mumkin',
                  style: TextStyle(color: Colors.grey, fontSize: 12),
                ),
              ],
            ),
          );
        }
        return RefreshIndicator(
          onRefresh: () async {}, // SyncNotifier orqali boshqariladi
          child: ListView.builder(
            itemCount: stores.length,
            itemBuilder: (ctx, i) => _StoreCard(store: stores[i]),
          ),
        );
      },
      loading: () => const Center(child: CircularProgressIndicator()),
      error: (e, _) => Center(child: Text('Xatolik: $e')),
    );
  }
}

class _StoreCard extends StatelessWidget {
  const _StoreCard({required this.store});
  final Store store;

  @override
  Widget build(BuildContext context) {
    return Card(
      margin: const EdgeInsets.symmetric(horizontal: 12, vertical: 4),
      child: ListTile(
        leading: const CircleAvatar(child: Icon(Icons.store)),
        title: Text(store.name,
            style: const TextStyle(fontWeight: FontWeight.w600)),
        subtitle: store.address != null ? Text(store.address!) : null,
        trailing: const Icon(Icons.chevron_right),
        onTap: () => context.push('/home/stores/${store.id}'),
      ),
    );
  }
}
