import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import 'marketplace_models.dart';
import 'marketplace_providers.dart';

/// Marketplace bosh ekrani — banner karusel, aksiyalar, mahsulotlar.
class MarketplaceBrowseScreen extends ConsumerStatefulWidget {
  const MarketplaceBrowseScreen({super.key});

  @override
  ConsumerState<MarketplaceBrowseScreen> createState() =>
      _MarketplaceBrowseScreenState();
}

class _MarketplaceBrowseScreenState
    extends ConsumerState<MarketplaceBrowseScreen> {
  final _searchController = TextEditingController();

  @override
  void dispose() {
    _searchController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Marketplace'),
        actions: [
          IconButton(
            icon: const Icon(Icons.shopping_cart_outlined),
            tooltip: 'Buyurtmalarim',
            onPressed: () => context.go('/home/marketplace/orders'),
          ),
        ],
        bottom: PreferredSize(
          preferredSize: const Size.fromHeight(56),
          child: _SearchBar(controller: _searchController),
        ),
      ),
      body: const _MarketplaceBody(),
    );
  }
}

class _SearchBar extends ConsumerWidget {
  const _SearchBar({required this.controller});
  final TextEditingController controller;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(16, 0, 16, 8),
      child: TextField(
        controller: controller,
        decoration: InputDecoration(
          hintText: 'Mahsulot qidirish...',
          prefixIcon: const Icon(Icons.search, size: 20),
          suffixIcon: controller.text.isNotEmpty
              ? IconButton(
                  icon: const Icon(Icons.clear, size: 18),
                  onPressed: () {
                    controller.clear();
                    ref.read(marketplaceSearchProvider.notifier).clear();
                  },
                )
              : null,
          isDense: true,
          border: OutlineInputBorder(
            borderRadius: BorderRadius.circular(10),
            borderSide: BorderSide.none,
          ),
          filled: true,
          fillColor: Colors.grey.shade100,
          contentPadding: const EdgeInsets.symmetric(vertical: 10),
        ),
        onChanged: (v) => ref.read(marketplaceSearchProvider.notifier).set(v),
      ),
    );
  }
}

class _MarketplaceBody extends ConsumerWidget {
  const _MarketplaceBody();

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    return RefreshIndicator(
      onRefresh: () async {
        ref.invalidate(bannersNotifierProvider);
        ref.invalidate(promosNotifierProvider);
        ref.invalidate(productsNotifierProvider);
      },
      child: CustomScrollView(
        slivers: [
          // --- Reklama bannerlari ---
          const SliverToBoxAdapter(child: _BannerCarousel()),

          // --- Qaynoq aksiyalar ---
          const SliverToBoxAdapter(child: SizedBox(height: 8)),
          const SliverToBoxAdapter(child: _PromoSection()),

          // --- Mahsulotlar sarlavhasi ---
          SliverToBoxAdapter(
            child: Padding(
              padding: const EdgeInsets.fromLTRB(16, 16, 16, 8),
              child: Row(
                children: [
                  Text(
                    'Mahsulotlar',
                    style: Theme.of(context)
                        .textTheme
                        .titleMedium
                        ?.copyWith(fontWeight: FontWeight.bold),
                  ),
                  const Spacer(),
                  const _SupplierFilterChip(),
                ],
              ),
            ),
          ),

          // --- Mahsulotlar ro'yxati ---
          const _ProductsSliver(),

          const SliverToBoxAdapter(child: SizedBox(height: 24)),
        ],
      ),
    );
  }
}

// ---------------------------------------------------------------------------
// Bannerlar karusel

class _BannerCarousel extends ConsumerStatefulWidget {
  const _BannerCarousel();

  @override
  ConsumerState<_BannerCarousel> createState() => _BannerCarouselState();
}

class _BannerCarouselState extends ConsumerState<_BannerCarousel> {
  final _pageController = PageController();
  int _currentPage = 0;

  @override
  void dispose() {
    _pageController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final bannersState = ref.watch(bannersNotifierProvider);

    return switch (bannersState) {
      BannersLoading() => const SizedBox(
          height: 160,
          child: Center(child: CircularProgressIndicator()),
        ),
      BannersError(:final message) => SizedBox(
          height: 80,
          child: Center(
            child: Text(
              'Bannerlar yuklanmadi: $message',
              style: const TextStyle(color: Colors.grey, fontSize: 12),
            ),
          ),
        ),
      BannersLoaded(banners: final banners) when banners.isEmpty =>
        const SizedBox.shrink(),
      BannersLoaded(:final banners) => _buildCarousel(banners),
    };
  }

  Widget _buildCarousel(List<MarketplaceBanner> banners) {
    return SizedBox(
      height: 164,
      child: Column(
        children: [
          Expanded(
            child: PageView.builder(
              controller: _pageController,
              onPageChanged: (i) => setState(() => _currentPage = i),
              itemCount: banners.length,
              itemBuilder: (context, i) => _BannerTile(banner: banners[i]),
            ),
          ),
          if (banners.length > 1)
            Padding(
              padding: const EdgeInsets.only(top: 6),
              child: Row(
                mainAxisAlignment: MainAxisAlignment.center,
                children: List.generate(
                  banners.length,
                  (i) => AnimatedContainer(
                    duration: const Duration(milliseconds: 250),
                    margin: const EdgeInsets.symmetric(horizontal: 3),
                    width: _currentPage == i ? 18 : 6,
                    height: 6,
                    decoration: BoxDecoration(
                      borderRadius: BorderRadius.circular(3),
                      color: _currentPage == i
                          ? Theme.of(context).colorScheme.primary
                          : Colors.grey.shade300,
                    ),
                  ),
                ),
              ),
            ),
        ],
      ),
    );
  }
}

class _BannerTile extends StatelessWidget {
  const _BannerTile({required this.banner});
  final MarketplaceBanner banner;

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: () {
        if (banner.targetProductId != null) {
          // Mahsulotga scroll qilish yoki detail ochish
          // v2c da kengaytirish mumkin
        }
      },
      child: Container(
        margin: const EdgeInsets.symmetric(horizontal: 12),
        decoration: BoxDecoration(
          borderRadius: BorderRadius.circular(12),
          gradient: LinearGradient(
            colors: [
              Theme.of(context).colorScheme.primaryContainer,
              Theme.of(context).colorScheme.secondaryContainer,
            ],
          ),
        ),
        child: ClipRRect(
          borderRadius: BorderRadius.circular(12),
          child: Stack(
            fit: StackFit.expand,
            children: [
              if (banner.imageUrl.isNotEmpty)
                Image.network(
                  banner.imageUrl,
                  fit: BoxFit.cover,
                  errorBuilder: (_, __, ___) => _BannerPlaceholder(
                    title: banner.title,
                  ),
                )
              else
                _BannerPlaceholder(title: banner.title),
              if (banner.title != null)
                Positioned(
                  left: 0,
                  right: 0,
                  bottom: 0,
                  child: Container(
                    padding: const EdgeInsets.symmetric(
                        horizontal: 14, vertical: 8),
                    decoration: BoxDecoration(
                      gradient: LinearGradient(
                        begin: Alignment.bottomCenter,
                        end: Alignment.topCenter,
                        colors: [
                          Colors.black.withValues(alpha: 0.55),
                          Colors.transparent,
                        ],
                      ),
                    ),
                    child: Text(
                      banner.title!,
                      style: const TextStyle(
                        color: Colors.white,
                        fontSize: 13,
                        fontWeight: FontWeight.w600,
                      ),
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                    ),
                  ),
                ),
            ],
          ),
        ),
      ),
    );
  }
}

class _BannerPlaceholder extends StatelessWidget {
  const _BannerPlaceholder({this.title});
  final String? title;

  @override
  Widget build(BuildContext context) {
    return Container(
      color: Theme.of(context).colorScheme.primaryContainer,
      child: Center(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(
              Icons.local_offer,
              size: 40,
              color: Theme.of(context).colorScheme.primary,
            ),
            if (title != null) ...[
              const SizedBox(height: 6),
              Text(
                title!,
                style: TextStyle(
                  color: Theme.of(context).colorScheme.primary,
                  fontWeight: FontWeight.w600,
                ),
              ),
            ],
          ],
        ),
      ),
    );
  }
}

// ---------------------------------------------------------------------------
// Aksiyalar bo'limi

class _PromoSection extends ConsumerWidget {
  const _PromoSection();

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final promosState = ref.watch(promosNotifierProvider);

    return switch (promosState) {
      PromosLoading() => const SizedBox(
          height: 100,
          child: Center(child: CircularProgressIndicator()),
        ),
      PromosError() => const SizedBox.shrink(),
      PromosLoaded(promos: final promos) when promos.isEmpty =>
        const SizedBox.shrink(),
      PromosLoaded(:final promos) => _buildPromos(context, promos),
    };
  }

  Widget _buildPromos(BuildContext context, List<MarketplacePromo> promos) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Padding(
          padding: const EdgeInsets.fromLTRB(16, 8, 16, 8),
          child: Text(
            'Qaynoq aksiyalar',
            style: Theme.of(context)
                .textTheme
                .titleMedium
                ?.copyWith(fontWeight: FontWeight.bold),
          ),
        ),
        SizedBox(
          height: 130,
          child: ListView.separated(
            scrollDirection: Axis.horizontal,
            padding: const EdgeInsets.symmetric(horizontal: 12),
            itemCount: promos.length,
            separatorBuilder: (_, __) => const SizedBox(width: 10),
            itemBuilder: (context, i) => _PromoCard(promo: promos[i]),
          ),
        ),
      ],
    );
  }
}

class _PromoCard extends StatelessWidget {
  const _PromoCard({required this.promo});
  final MarketplacePromo promo;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: 160,
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(12),
        color: Colors.orange.shade50,
        border: Border.all(color: Colors.orange.shade200),
      ),
      padding: const EdgeInsets.all(12),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // Chegirma ulushi
          if (promo.discountPercent != null)
            Container(
              padding:
                  const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
              decoration: BoxDecoration(
                color: Colors.orange,
                borderRadius: BorderRadius.circular(6),
              ),
              child: Text(
                '-${promo.discountPercent!.toStringAsFixed(0)}%',
                style: const TextStyle(
                  color: Colors.white,
                  fontSize: 11,
                  fontWeight: FontWeight.bold,
                ),
              ),
            ),
          const SizedBox(height: 6),
          Expanded(
            child: Text(
              promo.productName,
              style: const TextStyle(
                fontWeight: FontWeight.w600,
                fontSize: 13,
              ),
              maxLines: 2,
              overflow: TextOverflow.ellipsis,
            ),
          ),
          const SizedBox(height: 4),
          Text(
            promo.supplierName,
            style: TextStyle(
              fontSize: 11,
              color: Colors.grey.shade600,
            ),
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
          ),
          const SizedBox(height: 4),
          Row(
            children: [
              Text(
                _fmt(promo.promoPrice),
                style: TextStyle(
                  fontSize: 13,
                  fontWeight: FontWeight.bold,
                  color: Colors.orange.shade800,
                ),
              ),
              const SizedBox(width: 4),
              if (promo.originalPrice > promo.promoPrice)
                Text(
                  _fmt(promo.originalPrice),
                  style: const TextStyle(
                    fontSize: 11,
                    decoration: TextDecoration.lineThrough,
                    color: Colors.grey,
                  ),
                ),
            ],
          ),
        ],
      ),
    );
  }

  String _fmt(double v) {
    if (v >= 1000000) {
      return "${(v / 1000000).toStringAsFixed(1)} mln so'm";
    }
    if (v >= 1000) {
      return "${(v / 1000).toStringAsFixed(0)} ming so'm";
    }
    return "${v.toStringAsFixed(0)} so'm";
  }
}

// ---------------------------------------------------------------------------
// Supplier filtri

class _SupplierFilterChip extends ConsumerWidget {
  const _SupplierFilterChip();

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final selectedSupplier =
        ref.watch(marketplaceSupplierFilterProvider);
    final productsState = ref.watch(productsNotifierProvider);

    // Mavjud supplierlar ro'yxatini mahsulotlardan olish
    final suppliers = <String, String>{};
    if (productsState is ProductsLoaded) {
      for (final p in productsState.products) {
        suppliers[p.supplierEnterpriseId] = p.supplierEnterpriseName;
      }
    }

    if (suppliers.isEmpty) return const SizedBox.shrink();

    return TextButton.icon(
      onPressed: () => _showSupplierSheet(context, ref, suppliers),
      icon: const Icon(Icons.filter_list, size: 16),
      label: Text(
        selectedSupplier != null
            ? (suppliers[selectedSupplier] ?? 'Filtr')
            : 'Filtr',
        style: const TextStyle(fontSize: 13),
      ),
      style: TextButton.styleFrom(
        padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
      ),
    );
  }

  void _showSupplierSheet(
    BuildContext context,
    WidgetRef ref,
    Map<String, String> suppliers,
  ) {
    showModalBottomSheet<void>(
      context: context,
      builder: (ctx) => SafeArea(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            ListTile(
              title: const Text('Barcha supplierlar'),
              leading: const Icon(Icons.clear),
              onTap: () {
                ref
                    .read(marketplaceSupplierFilterProvider.notifier)
                    .clear();
                Navigator.pop(ctx);
              },
            ),
            const Divider(height: 1),
            ...suppliers.entries.map(
              (e) => ListTile(
                title: Text(e.value),
                leading: const Icon(Icons.storefront),
                onTap: () {
                  ref
                      .read(marketplaceSupplierFilterProvider.notifier)
                      .set(e.key);
                  Navigator.pop(ctx);
                },
              ),
            ),
          ],
        ),
      ),
    );
  }
}

// ---------------------------------------------------------------------------
// Mahsulotlar ro'yxati (Sliver)

class _ProductsSliver extends ConsumerWidget {
  const _ProductsSliver();

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final productsState = ref.watch(productsNotifierProvider);

    return switch (productsState) {
      ProductsLoading() => const SliverToBoxAdapter(
          child: Padding(
            padding: EdgeInsets.all(32),
            child: Center(child: CircularProgressIndicator()),
          ),
        ),
      ProductsError(:final message) => SliverToBoxAdapter(
          child: Padding(
            padding: const EdgeInsets.all(24),
            child: Center(
              child: Text(
                'Xatolik: $message',
                style: const TextStyle(color: Colors.red),
                textAlign: TextAlign.center,
              ),
            ),
          ),
        ),
      ProductsLoaded(products: final products) when products.isEmpty =>
        const SliverToBoxAdapter(
          child: Padding(
            padding: EdgeInsets.all(32),
            child: Center(
              child: Text(
                'Mahsulot topilmadi',
                style: TextStyle(color: Colors.grey),
              ),
            ),
          ),
        ),
      ProductsLoaded(:final products) => SliverList(
          delegate: SliverChildBuilderDelegate(
            (context, i) => _ProductTile(product: products[i]),
            childCount: products.length,
          ),
        ),
    };
  }
}

class _ProductTile extends ConsumerWidget {
  const _ProductTile({required this.product});
  final MarketplaceProduct product;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    return Card(
      margin: const EdgeInsets.symmetric(horizontal: 12, vertical: 4),
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Row(
          children: [
            // Mahsulot ikonasi
            Container(
              width: 52,
              height: 52,
              decoration: BoxDecoration(
                borderRadius: BorderRadius.circular(8),
                color: Colors.blue.shade50,
              ),
              child: Icon(
                Icons.inventory_2_outlined,
                color: Colors.blue.shade400,
                size: 28,
              ),
            ),
            const SizedBox(width: 12),

            // Ma'lumot
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    product.name,
                    style: const TextStyle(
                      fontWeight: FontWeight.w600,
                      fontSize: 14,
                    ),
                    maxLines: 2,
                    overflow: TextOverflow.ellipsis,
                  ),
                  const SizedBox(height: 2),
                  Text(
                    product.supplierEnterpriseName,
                    style: TextStyle(
                      fontSize: 12,
                      color: Colors.grey.shade600,
                    ),
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                  ),
                  const SizedBox(height: 4),
                  Row(
                    children: [
                      Text(
                        _fmtPrice(product.price),
                        style: const TextStyle(
                          fontSize: 13,
                          fontWeight: FontWeight.w600,
                          color: Colors.blue,
                        ),
                      ),
                      const SizedBox(width: 8),
                      Text(
                        product.unit,
                        style: TextStyle(
                          fontSize: 11,
                          color: Colors.grey.shade500,
                        ),
                      ),
                    ],
                  ),
                ],
              ),
            ),

            // Buyurtma berish tugmasi
            _OrderButton(product: product),
          ],
        ),
      ),
    );
  }

  String _fmtPrice(double v) {
    if (v >= 1000000) return '${(v / 1000000).toStringAsFixed(1)} mln';
    if (v >= 1000) return '${(v / 1000).toStringAsFixed(0)} ming';
    return v.toStringAsFixed(0);
  }
}

/// Mahsulotni savatga qo'shish yoki buyurtma berish tugmasi.
class _OrderButton extends ConsumerWidget {
  const _OrderButton({required this.product});
  final MarketplaceProduct product;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final cartState = ref.watch(marketplaceCartProvider);
    final inCart = cartState.items.any((e) => e.product.id == product.id);

    if (inCart) {
      return FilledButton.icon(
        style: FilledButton.styleFrom(
          backgroundColor: Colors.green,
          padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 8),
          minimumSize: Size.zero,
        ),
        onPressed: () => context.go('/home/marketplace/cart'),
        icon: const Icon(Icons.shopping_cart, size: 16),
        label: const Text('Savatda', style: TextStyle(fontSize: 12)),
      );
    }

    return FilledButton(
      style: FilledButton.styleFrom(
        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
        minimumSize: Size.zero,
      ),
      onPressed: () => _addToCart(context, ref),
      child: const Text('Qo\'sh', style: TextStyle(fontSize: 12)),
    );
  }

  void _addToCart(BuildContext context, WidgetRef ref) {
    ref.read(marketplaceCartProvider.notifier).addItem(product);
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text('${product.name} savatga qo\'shildi'),
        duration: const Duration(seconds: 2),
        action: SnackBarAction(
          label: 'Savat',
          onPressed: () => context.go('/home/marketplace/cart'),
        ),
      ),
    );
  }
}
