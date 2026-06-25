import 'dart:async';

import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../data/local/database_provider.dart';
import 'attendance_repository.dart';
import 'biometric_service.dart';
import 'gps_service.dart';

/// Biometrik xizmat provider (override qilinishi mumkin)
final biometricServiceProvider = Provider<BiometricService>((ref) {
  return LocalAuthBiometricService();
});

/// GPS xizmat provider (override qilinishi mumkin)
final gpsServiceProvider = Provider<GpsService>((ref) {
  return GeolocatorGpsService();
});

/// AttendanceRepository provider
final attendanceRepositoryProvider = Provider<AttendanceRepository>((ref) {
  final db = ref.watch(databaseProvider);
  return AttendanceRepository(db: db);
});

// ---------------------------------------------------------------------------
// Davomat holati

sealed class AttendanceState {
  const AttendanceState();
}

class AttendanceIdle extends AttendanceState {
  const AttendanceIdle();
}

class AttendanceLoading extends AttendanceState {
  const AttendanceLoading();
}

class AttendanceCheckedIn extends AttendanceState {
  const AttendanceCheckedIn({
    required this.record,
    this.lastGps,
  });
  final AttendanceRecord record;
  final GpsPosition? lastGps;
}

class AttendanceCheckedOut extends AttendanceState {
  const AttendanceCheckedOut({required this.record});
  final AttendanceRecord record;
}

class AttendanceError extends AttendanceState {
  const AttendanceError({required this.message});
  final String message;
}

// ---------------------------------------------------------------------------
// Davomat Notifier

class AttendanceNotifier extends StateNotifier<AttendanceState> {
  AttendanceNotifier({
    required AttendanceRepository repository,
    required BiometricService biometricService,
    required GpsService gpsService,
  })  : _repository = repository,
        _biometricService = biometricService,
        _gpsService = gpsService,
        super(const AttendanceIdle());

  final AttendanceRepository _repository;
  final BiometricService _biometricService;
  final GpsService _gpsService;

  /// GPS yig'ish intervali — deyarli jonli kuzatuv uchun 30s (foydalanuvchi so'rovi).
  /// (Avval ADR §3.7 bo'yicha 3 daqiqa edi; 30s — batareya/trafik biroz ko'proq.)
  static const _gpsInterval = Duration(seconds: 30);
  Timer? _gpsTimer;

  /// Check-in: biometrik → GPS → outbox
  Future<void> checkIn() async {
    state = const AttendanceLoading();
    try {
      // 1. GPS ruxsati va joylashuv
      await _gpsService.requestPermission();
      final gps = await _gpsService.getCurrentPosition();

      // 2. Biometrik autentifikatsiya (qurilma-lokal)
      //    Natija: true/false — ma'lumot serverga bormaydi
      final verified = await _biometricService.authenticate(
        reason: 'Ish kunini boshlash uchun biometriyangizni tasdiqlang',
      );

      // 3. Repository check-in (biometric_verified bayroq bilan)
      final record = await _repository.checkIn(
        biometricVerified: verified,
        gpsPosition: gps,
      );

      state = AttendanceCheckedIn(record: record, lastGps: gps);

      // 4. DARHOL birinchi GPS nuqtasini yuborish — xaritada tez ko'rinishi uchun
      //    (timer'ning birinchi tiki kutilmaydi), so'ng davriy yig'ish.
      if (gps != null) {
        await _repository.ingestGps(position: gps);
      }
      _startGpsTracking();
    } on BiometricRequiredException {
      state = const AttendanceError(
          message:
              'Biometrik autentifikatsiya rad etildi. Check-in mumkin emas.');
    } on AlreadyCheckedInException {
      state = const AttendanceError(message: 'Shu kun allaqachon kirilgan.');
    } on Exception catch (e) {
      state = AttendanceError(message: e.toString());
    }
  }

  /// Check-out: GPS → outbox → GPS tracking to'xtatish
  Future<void> checkOut() async {
    state = const AttendanceLoading();
    try {
      final gps = await _gpsService.getCurrentPosition();
      final record = await _repository.checkOut(gpsPosition: gps);

      // GPS tracking to'xtatish — ish tashqarisida GPS yo'q (ADR §3.7)
      _stopGpsTracking();

      state = AttendanceCheckedOut(record: record);
    } on NotCheckedInException {
      state = const AttendanceError(
          message: 'Avval kirish qayd etilmagan.');
    } on Exception catch (e) {
      state = AttendanceError(message: e.toString());
    }
  }

  /// Davriy GPS yig'ish — faqat ish vaqtida
  void _startGpsTracking() {
    _gpsTimer?.cancel();
    _gpsTimer = Timer.periodic(_gpsInterval, (_) async {
      if (!_repository.isCheckedIn) {
        _stopGpsTracking();
        return;
      }
      final gps = await _gpsService.getCurrentPosition();
      if (gps != null) {
        await _repository.ingestGps(position: gps);
        // Holat yangilash (lastGps)
        final current = state;
        if (current is AttendanceCheckedIn) {
          state = AttendanceCheckedIn(
              record: current.record, lastGps: gps);
        }
      }
    });
  }

  void _stopGpsTracking() {
    _gpsTimer?.cancel();
    _gpsTimer = null;
  }

  @override
  void dispose() {
    _stopGpsTracking();
    super.dispose();
  }
}

final attendanceNotifierProvider =
    StateNotifierProvider<AttendanceNotifier, AttendanceState>((ref) {
  return AttendanceNotifier(
    repository: ref.watch(attendanceRepositoryProvider),
    biometricService: ref.watch(biometricServiceProvider),
    gpsService: ref.watch(gpsServiceProvider),
  );
});
