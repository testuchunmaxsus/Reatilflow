import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

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
  /// [preselectedStoreId] — do'kon sahifasidan kelinsa avtomatik to'ldiriladi.
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
        _lines[existing] = _lines[existing].copyWith(qty: _lines[existing].qty + 1);
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

    // T11 narx himoyasi: faqat product_id + qty — narx YO'Q
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

    // Muvaffaqiyatli yaratilsa — orqaga qayt
    ref.listen(createOrderProvider, (_, next) {
      if (next is CreateOrderSuccess) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(
            content: Text('Buyurtma saqlandi (offline). Sync qilinadi.'),
            backgroundColor: Colors.green,
          ),
        );
        Navigator.of(context).pop();
      } else if (next is CreateOrderFailure) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text('Xatolik: ${next.error}'),
            backgroundColor: Colors.red,
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
            const Padding(
              padding: EdgeInsets.all(12),
              child: SizedBox(
                width: 20,
                height: 20,
                child: CircularProgressIndicator(strokeWidth: 2),
              ),
            ),
        ],
      ),
      body: SingleChildScrollView(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            // T11 narx himoyasi eslatmasi
            Container(
              padding: const EdgeInsets.all(10),
              decoration: BoxDecoration(
                color: Colors.blue.shade50,
                borderRadius: BorderRadius.circular(8),
                border: Border.all(color: Colors.blue.shade200),
              ),
              child: const Row(
                children: [
                  Icon(Icons.info_outline, color: Colors.blue, size: 18),
                  SizedBox(width: 8),
                  Expanded(
                    child: Text(
                      'Narx server tomonida hisoblanadi. '
                      'Faqat mahsulot va miqdor kiriting.',
                      style: TextStyle(fontSize: 12, color: Colors.blue),
                    ),
                  ),
                ],
              ),
            ),

            const SizedBox(height: 16),

            // Do'kon tanlash
            Text("Do'kon", style: Theme.of(context).textTheme.titleMedium),
            const SizedBox(height: 6),
            _StoreSelector(
              selected: _selectedStore,
              onSelected: (s) => setState(() => _selectedStore = s),
            ),

            const SizedBox(height: 16),

            // Buyurtma turi
            Text('Tur', style: Theme.of(context).textTheme.titleMedium),
            const SizedBox(height: 6),
            SegmentedButton<String>(
              segments: const [
                ButtonSegment(value: 'bozor', label: Text('Bozor')),
                ButtonSegment(value: 'oddiy', label: Text('Oddiy')),
              ],
              selected: {_mode},
              onSelectionChanged: (s) => setState(() => _mode = s.first),
            ),

            const SizedBox(height: 16),

            // Mahsulotlar qo'shish
            Row(
              children: [
                Text('Mahsulotlar',
                    style: Theme.of(context).textTheme.titleMedium),
                const Spacer(),
                TextButton.icon(
                  icon: const Icon(Icons.add),
                  label: const Text("Qo'shish"),
                  onPressed: () => _showProductPicker(context),
                ),
              ],
            ),

            // Qo'shilgan mahsulotlar
            if (_lines.isEmpty)
              const Padding(
                padding: EdgeInsets.symmetric(vertical: 12),
                child: Center(
                  child: Text(
                    'Mahsulot qo\'shing',
                    style: TextStyle(color: Colors.grey),
                  ),
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

            const SizedBox(height: 8),

            // Jami qator soni
            if (_lines.isNotEmpty)
              Align(
                alignment: Alignment.centerRight,
                child: Text(
                  'Jami: ${_lines.length} tur mahsulot',
                  style: const TextStyle(
                      fontWeight: FontWeight.w600, color: Colors.grey),
                ),
              ),

            const SizedBox(height: 80),
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
    if (selected != null) {
      return Card(
        child: ListTile(
          leading: const Icon(Icons.store),
          title: Text(selected!.name),
          subtitle: selected!.address != null ? Text(selected!.address!) : null,
          trailing: TextButton(
            child: const Text("O'zgartirish"),
            onPressed: () => _showStorePicker(context, ref),
          ),
        ),
      );
    }

    return OutlinedButton.icon(
      onPressed: () => _showStorePicker(context, ref),
      icon: const Icon(Icons.store_outlined),
      label: const Text("Do'kon tanlang"),
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
    return DraggableScrollableSheet(
      initialChildSize: 0.7,
      maxChildSize: 0.9,
      minChildSize: 0.4,
      expand: false,
      builder: (_, controller) => Column(
        children: [
          Padding(
            padding: const EdgeInsets.all(16),
            child: Text("Do'kon tanlang",
                style: Theme.of(context).textTheme.titleMedium),
          ),
          Expanded(
            child: storesAsync.when(
              data: (stores) => ListView.builder(
                controller: controller,
                itemCount: stores.length,
                itemBuilder: (ctx, i) => ListTile(
                  leading: const Icon(Icons.store),
                  title: Text(stores[i].name),
                  subtitle: stores[i].address != null
                      ? Text(stores[i].address!)
                      : null,
                  onTap: () => Navigator.pop(ctx, stores[i]),
                ),
              ),
              loading: () => const Center(child: CircularProgressIndicator()),
              error: (e, _) => Center(child: Text('Xatolik: $e')),
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
    return DraggableScrollableSheet(
      initialChildSize: 0.8,
      maxChildSize: 0.95,
      minChildSize: 0.5,
      expand: false,
      builder: (_, scrollCtrl) => Column(
        children: [
          Padding(
            padding: const EdgeInsets.fromLTRB(16, 16, 16, 8),
            child: TextField(
              controller: _controller,
              decoration: InputDecoration(
                hintText: 'Mahsulot qidirish...',
                prefixIcon: const Icon(Icons.search),
                border: OutlineInputBorder(
                    borderRadius: BorderRadius.circular(8)),
                contentPadding: const EdgeInsets.symmetric(vertical: 8),
              ),
              onChanged: ref.read(productSearchProvider.notifier).setQuery,
            ),
          ),
          Expanded(
            child: productsAsync.when(
              data: (products) => ListView.builder(
                controller: scrollCtrl,
                itemCount: products.length,
                itemBuilder: (ctx, i) => ListTile(
                  leading: const Icon(Icons.inventory_2_outlined),
                  title: Text(products[i].nameUz),
                  subtitle: products[i].sku != null
                      ? Text(products[i].sku!)
                      : null,
                  trailing: Text(products[i].unit,
                      style: const TextStyle(fontSize: 12)),
                  onTap: () => Navigator.pop(ctx, products[i]),
                ),
              ),
              loading: () => const Center(child: CircularProgressIndicator()),
              error: (e, _) => Center(child: Text('Xatolik: $e')),
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
    return Card(
      margin: const EdgeInsets.symmetric(vertical: 4),
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
        child: Row(
          children: [
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(line.product.nameUz,
                      style: const TextStyle(fontWeight: FontWeight.w600)),
                  Text(
                    // Narx ko'rsatilmaydi — server hisoblaydi (T11)
                    'Birlik: ${line.product.unit}  |  Narx: server',
                    style: const TextStyle(fontSize: 11, color: Colors.grey),
                  ),
                ],
              ),
            ),
            // Miqdor boshqaruvi
            Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                IconButton(
                  icon: const Icon(Icons.remove_circle_outline),
                  onPressed: () => onQtyChanged(line.qty - 1),
                  iconSize: 20,
                ),
                SizedBox(
                  width: 40,
                  child: Text(
                    line.qty % 1 == 0
                        ? line.qty.toStringAsFixed(0)
                        : line.qty.toStringAsFixed(1),
                    textAlign: TextAlign.center,
                    style: const TextStyle(
                        fontWeight: FontWeight.bold, fontSize: 16),
                  ),
                ),
                IconButton(
                  icon: const Icon(Icons.add_circle_outline),
                  onPressed: () => onQtyChanged(line.qty + 1),
                  iconSize: 20,
                ),
                IconButton(
                  icon: const Icon(Icons.delete_outline, color: Colors.red),
                  onPressed: onRemove,
                  iconSize: 20,
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }
}
