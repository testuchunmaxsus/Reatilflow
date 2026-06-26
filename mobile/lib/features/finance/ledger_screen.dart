import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
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

  void _openCreateForm() {
    showModalBottomSheet<void>(
      context: context,
      isScrollControlled: true,
      useSafeArea: true,
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(
          top: Radius.circular(AppSpacing.radiusXxl),
        ),
      ),
      builder: (_) => _CreateLedgerSheet(
        initialStoreId: _storeIdController.text.trim(),
        onSuccess: () {
          Navigator.of(context).pop();
          ref.read(ledgerNotifierProvider.notifier).reload();
        },
      ),
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
      floatingActionButton: FloatingActionButton.extended(
        onPressed: _openCreateForm,
        icon: const Icon(Icons.add),
        label: const Text('Yozuv qo\'shish'),
        tooltip: 'Yangi ledger yozuv yaratish',
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

class _LedgerEntryCard extends ConsumerWidget {
  const _LedgerEntryCard({required this.entry});
  final LedgerEntry entry;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
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

    final approveState = ref.watch(approveLedgerProvider(entry.id));
    final isApproving = approveState is ApproveLedgerLoading;
    final isApproved = entry.status == LedgerEntryStatus.approved ||
        approveState is ApproveLedgerSuccess;

    // Tasdiqlash muvaffaqiyatli bo'lganda ledgerni yangilash
    ref.listen<ApproveLedgerState>(
      approveLedgerProvider(entry.id),
      (_, next) {
        if (next is ApproveLedgerSuccess) {
          ref.read(ledgerNotifierProvider.notifier).reload();
        } else if (next is ApproveLedgerFailure) {
          ScaffoldMessenger.of(context).showSnackBar(
            SnackBar(
              content: Text('Xatolik: ${next.message}'),
              backgroundColor: appColors.danger,
            ),
          );
        }
      },
    );

    return AppCard(
      padding: const EdgeInsets.symmetric(
          horizontal: AppSpacing.md, vertical: AppSpacing.md),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
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
                        const SizedBox(width: AppSpacing.xs),
                        StatusBadge(
                          status: isApproved
                              ? LedgerEntryStatus.approved.label
                              : LedgerEntryStatus.pending.label,
                          variant: isApproved
                              ? StatusVariant.success
                              : StatusVariant.warning,
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
                      style:
                          tt.labelSmall?.copyWith(color: cs.onSurfaceVariant),
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

          // Tasdiqlash tugmasi — faqat pending holat uchun
          if (!isApproved) ...[
            const SizedBox(height: AppSpacing.sm),
            Align(
              alignment: Alignment.centerRight,
              child: isApproving
                  ? const SizedBox(
                      width: 20,
                      height: 20,
                      child: CircularProgressIndicator(strokeWidth: 2),
                    )
                  : FilledButton.tonalIcon(
                      onPressed: () => ref
                          .read(approveLedgerProvider(entry.id).notifier)
                          .approve(entry.id),
                      icon: const Icon(Icons.check_circle_outline,
                          size: AppSpacing.iconSm),
                      label: const Text('Tasdiqlash'),
                      style: FilledButton.styleFrom(
                        minimumSize: const Size(0, 32),
                        padding: const EdgeInsets.symmetric(
                            horizontal: AppSpacing.md, vertical: AppSpacing.xs),
                        textStyle: const TextStyle(fontSize: 12),
                      ),
                    ),
            ),
          ],
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

// ---------------------------------------------------------------------------
// Yangi ledger yozuv yaratish bottom-sheet

class _CreateLedgerSheet extends ConsumerStatefulWidget {
  const _CreateLedgerSheet({
    required this.onSuccess,
    this.initialStoreId,
  });

  final VoidCallback onSuccess;
  final String? initialStoreId;

  @override
  ConsumerState<_CreateLedgerSheet> createState() =>
      _CreateLedgerSheetState();
}

class _CreateLedgerSheetState extends ConsumerState<_CreateLedgerSheet> {
  final _formKey = GlobalKey<FormState>();
  late final TextEditingController _storeIdCtrl;
  late final TextEditingController _amountCtrl;
  final _refTypeCtrl = TextEditingController();
  final _refIdCtrl = TextEditingController();

  LedgerEntryType _type = LedgerEntryType.debit;
  String _currency = 'UZS';
  DateTime _validFrom = DateTime.now();

  static const _currencies = ['UZS', 'USD', 'EUR'];

  @override
  void initState() {
    super.initState();
    _storeIdCtrl = TextEditingController(text: widget.initialStoreId ?? '');
    _amountCtrl = TextEditingController();
  }

  @override
  void dispose() {
    _storeIdCtrl.dispose();
    _amountCtrl.dispose();
    _refTypeCtrl.dispose();
    _refIdCtrl.dispose();
    super.dispose();
  }

  Future<void> _pickDate() async {
    final picked = await showDatePicker(
      context: context,
      initialDate: _validFrom,
      firstDate: DateTime(2020),
      lastDate: DateTime.now().add(const Duration(days: 365)),
    );
    if (picked != null) setState(() => _validFrom = picked);
  }

  Future<void> _submit() async {
    if (!_formKey.currentState!.validate()) return;

    final request = CreateLedgerRequest(
      storeId: _storeIdCtrl.text.trim(),
      type: _type,
      amount: double.parse(_amountCtrl.text.trim()),
      currency: _currency,
      validFrom: _validFrom,
      refType: _refTypeCtrl.text.trim().isEmpty
          ? null
          : _refTypeCtrl.text.trim(),
      refId:
          _refIdCtrl.text.trim().isEmpty ? null : _refIdCtrl.text.trim(),
    );

    await ref.read(createLedgerProvider.notifier).create(request);
  }

  @override
  Widget build(BuildContext context) {
    final appColors = AppTheme.colorsOf(context);
    final cs = Theme.of(context).colorScheme;
    final tt = Theme.of(context).textTheme;

    ref.listen<CreateLedgerState>(createLedgerProvider, (_, next) {
      if (next is CreateLedgerSuccess) {
        widget.onSuccess();
      } else if (next is CreateLedgerFailure) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text('Xatolik: ${next.message}'),
            backgroundColor: appColors.danger,
          ),
        );
        ref.read(createLedgerProvider.notifier).reset();
      }
    });

    final createState = ref.watch(createLedgerProvider);
    final isLoading = createState is CreateLedgerLoading;

    return Padding(
      padding: EdgeInsets.only(
        left: AppSpacing.lg,
        right: AppSpacing.lg,
        top: AppSpacing.lg,
        bottom: MediaQuery.of(context).viewInsets.bottom + AppSpacing.xl,
      ),
      child: Form(
        key: _formKey,
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            // Tutqich
            Center(
              child: Container(
                width: 40,
                height: 4,
                margin: const EdgeInsets.only(bottom: AppSpacing.lg),
                decoration: BoxDecoration(
                  color: cs.outlineVariant,
                  borderRadius: BorderRadius.circular(AppSpacing.radiusFull),
                ),
              ),
            ),

            Text(
              'Yangi ledger yozuv',
              style:
                  tt.titleMedium?.copyWith(fontWeight: FontWeight.w700),
            ),
            const SizedBox(height: AppSpacing.lg),

            // Do'kon UUID
            TextFormField(
              controller: _storeIdCtrl,
              decoration: const InputDecoration(
                labelText: "Do'kon UUID *",
                hintText: '019012ab-...',
                prefixIcon: Icon(Icons.store_outlined),
              ),
              validator: (v) =>
                  (v == null || v.trim().isEmpty) ? 'Majburiy maydon' : null,
              textInputAction: TextInputAction.next,
            ),
            const SizedBox(height: AppSpacing.md),

            // Tur: Debit / Kredit
            Row(
              children: [
                Text('Tur:', style: tt.bodyMedium),
                const SizedBox(width: AppSpacing.md),
                _TypeToggle(
                  selected: _type,
                  onChanged: (t) => setState(() => _type = t),
                ),
              ],
            ),
            const SizedBox(height: AppSpacing.md),

            // Miqdor + valyuta
            Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Expanded(
                  flex: 3,
                  child: TextFormField(
                    controller: _amountCtrl,
                    decoration: const InputDecoration(
                      labelText: 'Miqdor *',
                      hintText: '0.00',
                      prefixIcon: Icon(Icons.attach_money_outlined),
                    ),
                    keyboardType: const TextInputType.numberWithOptions(
                        decimal: true),
                    inputFormatters: [
                      FilteringTextInputFormatter.allow(
                          RegExp(r'^\d+\.?\d{0,2}')),
                    ],
                    validator: (v) {
                      if (v == null || v.trim().isEmpty) {
                        return 'Majburiy';
                      }
                      final d = double.tryParse(v.trim());
                      if (d == null || d <= 0) return 'Musbat son kiriting';
                      return null;
                    },
                    textInputAction: TextInputAction.next,
                  ),
                ),
                const SizedBox(width: AppSpacing.sm),
                Expanded(
                  flex: 2,
                  child: DropdownButtonFormField<String>(
                    // ignore: deprecated_member_use
                    value: _currency,
                    decoration: const InputDecoration(labelText: 'Valyuta'),
                    items: _currencies
                        .map((c) => DropdownMenuItem(
                              value: c,
                              child: Text(c),
                            ))
                        .toList(),
                    onChanged: (v) {
                      if (v != null) setState(() => _currency = v);
                    },
                  ),
                ),
              ],
            ),
            const SizedBox(height: AppSpacing.md),

            // Sana (valid_from)
            InkWell(
              onTap: _pickDate,
              borderRadius: BorderRadius.circular(AppSpacing.radiusMd),
              child: InputDecorator(
                decoration: const InputDecoration(
                  labelText: 'Sana (valid_from) *',
                  prefixIcon: Icon(Icons.calendar_today_outlined),
                ),
                child: Text(
                  '${_validFrom.day.toString().padLeft(2, '0')}.'
                  '${_validFrom.month.toString().padLeft(2, '0')}.'
                  '${_validFrom.year}',
                  style: tt.bodyMedium,
                ),
              ),
            ),
            const SizedBox(height: AppSpacing.md),

            // Ref type (ixtiyoriy)
            TextFormField(
              controller: _refTypeCtrl,
              decoration: const InputDecoration(
                labelText: 'Ref turi (ixtiyoriy)',
                hintText: 'order | delivery | ...',
                prefixIcon: Icon(Icons.link_outlined),
              ),
              textInputAction: TextInputAction.next,
            ),
            const SizedBox(height: AppSpacing.md),

            // Ref ID (ixtiyoriy)
            TextFormField(
              controller: _refIdCtrl,
              decoration: const InputDecoration(
                labelText: 'Ref ID (ixtiyoriy)',
                hintText: 'UUID yoki raqam',
                prefixIcon: Icon(Icons.tag_outlined),
              ),
              textInputAction: TextInputAction.done,
              onFieldSubmitted: (_) => _submit(),
            ),
            const SizedBox(height: AppSpacing.xl),

            // Yuborish tugmasi
            SizedBox(
              width: double.infinity,
              height: AppSpacing.buttonHeight,
              child: FilledButton.icon(
                onPressed: isLoading ? null : _submit,
                icon: isLoading
                    ? const SizedBox(
                        width: 18,
                        height: 18,
                        child: CircularProgressIndicator(
                            strokeWidth: 2, color: Colors.white),
                      )
                    : const Icon(Icons.save_outlined),
                label: Text(isLoading ? 'Saqlanmoqda...' : 'Saqlash'),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

// ---------------------------------------------------------------------------

class _TypeToggle extends StatelessWidget {
  const _TypeToggle({
    required this.selected,
    required this.onChanged,
  });

  final LedgerEntryType selected;
  final ValueChanged<LedgerEntryType> onChanged;

  @override
  Widget build(BuildContext context) {
    return Row(
      children: LedgerEntryType.values.map((t) {
        final appColors = AppTheme.colorsOf(context);
        final isSelected = selected == t;
        final color =
            t == LedgerEntryType.debit ? appColors.danger : appColors.success;

        return Padding(
          padding: const EdgeInsets.only(right: AppSpacing.xs),
          child: ChoiceChip(
            label: Text(t.label),
            selected: isSelected,
            selectedColor: color.withValues(alpha: 0.15),
            side: BorderSide(
              color: isSelected ? color : Theme.of(context).colorScheme.outline,
            ),
            labelStyle: TextStyle(
              color: isSelected
                  ? color
                  : Theme.of(context).colorScheme.onSurfaceVariant,
              fontWeight:
                  isSelected ? FontWeight.w600 : FontWeight.w400,
            ),
            onSelected: (_) => onChanged(t),
          ),
        );
      }).toList(),
    );
  }
}
