import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/theme/app_spacing.dart';
import '../../core/theme/app_theme.dart';
import '../../core/widgets/app_card.dart';
import '../../core/widgets/empty_state.dart';
import '../../core/widgets/section_header.dart';
import 'marketplace_models.dart';
import 'marketplace_providers.dart';

/// Marketplace bosh ekrani — banner karusel, aksiyalar, mahsulotlar grid.
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
    final cs = Theme.of(context).colorScheme;
    final cartState = ref.watch(marketplaceCartProvider);
    final cartCount = cartState.items.length;

    return Scaffold(
      appBar: AppBar(
        title: const Text('Marketplace'),
        actions: [
          // Savat badge
          Stack(
            clipBehavior: Clip.none,
            children: [
              IconButton(
                icon: const Icon(Icons.shopping_cart_outlined),
                tooltip: 'Savat',
                onPressed: () =>
                    context.go('/home/marketplace/cart'),
              ),
              if (cartCount > 0)
                Positioned(
                  right: 4,
                  top: 4,
                  child: Container(
                    width: 18,
                    height: 18,
                    decoration: BoxDecoration(
                      color: cs.error,
                      shape: BoxShape.circle,
                    ),
                    child: Center(
                      child: Text(
                        '$cartCount',
                        style: TextStyle(
                          color: cs.onError,
                          fontSize: 10,
                          fontWeight: FontWeight.w700,
                        ),
                      ),
                    ),
                  ),
                ),
            ],
          ),
          IconButton(
            icon: const Icon(Icons.receipt_long_outlined),
            tooltip: 'Buyurtmalarim',
            onPressed: () =>
                context.go('/home/marketplace/orders'),
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
      padding: const EdgeInsets.fromLTRB(
        AppSpacing.lg,
        0,
        AppSpacing.lg,
        AppSpacing.sm,
      ),
      child: TextField(
        controller: controller,
        decoration: InputDecoration(
          hintText: 'Mahsulot qidirish...',
          prefixIcon: const Icon(Icons.search, size: AppSpacing.iconSm),
          suffixIcon: controller.text.isNotEmpty
              ? IconButton(
                  icon: const Icon(Icons.clear, size: AppSpacing.iconSm),
                  onPressed: () {
                    controller.clear();
                    ref.read(marketplaceSearchProvider.notifier).clear();
                  },
                )
              : null,
          isDense: true,
        ),
        onChanged: (v) {
          ref.read(marketplaceSearchProvider.notifier).set(v);
        },
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
          const SliverToBoxAdapter(
            child: Padding(
              padding: EdgeInsets.only(top: AppSpacing.md),
              child: _BannerCarousel(),
            ),
          ),

          // --- Qaynoq aksiyalar ---
          const SliverToBoxAdapter(child: SizedBox(height: AppSpacing.sm)),
          const SliverToBoxAdapter(child: _PromoSection()),

          // --- Mahsulotlar sarlavhasi ---
          SliverToBoxAdapter(
            child: Padding(
              padding: const EdgeInsets.fromLTRB(
                AppSpacing.lg,
                AppSpacing.lg,
                AppSpacing.lg,
                AppSpacing.sm,
              ),
              child: Row(
                children: [
                  Expanded(
                    child: SectionHeader(title: 'Mahsulotlar'),
                  ),
                  const _SupplierFilterChip(),
                ],
              ),
            ),
          ),

          // --- Mahsulotlar grid ---
          const _ProductsSliver(),

          const SliverToBoxAdapter(
              child: SizedBox(height: AppSpacing.xxxl)),
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
      BannersLoading() => SizedBox(
          height: 160,
          child: ListView.separated(
            scrollDirection: Axis.horizontal,
            padding: const EdgeInsets.symmetric(horizontal: AppSpacing.lg),
            itemCount: 2,
            separatorBuilder: (_, __) => const SizedBox(width: AppSpacing.sm),
            itemBuilder: (_, __) => _BannerSkeleton(),
          ),
        ),
      BannersError(:final message) => SizedBox(
          height: 72,
          child: Center(
            child: Text(
              'Bannerlar yuklanmadi',
              style: Theme.of(context).textTheme.bodySmall?.copyWith(
                    color: Theme.of(context).colorScheme.onSurfaceVariant,
                  ),
            ),
          ),
        ),
      BannersLoaded(banners: final banners) when banners.isEmpty =>
        const SizedBox.shrink(),
      BannersLoaded(:final banners) => _buildCarousel(banners),
    };
  }

  Widget _buildCarousel(List<MarketplaceBanner> banners) {
    final cs = Theme.of(context).colorScheme;
    return SizedBox(
      height: 172,
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
              padding: const EdgeInsets.only(top: AppSpacing.sm),
              child: Row(
                mainAxisAlignment: MainAxisAlignment.center,
                children: List.generate(
                  banners.length,
                  (i) => AnimatedContainer(
                    duration: const Duration(milliseconds: 250),
                    margin: const EdgeInsets.symmetric(horizontal: 3),
                    width: _currentPage == i ? 20 : 6,
                    height: 6,
                    decoration: BoxDecoration(
                      borderRadius:
                          BorderRadius.circular(AppSpacing.radiusFull),
                      color: _currentPage == i
                          ? cs.primary
                          : cs.outlineVariant,
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

class _BannerSkeleton extends StatelessWidget {
  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    return Container(
      width: MediaQuery.of(context).size.width - AppSpacing.xxl * 2,
      height: 152,
      decoration: BoxDecoration(
        color: cs.surfaceContainerHighest,
        borderRadius: BorderRadius.circular(AppSpacing.radiusLg),
      ),
    );
  }
}

class _BannerTile extends StatelessWidget {
  const _BannerTile({required this.banner});
  final MarketplaceBanner banner;

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;

    return GestureDetector(
      onTap: () {
        if (banner.targetProductId != null) {
          // v2c da kengaytirish mumkin
        }
      },
      child: Container(
        margin: const EdgeInsets.symmetric(horizontal: AppSpacing.lg),
        decoration: BoxDecoration(
          borderRadius: BorderRadius.circular(AppSpacing.radiusLg),
          gradient: LinearGradient(
            colors: [
              cs.primaryContainer,
              cs.secondaryContainer,
            ],
          ),
        ),
        child: ClipRRect(
          borderRadius: BorderRadius.circular(AppSpacing.radiusLg),
          child: Stack(
            fit: StackFit.expand,
            children: [
              if (banner.imageUrl.isNotEmpty)
                Image.network(
                  banner.imageUrl,
                  fit: BoxFit.cover,
                  errorBuilder: (_, __, ___) =>
                      _BannerPlaceholder(title: banner.title),
                )
              else
                _BannerPlaceholder(title: banner.title),

              // Gradient overlay + title
              if (banner.title != null)
                Positioned(
                  left: 0,
                  right: 0,
                  bottom: 0,
                  child: Container(
                    padding: const EdgeInsets.symmetric(
                      horizontal: AppSpacing.lg,
                      vertical: AppSpacing.md,
                    ),
                    decoration: BoxDecoration(
                      gradient: LinearGradient(
                        begin: Alignment.bottomCenter,
                        end: Alignment.topCenter,
                        colors: [
                          Colors.black.withValues(alpha: 0.6),
                          Colors.transparent,
                        ],
                      ),
                    ),
                    child: Text(
                      banner.title!,
                      style: Theme.of(context)
                          .textTheme
                          .titleSmall
                          ?.copyWith(
                            color: Colors.white,
                            fontWeight: FontWeight.w700,
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
    final cs = Theme.of(context).colorScheme;
    return Container(
      color: cs.primaryContainer,
      child: Center(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(Icons.local_offer_outlined,
                size: AppSpacing.iconXl, color: cs.primary),
            if (title != null) ...[
              const SizedBox(height: AppSpacing.sm),
              Padding(
                padding: const EdgeInsets.symmetric(
                    horizontal: AppSpacing.lg),
                child: Text(
                  title!,
                  style: Theme.of(context).textTheme.titleSmall?.copyWith(
                        color: cs.primary,
                        fontWeight: FontWeight.w600,
                      ),
                  textAlign: TextAlign.center,
                  maxLines: 2,
                  overflow: TextOverflow.ellipsis,
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
      PromosLoading() => Padding(
          padding: const EdgeInsets.fromLTRB(
            AppSpacing.lg,
            AppSpacing.md,
            AppSpacing.lg,
            0,
          ),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Container(
                width: 140,
                height: 20,
                decoration: BoxDecoration(
                  color: Theme.of(context).colorScheme.surfaceContainerHighest,
                  borderRadius:
                      BorderRadius.circular(AppSpacing.radiusSm),
                ),
              ),
              const SizedBox(height: AppSpacing.md),
              SizedBox(
                height: 130,
                child: ListView.separated(
                  scrollDirection: Axis.horizontal,
                  itemCount: 3,
                  separatorBuilder: (_, __) =>
                      const SizedBox(width: AppSpacing.sm),
                  itemBuilder: (_, __) => _PromoCardSkeleton(),
                ),
              ),
            ],
          ),
        ),
      PromosError() => const SizedBox.shrink(),
      PromosLoaded(promos: final promos) when promos.isEmpty =>
        const SizedBox.shrink(),
      PromosLoaded(:final promos) => _buildPromos(context, promos),
    };
  }

  Widget _buildPromos(
      BuildContext context, List<MarketplacePromo> promos) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Padding(
          padding: const EdgeInsets.fromLTRB(
            AppSpacing.lg,
            AppSpacing.md,
            AppSpacing.lg,
            AppSpacing.sm,
          ),
          child: SectionHeader(
            title: 'Qaynoq aksiyalar',
            subtitle: '${promos.length} ta taklif',
          ),
        ),
        SizedBox(
          height: 140,
          child: ListView.separated(
            scrollDirection: Axis.horizontal,
            padding: const EdgeInsets.symmetric(
                horizontal: AppSpacing.lg),
            itemCount: promos.length,
            separatorBuilder: (_, __) =>
                const SizedBox(width: AppSpacing.sm),
            itemBuilder: (context, i) =>
                _PromoCard(promo: promos[i]),
          ),
        ),
      ],
    );
  }
}

class _PromoCardSkeleton extends StatelessWidget {
  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    return Container(
      width: 160,
      decoration: BoxDecoration(
        color: cs.surfaceContainerHighest,
        borderRadius: BorderRadius.circular(AppSpacing.radiusLg),
      ),
    );
  }
}

class _PromoCard extends StatelessWidget {
  const _PromoCard({required this.promo});
  final MarketplacePromo promo;

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    final tt = Theme.of(context).textTheme;
    final appColors = AppTheme.colorsOf(context);

    return Container(
      width: 164,
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(AppSpacing.radiusLg),
        color: appColors.warningContainer.withValues(alpha: 0.5),
        border: Border.all(
            color: appColors.warning.withValues(alpha: 0.3)),
      ),
      padding: const EdgeInsets.all(AppSpacing.md),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // Chegirma badge + muddat qatori
          Row(
            children: [
              if (promo.discountPercent != null)
                Container(
                  padding: const EdgeInsets.symmetric(
                      horizontal: AppSpacing.sm, vertical: 2),
                  decoration: BoxDecoration(
                    color: appColors.warning,
                    borderRadius:
                        BorderRadius.circular(AppSpacing.radiusXs),
                  ),
                  child: Text(
                    '-${promo.discountPercent!.toStringAsFixed(0)}%',
                    style: tt.labelSmall?.copyWith(
                      color: appColors.onWarning,
                      fontWeight: FontWeight.w700,
                    ),
                  ),
                ),
              const Spacer(),
              if (promo.endsAt != null)
                Icon(Icons.timer_outlined,
                    size: 12,
                    color: appColors.warning),
            ],
          ),

          const SizedBox(height: AppSpacing.sm),

          // Nomi
          Expanded(
            child: Text(
              promo.productName,
              style: tt.titleSmall?.copyWith(
                fontWeight: FontWeight.w600,
              ),
              maxLines: 2,
              overflow: TextOverflow.ellipsis,
            ),
          ),

          const SizedBox(height: AppSpacing.xs),

          // Supplier
          Text(
            promo.supplierName,
            style: tt.labelSmall?.copyWith(
              color: cs.onSurfaceVariant,
            ),
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
          ),

          const SizedBox(height: AppSpacing.xs),

          // Narxlar
          Row(
            crossAxisAlignment: CrossAxisAlignment.end,
            children: [
              Text(
                _fmt(promo.promoPrice),
                style: tt.labelLarge?.copyWith(
                  fontWeight: FontWeight.w700,
                  color: appColors.warning,
                ),
              ),
              const SizedBox(width: AppSpacing.xs),
              if (promo.originalPrice > promo.promoPrice)
                Text(
                  _fmt(promo.originalPrice),
                  style: tt.labelSmall?.copyWith(
                    decoration: TextDecoration.lineThrough,
                    color: cs.onSurfaceVariant,
                  ),
                ),
            ],
          ),
        ],
      ),
    );
  }

  String _fmt(double v) {
    if (v >= 1000000) return '${(v / 1000000).toStringAsFixed(1)} mln';
    if (v >= 1000) return '${(v / 1000).toStringAsFixed(0)} ming';
    return v.toStringAsFixed(0);
  }
}

// ---------------------------------------------------------------------------
// Supplier filtri

class _SupplierFilterChip extends ConsumerWidget {
  const _SupplierFilterChip();

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final cs = Theme.of(context).colorScheme;
    final selectedSupplier = ref.watch(marketplaceSupplierFilterProvider);
    final productsState = ref.watch(productsNotifierProvider);

    // Mavjud supplierlar ro'yxatini mahsulotlardan olish
    final suppliers = <String, String>{};
    if (productsState is ProductsLoaded) {
      for (final p in productsState.products) {
        suppliers[p.supplierEnterpriseId] = p.supplierEnterpriseName;
      }
    }

    if (suppliers.isEmpty) return const SizedBox.shrink();

    final isFiltered = selectedSupplier != null;

    return FilledButton.tonalIcon(
      onPressed: () => _showSupplierSheet(context, ref, suppliers),
      icon: Icon(
        isFiltered ? Icons.filter_alt : Icons.filter_list,
        size: AppSpacing.iconSm,
      ),
      label: Text(
        isFiltered
            ? (suppliers[selectedSupplier] ?? 'Filtr')
            : 'Filtr',
        style: Theme.of(context).textTheme.labelMedium,
      ),
      style: FilledButton.styleFrom(
        padding: const EdgeInsets.symmetric(
            horizontal: AppSpacing.sm, vertical: AppSpacing.xs),
        minimumSize: Size.zero,
        tapTargetSize: MaterialTapTargetSize.shrinkWrap,
        backgroundColor: isFiltered
            ? cs.primaryContainer
            : cs.surfaceContainerHighest,
        foregroundColor: isFiltered ? cs.primary : cs.onSurfaceVariant,
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
            // Handle
            Center(
              child: Container(
                width: 32,
                height: 4,
                margin: const EdgeInsets.only(
                    top: AppSpacing.sm, bottom: AppSpacing.md),
                decoration: BoxDecoration(
                  color:
                      Theme.of(context).colorScheme.outlineVariant,
                  borderRadius:
                      BorderRadius.circular(AppSpacing.radiusFull),
                ),
              ),
            ),
            Padding(
              padding: const EdgeInsets.fromLTRB(
                  AppSpacing.lg, 0, AppSpacing.lg, AppSpacing.sm),
              child: const SectionHeader(title: 'Supplier tanlash'),
            ),
            ListTile(
              title: const Text('Barchasi'),
              leading: Container(
                width: 36,
                height: 36,
                decoration: BoxDecoration(
                  color: Theme.of(context)
                      .colorScheme
                      .surfaceContainerHighest,
                  borderRadius:
                      BorderRadius.circular(AppSpacing.radiusSm),
                ),
                child: const Icon(Icons.clear, size: AppSpacing.iconSm),
              ),
              onTap: () {
                ref
                    .read(marketplaceSupplierFilterProvider.notifier)
                    .clear();
                Navigator.pop(ctx);
              },
            ),
            Divider(
                color: Theme.of(context).colorScheme.outlineVariant,
                height: 1),
            ...suppliers.entries.map(
              (e) => ListTile(
                title: Text(e.value),
                leading: Container(
                  width: 36,
                  height: 36,
                  decoration: BoxDecoration(
                    color: Theme.of(context).colorScheme.primaryContainer,
                    borderRadius:
                        BorderRadius.circular(AppSpacing.radiusSm),
                  ),
                  child: Icon(Icons.storefront,
                      size: AppSpacing.iconSm,
                      color: Theme.of(context).colorScheme.primary),
                ),
                onTap: () {
                  ref
                      .read(marketplaceSupplierFilterProvider.notifier)
                      .set(e.key);
                  Navigator.pop(ctx);
                },
              ),
            ),
            const SizedBox(height: AppSpacing.lg),
          ],
        ),
      ),
    );
  }
}

// ---------------------------------------------------------------------------
// Mahsulotlar grid (Sliver)

class _ProductsSliver extends ConsumerWidget {
  const _ProductsSliver();

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final productsState = ref.watch(productsNotifierProvider);

    return switch (productsState) {
      ProductsLoading() => SliverPadding(
          padding: const EdgeInsets.symmetric(horizontal: AppSpacing.lg),
          sliver: SliverGrid.count(
            crossAxisCount: 2,
            crossAxisSpacing: AppSpacing.sm,
            mainAxisSpacing: AppSpacing.sm,
            childAspectRatio: 0.72,
            children: List.generate(6, (_) => _ProductCardSkeleton()),
          ),
        ),
      ProductsError(:final message) => SliverToBoxAdapter(
          child: Padding(
            padding: const EdgeInsets.all(AppSpacing.xl),
            child: EmptyState(
              icon: Icons.error_outline,
              title: 'Xatolik yuz berdi',
              message: message,
              iconColor: AppTheme.colorsOf(context).danger,
              compact: true,
            ),
          ),
        ),
      ProductsLoaded(products: final products) when products.isEmpty =>
        const SliverToBoxAdapter(
          child: Padding(
            padding: EdgeInsets.all(AppSpacing.xl),
            child: EmptyState(
              icon: Icons.search_off,
              title: 'Mahsulot topilmadi',
              message:
                  'Boshqa kalit so\'z bilan qidiring yoki filtrni tozalang',
              compact: true,
            ),
          ),
        ),
      ProductsLoaded(:final products) => SliverPadding(
          padding: const EdgeInsets.symmetric(horizontal: AppSpacing.lg),
          sliver: SliverGrid.count(
            crossAxisCount: 2,
            crossAxisSpacing: AppSpacing.sm,
            mainAxisSpacing: AppSpacing.sm,
            childAspectRatio: 0.72,
            children: products
                .map((p) => _ProductCard(product: p))
                .toList(),
          ),
        ),
    };
  }
}

class _ProductCardSkeleton extends StatelessWidget {
  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    final base = cs.surfaceContainerHighest;

    Widget block(double w, double h) => Container(
          width: w,
          height: h,
          decoration: BoxDecoration(
            color: base,
            borderRadius: BorderRadius.circular(AppSpacing.radiusSm),
          ),
        );

    return AppCard(
      padding: const EdgeInsets.all(AppSpacing.md),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Container(
            height: 80,
            decoration: BoxDecoration(
              color: base,
              borderRadius: BorderRadius.circular(AppSpacing.radiusSm),
            ),
          ),
          const SizedBox(height: AppSpacing.sm),
          block(double.infinity, 16),
          const SizedBox(height: AppSpacing.xs),
          block(100, 12),
          const SizedBox(height: AppSpacing.sm),
          block(80, 14),
          const Spacer(),
          block(double.infinity, 36),
        ],
      ),
    );
  }
}

class _ProductCard extends ConsumerWidget {
  const _ProductCard({required this.product});
  final MarketplaceProduct product;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final cs = Theme.of(context).colorScheme;
    final tt = Theme.of(context).textTheme;
    final cartState = ref.watch(marketplaceCartProvider);
    final inCart =
        cartState.items.any((e) => e.product.id == product.id);

    return AppCard(
      padding: EdgeInsets.zero,
      onTap: inCart
          ? () => context.go('/home/marketplace/cart')
          : null,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // Mahsulot "rasm" zone
          Container(
            height: 86,
            decoration: BoxDecoration(
              color: inCart
                  ? AppTheme.colorsOf(context)
                      .successContainer
                      .withValues(alpha: 0.5)
                  : cs.primaryContainer.withValues(alpha: 0.5),
              borderRadius: const BorderRadius.vertical(
                top: Radius.circular(AppSpacing.radiusLg),
              ),
            ),
            child: Stack(
              children: [
                if (product.imageUrl != null)
                  ClipRRect(
                    borderRadius: const BorderRadius.vertical(
                      top: Radius.circular(AppSpacing.radiusLg),
                    ),
                    child: Image.network(
                      product.imageUrl!,
                      width: double.infinity,
                      height: 86,
                      fit: BoxFit.cover,
                      errorBuilder: (_, __, ___) =>
                          _ProductIcon(product: product, inCart: inCart),
                    ),
                  )
                else
                  _ProductIcon(product: product, inCart: inCart),

                // inCart indicator
                if (inCart)
                  Positioned(
                    top: AppSpacing.xs,
                    right: AppSpacing.xs,
                    child: Container(
                      padding: const EdgeInsets.all(3),
                      decoration: BoxDecoration(
                        color: AppTheme.colorsOf(context).success,
                        shape: BoxShape.circle,
                      ),
                      child: Icon(Icons.check,
                          size: 10,
                          color:
                              AppTheme.colorsOf(context).onSuccess),
                    ),
                  ),
              ],
            ),
          ),

          // Matn + tugma
          Expanded(
            child: Padding(
              padding: const EdgeInsets.all(AppSpacing.sm),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    product.name,
                    style: tt.labelLarge?.copyWith(
                      fontWeight: FontWeight.w600,
                    ),
                    maxLines: 2,
                    overflow: TextOverflow.ellipsis,
                  ),
                  const SizedBox(height: AppSpacing.xs),
                  Text(
                    product.supplierEnterpriseName,
                    style: tt.labelSmall?.copyWith(
                      color: cs.onSurfaceVariant,
                    ),
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                  ),
                  const Spacer(),
                  // Narx
                  Text(
                    '${_fmtPrice(product.price)} so\'m',
                    style: tt.labelLarge?.copyWith(
                      fontWeight: FontWeight.w700,
                      color: cs.primary,
                    ),
                  ),
                  Text(
                    product.unit,
                    style: tt.labelSmall?.copyWith(
                      color: cs.onSurfaceVariant,
                    ),
                  ),
                  const SizedBox(height: AppSpacing.sm),
                  // Tugma
                  _ProductCardButton(product: product, inCart: inCart),
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }

  String _fmtPrice(double v) {
    if (v >= 1000000) return '${(v / 1000000).toStringAsFixed(1)} mln';
    if (v >= 1000) return '${(v / 1000).toStringAsFixed(0)} ming';
    return v.toStringAsFixed(0);
  }
}

class _ProductIcon extends StatelessWidget {
  const _ProductIcon({required this.product, required this.inCart});
  final MarketplaceProduct product;
  final bool inCart;

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    final appColors = AppTheme.colorsOf(context);
    return Center(
      child: Icon(
        Icons.inventory_2_outlined,
        size: AppSpacing.iconXl,
        color: inCart
            ? appColors.success.withValues(alpha: 0.6)
            : cs.primary.withValues(alpha: 0.5),
      ),
    );
  }
}

class _ProductCardButton extends ConsumerWidget {
  const _ProductCardButton({
    required this.product,
    required this.inCart,
  });
  final MarketplaceProduct product;
  final bool inCart;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final appColors = AppTheme.colorsOf(context);

    if (inCart) {
      return SizedBox(
        width: double.infinity,
        child: FilledButton.icon(
          style: FilledButton.styleFrom(
            backgroundColor: appColors.success,
            foregroundColor: appColors.onSuccess,
            padding: const EdgeInsets.symmetric(
              horizontal: AppSpacing.sm,
              vertical: AppSpacing.xs,
            ),
            minimumSize: const Size(0, 32),
          ),
          onPressed: () => context.go('/home/marketplace/cart'),
          icon: const Icon(Icons.shopping_cart, size: AppSpacing.iconSm),
          label: const Text('Savatda'),
        ),
      );
    }

    return SizedBox(
      width: double.infinity,
      child: FilledButton(
        style: FilledButton.styleFrom(
          padding: const EdgeInsets.symmetric(
            horizontal: AppSpacing.sm,
            vertical: AppSpacing.xs,
          ),
          minimumSize: const Size(0, 32),
        ),
        onPressed: () => _addToCart(context, ref),
        child: const Text('Savatga'),
      ),
    );
  }

  void _addToCart(BuildContext context, WidgetRef ref) {
    ref.read(marketplaceCartProvider.notifier).addItem(product);
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text('${product.name} savatga qo\'shildi'),
        duration: const Duration(seconds: 2),
        behavior: SnackBarBehavior.floating,
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(AppSpacing.radiusMd),
        ),
        action: SnackBarAction(
          label: 'Savat',
          onPressed: () => context.go('/home/marketplace/cart'),
        ),
      ),
    );
  }
}
