import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/theme/app_spacing.dart';
import '../../core/theme/app_theme.dart';
import '../../core/widgets/widgets.dart';
import 'attendance_providers.dart';
import 'attendance_repository.dart';
import 'gps_service.dart';

/// Davomat ekrani — Face ID (qurilma biometriyasi) + GPS + tarix.
///
/// Qoidalar (ATTENDANCE.md):
/// - biometric_verified = lokal qurilmada tekshiriladi
/// - Biometrik ma'lumot serverga bormaydi — faqat bayroq
/// - GPS ish vaqtida (check-in → check-out) davriy olinadi
/// - Vaqt server-avtoritar
class AttendanceScreen extends ConsumerStatefulWidget {
  const AttendanceScreen({super.key});

  @override
  ConsumerState<AttendanceScreen> createState() => _AttendanceScreenState();
}

class _AttendanceScreenState extends ConsumerState<AttendanceScreen>
    with SingleTickerProviderStateMixin {
  late final TabController _tabController;

  @override
  void initState() {
    super.initState();
    _tabController = TabController(length: 2, vsync: this);
  }

  @override
  void dispose() {
    _tabController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final state = ref.watch(attendanceNotifierProvider);
    final cs = Theme.of(context).colorScheme;

    ref.listen(attendanceNotifierProvider, (_, next) {
      if (next is AttendanceError) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text(next.message),
            backgroundColor: cs.error,
          ),
        );
      }
    });

    return Scaffold(
      appBar: AppBar(
        title: const Text('Davomat'),
        actions: [
          IconButton(
            icon: const Icon(Icons.info_outline),
            onPressed: () => _showInfoDialog(context),
          ),
        ],
        bottom: TabBar(
          controller: _tabController,
          tabs: const [
            Tab(text: 'Bugun'),
            Tab(text: 'Tarix'),
          ],
        ),
      ),
      body: TabBarView(
        controller: _tabController,
        children: [
          _AttendanceBody(state: state),
          const _AttendanceHistoryTab(),
        ],
      ),
    );
  }

  void _showInfoDialog(BuildContext context) {
    showDialog<void>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Davomat haqida'),
        content: const Text(
          'Biometrik ma\'lumotingiz faqat qurilmangizda tekshiriladi.\n\n'
          'Serverga faqat "tasdiqlandi" belgisi yuboriladi — '
          'yuz tasviri yoki barmoq izi saqlanmaydi.\n\n'
          'GPS ish vaqtida (kirish-chiqish oralig\'ida) olinadi.',
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx),
            child: const Text('Tushunarli'),
          ),
        ],
      ),
    );
  }
}

class _AttendanceBody extends ConsumerWidget {
  const _AttendanceBody({required this.state});
  final AttendanceState state;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    return SingleChildScrollView(
      padding: const EdgeInsets.all(AppSpacing.xl),
      child: Column(
        children: [
          const SizedBox(height: AppSpacing.xl),

          _StatusCircle(state: state),

          const SizedBox(height: AppSpacing.xl),

          _StatusText(state: state),

          const SizedBox(height: AppSpacing.md),

          _GpsInfo(state: state),

          const SizedBox(height: AppSpacing.xxxl),

          _ActionButtons(state: state),

          const SizedBox(height: AppSpacing.xl),

          _BiometricNote(),
        ],
      ),
    );
  }
}

// ---------------------------------------------------------------------------

class _StatusCircle extends StatelessWidget {
  const _StatusCircle({required this.state});
  final AttendanceState state;

  @override
  Widget build(BuildContext context) {
    final appColors = AppTheme.colorsOf(context);
    final cs = Theme.of(context).colorScheme;

    if (state is AttendanceLoading) {
      return SizedBox(
        width: 96,
        height: 96,
        child: CircularProgressIndicator(strokeWidth: 4, color: cs.primary),
      );
    }

    final (icon, color) = switch (state) {
      AttendanceCheckedIn() => (Icons.work_outlined, appColors.success),
      AttendanceCheckedOut() => (Icons.work_off_outlined, cs.onSurfaceVariant),
      AttendanceError() => (Icons.error_outline, appColors.danger),
      _ => (Icons.fingerprint, cs.primary),
    };

    return Container(
      width: 100,
      height: 100,
      decoration: BoxDecoration(
        shape: BoxShape.circle,
        color: color.withValues(alpha: 0.1),
        border: Border.all(color: color, width: 2.5),
      ),
      child: Icon(icon, size: 52, color: color),
    );
  }
}

// ---------------------------------------------------------------------------

class _StatusText extends StatelessWidget {
  const _StatusText({required this.state});
  final AttendanceState state;

  @override
  Widget build(BuildContext context) {
    final tt = Theme.of(context).textTheme;
    final cs = Theme.of(context).colorScheme;
    final appColors = AppTheme.colorsOf(context);

    final (title, subtitle, titleColor) = switch (state) {
      AttendanceIdle() => (
          'Ish kuni boshlanmagan',
          'Kirish uchun Face ID bosing',
          cs.onSurface,
        ),
      AttendanceLoading() => (
          'Kutilmoqda...',
          'Iltimos kuting',
          cs.onSurfaceVariant,
        ),
      AttendanceCheckedIn(:final record) => (
          'Ish jarayonda',
          _formatTime(record.checkInAt),
          appColors.success,
        ),
      AttendanceCheckedOut(:final record) => (
          'Ish tugadi',
          'Kirish: ${_formatTime(record.checkInAt)}'
              '\nChiqish: ${_formatTime(record.checkOutAt!)}',
          cs.onSurface,
        ),
      AttendanceError(:final message) => (
          'Xatolik',
          message,
          appColors.danger,
        ),
    };

    return Column(
      children: [
        Text(
          title,
          style: tt.headlineSmall?.copyWith(
            fontWeight: FontWeight.w700,
            color: titleColor,
          ),
          textAlign: TextAlign.center,
        ),
        const SizedBox(height: AppSpacing.sm),
        Text(
          subtitle,
          style: tt.bodyMedium?.copyWith(color: cs.onSurfaceVariant),
          textAlign: TextAlign.center,
        ),
      ],
    );
  }

  String _formatTime(DateTime dt) =>
      '${dt.hour.toString().padLeft(2, '0')}:${dt.minute.toString().padLeft(2, '0')}';
}

// ---------------------------------------------------------------------------

class _GpsInfo extends StatelessWidget {
  const _GpsInfo({required this.state});
  final AttendanceState state;

  @override
  Widget build(BuildContext context) {
    GpsPosition? gps;
    if (state case AttendanceCheckedIn(:final lastGps)) {
      gps = lastGps;
    }
    if (gps == null) return const SizedBox.shrink();

    final appColors = AppTheme.colorsOf(context);
    final tt = Theme.of(context).textTheme;

    return AppCard(
      padding: const EdgeInsets.symmetric(
          horizontal: AppSpacing.lg, vertical: AppSpacing.sm),
      color: appColors.infoContainer.withValues(alpha: 0.3),
      borderColor: appColors.info.withValues(alpha: 0.3),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(Icons.gps_fixed,
              size: AppSpacing.iconXs, color: appColors.info),
          const SizedBox(width: AppSpacing.xs),
          Text(
            'GPS: ${gps.lat.toStringAsFixed(4)}, ${gps.lng.toStringAsFixed(4)}',
            style: tt.labelMedium?.copyWith(color: appColors.info),
          ),
        ],
      ),
    );
  }
}

// ---------------------------------------------------------------------------

class _ActionButtons extends ConsumerWidget {
  const _ActionButtons({required this.state});
  final AttendanceState state;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final notifier = ref.read(attendanceNotifierProvider.notifier);
    final appColors = AppTheme.colorsOf(context);

    if (state is AttendanceLoading) return const SizedBox.shrink();

    if (state is AttendanceCheckedIn) {
      return SizedBox(
        width: double.infinity,
        child: FilledButton.icon(
          style: FilledButton.styleFrom(
            backgroundColor: appColors.warning,
            padding: const EdgeInsets.symmetric(vertical: AppSpacing.lg),
          ),
          onPressed: notifier.checkOut,
          icon: const Icon(Icons.logout_outlined),
          label: const Text('Ish kunini tugatish',
              style: TextStyle(fontSize: 16)),
        ),
      );
    }

    if (state is AttendanceCheckedOut) {
      return Column(
        children: [
          Container(
            width: 64,
            height: 64,
            decoration: BoxDecoration(
              shape: BoxShape.circle,
              color: appColors.successContainer.withValues(alpha: 0.5),
            ),
            child: Icon(Icons.check_circle_outline,
                color: appColors.success, size: AppSpacing.iconXl),
          ),
          const SizedBox(height: AppSpacing.md),
          Text(
            'Bugungi ish kuni qayd etildi',
            style: Theme.of(context).textTheme.titleMedium?.copyWith(
                color: appColors.success, fontWeight: FontWeight.w600),
          ),
        ],
      );
    }

    // Idle yoki Error — check-in tugmasi
    return SizedBox(
      width: double.infinity,
      child: FilledButton.icon(
        style: FilledButton.styleFrom(
          padding: const EdgeInsets.symmetric(vertical: AppSpacing.lg),
        ),
        onPressed: notifier.checkIn,
        icon: const Icon(Icons.fingerprint, size: 28),
        label: const Text('Ish kunini boshlash (Face ID)',
            style: TextStyle(fontSize: 16)),
      ),
    );
  }
}

// ---------------------------------------------------------------------------

class _BiometricNote extends StatelessWidget {
  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    final tt = Theme.of(context).textTheme;

    return AppCard(
      color: cs.surfaceContainerHighest.withValues(alpha: 0.6),
      padding: const EdgeInsets.all(AppSpacing.md),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Icon(Icons.security_outlined,
              size: AppSpacing.iconSm, color: cs.onSurfaceVariant),
          const SizedBox(width: AppSpacing.sm),
          Expanded(
            child: Text(
              'Xavfsizlik: biometrik ma\'lumotingiz faqat qurilmangizda '
              'tekshiriladi. Serverga faqat "tasdiqlandi" belgisi yuboriladi.',
              style: tt.bodySmall?.copyWith(color: cs.onSurfaceVariant),
            ),
          ),
        ],
      ),
    );
  }
}

// ---------------------------------------------------------------------------
// Davomat tarixi tab

/// Davomat tarixi sahifasi — GET /attendance paginated ro'yxat.
class _AttendanceHistoryTab extends ConsumerStatefulWidget {
  const _AttendanceHistoryTab();

  @override
  ConsumerState<_AttendanceHistoryTab> createState() =>
      _AttendanceHistoryTabState();
}

class _AttendanceHistoryTabState
    extends ConsumerState<_AttendanceHistoryTab> {
  int _offset = 0;
  static const int _pageSize = 20;

  @override
  Widget build(BuildContext context) {
    final historyAsync = ref.watch(attendanceHistoryProvider(_offset));

    return RefreshIndicator(
      onRefresh: () async {
        ref.invalidate(attendanceHistoryProvider(_offset));
      },
      child: historyAsync.when(
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (e, _) => _HistoryError(
          message: e.toString(),
          onRetry: () =>
              ref.invalidate(attendanceHistoryProvider(_offset)),
        ),
        data: (page) {
          if (page.items.isEmpty && _offset == 0) {
            return const _HistoryEmpty();
          }
          return ListView.builder(
            padding: const EdgeInsets.all(AppSpacing.lg),
            itemCount: page.items.length + 1, // +1 pagination footer
            itemBuilder: (ctx, i) {
              if (i == page.items.length) {
                return _PaginationFooter(
                  offset: _offset,
                  total: page.total,
                  pageSize: _pageSize,
                  onPrev: _offset > 0
                      ? () => setState(() => _offset -= _pageSize)
                      : null,
                  onNext: (_offset + _pageSize) < page.total
                      ? () => setState(() => _offset += _pageSize)
                      : null,
                );
              }
              return _HistoryRecordCard(record: page.items[i]);
            },
          );
        },
      ),
    );
  }
}

// ---------------------------------------------------------------------------

class _HistoryRecordCard extends StatelessWidget {
  const _HistoryRecordCard({required this.record});
  final AttendanceHistoryRecord record;

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    final tt = Theme.of(context).textTheme;
    final appColors = AppTheme.colorsOf(context);

    final isComplete = record.checkOutAt != null;
    final minutes = record.workMinutes;

    return AppCard(
      margin: const EdgeInsets.only(bottom: AppSpacing.sm),
      padding: const EdgeInsets.all(AppSpacing.lg),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // Sana + holat badge
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              Text(
                _formatDate(record.workDate),
                style: tt.titleSmall?.copyWith(fontWeight: FontWeight.w700),
              ),
              StatusBadge(
                status: isComplete ? 'Tugallangan' : 'Ochiq',
                variant:
                    isComplete ? StatusVariant.success : StatusVariant.warning,
                icon: isComplete
                    ? Icons.check_circle_outline
                    : Icons.radio_button_unchecked,
              ),
            ],
          ),
          const SizedBox(height: AppSpacing.sm),

          // Kirish vaqti
          _TimeRow(
            icon: Icons.login_outlined,
            label: 'Kirish',
            time: record.checkInAt,
            color: appColors.success,
          ),

          // Chiqish vaqti
          if (isComplete)
            _TimeRow(
              icon: Icons.logout_outlined,
              label: 'Chiqish',
              time: record.checkOutAt!,
              color: appColors.warning,
            ),

          // Ish davomiyligi
          if (minutes != null) ...[
            const SizedBox(height: AppSpacing.xs),
            Row(
              children: [
                Icon(Icons.timer_outlined,
                    size: AppSpacing.iconXs,
                    color: cs.onSurfaceVariant),
                const SizedBox(width: AppSpacing.xs),
                Text(
                  '${_formatDuration(minutes)} ish vaqti',
                  style: tt.bodySmall?.copyWith(color: cs.onSurfaceVariant),
                ),
              ],
            ),
          ],
        ],
      ),
    );
  }

  String _formatDate(DateTime dt) {
    const months = [
      'yanvar', 'fevral', 'mart', 'aprel', 'may', 'iyun',
      'iyul', 'avgust', 'sentabr', 'oktabr', 'noyabr', 'dekabr',
    ];
    return '${dt.day} ${months[dt.month - 1]} ${dt.year}';
  }

  String _formatDuration(int minutes) {
    final h = minutes ~/ 60;
    final m = minutes % 60;
    if (h == 0) return '${m}m';
    return '${h}s ${m}m';
  }
}

class _TimeRow extends StatelessWidget {
  const _TimeRow({
    required this.icon,
    required this.label,
    required this.time,
    required this.color,
  });

  final IconData icon;
  final String label;
  final DateTime time;
  final Color color;

  @override
  Widget build(BuildContext context) {
    final tt = Theme.of(context).textTheme;
    final cs = Theme.of(context).colorScheme;
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 2),
      child: Row(
        children: [
          Icon(icon, size: AppSpacing.iconXs, color: color),
          const SizedBox(width: AppSpacing.xs),
          Text(
            '$label: ',
            style: tt.bodySmall?.copyWith(color: cs.onSurfaceVariant),
          ),
          Text(
            _fmt(time),
            style: tt.bodySmall?.copyWith(fontWeight: FontWeight.w600),
          ),
        ],
      ),
    );
  }

  String _fmt(DateTime dt) =>
      '${dt.hour.toString().padLeft(2, '0')}:${dt.minute.toString().padLeft(2, '0')}';
}

// ---------------------------------------------------------------------------

class _HistoryEmpty extends StatelessWidget {
  const _HistoryEmpty();

  @override
  Widget build(BuildContext context) {
    return const Center(
      child: EmptyState(
        icon: Icons.history_outlined,
        title: 'Davomat tarixi topilmadi',
        message: 'Ish kunlari qayd etilgandan so\'ng bu yerda ko\'rinadi',
      ),
    );
  }
}

class _HistoryError extends StatelessWidget {
  const _HistoryError({required this.message, required this.onRetry});
  final String message;
  final VoidCallback onRetry;

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    final tt = Theme.of(context).textTheme;
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(AppSpacing.xl),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(Icons.error_outline,
                size: AppSpacing.iconXl, color: cs.error),
            const SizedBox(height: AppSpacing.md),
            Text(
              'Yuklashda xatolik',
              style: tt.titleMedium?.copyWith(color: cs.error),
            ),
            const SizedBox(height: AppSpacing.xs),
            Text(
              message,
              style: tt.bodySmall?.copyWith(color: cs.onSurfaceVariant),
              textAlign: TextAlign.center,
            ),
            const SizedBox(height: AppSpacing.lg),
            FilledButton.icon(
              onPressed: onRetry,
              icon: const Icon(Icons.refresh),
              label: const Text('Qaytadan urinish'),
            ),
          ],
        ),
      ),
    );
  }
}

class _PaginationFooter extends StatelessWidget {
  const _PaginationFooter({
    required this.offset,
    required this.total,
    required this.pageSize,
    required this.onPrev,
    required this.onNext,
  });

  final int offset;
  final int total;
  final int pageSize;
  final VoidCallback? onPrev;
  final VoidCallback? onNext;

  @override
  Widget build(BuildContext context) {
    if (total <= pageSize) return const SizedBox.shrink();
    final tt = Theme.of(context).textTheme;
    final cs = Theme.of(context).colorScheme;
    final current = offset ~/ pageSize + 1;
    final totalPages = (total / pageSize).ceil();

    return Padding(
      padding: const EdgeInsets.symmetric(vertical: AppSpacing.lg),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [
          TextButton.icon(
            onPressed: onPrev,
            icon: const Icon(Icons.chevron_left),
            label: const Text('Oldingi'),
          ),
          Text(
            '$current / $totalPages',
            style: tt.bodySmall?.copyWith(color: cs.onSurfaceVariant),
          ),
          TextButton.icon(
            onPressed: onNext,
            icon: const Icon(Icons.chevron_right),
            label: const Text('Keyingi'),
          ),
        ],
      ),
    );
  }
}
