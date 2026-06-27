import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/theme/app_spacing.dart';
import '../../core/theme/app_theme.dart';
import '../../core/widgets/widgets.dart';
import 'contract_models.dart';
import 'contract_providers.dart';

/// Shartnomalar ro'yxati ekrani (agent uchun).
///
/// Online GET /contracts?store_id=... + offline pending outbox yozuvlari.
class ContractListScreen extends ConsumerWidget {
  const ContractListScreen({super.key, required this.storeId});
  final String storeId;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final cs = Theme.of(context).colorScheme;
    final state = ref.watch(contractListProvider(storeId));

    return Scaffold(
      appBar: AppBar(
        title: const Text('Shartnomalar'),
        actions: [
          IconButton(
            icon: const Icon(Icons.refresh_outlined),
            tooltip: 'Yangilash',
            onPressed: () =>
                ref.read(contractListProvider(storeId).notifier).load(),
          ),
        ],
      ),
      body: switch (state) {
        ContractListLoading() =>
          Center(child: CircularProgressIndicator(color: cs.primary)),
        ContractListError(:final message, :final pending) =>
          _ContractListBody(
            contracts: const [],
            pending: pending,
            errorMessage: message,
            storeId: storeId,
            onRetry: () =>
                ref.read(contractListProvider(storeId).notifier).load(),
          ),
        ContractListLoaded(:final contracts, :final pending) =>
          _ContractListBody(
            contracts: contracts,
            pending: pending,
            storeId: storeId,
          ),
      },
      floatingActionButton: FloatingActionButton.extended(
        onPressed: () =>
            context.push('/home/stores/$storeId/contracts/create'),
        icon: const Icon(Icons.add),
        label: const Text("Yangi shartnoma"),
      ),
    );
  }
}

class _ContractListBody extends StatelessWidget {
  const _ContractListBody({
    required this.contracts,
    required this.pending,
    required this.storeId,
    this.errorMessage,
    this.onRetry,
  });

  final List<Contract> contracts;
  final List<PendingContract> pending;
  final String storeId;
  final String? errorMessage;
  final VoidCallback? onRetry;

  @override
  Widget build(BuildContext context) {
    final hasContent =
        contracts.isNotEmpty || pending.isNotEmpty;

    if (!hasContent && errorMessage == null) {
      return EmptyState(
        icon: Icons.handshake_outlined,
        title: 'Shartnomalar yo\'q',
        message:
            'Bu do\'kon bilan hali shartnoma tuzilmagan. '
            'Yangi shartnoma yarating.',
        actionLabel: 'Shartnoma tuzish',
        onAction: () =>
            context.push('/home/stores/$storeId/contracts/create'),
      );
    }

    return ListView(
      padding: const EdgeInsets.all(AppSpacing.lg),
      children: [
        // Xato xabar (tarmoq yo'q, lekin pending bor)
        if (errorMessage != null) ...[
          _ErrorBanner(message: errorMessage!, onRetry: onRetry),
          const SizedBox(height: AppSpacing.md),
        ],

        // Pending outbox yozuvlari
        if (pending.isNotEmpty) ...[
          SectionHeader(
            title: 'Yuborilmoqda',
            subtitle: '${pending.length} ta kutilmoqda',
          ),
          const SizedBox(height: AppSpacing.sm),
          ...pending.map((p) => _PendingContractTile(contract: p)),
          const SizedBox(height: AppSpacing.lg),
        ],

        // Server shartnomalar
        if (contracts.isNotEmpty) ...[
          SectionHeader(
            title: 'Shartnomalar',
            subtitle: '${contracts.length} ta',
          ),
          const SizedBox(height: AppSpacing.sm),
          ...contracts.map((c) => _ContractTile(contract: c)),
        ],
      ],
    );
  }
}

class _ErrorBanner extends StatelessWidget {
  const _ErrorBanner({required this.message, this.onRetry});
  final String message;
  final VoidCallback? onRetry;

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    final tt = Theme.of(context).textTheme;

    return AppCard(
      padding: const EdgeInsets.all(AppSpacing.md),
      borderColor: cs.errorContainer,
      child: Row(
        children: [
          Icon(Icons.wifi_off_outlined,
              color: cs.error, size: AppSpacing.iconMd),
          const SizedBox(width: AppSpacing.md),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  'Tarmoq mavjud emas',
                  style: tt.labelMedium
                      ?.copyWith(fontWeight: FontWeight.w600, color: cs.error),
                ),
                Text(
                  'Pending shartnomalar ko\'rsatilmoqda.',
                  style: tt.bodySmall?.copyWith(color: cs.onSurfaceVariant),
                ),
              ],
            ),
          ),
          if (onRetry != null)
            TextButton(
                onPressed: onRetry, child: const Text('Qayta')),
        ],
      ),
    );
  }
}

String _fmtDate(DateTime dt) =>
    '${dt.day.toString().padLeft(2, '0')}.'
    '${dt.month.toString().padLeft(2, '0')}.'
    '${dt.year}';

class _ContractTile extends StatelessWidget {
  const _ContractTile({required this.contract});
  final Contract contract;

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    final tt = Theme.of(context).textTheme;
    final appColors = AppTheme.colorsOf(context);

    final (statusColor, statusBg) = switch (contract.status) {
      ContractStatus.active => (appColors.success, appColors.successContainer),
      ContractStatus.expired => (appColors.danger, appColors.dangerContainer),
      ContractStatus.pending => (appColors.warning, appColors.warningContainer),
      ContractStatus.cancelled => (cs.onSurfaceVariant, cs.surfaceContainerHighest),
    };

    return Padding(
      padding: const EdgeInsets.only(bottom: AppSpacing.sm),
      child: AppCard(
        padding: const EdgeInsets.all(AppSpacing.md),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Expanded(
                  child: Text(
                    '# ${contract.number}',
                    style: tt.titleSmall
                        ?.copyWith(fontWeight: FontWeight.w700),
                  ),
                ),
                Container(
                  padding: const EdgeInsets.symmetric(
                    horizontal: AppSpacing.sm,
                    vertical: AppSpacing.xs,
                  ),
                  decoration: BoxDecoration(
                    color: statusBg,
                    borderRadius: BorderRadius.circular(AppSpacing.radiusXs),
                  ),
                  child: Text(
                    contract.status.label,
                    style: tt.labelSmall?.copyWith(
                      color: statusColor,
                      fontWeight: FontWeight.w600,
                    ),
                  ),
                ),
              ],
            ),
            const SizedBox(height: AppSpacing.xs),
            Text(
              contract.supplierEnterpriseName,
              style: tt.bodySmall?.copyWith(color: cs.onSurfaceVariant),
            ),
            const SizedBox(height: AppSpacing.xs),
            Row(
              children: [
                Icon(Icons.date_range_outlined,
                    size: AppSpacing.iconXs,
                    color: cs.onSurfaceVariant),
                const SizedBox(width: AppSpacing.xs),
                Text(
                  '${_fmtDate(contract.validFrom)} — '
                  '${_fmtDate(contract.validTo)}',
                  style: tt.bodySmall
                      ?.copyWith(color: cs.onSurfaceVariant),
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }
}

class _PendingContractTile extends StatelessWidget {
  const _PendingContractTile({required this.contract});
  final PendingContract contract;

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    final tt = Theme.of(context).textTheme;
    final appColors = AppTheme.colorsOf(context);

    final hasError = contract.hasError;
    final indicatorColor =
        hasError ? appColors.danger : appColors.warning;
    final icon = hasError ? Icons.error_outline : Icons.pending_outlined;

    return Padding(
      padding: const EdgeInsets.only(bottom: AppSpacing.sm),
      child: AppCard(
        padding: const EdgeInsets.all(AppSpacing.md),
        borderColor: indicatorColor.withValues(alpha: 0.4),
        child: Row(
          children: [
            Icon(icon, color: indicatorColor, size: AppSpacing.iconMd),
            const SizedBox(width: AppSpacing.md),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    '# ${contract.number}',
                    style: tt.titleSmall
                        ?.copyWith(fontWeight: FontWeight.w700),
                  ),
                  Text(
                    '${_fmtDate(contract.validFrom)} — '
                    '${_fmtDate(contract.validTo)}',
                    style: tt.bodySmall
                        ?.copyWith(color: cs.onSurfaceVariant),
                  ),
                  if (hasError)
                    Text(
                      'Yuborishda xatolik yuz berdi',
                      style: tt.bodySmall?.copyWith(color: appColors.danger),
                    ),
                ],
              ),
            ),
            Container(
              padding: const EdgeInsets.symmetric(
                horizontal: AppSpacing.sm,
                vertical: AppSpacing.xs,
              ),
              decoration: BoxDecoration(
                color: indicatorColor.withValues(alpha: 0.12),
                borderRadius: BorderRadius.circular(AppSpacing.radiusXs),
              ),
              child: Text(
                hasError ? 'Xatolik' : 'Kutilmoqda',
                style: tt.labelSmall?.copyWith(
                  color: indicatorColor,
                  fontWeight: FontWeight.w600,
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}
