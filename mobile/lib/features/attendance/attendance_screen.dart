import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

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

    // Xato ko'rsatish
    ref.listen(attendanceNotifierProvider, (_, next) {
      if (next is AttendanceError) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text(next.message),
            backgroundColor: Colors.red,
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
      padding: const EdgeInsets.all(24),
      child: Column(
        children: [
          const SizedBox(height: 24),

          // Holat ikonkasi
          _StatusIcon(state: state),

          const SizedBox(height: 24),

          // Holat matni
          _StatusText(state: state),

          const SizedBox(height: 12),

          // GPS ma'lumoti
          _GpsInfo(state: state),

          const SizedBox(height: 40),

          // Tugma(lar)
          _ActionButtons(state: state),

          const SizedBox(height: 24),

          // Biometrik izoh
          const _BiometricNote(),
        ],
      ),
    );
  }
}

class _StatusIcon extends StatelessWidget {
  const _StatusIcon({required this.state});
  final AttendanceState state;

  @override
  Widget build(BuildContext context) {
    final (icon, color) = switch (state) {
      AttendanceCheckedIn() => (Icons.work, Colors.green),
      AttendanceCheckedOut() => (Icons.work_off, Colors.grey),
      AttendanceLoading() => (Icons.hourglass_bottom, Colors.blue),
      AttendanceError() => (Icons.error_outline, Colors.red),
      AttendanceIdle() => (Icons.fingerprint, Colors.blue),
    };

    if (state is AttendanceLoading) {
      return const SizedBox(
        width: 80,
        height: 80,
        child: CircularProgressIndicator(strokeWidth: 4),
      );
    }

    return Container(
      width: 100,
      height: 100,
      decoration: BoxDecoration(
        shape: BoxShape.circle,
        color: color.withValues(alpha:0.1),
        border: Border.all(color: color, width: 2),
      ),
      child: Icon(icon, size: 56, color: color),
    );
  }
}

class _StatusText extends StatelessWidget {
  const _StatusText({required this.state});
  final AttendanceState state;

  @override
  Widget build(BuildContext context) {
    final (title, subtitle) = switch (state) {
      AttendanceIdle() => ('Ish kuni boshlanmagan', 'Kirish uchun Face ID bosing'),
      AttendanceLoading() => ('Kutilmoqda...', 'Iltimos kuting'),
      AttendanceCheckedIn(:final record) => (
          'Ish jarayonda',
          _formatTime(record.checkInAt),
        ),
      AttendanceCheckedOut(:final record) => (
          'Ish tugadi',
          'Kirish: ${_formatTime(record.checkInAt)}'
              '\nChiqish: ${_formatTime(record.checkOutAt!)}',
        ),
      AttendanceError(:final message) => ('Xatolik', message),
    };

    return Column(
      children: [
        Text(
          title,
          style: Theme.of(context).textTheme.headlineSmall?.copyWith(
                fontWeight: FontWeight.bold,
              ),
          textAlign: TextAlign.center,
        ),
        const SizedBox(height: 8),
        Text(
          subtitle,
          style: Theme.of(context).textTheme.bodyMedium?.copyWith(
                color: Colors.grey,
              ),
          textAlign: TextAlign.center,
        ),
      ],
    );
  }

  String _formatTime(DateTime dt) {
    return '${dt.hour.toString().padLeft(2, '0')}:${dt.minute.toString().padLeft(2, '0')}';
  }
}

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

    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
      decoration: BoxDecoration(
        color: Colors.blue.shade50,
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: Colors.blue.shade100),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          const Icon(Icons.location_on, size: 16, color: Colors.blue),
          const SizedBox(width: 6),
          Text(
            'GPS: ${gps.lat.toStringAsFixed(4)}, ${gps.lng.toStringAsFixed(4)}',
            style: const TextStyle(fontSize: 12, color: Colors.blue),
          ),
        ],
      ),
    );
  }
}

class _ActionButtons extends ConsumerWidget {
  const _ActionButtons({required this.state});
  final AttendanceState state;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final notifier = ref.read(attendanceNotifierProvider.notifier);

    if (state is AttendanceLoading) {
      return const SizedBox.shrink();
    }

    if (state is AttendanceCheckedIn) {
      return SizedBox(
        width: double.infinity,
        child: FilledButton.icon(
          style: FilledButton.styleFrom(
            backgroundColor: Colors.orange,
            padding: const EdgeInsets.symmetric(vertical: 16),
          ),
          onPressed: notifier.checkOut,
          icon: const Icon(Icons.logout),
          label: const Text('Ish kunini tugatish',
              style: TextStyle(fontSize: 16)),
        ),
      );
    }

    if (state is AttendanceCheckedOut) {
      return const Column(
        children: [
          Icon(Icons.check_circle, color: Colors.green, size: 48),
          SizedBox(height: 8),
          Text('Bugungi ish kuni qayd etildi',
              style: TextStyle(color: Colors.green, fontSize: 16)),
        ],
      );
    }

    // Idle yoki Error — check-in tugmasi
    return SizedBox(
      width: double.infinity,
      child: FilledButton.icon(
        style: FilledButton.styleFrom(
          padding: const EdgeInsets.symmetric(vertical: 16),
        ),
        onPressed: notifier.checkIn,
        icon: const Icon(Icons.fingerprint, size: 28),
        label: const Text('Ish kunini boshlash (Face ID)',
            style: TextStyle(fontSize: 16)),
      ),
    );
  }
}

class _BiometricNote extends StatelessWidget {
  const _BiometricNote();

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: Colors.grey.shade100,
        borderRadius: BorderRadius.circular(8),
      ),
      child: const Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Icon(Icons.security, size: 18, color: Colors.grey),
          SizedBox(width: 8),
          Expanded(
            child: Text(
              'Xavfsizlik: biometrik ma\'lumotingiz faqat qurilmangizda '
              'tekshiriladi. Serverga faqat "tasdiqlandi" belgisi yuboriladi.',
              style: TextStyle(fontSize: 12, color: Colors.grey),
            ),
          ),
        ],
      ),
    );
  }
}
