import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/theme/app_spacing.dart';
import '../../core/theme/app_theme.dart';
import '../../core/widgets/widgets.dart';
import '../auth/auth_providers.dart';
import '../auth/auth_repository.dart';
import 'finance_models.dart';
import 'finance_providers.dart';
import 'ledger_screen.dart';

/// Do'kon roli uchun moliya/balans ekrani.
///
/// Store foydalanuvchisi o'z do'konining balansini ko'radi.
/// storeId auth.user.branchId dan olinadi.
class StoreBalanceScreen extends ConsumerWidget {
  const StoreBalanceScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final authState = ref.watch(authNotifierProvider);
    final storeId = switch (authState) {
      AuthStateAuthenticated(:final user) => user.branchId,
      _ => null,
    };

    if (storeId == null) {
      return Scaffold(
        appBar: AppBar(title: const Text("Do'kon balansi")),
        body: const EmptyState(
          icon: Icons.store_mall_directory_outlined,
          title: "Do'kon ID topilmadi",
          message: "Akkauntga do'kon biriktirilmagan. "
              'Administrator bilan bog\'laning.',
        ),
      );
    }

    return Scaffold(
      appBar: AppBar(
        title: const Text("Do'kon balansi"),
        actions: [
          IconButton(
            icon: const Icon(Icons.refresh_outlined),
            tooltip: 'Yangilash',
            onPressed: () =>
                ref.read(financeBalanceProvider(storeId).notifier).reload(),
          ),
        ],
      ),
      body: SingleChildScrollView(
        padding: const EdgeInsets.all(AppSpacing.lg),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            SectionHeader(subtitle: _formattedDate(), title: "Do'kon balansi"),

            const SizedBox(height: AppSpacing.xl),

            _BalanceCard(storeId: storeId),

            const SizedBox(height: AppSpacing.lg),

            _LedgerCard(storeId: storeId),

            const SizedBox(height: AppSpacing.lg),

            _BalanceInfoCard(),
          ],
        ),
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
            padding: EdgeInsets.all(AppSpacing.xxxl),
            child: Center(child: CircularProgressIndicator()),
          ),
        ),
      FinanceBalanceError(:final message) => AppCard(
          color: appColors.dangerContainer.withValues(alpha: 0.3),
          borderColor: appColors.danger.withValues(alpha: 0.3),
          padding: const EdgeInsets.all(AppSpacing.lg),
          child: Column(
            children: [
              Icon(Icons.error_outline,
                  color: appColors.danger, size: AppSpacing.iconXl),
              const SizedBox(height: AppSpacing.md),
              Text(
                'Xatolik: $message',
                style: Theme.of(context).textTheme.bodyMedium?.copyWith(
                    color: appColors.danger),
                textAlign: TextAlign.center,
              ),
              const SizedBox(height: AppSpacing.md),
              FilledButton.icon(
                style: FilledButton.styleFrom(
                    backgroundColor: appColors.danger),
                onPressed: () =>
                    ref.read(financeBalanceProvider(storeId).notifier).reload(),
                icon: const Icon(Icons.refresh_outlined,
                    size: AppSpacing.iconXs),
                label: const Text('Qayta urinish'),
              ),
            ],
          ),
        ),
      FinanceBalanceLoaded(:final balance) =>
        _BalanceLoadedCard(balance: balance),
    };
  }
}

class _BalanceLoadedCard extends StatelessWidget {
  const _BalanceLoadedCard({required this.balance});
  final FinanceBalance balance;

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
        balance.isDebt ? Icons.trending_up : Icons.savings_outlined;

    return AppCard(
      color: bgColor,
      borderColor: borderColor,
      padding: const EdgeInsets.all(AppSpacing.xl),
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
                  borderRadius: BorderRadius.circular(AppSpacing.radiusMd),
                ),
                child: Icon(Icons.account_balance_wallet_outlined,
                    color: color, size: AppSpacing.iconMd),
              ),
              const SizedBox(width: AppSpacing.md),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      'Moliyaviy balans',
                      style: tt.titleMedium
                          ?.copyWith(fontWeight: FontWeight.w700),
                    ),
                    Row(
                      children: [
                        Icon(statusIcon, color: color, size: 14),
                        const SizedBox(width: AppSpacing.xs),
                        StatusBadge(
                          status: statusLabel,
                          variant: balance.isDebt
                              ? StatusVariant.danger
                              : StatusVariant.success,
                        ),
                      ],
                    ),
                  ],
                ),
              ),
            ],
          ),

          const SizedBox(height: AppSpacing.xl),

          // Asosiy qiymat — yirik
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

class _LedgerCard extends StatelessWidget {
  const _LedgerCard({required this.storeId});
  final String storeId;

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

// ---------------------------------------------------------------------------

class _BalanceInfoCard extends StatelessWidget {
  @override
  Widget build(BuildContext context) {
    final appColors = AppTheme.colorsOf(context);
    final tt = Theme.of(context).textTheme;

    return AppCard(
      color: appColors.infoContainer.withValues(alpha: 0.25),
      borderColor: appColors.info.withValues(alpha: 0.25),
      padding: const EdgeInsets.all(AppSpacing.md),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Icon(Icons.info_outline,
              color: appColors.info, size: AppSpacing.iconSm),
          const SizedBox(width: AppSpacing.sm),
          Expanded(
            child: Text(
              'Balans server tomonida hisoblangan. '
              'Muammolar yuzaga kelganda administrator bilan bog\'laning.',
              style: tt.bodySmall?.copyWith(color: appColors.info),
            ),
          ),
        ],
      ),
    );
  }
}
