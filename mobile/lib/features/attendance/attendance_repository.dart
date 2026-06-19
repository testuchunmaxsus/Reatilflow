import 'dart:convert';

import 'package:drift/drift.dart';
import 'package:uuid/uuid.dart';

import '../../data/local/dao/outbox_dao.dart';
import '../../data/local/database.dart';
import 'gps_service.dart';

/// Davomat yozuvi — lokal holat
class AttendanceRecord {
  AttendanceRecord({
    required this.id,
    required this.checkInAt,
    required this.checkInGpsLat,
    required this.checkInGpsLng,
    required this.biometricVerified,
    required this.clientUuidCheckIn,
    this.checkOutAt,
    this.checkOutGpsLat,
    this.checkOutGpsLng,
    this.clientUuidCheckOut,
  });

  final String id;
  final DateTime checkInAt;
  final double checkInGpsLat;
  final double checkInGpsLng;
  final bool biometricVerified;
  final String clientUuidCheckIn;
  DateTime? checkOutAt;
  double? checkOutGpsLat;
  double? checkOutGpsLng;
  String? clientUuidCheckOut;

  bool get isCheckedOut => checkOutAt != null;
}

/// Davomat repository — outbox orqali offline saqlanadi.
///
/// Qoidalar:
/// - biometric_verified = true → check-in mumkin (ATTENDANCE.md)
/// - biometric_verified = false → check-in rad etiladi
/// - Biometrik ma'lumot serverga BORMAYDI — faqat bayroq
/// - GPS ish vaqtida olinadi (ADR §3.7)
/// - Vaqt server-avtoritar (ATTENDANCE.md §Server-avtoritar vaqt)
class AttendanceRepository {
  AttendanceRepository({required AppDatabase db})
      : _outboxDao = OutboxDao(db);

  final OutboxDao _outboxDao;

  static const _uuid = Uuid();

  AttendanceRecord? _currentRecord;
  AttendanceRecord? get currentRecord => _currentRecord;

  bool get isCheckedIn =>
      _currentRecord != null && !_currentRecord!.isCheckedOut;

  /// Check-in — biometrik muvaffaqiyatli bo'lsa outbox'ga yozadi.
  ///
  /// [biometricVerified] — local_auth.authenticate() natijasi.
  /// [gpsPosition] — joriy GPS koordinata.
  ///
  /// Xato: biometricVerified=false bo'lsa — [BiometricRequiredException].
  Future<AttendanceRecord> checkIn({
    required bool biometricVerified,
    required GpsPosition? gpsPosition,
  }) async {
    if (!biometricVerified) {
      throw const BiometricRequiredException();
    }

    if (isCheckedIn) {
      throw const AlreadyCheckedInException();
    }

    final clientUuid = _uuid.v4();
    final now = DateTime.now();

    final lat = gpsPosition?.lat ?? 0.0;
    final lng = gpsPosition?.lng ?? 0.0;

    // Outbox — POST /attendance/check-in formatda
    // biometric_verified faqat bayroq — haqiqiy biometrik ma'lumot YO'Q
    final payload = {
      'biometric_verified': true, // bayroq — ATTENDANCE.md §3
      'gps_lat': lat.toStringAsFixed(7),
      'gps_lng': lng.toStringAsFixed(7),
      'source': 'device_faceid',
      'client_uuid': clientUuid,
    };

    await _outboxDao.insertOp(
      OutboxQueueCompanion.insert(
        opType: 'attendance.check_in',
        clientUuid: clientUuid,
        payload: jsonEncode(payload),
        createdAt: Value(now),
      ),
    );

    _currentRecord = AttendanceRecord(
      id: clientUuid,
      checkInAt: now,
      checkInGpsLat: lat,
      checkInGpsLng: lng,
      biometricVerified: biometricVerified,
      clientUuidCheckIn: clientUuid,
    );

    return _currentRecord!;
  }

  /// Check-out — outbox'ga yozadi.
  Future<AttendanceRecord> checkOut({
    required GpsPosition? gpsPosition,
  }) async {
    if (!isCheckedIn) {
      throw const NotCheckedInException();
    }

    final clientUuid = _uuid.v4();
    final now = DateTime.now();
    final lat = gpsPosition?.lat ?? 0.0;
    final lng = gpsPosition?.lng ?? 0.0;

    // Outbox — POST /attendance/check-out formatda
    final payload = {
      'gps_lat': lat.toStringAsFixed(7),
      'gps_lng': lng.toStringAsFixed(7),
      'client_uuid': clientUuid,
    };

    await _outboxDao.insertOp(
      OutboxQueueCompanion.insert(
        opType: 'attendance.check_out',
        clientUuid: clientUuid,
        payload: jsonEncode(payload),
        createdAt: Value(now),
      ),
    );

    _currentRecord!.checkOutAt = now;
    _currentRecord!.checkOutGpsLat = lat;
    _currentRecord!.checkOutGpsLng = lng;
    _currentRecord!.clientUuidCheckOut = clientUuid;

    return _currentRecord!;
  }

  /// GPS ingest — ish vaqtida davriy joylashuv yuborish.
  /// ADR §3.7: faqat isCheckedIn bo'lsa chaqiriladi.
  Future<void> ingestGps({required GpsPosition position}) async {
    if (!isCheckedIn) return; // Ish tashqarisida GPS yo'q

    final clientUuid = _uuid.v4();
    final now = DateTime.now();

    final payload = {
      'points': [
        {
          'lat': position.lat.toStringAsFixed(7),
          'lng': position.lng.toStringAsFixed(7),
          'recorded_at': now.toUtc().toIso8601String(),
          'speed': null,
          'delivery_id': null,
        }
      ],
    };

    await _outboxDao.insertOp(
      OutboxQueueCompanion.insert(
        opType: 'gps.ingest',
        clientUuid: clientUuid,
        payload: jsonEncode(payload),
        createdAt: Value(now),
      ),
    );
  }
}

// ---------------------------------------------------------------------------
// Xato turlari

class BiometricRequiredException implements Exception {
  const BiometricRequiredException();

  @override
  String toString() =>
      'BiometricRequiredException: Biometrik autentifikatsiya talab qilinadi';
}

class AlreadyCheckedInException implements Exception {
  const AlreadyCheckedInException();

  @override
  String toString() =>
      'AlreadyCheckedInException: Shu kun allaqachon kirilgan';
}

class NotCheckedInException implements Exception {
  const NotCheckedInException();

  @override
  String toString() =>
      'NotCheckedInException: Avval kirish qayd etilmagan';
}
