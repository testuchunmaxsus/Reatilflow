import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/theme/app_spacing.dart';
import '../../core/theme/app_theme.dart';
import '../../core/widgets/widgets.dart';
import 'finance_models.dart';
import 'finance_providers.dart';

/// Ledger yozuvlari ro'yxati ekrani.
///
/// Filtrlar: do'kon UUID, yozuv turi (debit | credit | hammasi).
/// Backend: GET /finance/ledger (STOCK_FINANCE.md §2.5).
class LedgerScreen extends ConsumerStatefulWidget {
  const LedgerScreen({super.key, this.initialStoreId});
  final String? initialStoreId;

  @override
  ConsumerState<LedgerScreen> createState() => _LedgerScreenState();
}

class _LedgerScreenState extends ConsumerState<LedgerScreen> {
  late final TextEditingController _storeIdController;
  String? _typeFilter;

  @override
  void initState() {
    super.initState();
    _storeIdController =
        TextEditingController(text: widget.initialStoreId ?? '');
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (widget.initialStoreId != null && widget.initialStoreId!.isNotEmpty) {
        ref
            .read(ledgerNotifierProvider.notifier)
            .load(storeId: widget.initialStoreId);
      }
    });
  }

  @override
  void dispose() {
    _storeIdController.dispose();
    super.dispose();
  }

  void _applyFilters() {
    final storeId = _storeIdController.text.trim();
    ref.read(ledgerNotifierProvider.notifier).load(
          storeId: storeId.isEmpty ? null : storeId,
          entryType: _typeFilter,
        );
  }

  @override
  Widget build(BuildContext context) {
    final ledgerState = ref.watch(ledgerNotifierProvider);
    final cs = Theme.of(context).colorScheme;

    return Scaffold(
      appBar: AppBar(
        title: const Text('Buxgalteriya yozuvlari'),
        actions: [
          IconButton(
            icon: const Icon(Icons.refresh_outlined),
            tooltip: 'Yangilash',
            onPressed: () =>
                ref.read(ledgerNotifierProvider.notifier).reload(),
          ),
        ],
      ),
      body: Column(
        children: [
          _FilterPanel(
            controller: _storeIdController,
            typeFilter: _typeFilter,
            onTypeChanged: (v) {
              setState(() => _typeFilter = v);
              _applyFilters();
            },
            onSearch: _applyFilters,
          ),

          Divider(height: 1, color: cs.outlineVariant),

          Expanded(
            child: _LedgerBody(state: ledgerState),
          ),
        ],
      ),
    );
  }
}

// ---------------------------------------------------------------------------

class _FilterPanel extends StatelessWidget {
  const _FilterPanel({
    required this.controller,
    required this.typeFilter,
    required this.onTypeChanged,
    required this.onSearch,
  });

  final TextEditingController controller;
  final String? typeFilter;
  final ValueChanged<String?> onTypeChanged;
  final VoidCallback onSearch;

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    final appColors = AppTheme.colorsOf(context);

    return Padding(
      padding: const EdgeInsets.fromLTRB(
          AppSpacing.lg, AppSpacing.md, AppSpacing.lg, AppSpacing.sm),
      child: Column(
        children: [
          Row(
            children: [
              Expanded(
                child: TextField(
                  controller: controller,
                  decoration: const InputDecoration(
                    labelText: "Do'kon UUID (ixtiyoriy)",
                    hintText: '019012ab-...',
                    prefixIcon: Icon(Icons.store_outlined),
                  ),
                  onSubmitted: (_) => onSearch(),
                ),
              ),
              const SizedBox(width: AppSpacing.sm),
              FilledButton(
                onPressed: onSearch,
                child: const Text('Filtr'),
              ),
            ],
          ),
          const SizedBox(height: AppSpacing.sm),
          Row(
            children: [
              _TypeChip(
                label: 'Hammasi',
                selected: typeFilter == null,
                onTap: () => onTypeChanged(null),
              ),
              const SizedBox(width: AppSpacing.xs),
              _TypeChip(
                label: 'Debet',
                selected: typeFilter == 'debit',
                color: appColors.danger,
                onTap: () => onTypeChanged('debit'),
              ),
              const SizedBox(width: AppSpacing.xs),
              _TypeChip(
                label: 'Kredit',
                selected: typeFilter == 'credit',
                color: appColors.success,
                onTap: () => onTypeChanged('credit'),
              ),
            ],
          ),
        ],
      ),
    );
  }
}

class _TypeChip extends StatelessWidget {
  const _TypeChip({
    required this.label,
    required this.selected,
    required this.onTap,
    this.color,
  });

  final String label;
  final bool selected;
  final VoidCallback onTap;
  final Color? color;

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    final tt = Theme.of(context).textTheme;
    final activeColor = color ?? cs.primary;

    return GestureDetector(
      onTap: onTap,
      child: AnimatedContainer(
        duration: const Duration(milliseconds: 150),
        padding: const EdgeInsets.symmetric(
            horizontal: AppSpacing.md, vertical: AppSpacing.xs),
        decoration: BoxDecoration(
          color: selected
              ? activeColor.withValues(alpha: 0.12)
              : cs.surfaceContainerHighest,
          borderRadius: BorderRadius.circular(AppSpacing.radiusFull),
          border: Border.all(
            color: selected ? activeColor : cs.outlineVariant,
          ),
        ),
        child: Text(
          label,
          style: tt.labelMedium?.copyWith(
            fontWeight: selected ? FontWeight.w600 : FontWeight.w400,
            color: selected ? activeColor : cs.onSurfaceVariant,
          ),
        ),
      ),
    );
  }
}

// ---------------------------------------------------------------------------

class _LedgerBody extends StatelessWidget {
  const _LedgerBody({required this.state});
  final LedgerState state;

  @override
  Widget build(BuildContext context) {
    return switch (state) {
      LedgerLoading() => Center(
          child: CircularProgressIndicator(
              color: Theme.of(context).colorScheme.primary),
        ),
      LedgerError(:final message) => EmptyState(
          icon: Icons.error_outline,
          title: 'Xatolik yuz berdi',
          message: message,
        ),
      LedgerLoaded(:final page) => page.items.isEmpty
          ? const EmptyState(
              icon: Icons.receipt_long_outlined,
              title: 'Yozuvlar topilmadi',
              message: "Filtr shartlariga mos yozuv yo'q.",
            )
          : _LedgerList(page: page),
    };
  }
}

class _LedgerList extends StatelessWidget {
  const _LedgerList({required this.page});
  final LedgerPage page;

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    final tt = Theme.of(context).textTheme;

    return Column(
      children: [
        Padding(
          padding: const EdgeInsets.symmetric(
              horizontal: AppSpacing.lg, vertical: AppSpacing.sm),
          child: Row(
            children: [
              Text(
                'Jami: ${page.total} yozuv',
                style: tt.bodySmall?.copyWith(color: cs.onSurfaceVariant),
              ),
            ],
          ),
        ),
        Expanded(
          child: ListView.separated(
            padding: const EdgeInsets.fromLTRB(
                AppSpacing.lg, 0, AppSpacing.lg, AppSpacing.xl),
            itemCount: page.items.length,
            separatorBuilder: (_, __) =>
                const SizedBox(height: AppSpacing.sm),
            itemBuilder: (context, index) {
              return _LedgerEntryCard(entry: page.items[index]);
            },
          ),
        ),
      ],
    );
  }
}

class _LedgerEntryCard extends StatelessWidget {
  const _LedgerEntryCard({required this.entry});
  final LedgerEntry entry;

  @override
  Widget build(BuildContext context) {
    final appColors = AppTheme.colorsOf(context);
    final tt = Theme.of(context).textTheme;
    final cs = Theme.of(context).colorScheme;

    final isDebit = entry.type == LedgerEntryType.debit;
    final color = isDebit ? appColors.danger : appColors.success;
    final bgColor = isDebit
        ? appColors.dangerContainer.withValues(alpha: 0.15)
        : appColors.successContainer.withValues(alpha: 0.15);
    final icon = isDebit ? Icons.arrow_upward : Icons.arrow_downward;
    final sign = isDebit ? '+' : '-';

    return AppCard(
      padding: const EdgeInsets.symmetric(
          horizontal: AppSpacing.md, vertical: AppSpacing.md),
      child: Row(
        children: [
          Container(
            width: 40,
            height: 40,
            decoration: BoxDecoration(
              color: bgColor,
              borderRadius: BorderRadius.circular(AppSpacing.radiusSm),
            ),
            child: Icon(icon, color: color, size: AppSpacing.iconSm),
          ),
          const SizedBox(width: AppSpacing.md),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  children: [
                    StatusBadge(
                      status: entry.type.label,
                      variant: isDebit
                          ? StatusVariant.danger
                          : StatusVariant.success,
                    ),
                    if (entry.refType != null) ...[
                      const SizedBox(width: AppSpacing.xs),
                      Text(
                        entry.refType!,
                        style: tt.labelSmall
                            ?.copyWith(color: cs.onSurfaceVariant),
                      ),
                    ],
                  ],
                ),
                const SizedBox(height: 2),
                Text(
                  _fmtDate(entry.entryDate),
                  style: tt.labelSmall?.copyWith(color: cs.onSurfaceVariant),
                ),
              ],
            ),
          ),
          Text(
            '$sign${_fmtAmount(entry.amountValue)} ${entry.currency}',
            style: tt.titleSmall?.copyWith(
              color: color,
              fontWeight: FontWeight.w700,
            ),
          ),
        ],
      ),
    );
  }

  String _fmtAmount(double amount) {
    final formatted = amount.toStringAsFixed(2);
    final parts = formatted.split('.');
    final intPart = parts[0];
    final decPart = parts[1];
    final buffer = StringBuffer();
    for (int i = 0; i < intPart.length; i++) {
      if (i > 0 && (intPart.length - i) % 3 == 0) buffer.write(' ');
      buffer.write(intPart[i]);
    }
    return '$buffer.$decPart';
  }

  String _fmtDate(DateTime dt) =>
      '${dt.day.toString().padLeft(2, '0')}.${dt.month.toString().padLeft(2, '0')}.${dt.year} '
      '${dt.hour.toString().padLeft(2, '0')}:${dt.minute.toString().padLeft(2, '0')}';
}
