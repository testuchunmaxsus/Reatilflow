import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/theme/app_spacing.dart';
import '../../core/widgets/widgets.dart';
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
          IconButton(
            icon: const Icon(Icons.qr_code_scanner_outlined),
            tooltip: 'Barcode skanerla',
            onPressed: () => _scanBarcode(context, ref),
          ),
        ],
        bottom: PreferredSize(
          preferredSize: const Size.fromHeight(64),
          child: Padding(
            padding: const EdgeInsets.fromLTRB(
                AppSpacing.lg, 0, AppSpacing.lg, AppSpacing.sm),
            child: _ProductSearchBar(),
          ),
        ),
      ),
      body: const _ProductList(),
    );
  }

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
        hintText: "Nom, SKU yoki barcode bo'yicha qidirish...",
        prefixIcon: const Icon(Icons.search_outlined),
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
    final cs = Theme.of(context).colorScheme;

    return productsAsync.when(
      data: (products) {
        if (products.isEmpty) {
          return const EmptyState(
            icon: Icons.inventory_2_outlined,
            title: 'Mahsulot topilmadi',
            message: "Sync qilinmagan yoki qidiruv noto'g'ri",
          );
        }
        return ListView.separated(
          padding: const EdgeInsets.all(AppSpacing.lg),
          itemCount: products.length,
          separatorBuilder: (_, __) =>
              const SizedBox(height: AppSpacing.sm),
          itemBuilder: (ctx, i) => _ProductCard(product: products[i]),
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

class _ProductCard extends StatelessWidget {
  const _ProductCard({required this.product});
  final Product product;

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    final tt = Theme.of(context).textTheme;

    return AppCard(
      padding: const EdgeInsets.all(AppSpacing.md),
      child: Row(
        children: [
          // Rasm yoki placeholder
          ClipRRect(
            borderRadius: BorderRadius.circular(AppSpacing.radiusSm),
            child: product.photoUrl != null
                ? Image.network(
                    product.photoUrl!,
                    width: 52,
                    height: 52,
                    fit: BoxFit.cover,
                    errorBuilder: (_, __, ___) => _PlaceholderIcon(cs: cs),
                  )
                : _PlaceholderIcon(cs: cs),
          ),

          const SizedBox(width: AppSpacing.md),

          // Matn
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  product.nameUz,
                  style: tt.titleSmall?.copyWith(fontWeight: FontWeight.w600),
                  maxLines: 2,
                  overflow: TextOverflow.ellipsis,
                ),
                const SizedBox(height: AppSpacing.xs),
                if (product.sku != null)
                  _MetaChip(
                      icon: Icons.tag_outlined, label: product.sku!),
                if (product.barcode != null)
                  _MetaChip(
                      icon: Icons.qr_code_outlined,
                      label: product.barcode!),
              ],
            ),
          ),

          const SizedBox(width: AppSpacing.sm),

          // O'ng tomon: birlik + narx holati
          Column(
            crossAxisAlignment: CrossAxisAlignment.end,
            children: [
              Container(
                padding: const EdgeInsets.symmetric(
                    horizontal: AppSpacing.sm, vertical: AppSpacing.xs),
                decoration: BoxDecoration(
                  color: cs.surfaceContainerHighest,
                  borderRadius: BorderRadius.circular(AppSpacing.radiusXs),
                ),
                child: Text(
                  product.unit,
                  style: tt.labelSmall?.copyWith(
                    color: cs.onSurfaceVariant,
                    fontWeight: FontWeight.w600,
                  ),
                ),
              ),
              const SizedBox(height: AppSpacing.xs),
              // Narx server-avtoritar — mahalliy narx ko'rsatilmaydi (T11)
              Text(
                'Narx: server',
                style: tt.labelSmall?.copyWith(
                    color: cs.tertiary, fontWeight: FontWeight.w500),
              ),
            ],
          ),
        ],
      ),
    );
  }
}

class _PlaceholderIcon extends StatelessWidget {
  const _PlaceholderIcon({required this.cs});
  final ColorScheme cs;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: 52,
      height: 52,
      decoration: BoxDecoration(
        color: cs.surfaceContainerHighest,
        borderRadius: BorderRadius.circular(AppSpacing.radiusSm),
      ),
      child: Icon(Icons.inventory_2_outlined,
          size: AppSpacing.iconMd, color: cs.onSurfaceVariant),
    );
  }
}

class _MetaChip extends StatelessWidget {
  const _MetaChip({required this.icon, required this.label});
  final IconData icon;
  final String label;

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    final tt = Theme.of(context).textTheme;
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        Icon(icon, size: 11, color: cs.onSurfaceVariant),
        const SizedBox(width: 3),
        Text(
          label,
          style: tt.labelSmall?.copyWith(color: cs.onSurfaceVariant),
        ),
      ],
    );
  }
}
