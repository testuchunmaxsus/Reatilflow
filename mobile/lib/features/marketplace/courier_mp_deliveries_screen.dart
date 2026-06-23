import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../delivery/proof_photo_service.dart';
import 'marketplace_models.dart';
import 'marketplace_providers.dart';

/// Kuryer Marketplace Yetkazish ekrani.
///
/// Kuryer roli + marketplace moduli yoqilganda ko'rinadi.
/// GET /marketplace/orders/deliveries — o'ziga tayinlangan yetkazishlar.
///
/// Har yetkazish uchun:
///   - Do'kon manzili, mahsulotlar ro'yxati
///   - Rasm olish → "Yetkazdim" → POST /marketplace/orders/{id}/proof-photo
class CourierMpDeliveriesScreen extends ConsumerWidget {
  const CourierMpDeliveriesScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final state = ref.watch(courierDeliveriesProvider);

    return Scaffold(
      appBar: AppBar(
        title: const Text('Marketplace Yetkazish'),
        actions: [
          IconButton(
            icon: const Icon(Icons.refresh),
            onPressed: () =>
                ref.read(courierDeliveriesProvider.notifier).load(),
          ),
        ],
      ),
      body: switch (state) {
        CourierDeliveriesLoading() =>
          const Center(child: CircularProgressIndicator()),
        CourierDeliveriesError(:final message) => _ErrorBody(
            message: message,
            onRetry: () =>
                ref.read(courierDeliveriesProvider.notifier).load(),
          ),
        CourierDeliveriesLoaded(orders: final orders) when orders.isEmpty =>
          const _EmptyDeliveries(),
        CourierDeliveriesLoaded(:final orders) => RefreshIndicator(
            onRefresh: () =>
                ref.read(courierDeliveriesProvider.notifier).load(),
            child: ListView.builder(
              padding: const EdgeInsets.all(12),
              itemCount: orders.length,
              itemBuilder: (context, i) =>
                  _DeliveryCard(order: orders[i]),
            ),
          ),
      },
    );
  }
}

// ---------------------------------------------------------------------------

class _ErrorBody extends StatelessWidget {
  const _ErrorBody({required this.message, required this.onRetry});
  final String message;
  final VoidCallback onRetry;

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(24),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            const Icon(Icons.error_outline, color: Colors.red, size: 40),
            const SizedBox(height: 8),
            Text('Xatolik: $message', textAlign: TextAlign.center),
            const SizedBox(height: 12),
            FilledButton(
              onPressed: onRetry,
              child: const Text('Qayta urinish'),
            ),
          ],
        ),
      ),
    );
  }
}

class _EmptyDeliveries extends StatelessWidget {
  const _EmptyDeliveries();

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(Icons.local_shipping_outlined,
              size: 64, color: Colors.grey.shade300),
          const SizedBox(height: 12),
          Text(
            'Marketplace yetkazishlar yo\'q',
            style: Theme.of(context)
                .textTheme
                .titleMedium
                ?.copyWith(color: Colors.grey),
          ),
          const SizedBox(height: 8),
          const Text(
            'Sizga tayinlangan marketplace buyurtmalar bu yerda ko\'rinadi.',
            style: TextStyle(color: Colors.grey, fontSize: 13),
            textAlign: TextAlign.center,
          ),
        ],
      ),
    );
  }
}

// ---------------------------------------------------------------------------

class _DeliveryCard extends StatelessWidget {
  const _DeliveryCard({required this.order});
  final MarketplaceOrder order;

  @override
  Widget build(BuildContext context) {
    return Card(
      margin: const EdgeInsets.only(bottom: 10),
      child: InkWell(
        borderRadius: BorderRadius.circular(12),
        onTap: () =>
            context.push('/home/courier/mp-deliveries/${order.id}'),
        child: Padding(
          padding: const EdgeInsets.all(14),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              // Buyurtma ID + holat badge
              Row(
                children: [
                  Container(
                    padding: const EdgeInsets.symmetric(
                        horizontal: 8, vertical: 3),
                    decoration: BoxDecoration(
                      color: const Color(0xFF8B5CF6).withValues(alpha: 0.12),
                      borderRadius: BorderRadius.circular(8),
                    ),
                    child: const Row(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        Icon(Icons.local_shipping,
                            size: 13,
                            color: Color(0xFF8B5CF6)),
                        SizedBox(width: 4),
                        Text(
                          'Yetkazilmoqda',
                          style: TextStyle(
                            fontSize: 11,
                            fontWeight: FontWeight.w600,
                            color: Color(0xFF8B5CF6),
                          ),
                        ),
                      ],
                    ),
                  ),
                  const Spacer(),
                  Text(
                    '#${order.id.substring(0, 8)}',
                    style: const TextStyle(
                        fontSize: 11, color: Colors.grey),
                  ),
                ],
              ),

              const SizedBox(height: 8),

              // Supplier nomi
              Row(
                children: [
                  const Icon(Icons.storefront,
                      size: 14, color: Colors.grey),
                  const SizedBox(width: 4),
                  Expanded(
                    child: Text(
                      order.supplierEnterpriseName,
                      style: const TextStyle(
                          fontWeight: FontWeight.w500, fontSize: 13),
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                    ),
                  ),
                ],
              ),

              const SizedBox(height: 6),

              // Mahsulotlar (qisqacha)
              Text(
                '${order.lines.length} ta mahsulot'
                '${order.totalAmount != null ? ' — ${order.totalAmount!.toStringAsFixed(0)} so\'m' : ''}',
                style: TextStyle(
                    fontSize: 12, color: Colors.grey.shade600),
              ),

              if (order.lines.isNotEmpty)
                Text(
                  order.lines
                      .take(2)
                      .map((l) => l.productName)
                      .join(', '),
                  style: TextStyle(
                      fontSize: 11, color: Colors.grey.shade500),
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                ),

              const SizedBox(height: 8),

              // Yetkazish tugmasi
              Row(
                mainAxisAlignment: MainAxisAlignment.end,
                children: [
                  FilledButton.icon(
                    style: FilledButton.styleFrom(
                      padding: const EdgeInsets.symmetric(
                          horizontal: 14, vertical: 8),
                      minimumSize: Size.zero,
                    ),
                    onPressed: () => context.push(
                      '/home/courier/mp-deliveries/${order.id}',
                    ),
                    icon: const Icon(Icons.camera_alt, size: 16),
                    label: const Text(
                      'Yetkazdim',
                      style: TextStyle(fontSize: 13),
                    ),
                  ),
                ],
              ),
            ],
          ),
        ),
      ),
    );
  }
}

// ===========================================================================
// Yetkazish detal + proof-photo ekrani

/// Kuryer bitta marketplace buyurtmasini yetkazish ekrani.
///
/// - Buyurtma ma'lumotlari (do'kon, mahsulotlar)
/// - Rasm olish/tanlash (image_picker)
/// - "Yetkazdim" → POST /marketplace/orders/{id}/proof-photo
class CourierMpDeliveryDetailScreen extends ConsumerStatefulWidget {
  const CourierMpDeliveryDetailScreen({
    super.key,
    required this.orderId,
  });

  final String orderId;

  @override
  ConsumerState<CourierMpDeliveryDetailScreen> createState() =>
      _CourierMpDeliveryDetailScreenState();
}

class _CourierMpDeliveryDetailScreenState
    extends ConsumerState<CourierMpDeliveryDetailScreen> {
  File? _selectedImage;
  final _proofService = ImagePickerProofPhotoService();

  @override
  Widget build(BuildContext context) {
    final orderAsync =
        ref.watch(marketplaceOrderDetailProvider(widget.orderId));
    final deliverState =
        ref.watch(marketplaceDeliverProvider(widget.orderId));

    // Muvaffaqiyat / xatolik kuzatuvchi
    ref.listen(
      marketplaceDeliverProvider(widget.orderId),
      (_, next) {
        if (next is MarketplaceDeliverSuccess) {
          ScaffoldMessenger.of(context).showSnackBar(
            const SnackBar(
              content: Text('Yetkazildi! Buyurtma tasdiqlandi.'),
              backgroundColor: Colors.green,
            ),
          );
          // Ro'yxatni yangilab orqaga qaytamiz
          ref.read(courierDeliveriesProvider.notifier).load();
          context.pop();
        }
        if (next is MarketplaceDeliverFailure) {
          ScaffoldMessenger.of(context).showSnackBar(
            SnackBar(
              content: Text('Xatolik: ${next.message}'),
              backgroundColor: Colors.red,
            ),
          );
        }
      },
    );

    return Scaffold(
      appBar: AppBar(
        title: const Text('Yetkazishni tasdiqlash'),
      ),
      body: orderAsync.when(
        loading: () =>
            const Center(child: CircularProgressIndicator()),
        error: (e, _) => Center(
          child: Text('Xatolik: $e',
              style: const TextStyle(color: Colors.red)),
        ),
        data: (order) => _DetailBody(
          order: order,
          selectedImage: _selectedImage,
          deliverState: deliverState,
          onPickCamera: _pickCamera,
          onPickGallery: _pickGallery,
          onDeliver: _deliver,
        ),
      ),
    );
  }

  Future<void> _pickCamera() async {
    final file = await _proofService.takePhoto();
    if (file != null) setState(() => _selectedImage = file);
  }

  Future<void> _pickGallery() async {
    final file = await _proofService.pickFromGallery();
    if (file != null) setState(() => _selectedImage = file);
  }

  Future<void> _deliver() async {
    final image = _selectedImage;
    if (image == null) return;
    await ref
        .read(marketplaceDeliverProvider(widget.orderId).notifier)
        .deliver(orderId: widget.orderId, imageFile: image);
  }
}

// ---------------------------------------------------------------------------

class _DetailBody extends StatelessWidget {
  const _DetailBody({
    required this.order,
    required this.selectedImage,
    required this.deliverState,
    required this.onPickCamera,
    required this.onPickGallery,
    required this.onDeliver,
  });

  final MarketplaceOrder order;
  final File? selectedImage;
  final MarketplaceDeliverState deliverState;
  final VoidCallback onPickCamera;
  final VoidCallback onPickGallery;
  final VoidCallback onDeliver;

  @override
  Widget build(BuildContext context) {
    final isLoading = deliverState is MarketplaceDeliverLoading;

    return SingleChildScrollView(
      padding: const EdgeInsets.all(16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // Buyurtma ma'lumot kartasi
          _OrderInfoCard(order: order),
          const SizedBox(height: 16),

          // Mahsulotlar ro'yxati
          _LinesCard(lines: order.lines),
          const SizedBox(height: 16),

          // Proof rasm
          Text(
            'Yetkazish isboti rasmi *',
            style: Theme.of(context)
                .textTheme
                .titleSmall
                ?.copyWith(fontWeight: FontWeight.bold),
          ),
          const SizedBox(height: 8),
          _ProofPhotoSection(
            selectedImage: selectedImage,
            onPickCamera: onPickCamera,
            onPickGallery: onPickGallery,
          ),
          const SizedBox(height: 20),

          // Yetkazdim tugmasi
          SizedBox(
            width: double.infinity,
            child: FilledButton.icon(
              style: FilledButton.styleFrom(
                backgroundColor: Colors.green,
                padding:
                    const EdgeInsets.symmetric(vertical: 14),
              ),
              onPressed: (selectedImage == null || isLoading)
                  ? null
                  : onDeliver,
              icon: isLoading
                  ? const SizedBox(
                      width: 18,
                      height: 18,
                      child: CircularProgressIndicator(
                          strokeWidth: 2, color: Colors.white),
                    )
                  : const Icon(Icons.check_circle_outline),
              label: Text(
                isLoading ? 'Yuborilmoqda...' : 'Yetkazdim',
                style: const TextStyle(fontSize: 16),
              ),
            ),
          ),

          if (selectedImage == null)
            Padding(
              padding: const EdgeInsets.only(top: 8),
              child: Text(
                'Isboti uchun rasm oling.',
                style: TextStyle(
                    color: Colors.orange.shade700, fontSize: 12),
                textAlign: TextAlign.center,
              ),
            ),

          const SizedBox(height: 24),
        ],
      ),
    );
  }
}

// ---------------------------------------------------------------------------

class _OrderInfoCard extends StatelessWidget {
  const _OrderInfoCard({required this.order});
  final MarketplaceOrder order;

  @override
  Widget build(BuildContext context) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(14),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              'Buyurtma',
              style: Theme.of(context)
                  .textTheme
                  .titleSmall
                  ?.copyWith(fontWeight: FontWeight.bold),
            ),
            const Divider(height: 12),
            _InfoRow(
              icon: Icons.tag,
              label: 'ID',
              value: '#${order.id.substring(0, 8)}',
            ),
            _InfoRow(
              icon: Icons.storefront,
              label: 'Supplier',
              value: order.supplierEnterpriseName,
            ),
            if (order.totalAmount != null)
              _InfoRow(
                icon: Icons.monetization_on_outlined,
                label: 'Summa',
                value:
                    '${order.totalAmount!.toStringAsFixed(0)} so\'m',
              ),
          ],
        ),
      ),
    );
  }
}

class _InfoRow extends StatelessWidget {
  const _InfoRow({
    required this.icon,
    required this.label,
    required this.value,
  });
  final IconData icon;
  final String label;
  final String value;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 4),
      child: Row(
        children: [
          Icon(icon, size: 15, color: Colors.grey),
          const SizedBox(width: 8),
          SizedBox(
            width: 64,
            child: Text(
              label,
              style: const TextStyle(fontSize: 12, color: Colors.grey),
            ),
          ),
          Expanded(
            child: Text(value, style: const TextStyle(fontSize: 13)),
          ),
        ],
      ),
    );
  }
}

// ---------------------------------------------------------------------------

class _LinesCard extends StatelessWidget {
  const _LinesCard({required this.lines});
  final List<MarketplaceOrderLine> lines;

  @override
  Widget build(BuildContext context) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(14),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              'Mahsulotlar (${lines.length} ta)',
              style: Theme.of(context)
                  .textTheme
                  .titleSmall
                  ?.copyWith(fontWeight: FontWeight.bold),
            ),
            const Divider(height: 12),
            ...lines.map(
              (line) => Padding(
                padding:
                    const EdgeInsets.symmetric(vertical: 4),
                child: Row(
                  children: [
                    const Icon(Icons.inventory_2_outlined,
                        size: 14, color: Colors.blue),
                    const SizedBox(width: 8),
                    Expanded(
                      child: Text(
                        line.productName,
                        style: const TextStyle(fontSize: 13),
                      ),
                    ),
                    Text(
                      'x${line.qty.toStringAsFixed(line.qty % 1 == 0 ? 0 : 1)}',
                      style: TextStyle(
                          fontSize: 12,
                          color: Colors.grey.shade600),
                    ),
                  ],
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

// ---------------------------------------------------------------------------

class _ProofPhotoSection extends StatelessWidget {
  const _ProofPhotoSection({
    required this.selectedImage,
    required this.onPickCamera,
    required this.onPickGallery,
  });

  final File? selectedImage;
  final VoidCallback onPickCamera;
  final VoidCallback onPickGallery;

  @override
  Widget build(BuildContext context) {
    return Column(
      children: [
        // Tanlangan rasm ko'rinishi
        if (selectedImage != null) ...[
          ClipRRect(
            borderRadius: BorderRadius.circular(10),
            child: Image.file(
              selectedImage!,
              height: 200,
              width: double.infinity,
              fit: BoxFit.cover,
            ),
          ),
          const SizedBox(height: 10),
        ] else
          Container(
            height: 120,
            width: double.infinity,
            decoration: BoxDecoration(
              color: Colors.grey.shade100,
              borderRadius: BorderRadius.circular(10),
              border: Border.all(color: Colors.grey.shade300),
            ),
            child: Column(
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                Icon(Icons.photo_camera_outlined,
                    size: 40, color: Colors.grey.shade400),
                const SizedBox(height: 6),
                Text(
                  'Rasm olinmadi',
                  style: TextStyle(
                      color: Colors.grey.shade500, fontSize: 13),
                ),
              ],
            ),
          ),

        const SizedBox(height: 10),

        // Tugmalar
        Row(
          children: [
            Expanded(
              child: OutlinedButton.icon(
                onPressed: onPickCamera,
                icon: const Icon(Icons.camera_alt, size: 18),
                label: const Text('Kamera'),
              ),
            ),
            const SizedBox(width: 10),
            Expanded(
              child: OutlinedButton.icon(
                onPressed: onPickGallery,
                icon: const Icon(Icons.photo_library, size: 18),
                label: const Text('Galereya'),
              ),
            ),
          ],
        ),
      ],
    );
  }
}
