import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/theme/app_spacing.dart';
import '../../core/theme/app_theme.dart';
import '../../core/widgets/app_card.dart';
import '../../core/widgets/empty_state.dart';
import '../../core/widgets/section_header.dart';
import '../../core/widgets/stat_card.dart';
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
    final cs = Theme.of(context).colorScheme;

    return Scaffold(
      appBar: AppBar(
        title: const Text('Kunlik hisobot'),
        actions: [
          IconButton(
            icon: const Icon(Icons.calendar_today),
            tooltip: 'Sana tanlash',
            onPressed: () => _pickDate(context, ref, selectedDate),
          ),
          IconButton(
            icon: const Icon(Icons.refresh),
            tooltip: 'Yangilash',
            onPressed: () => ref.invalidate(posSummaryProvider),
          ),
        ],
      ),
      body: summaryAsync.when(
        loading: () => _SummaryLoadingSkeleton(),
        error: (e, _) => EmptyState(
          icon: Icons.error_outline,
          title: 'Xatolik yuz berdi',
          message: '$e',
          iconColor: AppTheme.colorsOf(context).danger,
          actionLabel: 'Qayta urinish',
          onAction: () => ref.invalidate(posSummaryProvider),
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
    final cs = Theme.of(context).colorScheme;
    final tt = Theme.of(context).textTheme;
    final appColors = AppTheme.colorsOf(context);

    return SingleChildScrollView(
      padding: const EdgeInsets.all(AppSpacing.lg),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // Sana banner
          AppCard(
            padding: const EdgeInsets.symmetric(
              horizontal: AppSpacing.lg,
              vertical: AppSpacing.md,
            ),
            color: cs.primaryContainer,
            borderColor: cs.primary.withValues(alpha: 0.2),
            child: Row(
              children: [
                Container(
                  width: 36,
                  height: 36,
                  decoration: BoxDecoration(
                    color: cs.primary.withValues(alpha: 0.15),
                    borderRadius:
                        BorderRadius.circular(AppSpacing.radiusSm),
                  ),
                  child: Icon(Icons.calendar_today,
                      size: AppSpacing.iconSm, color: cs.primary),
                ),
                const SizedBox(width: AppSpacing.md),
                Text(
                  _formatDate(summary.date),
                  style: tt.titleMedium?.copyWith(
                    fontWeight: FontWeight.w700,
                    color: cs.onPrimaryContainer,
                  ),
                ),
              ],
            ),
          ),

          const SizedBox(height: AppSpacing.lg),

          // Asosiy statistika — StatCard
          Row(
            children: [
              Expanded(
                child: StatCard(
                  icon: Icons.receipt_long,
                  label: 'Sotuvlar soni',
                  value: '${summary.totalSales} ta',
                  accentColor: cs.primary,
                ),
              ),
              const SizedBox(width: AppSpacing.md),
              Expanded(
                child: StatCard(
                  icon: Icons.account_balance_wallet_outlined,
                  label: 'Jami summa',
                  value: _fmtCompact(summary.totalAmount),
                  subtitle: _fmtAmount(summary.totalAmount),
                  accentColor: appColors.success,
                ),
              ),
            ],
          ),

          const SizedBox(height: AppSpacing.xl),

          // To'lov usuli bo'yicha
          if (summary.byPaymentMethod.isNotEmpty) ...[
            SectionHeader(
              title: "To'lov usullari bo'yicha",
              subtitle:
                  '${summary.byPaymentMethod.length} ta usul',
            ),
            const SizedBox(height: AppSpacing.md),
            ...summary.byPaymentMethod.entries.map(
              (e) => Padding(
                padding:
                    const EdgeInsets.only(bottom: AppSpacing.sm),
                child: _PaymentMethodCard(
                  method: e.key,
                  data: e.value,
                ),
              ),
            ),
          ],

          if (summary.totalSales == 0)
            Padding(
              padding: const EdgeInsets.symmetric(
                  vertical: AppSpacing.xxl),
              child: EmptyState(
                icon: Icons.receipt_long_outlined,
                title: 'Sotuv mavjud emas',
                message: 'Bu kun uchun sotuv amalga oshirilmagan',
                compact: true,
              ),
            ),

          const SizedBox(height: AppSpacing.xl),
        ],
      ),
    );
  }

  String _formatDate(String dateStr) {
    final dt = DateTime.tryParse(dateStr);
    if (dt == null) return dateStr;
    const months = [
      'yanvar', 'fevral', 'mart', 'aprel', 'may', 'iyun',
      'iyul', 'avgust', 'sentabr', 'oktabr', 'noyabr', 'dekabr',
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

  String _fmtCompact(double v) {
    if (v >= 1000000000) {
      return '${(v / 1000000000).toStringAsFixed(1)} mlrd';
    }
    if (v >= 1000000) {
      return '${(v / 1000000).toStringAsFixed(1)} mln';
    }
    if (v >= 1000) {
      return '${(v / 1000).toStringAsFixed(0)} ming';
    }
    return v.toStringAsFixed(0);
  }
}

// ---------------------------------------------------------------------------

class _PaymentMethodCard extends StatelessWidget {
  const _PaymentMethodCard({required this.method, required this.data});
  final String method;
  final PosSummaryByMethod data;

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    final tt = Theme.of(context).textTheme;
    final (icon, label, accentColor) = _methodInfo(context, method);

    return AppCard(
      padding: const EdgeInsets.all(AppSpacing.md),
      child: Row(
        children: [
          // Icon
          Container(
            width: 44,
            height: 44,
            decoration: BoxDecoration(
              color: accentColor.withValues(alpha: 0.1),
              borderRadius: BorderRadius.circular(AppSpacing.radiusSm),
            ),
            child: Icon(icon, color: accentColor, size: AppSpacing.iconMd),
          ),

          const SizedBox(width: AppSpacing.md),

          // Ism + soni
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  label,
                  style: tt.titleSmall?.copyWith(
                    fontWeight: FontWeight.w600,
                  ),
                ),
                Text(
                  '${data.count} ta sotuv',
                  style: tt.bodySmall?.copyWith(
                    color: cs.onSurfaceVariant,
                  ),
                ),
              ],
            ),
          ),

          // Summa
          Text(
            _fmtAmount(data.amount),
            style: tt.titleSmall?.copyWith(
              fontWeight: FontWeight.w700,
              color: accentColor,
            ),
          ),
        ],
      ),
    );
  }

  String _fmtAmount(double v) {
    if (v >= 1000000) return '${(v / 1000000).toStringAsFixed(1)} mln';
    if (v >= 1000) return '${(v / 1000).toStringAsFixed(0)} ming';
    return '${v.toStringAsFixed(0)} so\'m';
  }

  (IconData, String, Color) _methodInfo(
      BuildContext context, String method) {
    final appColors = AppTheme.colorsOf(context);
    return switch (method) {
      'cash' => (Icons.money, 'Naqd pul', appColors.success),
      'card' => (
          Icons.credit_card,
          'Karta',
          Theme.of(context).colorScheme.primary
        ),
      'transfer' => (
          Icons.account_balance_outlined,
          "O'tkazma",
          Theme.of(context).colorScheme.secondary
        ),
      _ => (
          Icons.payment,
          method,
          Theme.of(context).colorScheme.onSurfaceVariant
        ),
    };
  }
}

// ---------------------------------------------------------------------------
// Loading skeleton

class _SummaryLoadingSkeleton extends StatelessWidget {
  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    final base = cs.surfaceContainerHighest;

    Widget shimmer(double w, double h) => Container(
          width: w,
          height: h,
          decoration: BoxDecoration(
            color: base,
            borderRadius: BorderRadius.circular(AppSpacing.radiusSm),
          ),
        );

    return SingleChildScrollView(
      padding: const EdgeInsets.all(AppSpacing.lg),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // Sana shimmer
          AppCard(
            child: Row(
              children: [
                shimmer(36, 36),
                const SizedBox(width: AppSpacing.md),
                shimmer(160, 20),
              ],
            ),
          ),
          const SizedBox(height: AppSpacing.lg),

          // StatCard skeletonlar
          Row(
            children: [
              Expanded(child: StatCard(
                icon: Icons.receipt_long,
                label: '',
                value: '',
                isLoading: true,
              )),
              const SizedBox(width: AppSpacing.md),
              Expanded(child: StatCard(
                icon: Icons.account_balance_wallet_outlined,
                label: '',
                value: '',
                isLoading: true,
              )),
            ],
          ),

          const SizedBox(height: AppSpacing.xl),

          shimmer(180, 20),
          const SizedBox(height: AppSpacing.md),

          for (int i = 0; i < 3; i++) ...[
            AppCard(
              child: Row(
                children: [
                  shimmer(44, 44),
                  const SizedBox(width: AppSpacing.md),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        shimmer(100, 16),
                        const SizedBox(height: AppSpacing.xs),
                        shimmer(70, 12),
                      ],
                    ),
                  ),
                  shimmer(80, 18),
                ],
              ),
            ),
            const SizedBox(height: AppSpacing.sm),
          ],
        ],
      ),
    );
  }
}
