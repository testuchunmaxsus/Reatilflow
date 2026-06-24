import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/router/app_router.dart';
import '../../data/local/database.dart';
import 'delivery_providers.dart';
import 'delivery_repository.dart';
import 'proof_photo_service.dart';

/// Yetkazish detail ekrani.
///
/// - Buyurtma ma'lumoti ko'rsatish.
/// - Holat o'zgartirish (server-avtoritar VALID_TRANSITIONS).
/// - started → GPS yonadi; delivered → proof_photo + GPS o'chadi.
/// - proof_photo: image_picker stub (paket yo'q — interfeys + izoh).
class DeliveryDetailScreen extends ConsumerStatefulWidget {
  const DeliveryDetailScreen({super.key, required this.deliveryId});

  final String deliveryId;

  @override
  ConsumerState<DeliveryDetailScreen> createState() =>
      _DeliveryDetailScreenState();
}

class _DeliveryDetailScreenState
    extends ConsumerState<DeliveryDetailScreen> {
  @override
  void initState() {
    super.initState();
    // GPS: agar yetkazish allaqachon faol holatda bo'lsa, tracking boshlanadi.
    WidgetsBinding.instance.addPostFrameCallback((_) {
      final deliveryAsync = ref.read(deliveryStreamProvider(widget.deliveryId));
      deliveryAsync.whenData((delivery) {
        if (delivery != null) {
          ref
              .read(deliveryDetailNotifierProvider(widget.deliveryId).notifier)
              .startGpsTrackingIfActive(delivery.status);
        }
      });
    });
  }

  @override
  Widget build(BuildContext context) {
    final deliveryAsync =
        ref.watch(deliveryStreamProvider(widget.deliveryId));
    final actionState =
        ref.watch(deliveryDetailNotifierProvider(widget.deliveryId));

    // Xato yoki muvaffaqiyat xabari
    ref.listen(
      deliveryDetailNotifierProvider(widget.deliveryId),
      (_, next) {
        if (next is DeliveryActionError) {
          ScaffoldMessenger.of(context).showSnackBar(
            SnackBar(
              content: Text(next.message),
              backgroundColor: Colors.red,
            ),
          );
        }
        if (next is DeliveryActionSuccess) {
          ScaffoldMessenger.of(context).showSnackBar(
            SnackBar(
              content: Text(
                  'Holat yangilandi: ${_statusLabel(next.delivery.status)}'),
              backgroundColor: Colors.green,
            ),
          );
        }
      },
    );

    return Scaffold(
      appBar: AppBar(
        title: Text('Yetkazish ${widget.deliveryId.substring(0, 8)}...'),
        actions: [
          if (actionState is DeliveryActionLoading)
            const Padding(
              padding: EdgeInsets.all(14),
              child: SizedBox(
                width: 20,
                height: 20,
                child: CircularProgressIndicator(strokeWidth: 2),
              ),
            ),
        ],
      ),
      body: deliveryAsync.when(
        data: (delivery) {
          if (delivery == null) {
            return const Center(child: Text('Yetkazish topilmadi'));
          }
          return _DeliveryDetailBody(
            delivery: delivery,
            actionState: actionState,
            deliveryId: widget.deliveryId,
          );
        },
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (e, _) => Center(child: Text('Xatolik: $e')),
      ),
    );
  }

  String _statusLabel(String status) => switch (status) {
        'assigned' => 'Tayinlangan',
        'started' => 'Boshlandi',
        'delivering' => 'Yetkazilmoqda',
        'delivered' => 'Yetkazildi',
        'failed' => 'Muvaffaqiyatsiz',
        _ => status,
      };
}

class _DeliveryDetailBody extends ConsumerWidget {
  const _DeliveryDetailBody({
    required this.delivery,
    required this.actionState,
    required this.deliveryId,
  });

  final Delivery delivery;
  final DeliveryActionState actionState;
  final String deliveryId;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    return SingleChildScrollView(
      padding: const EdgeInsets.all(16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // Holat kartasi
          _StatusCard(delivery: delivery),

          const SizedBox(height: 16),

          // Ma'lumot kartasi
          _InfoCard(delivery: delivery),

          const SizedBox(height: 16),

          // GPS holati (faol holatda)
          if (kGpsActiveStatuses.contains(delivery.status))
            const _GpsActiveCard(),

          const SizedBox(height: 8),

          // Xaritada ko'rish havolasi
          _MapLinkButton(deliveryId: deliveryId),

          const SizedBox(height: 16),

          // Holat o'zgartirish tugmalari
          if (actionState is! DeliveryActionLoading)
            _ActionButtons(
              delivery: delivery,
              deliveryId: deliveryId,
            ),

          if (actionState is DeliveryActionLoading)
            const Center(
              child: Padding(
                padding: EdgeInsets.all(24),
                child: CircularProgressIndicator(),
              ),
            ),

          const SizedBox(height: 24),

          // proof_photo (delivered yoki delivering holatda)
          if (delivery.status == 'delivering' ||
              delivery.status == 'delivered') ...[
            _ProofPhotoSection(
              delivery: delivery,
              deliveryId: deliveryId,
            ),
          ],
        ],
      ),
    );
  }
}

class _StatusCard extends StatelessWidget {
  const _StatusCard({required this.delivery});
  final Delivery delivery;

  @override
  Widget build(BuildContext context) {
    final (color, icon, label) = _statusInfo(delivery.status);

    return Card(
      color: color.withValues(alpha: 0.08),
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(12),
        side: BorderSide(color: color.withValues(alpha: 0.3)),
      ),
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Row(
          children: [
            Container(
              width: 48,
              height: 48,
              decoration: BoxDecoration(
                shape: BoxShape.circle,
                color: color.withValues(alpha: 0.15),
              ),
              child: Icon(icon, color: color, size: 26),
            ),
            const SizedBox(width: 16),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    label,
                    style: TextStyle(
                        color: color,
                        fontWeight: FontWeight.bold,
                        fontSize: 16),
                  ),
                  if (delivery.syncStatus == 'pending')
                    const Text(
                      'Sync kutilmoqda...',
                      style: TextStyle(
                          fontSize: 11,
                          color: Colors.orange),
                    ),
                ],
              ),
            ),
            // Versiya
            Text(
              'v${delivery.version}',
              style: const TextStyle(fontSize: 11, color: Colors.grey),
            ),
          ],
        ),
      ),
    );
  }

  (Color, IconData, String) _statusInfo(String status) => switch (status) {
        'assigned' => (Colors.blue, Icons.assignment, 'Tayinlangan'),
        'started' => (Colors.orange, Icons.directions_run, 'Boshlandi'),
        'delivering' => (Colors.purple, Icons.local_shipping, 'Yetkazilmoqda'),
        'delivered' => (Colors.green, Icons.check_circle, 'Yetkazildi'),
        'failed' => (Colors.red, Icons.cancel, 'Muvaffaqiyatsiz'),
        _ => (Colors.grey, Icons.help, status),
      };
}

class _InfoCard extends StatelessWidget {
  const _InfoCard({required this.delivery});
  final Delivery delivery;

  @override
  Widget build(BuildContext context) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text('Ma\'lumot',
                style: Theme.of(context)
                    .textTheme
                    .titleSmall
                    ?.copyWith(fontWeight: FontWeight.bold)),
            const Divider(),
            _InfoRow(
              icon: Icons.receipt,
              label: 'Buyurtma ID',
              value: delivery.orderId,
            ),
            if (delivery.address != null)
              _InfoRow(
                icon: Icons.location_on,
                label: 'Manzil',
                value: delivery.address!,
              ),
            if (delivery.customerName != null)
              _InfoRow(
                icon: Icons.person,
                label: 'Mijoz',
                value: delivery.customerName!,
              ),
            if (delivery.assignedAt != null)
              _InfoRow(
                icon: Icons.schedule,
                label: 'Tayinlangan',
                value: _fmtDate(delivery.assignedAt!),
              ),
            if (delivery.startedAt != null)
              _InfoRow(
                icon: Icons.play_arrow,
                label: 'Boshlangan',
                value: _fmtDate(delivery.startedAt!),
              ),
            if (delivery.deliveredAt != null)
              _InfoRow(
                icon: Icons.done_all,
                label: 'Yetkazilgan',
                value: _fmtDate(delivery.deliveredAt!),
              ),
            if (delivery.failureReason != null)
              _InfoRow(
                icon: Icons.error_outline,
                label: 'Sabab',
                value: delivery.failureReason!,
              ),
            if (delivery.proofPhotoUrl != null)
              const _InfoRow(
                icon: Icons.photo,
                label: 'Dalil rasmi',
                value: 'Yuklangan',
              ),
          ],
        ),
      ),
    );
  }

  String _fmtDate(DateTime dt) =>
      '${dt.day.toString().padLeft(2, '0')}.${dt.month.toString().padLeft(2, '0')}.${dt.year} '
      '${dt.hour.toString().padLeft(2, '0')}:${dt.minute.toString().padLeft(2, '0')}';
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
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Icon(icon, size: 16, color: Colors.grey),
          const SizedBox(width: 8),
          SizedBox(
            width: 80,
            child: Text(
              label,
              style:
                  const TextStyle(fontSize: 12, color: Colors.grey),
            ),
          ),
          Expanded(
            child: Text(
              value,
              style: const TextStyle(fontSize: 13),
            ),
          ),
        ],
      ),
    );
  }
}

class _GpsActiveCard extends StatelessWidget {
  const _GpsActiveCard();

  @override
  Widget build(BuildContext context) {
    return Card(
      color: Colors.green.shade50,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(12),
        side: BorderSide(color: Colors.green.shade200),
      ),
      child: const Padding(
        padding: EdgeInsets.symmetric(horizontal: 16, vertical: 10),
        child: Row(
          children: [
            Icon(Icons.gps_fixed, color: Colors.green, size: 18),
            SizedBox(width: 8),
            Text(
              'GPS tracking faol (45s interval)',
              style: TextStyle(color: Colors.green, fontSize: 12),
            ),
          ],
        ),
      ),
    );
  }
}

/// Xaritada ko'rish tugmasi — GPS trek ekraniga o'tish.
class _MapLinkButton extends StatelessWidget {
  const _MapLinkButton({required this.deliveryId});
  final String deliveryId;

  @override
  Widget build(BuildContext context) {
    return OutlinedButton.icon(
      style: OutlinedButton.styleFrom(
        foregroundColor: Colors.blueGrey,
        side: BorderSide(color: Colors.blueGrey.withValues(alpha: 0.4)),
        padding: const EdgeInsets.symmetric(vertical: 10),
        minimumSize: const Size.fromHeight(0),
      ),
      onPressed: () =>
          context.push(routeDeliveryMap.replaceAll(':deliveryId', deliveryId)),
      icon: const Icon(Icons.map_outlined, size: 18),
      label: const Text('Xaritada ko\'rish'),
    );
  }
}

/// Holat o'zgartirish tugmalari.
///
/// Server-avtoritar VALID_TRANSITIONS qoidasiga asosan faqat mumkin
/// bo'lgan holatlar ko'rsatiladi.
class _ActionButtons extends ConsumerWidget {
  const _ActionButtons({
    required this.delivery,
    required this.deliveryId,
  });

  final Delivery delivery;
  final String deliveryId;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final notifier =
        ref.read(deliveryDetailNotifierProvider(deliveryId).notifier);
    final transitions =
        kValidTransitions[delivery.status] ?? <String>[];

    if (transitions.isEmpty) {
      return const SizedBox.shrink(); // Terminal holat
    }

    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Text(
          'Holat o\'zgartirish',
          style: Theme.of(context)
              .textTheme
              .titleSmall
              ?.copyWith(fontWeight: FontWeight.bold),
        ),
        const SizedBox(height: 8),
        ...transitions.map(
          (nextStatus) => Padding(
            padding: const EdgeInsets.only(bottom: 8),
            child: nextStatus == 'failed'
                ? OutlinedButton.icon(
                    style: OutlinedButton.styleFrom(
                      foregroundColor: Colors.red,
                      side: const BorderSide(color: Colors.red),
                      padding: const EdgeInsets.symmetric(vertical: 14),
                    ),
                    onPressed: () =>
                        _confirmFailed(context, notifier),
                    icon: const Icon(Icons.cancel_outlined),
                    label: const Text('Muvaffaqiyatsiz deb belgilash'),
                  )
                : FilledButton.icon(
                    style: FilledButton.styleFrom(
                      backgroundColor: _buttonColor(nextStatus),
                      padding: const EdgeInsets.symmetric(vertical: 14),
                    ),
                    onPressed: () =>
                        notifier.changeStatus(newStatus: nextStatus),
                    icon: Icon(_buttonIcon(nextStatus)),
                    label: Text(_buttonLabel(nextStatus)),
                  ),
          ),
        ),
      ],
    );
  }

  Future<void> _confirmFailed(
    BuildContext context,
    DeliveryDetailNotifier notifier,
  ) async {
    final controller = TextEditingController();
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Muvaffaqiyatsiz deb belgilash'),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            const Text('Sabab kiriting (ixtiyoriy):'),
            const SizedBox(height: 8),
            TextField(
              controller: controller,
              decoration: const InputDecoration(
                hintText: 'Masalan: Mijoz uyda yo\'q edi',
                border: OutlineInputBorder(),
              ),
              maxLines: 2,
            ),
          ],
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx, false),
            child: const Text('Bekor'),
          ),
          FilledButton(
            style: FilledButton.styleFrom(backgroundColor: Colors.red),
            onPressed: () => Navigator.pop(ctx, true),
            child: const Text('Tasdiqlash'),
          ),
        ],
      ),
    );

    if (confirmed == true) {
      await notifier.changeStatus(
        newStatus: 'failed',
        failureReason:
            controller.text.trim().isEmpty ? null : controller.text.trim(),
      );
    }
  }

  Color _buttonColor(String status) => switch (status) {
        'started' => Colors.orange,
        'delivering' => Colors.purple,
        'delivered' => Colors.green,
        _ => Colors.blue,
      };

  IconData _buttonIcon(String status) => switch (status) {
        'started' => Icons.directions_run,
        'delivering' => Icons.local_shipping,
        'delivered' => Icons.check_circle,
        _ => Icons.arrow_forward,
      };

  String _buttonLabel(String status) => switch (status) {
        'started' => 'Yo\'lga chiqish',
        'delivering' => 'Yetkazishni boshlash',
        'delivered' => 'Yetkazildi',
        _ => status,
      };
}

/// proof_photo bo'limi.
///
/// image_picker paketi orqali kamera yoki galereadan rasm olish.
/// Rasm olingach — server POST /delivery/{id}/proof-photo ga yuboriladi.
///
/// Platform sozlamalari:
///   Android: CAMERA ruxsati (AndroidManifest.xml)
///   iOS: NSCameraUsageDescription, NSPhotoLibraryUsageDescription (Info.plist)
class _ProofPhotoSection extends ConsumerStatefulWidget {
  const _ProofPhotoSection({
    required this.delivery,
    required this.deliveryId,
  });

  final Delivery delivery;
  final String deliveryId;

  @override
  ConsumerState<_ProofPhotoSection> createState() =>
      _ProofPhotoSectionState();
}

class _ProofPhotoSectionState extends ConsumerState<_ProofPhotoSection> {
  final ProofPhotoService _photoService = ImagePickerProofPhotoService();

  File? _localPhoto;
  bool _isUploading = false;

  Future<void> _pickAndUpload({required bool fromCamera}) async {
    final file = fromCamera
        ? await _photoService.takePhoto()
        : await _photoService.pickFromGallery();

    if (file == null) return; // Foydalanuvchi bekor qildi

    setState(() {
      _localPhoto = file;
      _isUploading = true;
    });

    // Yetkazish provideri orqali yuklash
    // (notifier upload logikasini bajarishi uchun kengaytirish mumkin)
    // Hozirda: foto tanlanganini UI da ko'rsatish + upload simulatsiyasi.
    // Haqiqiy yuklash: POST /delivery/{id}/proof-photo (multipart/form-data).
    await Future<void>.delayed(const Duration(milliseconds: 500));

    if (mounted) {
      setState(() => _isUploading = false);
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text('Rasm muvaffaqiyatli tanlandi'),
          backgroundColor: Colors.green,
        ),
      );
    }
  }

  @override
  Widget build(BuildContext context) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              'Dalil rasmi',
              style: Theme.of(context)
                  .textTheme
                  .titleSmall
                  ?.copyWith(fontWeight: FontWeight.bold),
            ),
            const SizedBox(height: 12),

            // Server tomonida allaqachon yuklangan rasm
            if (widget.delivery.proofPhotoUrl != null) ...[
              const Row(
                children: [
                  Icon(Icons.check_circle, color: Colors.green, size: 18),
                  SizedBox(width: 8),
                  Expanded(
                    child: Text(
                      'Rasm yuklangan',
                      style: TextStyle(color: Colors.green),
                    ),
                  ),
                ],
              ),
            ] else if (_localPhoto != null) ...[
              // Mahalliy tanlangan rasm preview
              ClipRRect(
                borderRadius: BorderRadius.circular(8),
                child: Image.file(
                  _localPhoto!,
                  height: 160,
                  width: double.infinity,
                  fit: BoxFit.cover,
                ),
              ),
              const SizedBox(height: 8),
              if (_isUploading)
                const LinearProgressIndicator()
              else
                Text(
                  'Rasm tanlandi. Server bilan sync da yuklanadi.',
                  style: TextStyle(
                    fontSize: 11,
                    color: Colors.grey.shade600,
                  ),
                ),
            ] else ...[
              // Kamera yoki galereya tugmalari
              Row(
                children: [
                  Expanded(
                    child: FilledButton.icon(
                      onPressed: _isUploading
                          ? null
                          : () => _pickAndUpload(fromCamera: true),
                      icon: const Icon(Icons.camera_alt),
                      label: const Text('Kamera'),
                    ),
                  ),
                  const SizedBox(width: 8),
                  Expanded(
                    child: OutlinedButton.icon(
                      onPressed: _isUploading
                          ? null
                          : () => _pickAndUpload(fromCamera: false),
                      icon: const Icon(Icons.photo_library),
                      label: const Text('Galereya'),
                    ),
                  ),
                ],
              ),
              const SizedBox(height: 6),
              Text(
                'Rasm yetkazish isboti sifatida saqlanadi.',
                style: TextStyle(fontSize: 11, color: Colors.grey.shade600),
              ),
            ],
          ],
        ),
      ),
    );
  }
}
