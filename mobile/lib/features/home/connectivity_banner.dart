import 'package:connectivity_plus/connectivity_plus.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/theme/app_spacing.dart';
import '../../core/theme/app_theme.dart';

/// Offline holat banneri — ekran tepasida ko'rinadi.
///
/// Offline-first tamoyil: banner faqat axborot uchun,
/// UI bloklanmaydi — lokal ma'lumotlar har doim ko'rinadi.
class ConnectivityBanner extends ConsumerWidget {
  const ConnectivityBanner({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final connectivity = ref.watch(_connectivityProvider);

    return connectivity.when(
      data: (results) {
        final isOffline = results.every((r) => r == ConnectivityResult.none);
        if (!isOffline) return const SizedBox.shrink();

        final appColors = AppTheme.colorsOf(context);
        final tt = Theme.of(context).textTheme;

        return Container(
          width: double.infinity,
          color: appColors.warning,
          padding: const EdgeInsets.symmetric(
            vertical: AppSpacing.xs,
            horizontal: AppSpacing.lg,
          ),
          child: Row(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              Icon(
                Icons.wifi_off_rounded,
                size: AppSpacing.iconXs,
                color: appColors.onWarning,
              ),
              const SizedBox(width: AppSpacing.sm),
              Flexible(
                child: Text(
                  'Offline rejim — o\'zgarishlar tarmoq tiklananda yuboriladi',
                  style: tt.labelSmall?.copyWith(
                    color: appColors.onWarning,
                    fontWeight: FontWeight.w600,
                  ),
                  textAlign: TextAlign.center,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                ),
              ),
            ],
          ),
        );
      },
      loading: () => const SizedBox.shrink(),
      error: (_, __) => const SizedBox.shrink(),
    );
  }
}

final _connectivityProvider =
    StreamProvider<List<ConnectivityResult>>((ref) {
  return Connectivity().onConnectivityChanged;
});
