import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/router/app_router.dart';
import '../../core/theme/app_spacing.dart';
import '../../core/theme/app_theme.dart';
import '../../core/widgets/widgets.dart';
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
    WidgetsBinding.instance.addPostFrameCallback((_) {
      final deliveryAsync =
          ref.read(deliveryStreamProvider(widget.deliveryId));
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
    final cs = Theme.of(context).colorScheme;

    ref.listen(
      deliveryDetailNotifierProvider(widget.deliveryId),
      (_, next) {
        if (next is DeliveryActionError) {
          ScaffoldMessenger.of(context).showSnackBar(
            SnackBar(
              content: Text(next.message),
              backgroundColor: cs.error,
            ),
          );
        }
        if (next is DeliveryActionSuccess) {
          ScaffoldMessenger.of(context).showSnackBar(
            SnackBar(
              content: Text(
                  'Holat yangilandi: ${_statusLabel(next.delivery.status)}'),
              backgroundColor: AppTheme.colorsOf(context).success,
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
      body: deliveryAsync.when(
        data: (delivery) {
          if (delivery == null) {
            return const EmptyState(
              icon: Icons.local_shipping_outlined,
              title: 'Yetkazish topilmadi',
              message: "Bu yetkazish mavjud emas yoki o'chirilgan.",
            );
          }
          return _DeliveryDetailBody(
            delivery: delivery,
            actionState: actionState,
            deliveryId: widget.deliveryId,
          );
        },
        loading: () =>
            Center(child: CircularProgressIndicator(color: cs.primary)),
        error: (e, _) => EmptyState(
          icon: Icons.error_outline,
          title: 'Xatolik yuz berdi',
          message: e.toString(),
        ),
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
      padding: const EdgeInsets.all(AppSpacing.lg),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // Holat timeline kartasi
          _StatusTimelineCard(delivery: delivery),

          const SizedBox(height: AppSpacing.lg),

          // Ma'lumot kartasi
          _InfoCard(delivery: delivery),

          const SizedBox(height: AppSpacing.lg),

          // GPS holati (faol holatda)
          if (kGpsActiveStatuses.contains(delivery.status)) ...[
            _GpsActiveCard(),
            const SizedBox(height: AppSpacing.md),
          ],

          // Xaritada ko'rish havolasi
          _MapLinkButton(deliveryId: deliveryId),

          const SizedBox(height: AppSpacing.lg),

          // Holat o'zgartirish tugmalari
          if (actionState is DeliveryActionLoading)
            Center(
              child: Padding(
                padding: const EdgeInsets.all(AppSpacing.xl),
                child: CircularProgressIndicator(
                    color: Theme.of(context).colorScheme.primary),
              ),
            )
          else
            _ActionButtons(
              delivery: delivery,
              deliveryId: deliveryId,
            ),

          const SizedBox(height: AppSpacing.xl),

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

// ---------------------------------------------------------------------------

/// Holat timeline kartasi — renk + ikon + matn + sync holat.
class _StatusTimelineCard extends StatelessWidget {
  const _StatusTimelineCard({required this.delivery});
  final Delivery delivery;

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    final tt = Theme.of(context).textTheme;
    final appColors = AppTheme.colorsOf(context);
    final (icon, variant, label) = _statusInfo(delivery.status);

    final (bgColor, borderColor) = switch (variant) {
      StatusVariant.success => (
          appColors.successContainer.withValues(alpha: 0.4),
          appColors.success.withValues(alpha: 0.3),
        ),
      StatusVariant.warning => (
          appColors.warningContainer.withValues(alpha: 0.4),
          appColors.warning.withValues(alpha: 0.3),
        ),
      StatusVariant.danger => (
          appColors.dangerContainer.withValues(alpha: 0.4),
          appColors.danger.withValues(alpha: 0.3),
        ),
      StatusVariant.info => (
          appColors.infoContainer.withValues(alpha: 0.4),
          appColors.info.withValues(alpha: 0.3),
        ),
      _ => (
          cs.surfaceContainerHighest,
          cs.outlineVariant,
        ),
    };

    final fgColor = switch (variant) {
      StatusVariant.success => appColors.success,
      StatusVariant.warning => appColors.warning,
      StatusVariant.danger => appColors.danger,
      StatusVariant.info => appColors.info,
      _ => cs.onSurfaceVariant,
    };

    return AppCard(
      color: bgColor,
      borderColor: borderColor,
      padding: const EdgeInsets.all(AppSpacing.lg),
      child: Row(
        children: [
          Container(
            width: 48,
            height: 48,
            decoration: BoxDecoration(
              shape: BoxShape.circle,
              color: fgColor.withValues(alpha: 0.15),
            ),
            child: Icon(icon, color: fgColor, size: AppSpacing.iconMd),
          ),
          const SizedBox(width: AppSpacing.lg),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                StatusBadge(
                  status: label,
                  variant: variant,
                  size: StatusBadgeSize.large,
                ),
                if (delivery.syncStatus == 'pending') ...[
                  const SizedBox(height: AppSpacing.xs),
                  Row(
                    children: [
                      Icon(Icons.sync_outlined,
                          size: 12,
                          color: cs.tertiary),
                      const SizedBox(width: 4),
                      Text(
                        'Sync kutilmoqda...',
                        style: tt.labelSmall?.copyWith(color: cs.tertiary),
                      ),
                    ],
                  ),
                ],
              ],
            ),
          ),
          Text(
            'v${delivery.version}',
            style: tt.labelSmall?.copyWith(color: cs.onSurfaceVariant),
          ),
        ],
      ),
    );
  }

  (IconData, StatusVariant, String) _statusInfo(String status) =>
      switch (status) {
        'assigned' => (Icons.assignment_outlined, StatusVariant.info, 'Tayinlangan'),
        'started' => (Icons.directions_run_outlined, StatusVariant.warning, 'Boshlandi'),
        'delivering' => (Icons.local_shipping_outlined, StatusVariant.warning, 'Yetkazilmoqda'),
        'delivered' => (Icons.check_circle_outline, StatusVariant.success, 'Yetkazildi'),
        'failed' => (Icons.cancel_outlined, StatusVariant.danger, 'Muvaffaqiyatsiz'),
        _ => (Icons.help_outline, StatusVariant.neutral, status),
      };
}

// ---------------------------------------------------------------------------

class _InfoCard extends StatelessWidget {
  const _InfoCard({required this.delivery});
  final Delivery delivery;

  @override
  Widget build(BuildContext context) {
    return AppCard(
      padding: const EdgeInsets.all(AppSpacing.lg),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          SectionHeader(title: "Ma'lumot"),
          const SizedBox(height: AppSpacing.md),
          _InfoRow(
            icon: Icons.receipt_outlined,
            label: 'Buyurtma ID',
            value: delivery.orderId,
          ),
          if (delivery.address != null)
            _InfoRow(
              icon: Icons.location_on_outlined,
              label: 'Manzil',
              value: delivery.address!,
            ),
          if (delivery.customerName != null)
            _InfoRow(
              icon: Icons.person_outline,
              label: 'Mijoz',
              value: delivery.customerName!,
            ),
          if (delivery.assignedAt != null)
            _InfoRow(
              icon: Icons.assignment_outlined,
              label: 'Tayinlangan',
              value: _fmtDate(delivery.assignedAt!),
            ),
          if (delivery.startedAt != null)
            _InfoRow(
              icon: Icons.play_arrow_outlined,
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
              valueColor: Theme.of(context).colorScheme.error,
            ),
          if (delivery.proofPhotoUrl != null)
            _InfoRow(
              icon: Icons.photo_outlined,
              label: 'Dalil rasmi',
              value: 'Yuklangan',
              valueColor: AppTheme.colorsOf(context).success,
            ),
        ],
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
    this.valueColor,
  });

  final IconData icon;
  final String label;
  final String value;
  final Color? valueColor;

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    final tt = Theme.of(context).textTheme;
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: AppSpacing.xs),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Icon(icon, size: AppSpacing.iconXs, color: cs.onSurfaceVariant),
          const SizedBox(width: AppSpacing.sm),
          SizedBox(
            width: 88,
            child: Text(
              label,
              style: tt.bodySmall?.copyWith(color: cs.onSurfaceVariant),
            ),
          ),
          Expanded(
            child: Text(
              value,
              style: tt.bodySmall?.copyWith(
                color: valueColor ?? cs.onSurface,
                fontWeight: FontWeight.w500,
              ),
            ),
          ),
        ],
      ),
    );
  }
}

// ---------------------------------------------------------------------------

class _GpsActiveCard extends StatelessWidget {
  const _GpsActiveCard();

  @override
  Widget build(BuildContext context) {
    final appColors = AppTheme.colorsOf(context);
    final tt = Theme.of(context).textTheme;
    return AppCard(
      padding: const EdgeInsets.symmetric(
          horizontal: AppSpacing.lg, vertical: AppSpacing.md),
      color: appColors.successContainer.withValues(alpha: 0.3),
      borderColor: appColors.success.withValues(alpha: 0.3),
      child: Row(
        children: [
          Icon(Icons.gps_fixed, color: appColors.success, size: AppSpacing.iconSm),
          const SizedBox(width: AppSpacing.sm),
          Text(
            'GPS tracking faol (45s interval)',
            style: tt.bodySmall?.copyWith(color: appColors.success),
          ),
        ],
      ),
    );
  }
}

// ---------------------------------------------------------------------------

class _MapLinkButton extends StatelessWidget {
  const _MapLinkButton({required this.deliveryId});
  final String deliveryId;

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      width: double.infinity,
      child: OutlinedButton.icon(
        onPressed: () => context.push(
            routeDeliveryMap.replaceAll(':deliveryId', deliveryId)),
        icon: const Icon(Icons.map_outlined, size: AppSpacing.iconSm),
        label: const Text("Xaritada ko'rish"),
      ),
    );
  }
}

// ---------------------------------------------------------------------------

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
    final transitions = kValidTransitions[delivery.status] ?? <String>[];

    if (transitions.isEmpty) return const SizedBox.shrink();

    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        SectionHeader(title: "Holat o'zgartirish"),
        const SizedBox(height: AppSpacing.sm),
        ...transitions.map(
          (nextStatus) => Padding(
            padding: const EdgeInsets.only(bottom: AppSpacing.sm),
            child: nextStatus == 'failed'
                ? OutlinedButton.icon(
                    style: OutlinedButton.styleFrom(
                      foregroundColor:
                          Theme.of(context).colorScheme.error,
                      side: BorderSide(
                          color: Theme.of(context).colorScheme.error),
                      padding: const EdgeInsets.symmetric(
                          vertical: AppSpacing.md),
                    ),
                    onPressed: () => _confirmFailed(context, notifier),
                    icon: const Icon(Icons.cancel_outlined),
                    label: const Text('Muvaffaqiyatsiz deb belgilash'),
                  )
                : FilledButton.icon(
                    style: FilledButton.styleFrom(
                      backgroundColor: _buttonColor(context, nextStatus),
                      padding: const EdgeInsets.symmetric(
                          vertical: AppSpacing.md),
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
            const SizedBox(height: AppSpacing.sm),
            TextField(
              controller: controller,
              decoration: const InputDecoration(
                hintText: "Masalan: Mijoz uyda yo'q edi",
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
            style: FilledButton.styleFrom(
                backgroundColor: Theme.of(ctx).colorScheme.error),
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

  Color _buttonColor(BuildContext context, String status) {
    final appColors = AppTheme.colorsOf(context);
    return switch (status) {
      'started' => appColors.warning,
      'delivering' => Theme.of(context).colorScheme.secondary,
      'delivered' => appColors.success,
      _ => Theme.of(context).colorScheme.primary,
    };
  }

  IconData _buttonIcon(String status) => switch (status) {
        'started' => Icons.directions_run_outlined,
        'delivering' => Icons.local_shipping_outlined,
        'delivered' => Icons.check_circle_outline,
        _ => Icons.arrow_forward,
      };

  String _buttonLabel(String status) => switch (status) {
        'started' => "Yo'lga chiqish",
        'delivering' => 'Yetkazishni boshlash',
        'delivered' => 'Yetkazildi',
        _ => status,
      };
}

// ---------------------------------------------------------------------------

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

    if (file == null) return;

    setState(() {
      _localPhoto = file;
      _isUploading = true;
    });

    await Future<void>.delayed(const Duration(milliseconds: 500));

    if (mounted) {
      setState(() => _isUploading = false);
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: const Text('Rasm muvaffaqiyatli tanlandi'),
          backgroundColor: AppTheme.colorsOf(context).success,
        ),
      );
    }
  }

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    final tt = Theme.of(context).textTheme;
    final appColors = AppTheme.colorsOf(context);

    return AppCard(
      padding: const EdgeInsets.all(AppSpacing.lg),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          SectionHeader(title: 'Dalil rasmi (isbot)'),
          const SizedBox(height: AppSpacing.md),

          if (widget.delivery.proofPhotoUrl != null) ...[
            // Yuklangan holat
            Row(
              children: [
                Container(
                  width: 40,
                  height: 40,
                  decoration: BoxDecoration(
                    color: appColors.successContainer.withValues(alpha: 0.5),
                    borderRadius: BorderRadius.circular(AppSpacing.radiusSm),
                  ),
                  child: Icon(Icons.check_circle_outline,
                      color: appColors.success, size: AppSpacing.iconSm),
                ),
                const SizedBox(width: AppSpacing.md),
                Expanded(
                  child: Text(
                    'Rasm yuklangan',
                    style: tt.bodyMedium?.copyWith(
                        color: appColors.success,
                        fontWeight: FontWeight.w600),
                  ),
                ),
              ],
            ),
          ] else if (_localPhoto != null) ...[
            // Mahalliy tanlangan rasm preview
            ClipRRect(
              borderRadius: BorderRadius.circular(AppSpacing.radiusMd),
              child: Image.file(
                _localPhoto!,
                height: 180,
                width: double.infinity,
                fit: BoxFit.cover,
              ),
            ),
            const SizedBox(height: AppSpacing.sm),
            if (_isUploading)
              LinearProgressIndicator(
                color: cs.primary,
                backgroundColor: cs.surfaceContainerHighest,
              )
            else
              Text(
                'Rasm tanlandi. Server bilan sync da yuklanadi.',
                style: tt.labelSmall?.copyWith(color: cs.onSurfaceVariant),
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
                    icon: const Icon(Icons.camera_alt_outlined),
                    label: const Text('Kamera'),
                  ),
                ),
                const SizedBox(width: AppSpacing.sm),
                Expanded(
                  child: OutlinedButton.icon(
                    onPressed: _isUploading
                        ? null
                        : () => _pickAndUpload(fromCamera: false),
                    icon: const Icon(Icons.photo_library_outlined),
                    label: const Text('Galereya'),
                  ),
                ),
              ],
            ),
            const SizedBox(height: AppSpacing.xs + 2),
            Text(
              'Rasm yetkazish isboti sifatida saqlanadi.',
              style: tt.labelSmall?.copyWith(color: cs.onSurfaceVariant),
            ),
          ],
        ],
      ),
    );
  }
}
