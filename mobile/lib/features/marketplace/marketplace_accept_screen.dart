import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

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
        loading: () =>
            const Center(child: CircularProgressIndicator()),
        error: (e, _) => Center(
          child: Text(
            'Xatolik: $e',
            style: const TextStyle(color: Colors.red),
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
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(24),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(Icons.info_outline,
                size: 56, color: Colors.orange.shade400),
            const SizedBox(height: 16),
            Text(
              'Buyurtma holati: ${order.status.label}',
              style: const TextStyle(
                  fontWeight: FontWeight.bold, fontSize: 16),
              textAlign: TextAlign.center,
            ),
            const SizedBox(height: 8),
            Text(
              'Faqat "Yetkazildi" holatidagi buyurtmalar qabul qilinadi.',
              style: TextStyle(color: Colors.grey.shade600),
              textAlign: TextAlign.center,
            ),
            const SizedBox(height: 16),
            FilledButton(
              onPressed: () => context.go('/home/marketplace/orders'),
              child: const Text('Orqaga'),
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
  // Har line uchun forma ma'lumotlari
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

  bool get _isValid => _formData.values.every((d) => d.isValid);

  @override
  Widget build(BuildContext context) {
    final acceptState =
        ref.watch(acceptOrderProvider(widget.order.id));

    // Muvaffaqiyat yoki xatolik xabari
    ref.listen(
      acceptOrderProvider(widget.order.id),
      (_, next) {
        if (next is AcceptOrderSuccess) {
          ScaffoldMessenger.of(context).showSnackBar(
            const SnackBar(
              content: Text(
                  'Qabul qilindi! Mahsulotlar inventarga qo\'shildi.'),
              backgroundColor: Colors.green,
            ),
          );
          context.go('/home/marketplace/orders');
        }
        if (next is AcceptOrderFailure) {
          ScaffoldMessenger.of(context).showSnackBar(
            SnackBar(
              content: Text('Xatolik: ${next.message}'),
              backgroundColor: Colors.red,
            ),
          );
        }
      },
    );

    final isLoading = acceptState is AcceptOrderLoading;

    return SingleChildScrollView(
      padding: const EdgeInsets.all(16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // Buyurtma ma'lumoti
          _OrderInfoCard(order: widget.order),

          const SizedBox(height: 16),

          // Proof photo (kuryer rasmi)
          if (widget.order.proofPhotoUrl != null) ...[
            _ProofPhotoCard(photoUrl: widget.order.proofPhotoUrl!),
            const SizedBox(height: 16),
          ],

          // Har line uchun forma
          Text(
            'Har mahsulot uchun ma\'lumot kiriting',
            style: Theme.of(context)
                .textTheme
                .titleSmall
                ?.copyWith(fontWeight: FontWeight.bold),
          ),
          const SizedBox(height: 8),

          ...widget.order.lines.map(
            (line) => _LineFormCard(
              line: line,
              formData: _formData[line.lineId]!,
              onChanged: () => setState(() {}),
            ),
          ),

          const SizedBox(height: 20),

          // Qabul qilish tugmasi
          SizedBox(
            width: double.infinity,
            child: FilledButton.icon(
              style: FilledButton.styleFrom(
                backgroundColor: Colors.green,
                padding: const EdgeInsets.symmetric(vertical: 14),
              ),
              onPressed: (!_isValid || isLoading) ? null : _accept,
              icon: isLoading
                  ? const SizedBox(
                      width: 18,
                      height: 18,
                      child: CircularProgressIndicator(
                          strokeWidth: 2, color: Colors.white),
                    )
                  : const Icon(Icons.check_circle_outline),
              label: Text(
                isLoading ? 'Qabul qilinmoqda...' : 'Qabul qilish',
                style: const TextStyle(fontSize: 16),
              ),
            ),
          ),

          if (!_isValid)
            Padding(
              padding: const EdgeInsets.only(top: 8),
              child: Text(
                'Barcha maydonlarni to\'ldiring.',
                style: TextStyle(color: Colors.orange.shade700, fontSize: 12),
                textAlign: TextAlign.center,
              ),
            ),

          const SizedBox(height: 24),
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
            _Row(
              icon: Icons.storefront,
              label: 'Supplier',
              value: order.supplierEnterpriseName,
            ),
            _Row(
              icon: Icons.tag,
              label: 'ID',
              value: '#${order.id.substring(0, 8)}',
            ),
            _Row(
              icon: Icons.inventory_2_outlined,
              label: 'Mahsulotlar',
              value: '${order.lines.length} ta',
            ),
          ],
        ),
      ),
    );
  }
}

class _Row extends StatelessWidget {
  const _Row({
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
            width: 72,
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

class _ProofPhotoCard extends StatelessWidget {
  const _ProofPhotoCard({required this.photoUrl});
  final String photoUrl;

  @override
  Widget build(BuildContext context) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(14),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              'Kuryer dalil rasmi',
              style: Theme.of(context)
                  .textTheme
                  .titleSmall
                  ?.copyWith(fontWeight: FontWeight.bold),
            ),
            const SizedBox(height: 10),
            ClipRRect(
              borderRadius: BorderRadius.circular(8),
              child: Image.network(
                photoUrl,
                height: 200,
                width: double.infinity,
                fit: BoxFit.cover,
                errorBuilder: (_, __, ___) => Container(
                  height: 80,
                  color: Colors.grey.shade100,
                  child: const Center(
                    child: Row(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        Icon(Icons.photo, color: Colors.grey),
                        SizedBox(width: 6),
                        Text(
                          'Rasm yuklanmadi',
                          style: TextStyle(color: Colors.grey),
                        ),
                      ],
                    ),
                  ),
                ),
              ),
            ),
          ],
        ),
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
    return Card(
      margin: const EdgeInsets.only(bottom: 10),
      child: Padding(
        padding: const EdgeInsets.all(14),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            // Mahsulot nomi
            Row(
              children: [
                const Icon(Icons.inventory_2_outlined,
                    size: 16, color: Colors.blue),
                const SizedBox(width: 6),
                Expanded(
                  child: Text(
                    line.productName,
                    style: const TextStyle(
                      fontWeight: FontWeight.w600,
                      fontSize: 14,
                    ),
                  ),
                ),
                Text(
                  'x${line.qty.toStringAsFixed(line.qty % 1 == 0 ? 0 : 1)} ${line.qty == line.qty.floorToDouble() ? '' : ''}',
                  style: TextStyle(
                      fontSize: 12, color: Colors.grey.shade600),
                ),
              ],
            ),
            const SizedBox(height: 12),

            // Yaroqlilik muddati
            _ExpiryDateField(
              formData: formData,
              onChanged: onChanged,
            ),

            const SizedBox(height: 10),

            // Ustama foizi
            _MarkupField(
              formData: formData,
              onChanged: onChanged,
            ),
          ],
        ),
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
    final hasDate = formData.expiryDate != null;

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        const Text(
          'Yaroqlilik muddati *',
          style: TextStyle(fontSize: 12, color: Colors.grey),
        ),
        const SizedBox(height: 4),
        InkWell(
          onTap: () => _pickDate(context),
          child: Container(
            padding: const EdgeInsets.symmetric(
                horizontal: 12, vertical: 10),
            decoration: BoxDecoration(
              border: Border.all(
                color: hasDate
                    ? Colors.green
                    : Colors.grey.shade300,
              ),
              borderRadius: BorderRadius.circular(8),
            ),
            child: Row(
              children: [
                Icon(
                  Icons.calendar_today,
                  size: 16,
                  color: hasDate ? Colors.green : Colors.grey,
                ),
                const SizedBox(width: 8),
                Text(
                  hasDate
                      ? _fmtDate(formData.expiryDate!)
                      : 'Muddatni tanlang',
                  style: TextStyle(
                    fontSize: 13,
                    color: hasDate ? Colors.black87 : Colors.grey,
                  ),
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
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        const Text(
          'Ustama foizi (%) *',
          style: TextStyle(fontSize: 12, color: Colors.grey),
        ),
        const SizedBox(height: 4),
        TextField(
          controller: formData.markupController,
          keyboardType: const TextInputType.numberWithOptions(decimal: true),
          decoration: InputDecoration(
            hintText: 'Masalan: 15',
            suffixText: '%',
            isDense: true,
            border: OutlineInputBorder(
              borderRadius: BorderRadius.circular(8),
            ),
            contentPadding: const EdgeInsets.symmetric(
                horizontal: 12, vertical: 10),
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

  bool get isValid =>
      expiryDate != null && markupPercent != null;

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
