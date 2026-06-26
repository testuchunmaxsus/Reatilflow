import 'dart:convert';

import 'package:dio/dio.dart';
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

/// Davomat tarixi yozuvi (server javobidan)
class AttendanceHistoryRecord {
  AttendanceHistoryRecord({
    required this.id,
    required this.workDate,
    required this.checkInAt,
    required this.checkInGpsLat,
    required this.checkInGpsLng,
    required this.biometricVerified,
    this.checkOutAt,
    this.checkOutGpsLat,
    this.checkOutGpsLng,
  });

  factory AttendanceHistoryRecord.fromJson(Map<String, dynamic> json) {
    return AttendanceHistoryRecord(
      id: json['id'] as String,
      workDate: DateTime.parse(json['work_date'] as String),
      checkInAt: DateTime.parse(json['check_in_at'] as String),
      checkInGpsLat: _parseDouble(json['check_in_gps_lat']),
      checkInGpsLng: _parseDouble(json['check_in_gps_lng']),
      biometricVerified: json['biometric_verified'] as bool? ?? false,
      checkOutAt: json['check_out_at'] != null
          ? DateTime.parse(json['check_out_at'] as String)
          : null,
      checkOutGpsLat: json['check_out_gps_lat'] != null
          ? _parseDouble(json['check_out_gps_lat'])
          : null,
      checkOutGpsLng: json['check_out_gps_lng'] != null
          ? _parseDouble(json['check_out_gps_lng'])
          : null,
    );
  }

  static double _parseDouble(dynamic v) {
    if (v is double) return v;
    if (v is int) return v.toDouble();
    return double.tryParse(v.toString()) ?? 0.0;
  }

  final String id;
  final DateTime workDate;
  final DateTime checkInAt;
  final double checkInGpsLat;
  final double checkInGpsLng;
  final bool biometricVerified;
  final DateTime? checkOutAt;
  final double? checkOutGpsLat;
  final double? checkOutGpsLng;

  /// Ish vaqti (daqiqada) — checkOut bo'lsa hisoblaydi
  int? get workMinutes {
    if (checkOutAt == null) return null;
    return checkOutAt!.difference(checkInAt).inMinutes;
  }
}

/// Paginated davomat tarixi
class AttendanceHistoryPage {
  const AttendanceHistoryPage({
    required this.items,
    required this.total,
    required this.limit,
    required this.offset,
  });

  final List<AttendanceHistoryRecord> items;
  final int total;
  final int limit;
  final int offset;
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
  AttendanceRepository({required AppDatabase db, required Dio dio})
      : _outboxDao = OutboxDao(db),
        _dio = dio;

  final OutboxDao _outboxDao;
  final Dio _dio;

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

  /// GET /attendance — davomat tarixini serverdan yuklash.
  ///
  /// [limit] va [offset] — sahifa parametrlari.
  /// RBAC: attendance:view (agent, courier, administrator, accountant).
  Future<AttendanceHistoryPage> fetchHistory({
    int limit = 20,
    int offset = 0,
  }) async {
    final response = await _dio.get<Map<String, dynamic>>(
      '/attendance',
      queryParameters: {'limit': limit, 'offset': offset},
    );
    final data = response.data!;
    final rawItems = (data['items'] as List<dynamic>?) ?? [];
    final items = rawItems
        .map((e) =>
            AttendanceHistoryRecord.fromJson(e as Map<String, dynamic>))
        .toList();
    return AttendanceHistoryPage(
      items: items,
      total: data['total'] as int? ?? 0,
      limit: data['limit'] as int? ?? limit,
      offset: data['offset'] as int? ?? offset,
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
