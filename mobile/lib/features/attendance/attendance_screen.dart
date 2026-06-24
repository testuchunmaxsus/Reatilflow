import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/theme/app_spacing.dart';
import '../../core/theme/app_theme.dart';
import '../../core/widgets/widgets.dart';
import 'attendance_providers.dart';
import 'gps_service.dart';

/// Davomat ekrani — Face ID (qurilma biometriyasi) + GPS.
///
/// Qoidalar (ATTENDANCE.md):
/// - biometric_verified = lokal qurilmada tekshiriladi
/// - Biometrik ma'lumot serverga bormaydi — faqat bayroq
/// - GPS ish vaqtida (check-in → check-out) davriy olinadi
/// - Vaqt server-avtoritar
class AttendanceScreen extends ConsumerWidget {
  const AttendanceScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
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
      ),
      body: _AttendanceBody(state: state),
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
