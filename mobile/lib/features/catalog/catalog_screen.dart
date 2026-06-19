import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../data/local/database.dart';
import 'barcode_scanner_service.dart';
import 'catalog_providers.dart';

/// Katalog ekrani — mahsulotlar lokal Drift'dan (offline).
/// Barcode skaner: mobile_scanner orqali MXIK / barcode skanerlash.
///
/// Platform sozlamalari:
///   Android: CAMERA ruxsati (AndroidManifest.xml)
///   iOS: NSCameraUsageDescription (Info.plist)
class CatalogScreen extends ConsumerWidget {
  const CatalogScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Katalog'),
        actions: [
          // Barcode skaner tugmasi
          IconButton(
            icon: const Icon(Icons.qr_code_scanner),
            tooltip: 'Barcode skanerla',
            onPressed: () => _scanBarcode(context, ref),
          ),
        ],
        bottom: PreferredSize(
          preferredSize: const Size.fromHeight(56),
          child: Padding(
            padding: const EdgeInsets.fromLTRB(12, 0, 12, 8),
            child: _ProductSearchBar(),
          ),
        ),
      ),
      body: const _ProductList(),
    );
  }

  /// Barcode skanerini ochish va natijani qidiruv maydoniga joylashtirish.
  Future<void> _scanBarcode(BuildContext context, WidgetRef ref) async {
    const scanner = MobileScannerService();
    final result = await scanner.scan(context);
    if (result != null && result.isNotEmpty) {
      ref.read(productSearchProvider.notifier).setQuery(result);
    }
  }
}

class _ProductSearchBar extends ConsumerWidget {
  @override
  Widget build(BuildContext context, WidgetRef ref) {
    return TextField(
      decoration: InputDecoration(
        hintText: 'Nom, SKU yoki barcode bo\'yicha qidirish...',
        prefixIcon: const Icon(Icons.search),
        suffixIcon: Consumer(
          builder: (_, ref, __) {
            final query = ref.watch(productSearchProvider);
            if (query.isEmpty) return const SizedBox.shrink();
            return IconButton(
              icon: const Icon(Icons.clear),
              onPressed: ref.read(productSearchProvider.notifier).clear,
            );
          },
        ),
        border: OutlineInputBorder(borderRadius: BorderRadius.circular(8)),
        filled: true,
        fillColor: Theme.of(context).colorScheme.surface,
        contentPadding: const EdgeInsets.symmetric(vertical: 8),
      ),
      onChanged: ref.read(productSearchProvider.notifier).setQuery,
    );
  }
}

class _ProductList extends ConsumerWidget {
  const _ProductList();

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final productsAsync = ref.watch(filteredProductsProvider);

    return productsAsync.when(
      data: (products) {
        if (products.isEmpty) {
          return Center(
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                Icon(Icons.inventory_2_outlined,
                    size: 64,
                    color: Theme.of(context).colorScheme.outline),
                const SizedBox(height: 12),
                Text(
                  'Mahsulot topilmadi',
                  style: TextStyle(
                      color: Theme.of(context).colorScheme.outline),
                ),
                const SizedBox(height: 6),
                Text(
                  'Sync qilinmagan yoki qidiruv noto\'g\'ri',
                  style: TextStyle(
                    color: Theme.of(context).colorScheme.outline,
                    fontSize: 12,
                  ),
                ),
              ],
            ),
          );
        }

        return ListView.builder(
          itemCount: products.length,
          itemBuilder: (ctx, i) => _ProductCard(product: products[i]),
        );
      },
      loading: () => const Center(child: CircularProgressIndicator()),
      error: (e, _) => Center(child: Text('Xatolik: $e')),
    );
  }
}

class _ProductCard extends StatelessWidget {
  const _ProductCard({required this.product});
  final Product product;

  @override
  Widget build(BuildContext context) {
    return Card(
      margin: const EdgeInsets.symmetric(horizontal: 12, vertical: 4),
      child: ListTile(
        leading: product.photoUrl != null
            ? ClipRRect(
                borderRadius: BorderRadius.circular(6),
                child: Image.network(
                  product.photoUrl!,
                  width: 48,
                  height: 48,
                  fit: BoxFit.cover,
                  errorBuilder: (_, __, ___) => const Icon(Icons.image_not_supported),
                ),
              )
            : const CircleAvatar(child: Icon(Icons.inventory_2)),
        title: Text(
          product.nameUz,
          style: const TextStyle(fontWeight: FontWeight.w600),
        ),
        subtitle: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            if (product.sku != null)
              Text('SKU: ${product.sku!}',
                  style: const TextStyle(fontSize: 11, color: Colors.grey)),
            if (product.barcode != null)
              Text('Barcode: ${product.barcode!}',
                  style: const TextStyle(fontSize: 11, color: Colors.grey)),
          ],
        ),
        trailing: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          crossAxisAlignment: CrossAxisAlignment.end,
          children: [
            Text(
              product.unit,
              style: const TextStyle(fontSize: 12, color: Colors.grey),
            ),
            // Narx server-avtoritar — mahalliy narx ko'rsatilmaydi (T11)
            const Text(
              'Narx: server',
              style: TextStyle(fontSize: 10, color: Colors.orange),
            ),
          ],
        ),
        isThreeLine: product.sku != null && product.barcode != null,
      ),
    );
  }
}
