import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'pos_models.dart';
import 'pos_providers.dart';

/// POS Kunlik hisobot ekrani.
///
/// GET /pos/summary?date=YYYY-MM-DD — jami sotuv, soni, to'lov usuli bo'yicha.
class PosSummaryScreen extends ConsumerWidget {
  const PosSummaryScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final summaryAsync = ref.watch(posSummaryProvider);
    final selectedDate = ref.watch(posSummaryDateProvider);

    return Scaffold(
      appBar: AppBar(
        title: const Text('Kunlik hisobot'),
        actions: [
          IconButton(
            icon: const Icon(Icons.refresh),
            tooltip: 'Yangilash',
            onPressed: () => ref.invalidate(posSummaryProvider),
          ),
          IconButton(
            icon: const Icon(Icons.calendar_today),
            tooltip: 'Sana tanlash',
            onPressed: () => _pickDate(context, ref, selectedDate),
          ),
        ],
      ),
      body: summaryAsync.when(
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (e, _) => Center(
          child: Padding(
            padding: const EdgeInsets.all(24),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                const Icon(Icons.error_outline, color: Colors.red, size: 48),
                const SizedBox(height: 12),
                Text('Xatolik: $e',
                    textAlign: TextAlign.center,
                    style: const TextStyle(color: Colors.red)),
                const SizedBox(height: 16),
                ElevatedButton.icon(
                  onPressed: () => ref.invalidate(posSummaryProvider),
                  icon: const Icon(Icons.refresh),
                  label: const Text('Qayta urinish'),
                ),
              ],
            ),
          ),
        ),
        data: (summary) => _SummaryBody(summary: summary),
      ),
    );
  }

  Future<void> _pickDate(
      BuildContext context, WidgetRef ref, String? current) async {
    final initial = current != null
        ? DateTime.tryParse(current) ?? DateTime.now()
        : DateTime.now();

    final picked = await showDatePicker(
      context: context,
      initialDate: initial,
      firstDate: DateTime(2024),
      lastDate: DateTime.now(),
    );
    if (picked != null) {
      final m = picked.month.toString().padLeft(2, '0');
      final d = picked.day.toString().padLeft(2, '0');
      ref.read(posSummaryDateProvider.notifier).state =
          '${picked.year}-$m-$d';
    }
  }
}

// ---------------------------------------------------------------------------

class _SummaryBody extends StatelessWidget {
  const _SummaryBody({required this.summary});
  final PosSummary summary;

  @override
  Widget build(BuildContext context) {
    return SingleChildScrollView(
      padding: const EdgeInsets.all(16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // Sana
          Row(
            children: [
              const Icon(Icons.calendar_today,
                  size: 18, color: Colors.blue),
              const SizedBox(width: 8),
              Text(
                _formatDate(summary.date),
                style: Theme.of(context)
                    .textTheme
                    .titleMedium
                    ?.copyWith(fontWeight: FontWeight.bold),
              ),
            ],
          ),

          const SizedBox(height: 16),

          // Asosiy statistika
          Row(
            children: [
              Expanded(
                child: _StatCard(
                  icon: Icons.receipt_long,
                  label: 'Sotuvlar soni',
                  value: '${summary.totalSales} ta',
                  color: Colors.blue,
                ),
              ),
              const SizedBox(width: 12),
              Expanded(
                child: _StatCard(
                  icon: Icons.attach_money,
                  label: 'Jami summa',
                  value: _fmtAmount(summary.totalAmount),
                  color: Colors.green,
                ),
              ),
            ],
          ),

          const SizedBox(height: 20),

          // To'lov usuli bo'yicha
          if (summary.byPaymentMethod.isNotEmpty) ...[
            Text(
              "To'lov usullari bo'yicha",
              style: Theme.of(context)
                  .textTheme
                  .titleSmall
                  ?.copyWith(fontWeight: FontWeight.w600),
            ),
            const SizedBox(height: 10),
            ...summary.byPaymentMethod.entries.map(
              (e) => _PaymentMethodRow(
                method: e.key,
                data: e.value,
              ),
            ),
          ],

          if (summary.totalSales == 0)
            const Padding(
              padding: EdgeInsets.symmetric(vertical: 32),
              child: Center(
                child: Text(
                  'Bu kun uchun sotuv mavjud emas',
                  style: TextStyle(color: Colors.grey, fontSize: 15),
                ),
              ),
            ),
        ],
      ),
    );
  }

  String _formatDate(String dateStr) {
    final dt = DateTime.tryParse(dateStr);
    if (dt == null) return dateStr;
    const months = [
      'yanvar',
      'fevral',
      'mart',
      'aprel',
      'may',
      'iyun',
      'iyul',
      'avgust',
      'sentabr',
      'oktabr',
      'noyabr',
      'dekabr',
    ];
    return '${dt.day} ${months[dt.month - 1]} ${dt.year}';
  }

  String _fmtAmount(double v) {
    final s = v.toStringAsFixed(0);
    final buf = StringBuffer();
    for (int i = 0; i < s.length; i++) {
      if (i > 0 && (s.length - i) % 3 == 0) buf.write(' ');
      buf.write(s[i]);
    }
    return "${buf.toString()} so'm";
  }
}

class _StatCard extends StatelessWidget {
  const _StatCard({
    required this.icon,
    required this.label,
    required this.value,
    required this.color,
  });
  final IconData icon;
  final String label;
  final String value;
  final Color color;

  @override
  Widget build(BuildContext context) {
    return Card(
      color: color.withValues(alpha: 0.08),
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(12),
        side: BorderSide(color: color.withValues(alpha: 0.25)),
      ),
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Icon(icon, color: color, size: 28),
            const SizedBox(height: 8),
            Text(label,
                style:
                    const TextStyle(fontSize: 12, color: Colors.grey)),
            const SizedBox(height: 4),
            Text(
              value,
              style: TextStyle(
                  fontSize: 20,
                  fontWeight: FontWeight.bold,
                  color: color),
            ),
          ],
        ),
      ),
    );
  }
}

class _PaymentMethodRow extends StatelessWidget {
  const _PaymentMethodRow({required this.method, required this.data});
  final String method;
  final PosSummaryByMethod data;

  @override
  Widget build(BuildContext context) {
    final (icon, label, color) = _methodInfo(method);

    return Card(
      margin: const EdgeInsets.only(bottom: 8),
      child: ListTile(
        leading: Icon(icon, color: color),
        title: Text(label, style: const TextStyle(fontWeight: FontWeight.w500)),
        subtitle: Text('${data.count} ta sotuv'),
        trailing: Text(
          '${data.amount.toStringAsFixed(0)} so\'m',
          style: TextStyle(
              fontWeight: FontWeight.bold,
              fontSize: 15,
              color: color),
        ),
      ),
    );
  }

  (IconData, String, Color) _methodInfo(String method) => switch (method) {
        'cash' => (Icons.money, 'Naqd pul', Colors.green),
        'card' => (Icons.credit_card, 'Karta', Colors.blue),
        'transfer' => (
            Icons.account_balance,
            "O'tkazma",
            Colors.purple
          ),
        _ => (Icons.payment, method, Colors.grey),
      };
}
