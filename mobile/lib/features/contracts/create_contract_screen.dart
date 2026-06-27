import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/theme/app_spacing.dart';
import '../../core/widgets/widgets.dart';
import '../home/sync_providers.dart';
import 'contract_models.dart';
import 'contract_providers.dart';

/// Shartnoma tuzish ekrani (agent uchun).
///
/// Oqim:
///   - storeId URL parametridan (majburiy).
///   - Agent shartnoma raqami, valid_from, valid_to kiritadi.
///   - supplier_enterprise_id YUBORILMAYDI — server agent tokenidan aniqlaydi.
///   - outbox `contract.create` yoziladi → sync.
class CreateContractScreen extends ConsumerStatefulWidget {
  const CreateContractScreen({super.key, required this.storeId});
  final String storeId;

  @override
  ConsumerState<CreateContractScreen> createState() =>
      _CreateContractScreenState();
}

class _CreateContractScreenState extends ConsumerState<CreateContractScreen> {
  final _formKey = GlobalKey<FormState>();
  final _numberController = TextEditingController();

  DateTime _validFrom = DateTime.now();
  DateTime _validTo = DateTime.now().add(const Duration(days: 365));
  bool _submitting = false;

  @override
  void dispose() {
    _numberController.dispose();
    super.dispose();
  }

  Future<void> _pickDate({required bool isFrom}) async {
    final initial = isFrom ? _validFrom : _validTo;
    final firstDate = isFrom ? DateTime(2020) : _validFrom;
    final lastDate = DateTime(2099);

    final picked = await showDatePicker(
      context: context,
      initialDate: initial,
      firstDate: firstDate,
      lastDate: lastDate,
      helpText: isFrom ? "Shartnoma boshlanishi" : "Shartnoma tugashi",
    );
    if (picked == null) return;
    setState(() {
      if (isFrom) {
        _validFrom = picked;
        // valid_to valid_from'dan oldin bo'lmasin
        if (_validTo.isBefore(_validFrom)) {
          _validTo = _validFrom.add(const Duration(days: 365));
        }
      } else {
        _validTo = picked;
      }
    });
  }

  Future<void> _submit() async {
    if (!_formKey.currentState!.validate()) return;

    setState(() => _submitting = true);

    try {
      final request = CreateContractRequest(
        storeId: widget.storeId,
        number: _numberController.text.trim(),
        validFrom: _validFrom,
        validTo: _validTo,
      );

      await ref
          .read(createContractProvider.notifier)
          .create(request);

      final state = ref.read(createContractProvider);
      if (state is CreateContractSuccess) {
        // Sync trigger (background)
        unawaited(ref.read(syncNotifierProvider.notifier).triggerSync());

        if (!mounted) return;
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: const Text(
                "Shartnoma yuborildi. Tarmoq bo'lganda qayta ishlanadi."),
            backgroundColor: Theme.of(context).colorScheme.primary,
            behavior: SnackBarBehavior.floating,
            shape: RoundedRectangleBorder(
              borderRadius: BorderRadius.circular(AppSpacing.radiusMd),
            ),
          ),
        );
        Navigator.of(context).pop(true);
      } else if (state is CreateContractFailure) {
        if (!mounted) return;
        _showError(state.message);
      }
    } on Exception catch (e) {
      if (!mounted) return;
      _showError(e.toString());
    } finally {
      if (mounted) setState(() => _submitting = false);
      ref.read(createContractProvider.notifier).reset();
    }
  }

  void _showError(String message) {
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text('Xatolik: $message'),
        backgroundColor: Theme.of(context).colorScheme.error,
        behavior: SnackBarBehavior.floating,
      ),
    );
  }

  String _fmtDate(DateTime dt) =>
      '${dt.day.toString().padLeft(2, '0')}.'
      '${dt.month.toString().padLeft(2, '0')}.'
      '${dt.year}';

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    final tt = Theme.of(context).textTheme;

    return Scaffold(
      appBar: AppBar(
        title: const Text('Shartnoma tuzish'),
        actions: [
          if (_submitting)
            Padding(
              padding: const EdgeInsets.all(AppSpacing.md),
              child: SizedBox(
                width: 20,
                height: 20,
                child: CircularProgressIndicator(
                  strokeWidth: 2,
                  color: cs.primary,
                ),
              ),
            )
          else
            TextButton(
              onPressed: _submit,
              child: const Text('Saqlash'),
            ),
        ],
      ),
      body: SingleChildScrollView(
        padding: const EdgeInsets.all(AppSpacing.lg),
        child: Form(
          key: _formKey,
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              // Ma'lumot banneri
              AppCard(
                padding: const EdgeInsets.all(AppSpacing.md),
                color: cs.primaryContainer.withValues(alpha: 0.4),
                outlined: false,
                child: Row(
                  children: [
                    Icon(Icons.info_outline,
                        color: cs.primary, size: AppSpacing.iconMd),
                    const SizedBox(width: AppSpacing.md),
                    Expanded(
                      child: Text(
                        'Shartnoma yaratilgandan so\'ng korxona '
                        'tomonidan tasdiqlash kerak bo\'ladi.',
                        style: tt.bodySmall?.copyWith(color: cs.primary),
                      ),
                    ),
                  ],
                ),
              ),

              const SizedBox(height: AppSpacing.lg),

              // Asosiy forma
              AppCard(
                padding: const EdgeInsets.all(AppSpacing.lg),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    const SectionHeader(title: "Shartnoma ma'lumotlari"),
                    const SizedBox(height: AppSpacing.md),

                    // Shartnoma raqami
                    TextFormField(
                      controller: _numberController,
                      textCapitalization: TextCapitalization.characters,
                      decoration: const InputDecoration(
                        labelText: 'Shartnoma raqami *',
                        hintText: 'Masalan: SH-2025-001',
                        prefixIcon: Icon(Icons.document_scanner_outlined),
                      ),
                      validator: (v) {
                        if (v == null || v.trim().isEmpty) {
                          return 'Shartnoma raqami majburiy';
                        }
                        if (v.trim().length < 3) {
                          return 'Kamida 3 ta belgi kiriting';
                        }
                        return null;
                      },
                    ),

                    const SizedBox(height: AppSpacing.lg),

                    const SectionHeader(title: 'Amal qilish muddati'),
                    const SizedBox(height: AppSpacing.md),

                    // Sana tanlovlar
                    Row(
                      children: [
                        Expanded(
                          child: _DatePickerTile(
                            label: 'Boshlanishi',
                            date: _validFrom,
                            formatted: _fmtDate(_validFrom),
                            onTap: () => _pickDate(isFrom: true),
                          ),
                        ),
                        const SizedBox(width: AppSpacing.sm),
                        Expanded(
                          child: _DatePickerTile(
                            label: 'Tugashi',
                            date: _validTo,
                            formatted: _fmtDate(_validTo),
                            onTap: () => _pickDate(isFrom: false),
                          ),
                        ),
                      ],
                    ),

                    // Muddat hisoblash
                    const SizedBox(height: AppSpacing.sm),
                    _DurationBadge(from: _validFrom, to: _validTo),
                  ],
                ),
              ),

              const SizedBox(height: AppSpacing.lg),

              // Eslatma: supplier server-avtoritar
              AppCard(
                padding: const EdgeInsets.all(AppSpacing.md),
                color: cs.surfaceContainerHighest,
                outlined: false,
                child: Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Icon(Icons.lock_outline,
                        color: cs.onSurfaceVariant,
                        size: AppSpacing.iconSm),
                    const SizedBox(width: AppSpacing.sm),
                    Expanded(
                      child: Text(
                        'Korxona ma\'lumotlari server tomonidan '
                        'avtomatik to\'ldiriladi.',
                        style: tt.bodySmall
                            ?.copyWith(color: cs.onSurfaceVariant),
                      ),
                    ),
                  ],
                ),
              ),

              const SizedBox(height: AppSpacing.xl),

              SizedBox(
                width: double.infinity,
                child: FilledButton.icon(
                  onPressed: _submitting ? null : _submit,
                  icon: _submitting
                      ? SizedBox(
                          width: 18,
                          height: 18,
                          child: CircularProgressIndicator(
                            strokeWidth: 2,
                            color: cs.onPrimary,
                          ),
                        )
                      : const Icon(Icons.handshake_outlined),
                  label: Text(
                    _submitting ? 'Yuborilmoqda...' : 'Shartnomani yuborish',
                  ),
                  style: FilledButton.styleFrom(
                    minimumSize:
                        const Size.fromHeight(AppSpacing.buttonHeight),
                  ),
                ),
              ),

              const SizedBox(height: AppSpacing.xl),
            ],
          ),
        ),
      ),
    );
  }
}

// ---------------------------------------------------------------------------

class _DatePickerTile extends StatelessWidget {
  const _DatePickerTile({
    required this.label,
    required this.date,
    required this.formatted,
    required this.onTap,
  });

  final String label;
  final DateTime date;
  final String formatted;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    final tt = Theme.of(context).textTheme;

    return AppCard(
      onTap: onTap,
      padding: const EdgeInsets.all(AppSpacing.md),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            label,
            style: tt.labelSmall?.copyWith(color: cs.onSurfaceVariant),
          ),
          const SizedBox(height: AppSpacing.xs),
          Row(
            children: [
              Icon(Icons.calendar_today_outlined,
                  size: AppSpacing.iconSm, color: cs.primary),
              const SizedBox(width: AppSpacing.xs),
              Text(
                formatted,
                style: tt.bodyMedium?.copyWith(
                  fontWeight: FontWeight.w600,
                  color: cs.primary,
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }
}

class _DurationBadge extends StatelessWidget {
  const _DurationBadge({required this.from, required this.to});
  final DateTime from;
  final DateTime to;

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    final tt = Theme.of(context).textTheme;

    final days = to.difference(from).inDays;
    final isValid = days >= 0;
    final months = (days / 30).round();

    return Row(
      children: [
        Icon(
          isValid ? Icons.timelapse_outlined : Icons.error_outline,
          size: AppSpacing.iconSm,
          color: isValid ? cs.onSurfaceVariant : cs.error,
        ),
        const SizedBox(width: AppSpacing.xs),
        Text(
          isValid
              ? 'Muddat: $days kun (~$months oy)'
              : "Noto'g'ri muddat",
          style: tt.bodySmall?.copyWith(
            color: isValid ? cs.onSurfaceVariant : cs.error,
          ),
        ),
      ],
    );
  }
}

/// Fire-and-forget helper (dart:async import yo'q)
void unawaited(Future<void> future) => future.ignore();
