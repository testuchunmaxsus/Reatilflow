import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/theme/app_spacing.dart';
import '../../core/theme/app_theme.dart';
import '../../core/widgets/app_card.dart';
import '../../core/widgets/section_header.dart';
import '../../core/widgets/status_badge.dart';
import 'marketplace_models.dart';
import 'marketplace_providers.dart';

/// Buyurtmani qabul qilish ekrani.
///
/// - proof_photo ko'rsatiladi (kuryer rasmi)
/// - Har line uchun muddat (expiry_date) + ustama % (markup_percent) kiritiladi
/// - "Qabul qilish" → PATCH /marketplace/orders/{id}/accept
/// - Mahsulotlar POS inventarga tushadi (backend)
class MarketplaceAcceptScreen extends ConsumerWidget {
  const MarketplaceAcceptScreen({super.key, required this.orderId});
  final String orderId;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final orderAsync =
        ref.watch(marketplaceOrderDetailProvider(orderId));

    return Scaffold(
      appBar: AppBar(
        title: const Text('Buyurtmani qabul qilish'),
      ),
      body: orderAsync.when(
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (e, _) => Center(
          child: Padding(
            padding: const EdgeInsets.all(AppSpacing.xl),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                Icon(Icons.error_outline,
                    size: AppSpacing.iconXl,
                    color: AppTheme.colorsOf(context).danger),
                const SizedBox(height: AppSpacing.md),
                Text(
                  'Xatolik: $e',
                  style: TextStyle(
                    color: AppTheme.colorsOf(context).danger,
                  ),
                  textAlign: TextAlign.center,
                ),
              ],
            ),
          ),
        ),
        data: (order) {
          if (!order.canAccept) {
            return _CannotAcceptBody(order: order);
          }
          return _AcceptBody(order: order);
        },
      ),
    );
  }
}

class _CannotAcceptBody extends StatelessWidget {
  const _CannotAcceptBody({required this.order});
  final MarketplaceOrder order;

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    final tt = Theme.of(context).textTheme;
    final appColors = AppTheme.colorsOf(context);

    // Status variant
    final variant = switch (order.status) {
      MarketplaceOrderStatus.accepted => StatusVariant.success,
      MarketplaceOrderStatus.delivered => StatusVariant.success,
      MarketplaceOrderStatus.confirmed => StatusVariant.info,
      MarketplaceOrderStatus.delivering => StatusVariant.info,
      MarketplaceOrderStatus.pending => StatusVariant.warning,
      MarketplaceOrderStatus.cancelled => StatusVariant.danger,
    };

    return Center(
      child: Padding(
        padding: const EdgeInsets.all(AppSpacing.xl),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Container(
              width: 72,
              height: 72,
              decoration: BoxDecoration(
                color: appColors.warningContainer,
                shape: BoxShape.circle,
              ),
              child: Icon(
                Icons.info_outline,
                size: AppSpacing.iconXl,
                color: appColors.warning,
              ),
            ),
            const SizedBox(height: AppSpacing.lg),
            Text(
              'Buyurtma holati',
              style: tt.titleMedium?.copyWith(
                fontWeight: FontWeight.w600,
                color: cs.onSurface,
              ),
              textAlign: TextAlign.center,
            ),
            const SizedBox(height: AppSpacing.sm),
            StatusBadge(
              status: order.status.label,
              variant: variant,
              size: StatusBadgeSize.large,
            ),
            const SizedBox(height: AppSpacing.md),
            Text(
              'Faqat "Yetkazildi" holatidagi buyurtmalar qabul qilinadi.',
              style: tt.bodyMedium?.copyWith(
                color: cs.onSurfaceVariant,
              ),
              textAlign: TextAlign.center,
            ),
            const SizedBox(height: AppSpacing.xl),
            FilledButton.icon(
              onPressed: () =>
                  context.go('/home/marketplace/orders'),
              icon: const Icon(Icons.arrow_back),
              label: const Text('Orqaga'),
            ),
          ],
        ),
      ),
    );
  }
}

class _AcceptBody extends ConsumerStatefulWidget {
  const _AcceptBody({required this.order});
  final MarketplaceOrder order;

  @override
  ConsumerState<_AcceptBody> createState() => _AcceptBodyState();
}

class _AcceptBodyState extends ConsumerState<_AcceptBody> {
  late final Map<String, _LineFormData> _formData;

  @override
  void initState() {
    super.initState();
    _formData = {
      for (final line in widget.order.lines)
        line.lineId: _LineFormData(lineId: line.lineId),
    };
  }

  @override
  void dispose() {
    for (final d in _formData.values) {
      d.dispose();
    }
    super.dispose();
  }

  bool get _isValid =>
      _formData.values.every((d) => d.isValid);

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    final tt = Theme.of(context).textTheme;
    final appColors = AppTheme.colorsOf(context);
    final acceptState =
        ref.watch(acceptOrderProvider(widget.order.id));

    // Natija eshitish
    ref.listen(
      acceptOrderProvider(widget.order.id),
      (_, next) {
        if (next is AcceptOrderSuccess) {
          ScaffoldMessenger.of(context).showSnackBar(
            SnackBar(
              content: const Text(
                  'Qabul qilindi! Mahsulotlar inventarga qo\'shildi.'),
              backgroundColor: appColors.success,
              behavior: SnackBarBehavior.floating,
              shape: RoundedRectangleBorder(
                borderRadius:
                    BorderRadius.circular(AppSpacing.radiusMd),
              ),
            ),
          );
          context.go('/home/marketplace/orders');
        }
        if (next is AcceptOrderFailure) {
          ScaffoldMessenger.of(context).showSnackBar(
            SnackBar(
              content: Text('Xatolik: ${next.message}'),
              backgroundColor: appColors.danger,
              behavior: SnackBarBehavior.floating,
              shape: RoundedRectangleBorder(
                borderRadius:
                    BorderRadius.circular(AppSpacing.radiusMd),
              ),
            ),
          );
        }
      },
    );

    final isLoading = acceptState is AcceptOrderLoading;

    return SingleChildScrollView(
      padding: const EdgeInsets.all(AppSpacing.lg),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // Buyurtma ma'lumoti
          _OrderInfoCard(order: widget.order),

          const SizedBox(height: AppSpacing.md),

          // Proof photo (kuryer rasmi)
          if (widget.order.proofPhotoUrl != null) ...[
            _ProofPhotoCard(
                photoUrl: widget.order.proofPhotoUrl!),
            const SizedBox(height: AppSpacing.md),
          ],

          // Har line uchun forma
          SectionHeader(
            title: 'Mahsulotlar uchun ma\'lumot',
            subtitle:
                '${widget.order.lines.length} ta mahsulot',
          ),
          const SizedBox(height: AppSpacing.md),

          ...widget.order.lines.map(
            (line) => Padding(
              padding: const EdgeInsets.only(bottom: AppSpacing.sm),
              child: _LineFormCard(
                line: line,
                formData: _formData[line.lineId]!,
                onChanged: () => setState(() {}),
              ),
            ),
          ),

          const SizedBox(height: AppSpacing.lg),

          // Validatsiya xabari
          if (!_isValid)
            AppCard(
              padding: const EdgeInsets.all(AppSpacing.md),
              color: appColors.warningContainer.withValues(alpha: 0.4),
              borderColor: appColors.warning.withValues(alpha: 0.3),
              child: Row(
                children: [
                  Icon(Icons.info_outline,
                      size: AppSpacing.iconSm,
                      color: appColors.warning),
                  const SizedBox(width: AppSpacing.sm),
                  Expanded(
                    child: Text(
                      'Barcha maydonlarni to\'ldiring.',
                      style: tt.bodySmall?.copyWith(
                        color: appColors.warning,
                        fontWeight: FontWeight.w600,
                      ),
                    ),
                  ),
                ],
              ),
            ),

          if (!_isValid)
            const SizedBox(height: AppSpacing.md),

          // Qabul qilish tugmasi
          SizedBox(
            width: double.infinity,
            child: FilledButton.icon(
              style: FilledButton.styleFrom(
                backgroundColor: _isValid
                    ? appColors.success
                    : cs.surfaceContainerHighest,
                foregroundColor: _isValid
                    ? appColors.onSuccess
                    : cs.onSurfaceVariant,
                minimumSize: const Size.fromHeight(AppSpacing.buttonHeight),
              ),
              onPressed: (!_isValid || isLoading) ? null : _accept,
              icon: isLoading
                  ? SizedBox(
                      width: 18,
                      height: 18,
                      child: CircularProgressIndicator(
                        strokeWidth: 2,
                        color: _isValid
                            ? appColors.onSuccess
                            : cs.onSurfaceVariant,
                      ),
                    )
                  : const Icon(Icons.check_circle_outline),
              label: Text(
                isLoading ? 'Qabul qilinmoqda...' : 'Qabul qilish',
                style: const TextStyle(
                    fontWeight: FontWeight.w700, fontSize: 16),
              ),
            ),
          ),

          const SizedBox(height: AppSpacing.xxl),
        ],
      ),
    );
  }

  Future<void> _accept() async {
    final lines = widget.order.lines.map((line) {
      final d = _formData[line.lineId]!;
      return AcceptOrderLine(
        lineId: line.lineId,
        expiryDate: d.expiryDate!,
        markupPercent: d.markupPercent!,
      );
    }).toList();

    await ref.read(acceptOrderProvider(widget.order.id).notifier).accept(
          orderId: widget.order.id,
          lines: lines,
        );
  }
}

// ---------------------------------------------------------------------------
// Yordamchi widgetlar

class _OrderInfoCard extends StatelessWidget {
  const _OrderInfoCard({required this.order});
  final MarketplaceOrder order;

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    final tt = Theme.of(context).textTheme;

    // Status variant
    final variant = switch (order.status) {
      MarketplaceOrderStatus.accepted => StatusVariant.success,
      MarketplaceOrderStatus.delivered => StatusVariant.success,
      MarketplaceOrderStatus.confirmed => StatusVariant.info,
      MarketplaceOrderStatus.delivering => StatusVariant.info,
      MarketplaceOrderStatus.pending => StatusVariant.warning,
      MarketplaceOrderStatus.cancelled => StatusVariant.danger,
    };

    return AppCard(
      padding: const EdgeInsets.all(AppSpacing.md),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // Sarlavha + holat
          Row(
            children: [
              Text(
                'Buyurtma ma\'lumoti',
                style: tt.titleSmall?.copyWith(
                  fontWeight: FontWeight.w700,
                ),
              ),
              const Spacer(),
              StatusBadge(
                status: order.status.label,
                variant: variant,
              ),
            ],
          ),
          const SizedBox(height: AppSpacing.md),
          Divider(color: cs.outlineVariant, height: 1),
          const SizedBox(height: AppSpacing.sm),
          _InfoRow(
            icon: Icons.storefront,
            label: 'Supplier',
            value: order.supplierEnterpriseName,
          ),
          _InfoRow(
            icon: Icons.tag,
            label: 'ID',
            value: '#${order.id.substring(0, 8)}',
            valueStyle: const TextStyle(fontFamily: 'monospace'),
          ),
          _InfoRow(
            icon: Icons.inventory_2_outlined,
            label: 'Mahsulotlar',
            value: '${order.lines.length} ta',
          ),
        ],
      ),
    );
  }
}

class _InfoRow extends StatelessWidget {
  const _InfoRow({
    required this.icon,
    required this.label,
    required this.value,
    this.valueStyle,
  });
  final IconData icon;
  final String label;
  final String value;
  final TextStyle? valueStyle;

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    final tt = Theme.of(context).textTheme;

    return Padding(
      padding: const EdgeInsets.symmetric(vertical: AppSpacing.xs),
      child: Row(
        children: [
          Icon(icon, size: AppSpacing.iconSm, color: cs.onSurfaceVariant),
          const SizedBox(width: AppSpacing.sm),
          SizedBox(
            width: 80,
            child: Text(
              label,
              style: tt.bodySmall?.copyWith(
                color: cs.onSurfaceVariant,
              ),
            ),
          ),
          Expanded(
            child: Text(
              value,
              style: tt.bodyMedium?.copyWith(
                fontWeight: FontWeight.w500,
              ).merge(valueStyle),
            ),
          ),
        ],
      ),
    );
  }
}

class _ProofPhotoCard extends StatelessWidget {
  const _ProofPhotoCard({required this.photoUrl});
  final String photoUrl;

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    final tt = Theme.of(context).textTheme;

    return AppCard(
      padding: const EdgeInsets.all(AppSpacing.md),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Icon(Icons.photo_camera_outlined,
                  size: AppSpacing.iconSm, color: cs.primary),
              const SizedBox(width: AppSpacing.sm),
              Text(
                'Kuryer dalil rasmi',
                style: tt.titleSmall?.copyWith(
                  fontWeight: FontWeight.w700,
                ),
              ),
            ],
          ),
          const SizedBox(height: AppSpacing.md),
          ClipRRect(
            borderRadius: BorderRadius.circular(AppSpacing.radiusMd),
            child: Image.network(
              photoUrl,
              height: 200,
              width: double.infinity,
              fit: BoxFit.cover,
              errorBuilder: (_, __, ___) => Container(
                height: 80,
                decoration: BoxDecoration(
                  color: cs.surfaceContainerHighest,
                  borderRadius:
                      BorderRadius.circular(AppSpacing.radiusMd),
                ),
                child: Center(
                  child: Row(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      Icon(Icons.photo_outlined,
                          color: cs.onSurfaceVariant,
                          size: AppSpacing.iconSm),
                      const SizedBox(width: AppSpacing.sm),
                      Text(
                        'Rasm yuklanmadi',
                        style: tt.bodySmall?.copyWith(
                          color: cs.onSurfaceVariant,
                        ),
                      ),
                    ],
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

/// Bitta buyurtma satri uchun forma.
class _LineFormCard extends StatelessWidget {
  const _LineFormCard({
    required this.line,
    required this.formData,
    required this.onChanged,
  });

  final MarketplaceOrderLine line;
  final _LineFormData formData;
  final VoidCallback onChanged;

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    final tt = Theme.of(context).textTheme;

    final hasDate = formData.expiryDate != null;
    final hasMarkup = formData.markupPercent != null;
    final isComplete = hasDate && hasMarkup;

    return AppCard(
      padding: const EdgeInsets.all(AppSpacing.md),
      borderColor: isComplete
          ? AppTheme.colorsOf(context).success.withValues(alpha: 0.4)
          : cs.outlineVariant,
      color: isComplete
          ? AppTheme.colorsOf(context)
              .successContainer
              .withValues(alpha: 0.15)
          : null,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // Mahsulot nomi + holat
          Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Container(
                width: 36,
                height: 36,
                decoration: BoxDecoration(
                  color: cs.primaryContainer,
                  borderRadius:
                      BorderRadius.circular(AppSpacing.radiusSm),
                ),
                child: Icon(
                  Icons.inventory_2_outlined,
                  size: AppSpacing.iconSm,
                  color: cs.primary,
                ),
              ),
              const SizedBox(width: AppSpacing.sm),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      line.productName,
                      style: tt.titleSmall?.copyWith(
                        fontWeight: FontWeight.w600,
                      ),
                    ),
                    Text(
                      'x${line.qty.toStringAsFixed(line.qty % 1 == 0 ? 0 : 1)}',
                      style: tt.bodySmall?.copyWith(
                        color: cs.onSurfaceVariant,
                      ),
                    ),
                  ],
                ),
              ),
              if (isComplete)
                Icon(Icons.check_circle,
                    size: AppSpacing.iconSm,
                    color: AppTheme.colorsOf(context).success),
            ],
          ),

          const SizedBox(height: AppSpacing.md),
          Divider(color: cs.outlineVariant, height: 1),
          const SizedBox(height: AppSpacing.md),

          // Yaroqlilik muddati
          _ExpiryDateField(
            formData: formData,
            onChanged: onChanged,
          ),

          const SizedBox(height: AppSpacing.md),

          // Ustama foizi
          _MarkupField(
            formData: formData,
            onChanged: onChanged,
          ),
        ],
      ),
    );
  }
}

class _ExpiryDateField extends StatelessWidget {
  const _ExpiryDateField({
    required this.formData,
    required this.onChanged,
  });
  final _LineFormData formData;
  final VoidCallback onChanged;

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    final tt = Theme.of(context).textTheme;
    final appColors = AppTheme.colorsOf(context);
    final hasDate = formData.expiryDate != null;

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          'Yaroqlilik muddati *',
          style: tt.labelMedium?.copyWith(
            color: cs.onSurfaceVariant,
            fontWeight: FontWeight.w600,
          ),
        ),
        const SizedBox(height: AppSpacing.xs),
        InkWell(
          onTap: () => _pickDate(context),
          borderRadius: BorderRadius.circular(AppSpacing.radiusMd),
          child: Container(
            padding: const EdgeInsets.symmetric(
              horizontal: AppSpacing.md,
              vertical: AppSpacing.sm + 2,
            ),
            decoration: BoxDecoration(
              border: Border.all(
                color: hasDate
                    ? appColors.success
                    : cs.outlineVariant,
                width: hasDate ? 1.5 : 1,
              ),
              borderRadius:
                  BorderRadius.circular(AppSpacing.radiusMd),
              color: hasDate
                  ? appColors.successContainer.withValues(alpha: 0.2)
                  : cs.surfaceContainerHighest.withValues(alpha: 0.4),
            ),
            child: Row(
              children: [
                Icon(
                  hasDate
                      ? Icons.event_available
                      : Icons.calendar_today,
                  size: AppSpacing.iconSm,
                  color: hasDate
                      ? appColors.success
                      : cs.onSurfaceVariant,
                ),
                const SizedBox(width: AppSpacing.sm),
                Text(
                  hasDate
                      ? _fmtDate(formData.expiryDate!)
                      : 'Muddatni tanlang',
                  style: tt.bodyMedium?.copyWith(
                    color: hasDate
                        ? cs.onSurface
                        : cs.onSurfaceVariant,
                    fontWeight: hasDate
                        ? FontWeight.w500
                        : FontWeight.normal,
                  ),
                ),
                const Spacer(),
                Icon(
                  Icons.chevron_right,
                  size: AppSpacing.iconSm,
                  color: cs.onSurfaceVariant,
                ),
              ],
            ),
          ),
        ),
      ],
    );
  }

  Future<void> _pickDate(BuildContext context) async {
    final now = DateTime.now();
    final picked = await showDatePicker(
      context: context,
      initialDate: formData.expiryDate ??
          now.add(const Duration(days: 30)),
      firstDate: now,
      lastDate: now.add(const Duration(days: 365 * 5)),
      helpText: 'Yaroqlilik muddatini tanlang',
    );
    if (picked != null) {
      formData.expiryDate = picked;
      onChanged();
    }
  }

  String _fmtDate(DateTime dt) {
    String pad(int n) => n.toString().padLeft(2, '0');
    return '${pad(dt.day)}.${pad(dt.month)}.${dt.year}';
  }
}

class _MarkupField extends StatelessWidget {
  const _MarkupField({
    required this.formData,
    required this.onChanged,
  });
  final _LineFormData formData;
  final VoidCallback onChanged;

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    final tt = Theme.of(context).textTheme;

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          'Ustama foizi (%) *',
          style: tt.labelMedium?.copyWith(
            color: cs.onSurfaceVariant,
            fontWeight: FontWeight.w600,
          ),
        ),
        const SizedBox(height: AppSpacing.xs),
        TextField(
          controller: formData.markupController,
          keyboardType:
              const TextInputType.numberWithOptions(decimal: true),
          decoration: InputDecoration(
            hintText: 'Masalan: 15',
            suffixText: '%',
            errorText: formData.markupError,
          ),
          onChanged: (v) {
            formData.validateMarkup(v);
            onChanged();
          },
        ),
      ],
    );
  }
}

// ---------------------------------------------------------------------------
// Forma ma'lumotlari

class _LineFormData {
  _LineFormData({required this.lineId});

  final String lineId;
  DateTime? expiryDate;
  final TextEditingController markupController = TextEditingController();
  String? markupError;

  double? get markupPercent {
    final v = double.tryParse(markupController.text.trim());
    if (v == null || v < 0) return null;
    return v;
  }

  bool get isValid => expiryDate != null && markupPercent != null;

  void validateMarkup(String v) {
    final num = double.tryParse(v.trim());
    if (num == null) {
      markupError = 'Raqam kiriting';
    } else if (num < 0) {
      markupError = '0 dan katta bo\'lsin';
    } else {
      markupError = null;
    }
  }

  void dispose() {
    markupController.dispose();
  }
}
