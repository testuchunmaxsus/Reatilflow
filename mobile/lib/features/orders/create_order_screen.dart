import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/theme/app_spacing.dart';
import '../../core/theme/app_theme.dart';
import '../../core/widgets/widgets.dart';
import '../../data/local/database.dart';
import '../auth/auth_providers.dart';
import '../auth/auth_repository.dart';
import '../catalog/catalog_providers.dart';
import '../stores/stores_providers.dart';
import 'order_repository.dart';
import 'orders_providers.dart';

/// Buyurtma yaratish ekrani.
///
/// Qoida (T11 narx himoyasi):
///   - Foydalanuvchi FAQAT mahsulot va miqdor kiritadi.
///   - Narx/discount KIRITILMAYDI — server hisoblaydi.
///   - Lokal unitPrice = 0 (faqat ko'rsatish placeholder).
///   - Buyurtma offline saqlanadi → outbox → sync → server narxni hisoblaydi.
class CreateOrderScreen extends ConsumerStatefulWidget {
  const CreateOrderScreen({super.key, this.preselectedStoreId});
  final String? preselectedStoreId;

  @override
  ConsumerState<CreateOrderScreen> createState() => _CreateOrderScreenState();
}

class _CreateOrderScreenState extends ConsumerState<CreateOrderScreen> {
  Store? _selectedStore;
  final List<_LineItem> _lines = [];
  String _mode = 'bozor';

  @override
  void initState() {
    super.initState();
    if (widget.preselectedStoreId != null) {
      _loadPreselectedStore(widget.preselectedStoreId!);
    }
  }

  Future<void> _loadPreselectedStore(String id) async {
    final dao = ref.read(storesDaoProvider);
    final store = await dao.getById(id);
    if (mounted && store != null) {
      setState(() => _selectedStore = store);
    }
  }

  void _addLine(Product product) {
    setState(() {
      final existing = _lines.indexWhere((l) => l.product.id == product.id);
      if (existing >= 0) {
        _lines[existing] =
            _lines[existing].copyWith(qty: _lines[existing].qty + 1);
      } else {
        _lines.add(_LineItem(product: product, qty: 1));
      }
    });
  }

  void _removeLine(int index) {
    setState(() => _lines.removeAt(index));
  }

  void _updateQty(int index, double qty) {
    if (qty <= 0) {
      _removeLine(index);
      return;
    }
    setState(() => _lines[index] = _lines[index].copyWith(qty: qty));
  }

  Future<void> _submit() async {
    final authState = ref.read(authNotifierProvider);
    final user = switch (authState) {
      AuthStateAuthenticated(:final user) => user,
      _ => null,
    };

    if (user == null || _selectedStore == null || _lines.isEmpty) return;

    final orderLines = _lines
        .map((l) => OrderLineInput(productId: l.product.id, qty: l.qty))
        .toList();

    await ref.read(createOrderProvider.notifier).createOrder(
          storeId: _selectedStore!.id,
          agentId: user.id,
          lines: orderLines,
          mode: _mode,
        );
  }

  @override
  Widget build(BuildContext context) {
    final createState = ref.watch(createOrderProvider);
    final cs = Theme.of(context).colorScheme;
    final appColors = AppTheme.colorsOf(context);

    ref.listen(createOrderProvider, (_, next) {
      if (next is CreateOrderSuccess) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content:
                const Text('Buyurtma saqlandi (offline). Sync qilinadi.'),
            backgroundColor: appColors.success,
          ),
        );
        Navigator.of(context).pop();
      } else if (next is CreateOrderFailure) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text('Xatolik: ${next.error}'),
            backgroundColor: cs.error,
          ),
        );
      }
    });

    final isLoading = createState is CreateOrderLoading;

    return Scaffold(
      appBar: AppBar(
        title: const Text('Buyurtma yaratish'),
        actions: [
          if (!isLoading)
            TextButton(
              onPressed:
                  (_selectedStore != null && _lines.isNotEmpty) ? _submit : null,
              child: const Text('Saqlash'),
            ),
          if (isLoading)
            Padding(
              padding: const EdgeInsets.all(AppSpacing.md),
              child: SizedBox(
                width: 20,
                height: 20,
                child: CircularProgressIndicator(
                    strokeWidth: 2, color: cs.primary),
              ),
            ),
        ],
      ),
      body: SingleChildScrollView(
        padding: const EdgeInsets.all(AppSpacing.lg),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            // T11 narx himoyasi eslatmasi
            AppCard(
              color: appColors.infoContainer.withValues(alpha: 0.3),
              borderColor: appColors.info.withValues(alpha: 0.3),
              padding: const EdgeInsets.all(AppSpacing.md),
              child: Row(
                children: [
                  Icon(Icons.info_outline,
                      color: appColors.info, size: AppSpacing.iconSm),
                  const SizedBox(width: AppSpacing.sm),
                  Expanded(
                    child: Text(
                      'Narx server tomonida hisoblanadi. '
                      'Faqat mahsulot va miqdor kiriting.',
                      style: Theme.of(context).textTheme.bodySmall?.copyWith(
                            color: appColors.info,
                          ),
                    ),
                  ),
                ],
              ),
            ),

            const SizedBox(height: AppSpacing.lg),

            // Do'kon tanlash
            const SectionHeader(title: "Do'kon"),
            const SizedBox(height: AppSpacing.sm),
            _StoreSelector(
              selected: _selectedStore,
              onSelected: (s) => setState(() => _selectedStore = s),
            ),

            const SizedBox(height: AppSpacing.lg),

            // Buyurtma turi
            const SectionHeader(title: 'Tur'),
            const SizedBox(height: AppSpacing.sm),
            SegmentedButton<String>(
              segments: const [
                ButtonSegment(value: 'bozor', label: Text('Bozor')),
                ButtonSegment(value: 'oddiy', label: Text('Oddiy')),
              ],
              selected: {_mode},
              onSelectionChanged: (s) => setState(() => _mode = s.first),
            ),

            const SizedBox(height: AppSpacing.lg),

            // Mahsulotlar qo'shish
            SectionHeader(
              title: 'Mahsulotlar',
              actionLabel: "Qo'shish",
              onAction: () => _showProductPicker(context),
            ),
            const SizedBox(height: AppSpacing.sm),

            if (_lines.isEmpty)
              Padding(
                padding: const EdgeInsets.symmetric(vertical: AppSpacing.lg),
                child: EmptyState(
                  icon: Icons.inventory_2_outlined,
                  title: "Mahsulot qo'shing",
                  message: "Yuqoridagi \"Qo'shish\" tugmasini bosing.",
                  compact: true,
                ),
              )
            else
              Column(
                children: List.generate(
                  _lines.length,
                  (i) => _LineRow(
                    line: _lines[i],
                    onRemove: () => _removeLine(i),
                    onQtyChanged: (qty) => _updateQty(i, qty),
                  ),
                ),
              ),

            if (_lines.isNotEmpty) ...[
              const SizedBox(height: AppSpacing.sm),
              Align(
                alignment: Alignment.centerRight,
                child: Text(
                  'Jami: ${_lines.length} tur mahsulot',
                  style: Theme.of(context).textTheme.labelMedium?.copyWith(
                        color: cs.onSurfaceVariant,
                        fontWeight: FontWeight.w600,
                      ),
                ),
              ),
            ],

            const SizedBox(height: 88),
          ],
        ),
      ),
      floatingActionButton: (_selectedStore != null && _lines.isNotEmpty)
          ? FloatingActionButton.extended(
              onPressed: isLoading ? null : _submit,
              icon: const Icon(Icons.save_outlined),
              label: const Text('Saqlash (offline)'),
            )
          : null,
    );
  }

  Future<void> _showProductPicker(BuildContext context) async {
    final product = await showModalBottomSheet<Product>(
      context: context,
      isScrollControlled: true,
      builder: (_) => const _ProductPickerSheet(),
    );
    if (product != null) _addLine(product);
  }
}

// ---------------------------------------------------------------------------

class _StoreSelector extends ConsumerWidget {
  const _StoreSelector({required this.selected, required this.onSelected});
  final Store? selected;
  final ValueChanged<Store> onSelected;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final cs = Theme.of(context).colorScheme;
    final tt = Theme.of(context).textTheme;

    if (selected != null) {
      return AppCard(
        padding: const EdgeInsets.all(AppSpacing.lg),
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
                  Text(selected!.name,
                      style: tt.titleSmall
                          ?.copyWith(fontWeight: FontWeight.w600)),
                  if (selected!.address != null)
                    Text(selected!.address!,
                        style: tt.bodySmall
                            ?.copyWith(color: cs.onSurfaceVariant)),
                ],
              ),
            ),
            TextButton(
              onPressed: () => _showStorePicker(context, ref),
              child: const Text("O'zgartirish"),
            ),
          ],
        ),
      );
    }

    return SizedBox(
      width: double.infinity,
      child: OutlinedButton.icon(
        onPressed: () => _showStorePicker(context, ref),
        icon: const Icon(Icons.store_outlined),
        label: const Text("Do'kon tanlang"),
      ),
    );
  }

  Future<void> _showStorePicker(BuildContext context, WidgetRef ref) async {
    final store = await showModalBottomSheet<Store>(
      context: context,
      isScrollControlled: true,
      builder: (_) => const _StorePickerSheet(),
    );
    if (store != null) onSelected(store);
  }
}

class _StorePickerSheet extends ConsumerWidget {
  const _StorePickerSheet();

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final storesAsync = ref.watch(storesStreamProvider);
    final cs = Theme.of(context).colorScheme;

    return DraggableScrollableSheet(
      initialChildSize: 0.7,
      maxChildSize: 0.9,
      minChildSize: 0.4,
      expand: false,
      builder: (_, controller) => Column(
        children: [
          Padding(
            padding: const EdgeInsets.all(AppSpacing.lg),
            child: SectionHeader(title: "Do'kon tanlang"),
          ),
          Divider(height: 1, color: cs.outlineVariant),
          Expanded(
            child: storesAsync.when(
              data: (stores) => ListView.separated(
                controller: controller,
                padding: const EdgeInsets.all(AppSpacing.lg),
                itemCount: stores.length,
                separatorBuilder: (_, __) =>
                    const SizedBox(height: AppSpacing.sm),
                itemBuilder: (ctx, i) => AppCard(
                  padding: const EdgeInsets.symmetric(
                      horizontal: AppSpacing.lg,
                      vertical: AppSpacing.md),
                  onTap: () => Navigator.pop(ctx, stores[i]),
                  child: Row(
                    children: [
                      Icon(Icons.store_outlined,
                          color: cs.onSurfaceVariant,
                          size: AppSpacing.iconSm),
                      const SizedBox(width: AppSpacing.md),
                      Expanded(
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Text(stores[i].name,
                                style: Theme.of(context)
                                    .textTheme
                                    .titleSmall
                                    ?.copyWith(
                                        fontWeight: FontWeight.w600)),
                            if (stores[i].address != null)
                              Text(stores[i].address!,
                                  style: Theme.of(context)
                                      .textTheme
                                      .bodySmall
                                      ?.copyWith(
                                          color: cs.onSurfaceVariant)),
                          ],
                        ),
                      ),
                    ],
                  ),
                ),
              ),
              loading: () =>
                  const Center(child: CircularProgressIndicator()),
              error: (e, _) => EmptyState(
                icon: Icons.error_outline,
                title: 'Xatolik',
                message: e.toString(),
              ),
            ),
          ),
        ],
      ),
    );
  }
}

class _ProductPickerSheet extends ConsumerStatefulWidget {
  const _ProductPickerSheet();

  @override
  ConsumerState<_ProductPickerSheet> createState() =>
      _ProductPickerSheetState();
}

class _ProductPickerSheetState extends ConsumerState<_ProductPickerSheet> {
  final _controller = TextEditingController();

  @override
  void dispose() {
    _controller.dispose();
    ref.read(productSearchProvider.notifier).clear();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final productsAsync = ref.watch(filteredProductsProvider);
    final cs = Theme.of(context).colorScheme;

    return DraggableScrollableSheet(
      initialChildSize: 0.8,
      maxChildSize: 0.95,
      minChildSize: 0.5,
      expand: false,
      builder: (_, scrollCtrl) => Column(
        children: [
          Padding(
            padding: const EdgeInsets.fromLTRB(
                AppSpacing.lg, AppSpacing.lg, AppSpacing.lg, AppSpacing.sm),
            child: TextField(
              controller: _controller,
              decoration: const InputDecoration(
                hintText: 'Mahsulot qidirish...',
                prefixIcon: Icon(Icons.search_outlined),
              ),
              onChanged: ref.read(productSearchProvider.notifier).setQuery,
            ),
          ),
          Divider(height: 1, color: cs.outlineVariant),
          Expanded(
            child: productsAsync.when(
              data: (products) => products.isEmpty
                  ? const EmptyState(
                      icon: Icons.inventory_2_outlined,
                      title: 'Mahsulot topilmadi',
                      compact: true,
                    )
                  : ListView.separated(
                      controller: scrollCtrl,
                      padding: const EdgeInsets.all(AppSpacing.lg),
                      itemCount: products.length,
                      separatorBuilder: (_, __) =>
                          const SizedBox(height: AppSpacing.sm),
                      itemBuilder: (ctx, i) => AppCard(
                        padding: const EdgeInsets.symmetric(
                            horizontal: AppSpacing.lg,
                            vertical: AppSpacing.md),
                        onTap: () => Navigator.pop(ctx, products[i]),
                        child: Row(
                          children: [
                            Container(
                              width: 40,
                              height: 40,
                              decoration: BoxDecoration(
                                color: cs.surfaceContainerHighest,
                                borderRadius: BorderRadius.circular(
                                    AppSpacing.radiusSm),
                              ),
                              child: Icon(Icons.inventory_2_outlined,
                                  size: AppSpacing.iconSm,
                                  color: cs.onSurfaceVariant),
                            ),
                            const SizedBox(width: AppSpacing.md),
                            Expanded(
                              child: Column(
                                crossAxisAlignment:
                                    CrossAxisAlignment.start,
                                children: [
                                  Text(
                                    products[i].nameUz,
                                    style: Theme.of(context)
                                        .textTheme
                                        .titleSmall
                                        ?.copyWith(
                                            fontWeight: FontWeight.w600),
                                    maxLines: 1,
                                    overflow: TextOverflow.ellipsis,
                                  ),
                                  if (products[i].sku != null)
                                    Text(
                                      'SKU: ${products[i].sku!}',
                                      style: Theme.of(context)
                                          .textTheme
                                          .labelSmall
                                          ?.copyWith(
                                              color: cs.onSurfaceVariant),
                                    ),
                                ],
                              ),
                            ),
                            Text(
                              products[i].unit,
                              style: Theme.of(context)
                                  .textTheme
                                  .labelSmall
                                  ?.copyWith(color: cs.onSurfaceVariant),
                            ),
                          ],
                        ),
                      ),
                    ),
              loading: () =>
                  const Center(child: CircularProgressIndicator()),
              error: (e, _) => EmptyState(
                icon: Icons.error_outline,
                title: 'Xatolik',
                message: e.toString(),
              ),
            ),
          ),
        ],
      ),
    );
  }
}

// ---------------------------------------------------------------------------

class _LineItem {
  const _LineItem({required this.product, required this.qty});
  final Product product;
  final double qty;

  _LineItem copyWith({Product? product, double? qty}) =>
      _LineItem(product: product ?? this.product, qty: qty ?? this.qty);
}

class _LineRow extends StatelessWidget {
  const _LineRow({
    required this.line,
    required this.onRemove,
    required this.onQtyChanged,
  });
  final _LineItem line;
  final VoidCallback onRemove;
  final ValueChanged<double> onQtyChanged;

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    final tt = Theme.of(context).textTheme;

    return AppCard(
      margin: const EdgeInsets.symmetric(vertical: AppSpacing.xs),
      padding: const EdgeInsets.symmetric(
          horizontal: AppSpacing.md, vertical: AppSpacing.sm),
      child: Row(
        children: [
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  line.product.nameUz,
                  style: tt.titleSmall
                      ?.copyWith(fontWeight: FontWeight.w600),
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                ),
                Text(
                  // Narx ko'rsatilmaydi — server hisoblaydi (T11)
                  'Birlik: ${line.product.unit}  |  Narx: server',
                  style: tt.labelSmall?.copyWith(color: cs.onSurfaceVariant),
                ),
              ],
            ),
          ),
          Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              IconButton(
                icon: const Icon(Icons.remove_circle_outline),
                onPressed: () => onQtyChanged(line.qty - 1),
                iconSize: AppSpacing.iconSm,
                color: cs.onSurfaceVariant,
              ),
              SizedBox(
                width: 40,
                child: Text(
                  line.qty % 1 == 0
                      ? line.qty.toStringAsFixed(0)
                      : line.qty.toStringAsFixed(1),
                  textAlign: TextAlign.center,
                  style: tt.titleSmall
                      ?.copyWith(fontWeight: FontWeight.w700),
                ),
              ),
              IconButton(
                icon: const Icon(Icons.add_circle_outline),
                onPressed: () => onQtyChanged(line.qty + 1),
                iconSize: AppSpacing.iconSm,
                color: cs.primary,
              ),
              IconButton(
                icon: Icon(Icons.delete_outline,
                    color: cs.error),
                onPressed: onRemove,
                iconSize: AppSpacing.iconSm,
              ),
            ],
          ),
        ],
      ),
    );
  }
}
