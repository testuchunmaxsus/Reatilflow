import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/theme/app_spacing.dart';
import '../../core/theme/app_theme.dart';
import '../../core/widgets/widgets.dart';
import 'finance_models.dart';
import 'finance_providers.dart';
import 'ledger_screen.dart';

/// Buxgalter moliya ekrani — do'kon balansi + ledger-ga o'tish.
///
/// Ekranda:
///   - Do'kon ID maydoni (buxgalter barcha do'konlarga kirish huquqiga ega).
///   - Tanlangan do'kon moliyaviy balansi.
///   - Ledger ro'yxatiga o'tish tugmasi.
class FinanceScreen extends ConsumerStatefulWidget {
  const FinanceScreen({super.key});

  @override
  ConsumerState<FinanceScreen> createState() => _FinanceScreenState();
}

class _FinanceScreenState extends ConsumerState<FinanceScreen> {
  final _storeIdController = TextEditingController();
  String? _activeStoreId;

  @override
  void dispose() {
    _storeIdController.dispose();
    super.dispose();
  }

  void _search() {
    final id = _storeIdController.text.trim();
    if (id.isEmpty) return;
    setState(() => _activeStoreId = id);
  }

  @override
  Widget build(BuildContext context) {
    final tt = Theme.of(context).textTheme;
    final cs = Theme.of(context).colorScheme;

    return SingleChildScrollView(
      padding: const EdgeInsets.all(AppSpacing.lg),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // Sahifa sarlavhasi
          SectionHeader(
            title: 'Moliya',
            subtitle: _formattedDate(),
          ),

          const SizedBox(height: AppSpacing.xl),

          // Do'kon qidirish
          _StoreSearchField(
            controller: _storeIdController,
            onSearch: _search,
          ),

          const SizedBox(height: AppSpacing.lg),

          // Balans kartasi
          if (_activeStoreId != null) ...[
            _BalanceCard(storeId: _activeStoreId!),
            const SizedBox(height: AppSpacing.lg),
          ] else
            AppCard(
              color: cs.surfaceContainerHighest.withValues(alpha: 0.5),
              padding: const EdgeInsets.all(AppSpacing.xl),
              child: Center(
                child: Text(
                  "Do'kon UUID ni kiriting va balansni ko'ring",
                  textAlign: TextAlign.center,
                  style: tt.bodyMedium?.copyWith(color: cs.onSurfaceVariant),
                ),
              ),
            ),

          const SizedBox(height: AppSpacing.sm),

          // Ledger ro'yxatiga o'tish
          _LedgerNavigationCard(storeId: _activeStoreId),
        ],
      ),
    );
  }

  String _formattedDate() {
    final now = DateTime.now();
    const months = [
      'yanvar', 'fevral', 'mart', 'aprel', 'may', 'iyun',
      'iyul', 'avgust', 'sentabr', 'oktabr', 'noyabr', 'dekabr',
    ];
    return '${now.day} ${months[now.month - 1]} ${now.year}';
  }
}

// ---------------------------------------------------------------------------

class _StoreSearchField extends StatelessWidget {
  const _StoreSearchField({
    required this.controller,
    required this.onSearch,
  });

  final TextEditingController controller;
  final VoidCallback onSearch;

  @override
  Widget build(BuildContext context) {
    return Row(
      children: [
        Expanded(
          child: TextField(
            controller: controller,
            decoration: const InputDecoration(
              labelText: "Do'kon UUID",
              hintText: '019012ab-...',
              prefixIcon: Icon(Icons.store_outlined),
            ),
            onSubmitted: (_) => onSearch(),
          ),
        ),
        const SizedBox(width: AppSpacing.sm),
        FilledButton.icon(
          onPressed: onSearch,
          icon: const Icon(Icons.search, size: AppSpacing.iconSm),
          label: const Text('Izla'),
        ),
      ],
    );
  }
}

// ---------------------------------------------------------------------------

class _BalanceCard extends ConsumerWidget {
  const _BalanceCard({required this.storeId});
  final String storeId;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final state = ref.watch(financeBalanceProvider(storeId));
    final appColors = AppTheme.colorsOf(context);

    return switch (state) {
      FinanceBalanceLoading() => const AppCard(
          child: Padding(
            padding: EdgeInsets.all(AppSpacing.xl),
            child: Center(child: CircularProgressIndicator()),
          ),
        ),
      FinanceBalanceError(:final message) => AppCard(
          color: appColors.dangerContainer.withValues(alpha: 0.3),
          borderColor: appColors.danger.withValues(alpha: 0.3),
          padding: const EdgeInsets.all(AppSpacing.lg),
          child: Row(
            children: [
              Icon(Icons.error_outline, color: appColors.danger),
              const SizedBox(width: AppSpacing.md),
              Expanded(
                child: Text(
                  'Xatolik: $message',
                  style: Theme.of(context)
                      .textTheme
                      .bodySmall
                      ?.copyWith(color: appColors.danger),
                ),
              ),
              TextButton(
                onPressed: () =>
                    ref.read(financeBalanceProvider(storeId).notifier).reload(),
                child: const Text('Qayta'),
              ),
            ],
          ),
        ),
      FinanceBalanceLoaded(:final balance) => _BalanceLoadedCard(
          balance: balance,
          onRefresh: () =>
              ref.read(financeBalanceProvider(storeId).notifier).reload(),
        ),
    };
  }
}

class _BalanceLoadedCard extends StatelessWidget {
  const _BalanceLoadedCard({
    required this.balance,
    required this.onRefresh,
  });

  final FinanceBalance balance;
  final VoidCallback onRefresh;

  @override
  Widget build(BuildContext context) {
    final appColors = AppTheme.colorsOf(context);
    final tt = Theme.of(context).textTheme;
    final cs = Theme.of(context).colorScheme;

    final color = balance.isDebt ? appColors.danger : appColors.success;
    final bgColor = balance.isDebt
        ? appColors.dangerContainer.withValues(alpha: 0.35)
        : appColors.successContainer.withValues(alpha: 0.35);
    final borderColor = color.withValues(alpha: 0.3);
    final statusLabel = balance.isDebt ? 'Qarzdorlik' : 'Kredit qoldiq';
    final statusIcon =
        balance.isDebt ? Icons.trending_up : Icons.trending_down;

    return AppCard(
      color: bgColor,
      borderColor: borderColor,
      padding: const EdgeInsets.all(AppSpacing.lg),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Container(
                width: AppSpacing.iconLg + AppSpacing.md,
                height: AppSpacing.iconLg + AppSpacing.md,
                decoration: BoxDecoration(
                  color: color.withValues(alpha: 0.15),
                  borderRadius: BorderRadius.circular(AppSpacing.radiusSm),
                ),
                child: Icon(Icons.account_balance_wallet_outlined,
                    color: color, size: AppSpacing.iconMd),
              ),
              const SizedBox(width: AppSpacing.md),
              Expanded(
                child: Text(
                  'Moliyaviy balans',
                  style: tt.titleMedium?.copyWith(fontWeight: FontWeight.w600),
                ),
              ),
              IconButton(
                icon: Icon(Icons.refresh_outlined,
                    size: AppSpacing.iconSm, color: cs.onSurfaceVariant),
                tooltip: 'Yangilash',
                onPressed: onRefresh,
                padding: EdgeInsets.zero,
                constraints: const BoxConstraints(),
              ),
            ],
          ),
          const SizedBox(height: AppSpacing.lg),

          // Holat badge
          Row(
            children: [
              Icon(statusIcon, color: color, size: AppSpacing.iconXs),
              const SizedBox(width: AppSpacing.xs),
              StatusBadge(
                status: statusLabel,
                variant: balance.isDebt
                    ? StatusVariant.danger
                    : StatusVariant.success,
              ),
            ],
          ),
          const SizedBox(height: AppSpacing.sm),

          // Asosiy qiymat
          Text(
            '${_fmt(balance.balanceAmount)} ${balance.currency}',
            style: tt.headlineMedium?.copyWith(
              color: color,
              fontWeight: FontWeight.w700,
              letterSpacing: -0.5,
            ),
          ),

          const SizedBox(height: AppSpacing.md),
          Divider(color: color.withValues(alpha: 0.2), height: 1),
          const SizedBox(height: AppSpacing.sm),

          Text(
            "Do'kon: ${balance.storeId}",
            style: tt.labelSmall?.copyWith(color: cs.onSurfaceVariant),
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
          ),
          Text(
            'Yangilangan: ${_fmtDate(balance.lastRecalcAt)}',
            style: tt.labelSmall?.copyWith(color: cs.onSurfaceVariant),
          ),
        ],
      ),
    );
  }

  String _fmt(double amount) {
    final abs = amount.abs();
    final formatted = abs.toStringAsFixed(2);
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

class _LedgerNavigationCard extends StatelessWidget {
  const _LedgerNavigationCard({this.storeId});
  final String? storeId;

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    final tt = Theme.of(context).textTheme;

    return AppCard(
      onTap: () {
        Navigator.of(context).push(
          MaterialPageRoute<void>(
            builder: (_) => LedgerScreen(initialStoreId: storeId),
          ),
        );
      },
      padding: const EdgeInsets.all(AppSpacing.lg),
      child: Row(
        children: [
          Container(
            width: AppSpacing.iconLg + AppSpacing.md,
            height: AppSpacing.iconLg + AppSpacing.md,
            decoration: BoxDecoration(
              color: cs.primaryContainer,
              borderRadius: BorderRadius.circular(AppSpacing.radiusSm),
            ),
            child: Icon(Icons.receipt_long_outlined,
                color: cs.primary, size: AppSpacing.iconMd),
          ),
          const SizedBox(width: AppSpacing.md),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  'Buxgalteriya yozuvlari',
                  style: tt.titleSmall?.copyWith(fontWeight: FontWeight.w600),
                ),
                Text(
                  'Debet va kredit yozuvlarini ko\'rish',
                  style: tt.bodySmall?.copyWith(color: cs.onSurfaceVariant),
                ),
              ],
            ),
          ),
          Icon(Icons.chevron_right,
              color: cs.onSurfaceVariant, size: AppSpacing.iconSm),
        ],
      ),
    );
  }
}
