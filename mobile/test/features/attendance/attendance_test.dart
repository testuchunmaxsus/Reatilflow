import 'dart:convert';

import 'package:drift/native.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:retail_mobile/data/local/dao/outbox_dao.dart';
import 'package:retail_mobile/data/local/database.dart';
import 'package:retail_mobile/features/attendance/attendance_repository.dart';
import 'package:retail_mobile/features/attendance/biometric_service.dart';
import 'package:retail_mobile/features/attendance/gps_service.dart';

AppDatabase _makeDb() => AppDatabase.forTesting(NativeDatabase.memory());

void main() {
  group('AttendanceRepository — biometrik + GPS', () {
    late AppDatabase db;
    late AttendanceRepository repository;
    late OutboxDao outboxDao;
    const testGps = GpsPosition(lat: 41.2995, lng: 69.2401);

    setUp(() {
      db = _makeDb();
      repository = AttendanceRepository(db: db);
      outboxDao = OutboxDao(db);
    });
    tearDown(() => db.close());

    // -------------------------------------------------------------------
    // CHECK-IN testlari
    // -------------------------------------------------------------------

    test(
      'checkIn — biometricVerified=true → outbox da attendance.check_in yoziladi',
      () async {
        final record = await repository.checkIn(
          biometricVerified: true,
          gpsPosition: testGps,
        );

        expect(record, isNotNull);
        expect(record.biometricVerified, isTrue);
        expect(record.checkInGpsLat, closeTo(testGps.lat, 0.0001));
        expect(record.checkInGpsLng, closeTo(testGps.lng, 0.0001));

        final pending = await outboxDao.getPending();
        expect(pending.length, equals(1));
        expect(pending.first.opType, equals('attendance.check_in'));

        final payload =
            jsonDecode(pending.first.payload) as Map<String, dynamic>;
        // Biometrik bayroq — faqat true (ma'lumot YO'Q)
        expect(payload['biometric_verified'], isTrue);
        expect(payload['source'], equals('device_faceid'));
        expect(payload['gps_lat'], isNotEmpty);
        expect(payload['gps_lng'], isNotEmpty);
        // Yuz tasviri yoki barmoq izi ma'lumoti YO'Q
        expect(payload.containsKey('face_data'), isFalse);
        expect(payload.containsKey('fingerprint'), isFalse);
      },
    );

    test(
      'checkIn — biometricVerified=false → BiometricRequiredException, '
      'outbox bo\'sh',
      () async {
        await expectLater(
          () => repository.checkIn(
            biometricVerified: false,
            gpsPosition: testGps,
          ),
          throwsA(isA<BiometricRequiredException>()),
        );

        final pending = await outboxDao.getPending();
        expect(pending, isEmpty);
        expect(repository.isCheckedIn, isFalse);
      },
    );

    test('checkIn — GPS null bo\'lsa ham ishlaydi (0.0 koordinata)', () async {
      final record = await repository.checkIn(
        biometricVerified: true,
        gpsPosition: null, // GPS mavjud bo'lmagan holat
      );

      expect(record, isNotNull);
      final pending = await outboxDao.getPending();
      expect(pending.length, equals(1));
      final payload =
          jsonDecode(pending.first.payload) as Map<String, dynamic>;
      expect(payload['biometric_verified'], isTrue);
    });

    test('checkIn ikkinchi marta → AlreadyCheckedInException', () async {
      await repository.checkIn(biometricVerified: true, gpsPosition: testGps);

      await expectLater(
        () => repository.checkIn(
            biometricVerified: true, gpsPosition: testGps),
        throwsA(isA<AlreadyCheckedInException>()),
      );
    });

    // -------------------------------------------------------------------
    // CHECK-OUT testlari
    // -------------------------------------------------------------------

    test('checkOut — check-in dan keyin ishlaydi', () async {
      await repository.checkIn(biometricVerified: true, gpsPosition: testGps);
      final outRecord =
          await repository.checkOut(gpsPosition: testGps);

      expect(outRecord.checkOutAt, isNotNull);
      expect(outRecord.checkOutGpsLat, closeTo(testGps.lat, 0.0001));

      final pending = await outboxDao.getPending();
      // check_in + check_out = 2 op
      expect(pending.length, equals(2));
      expect(
        pending.any((p) => p.opType == 'attendance.check_out'),
        isTrue,
      );
    });

    test('checkOut — check-in bo\'lmasa → NotCheckedInException', () async {
      await expectLater(
        () => repository.checkOut(gpsPosition: testGps),
        throwsA(isA<NotCheckedInException>()),
      );
    });

    // -------------------------------------------------------------------
    // GPS ingest testlari
    // -------------------------------------------------------------------

    test('ingestGps — ish vaqtida outbox\'ga yozadi', () async {
      await repository.checkIn(biometricVerified: true, gpsPosition: testGps);
      await repository.ingestGps(position: testGps);

      final pending = await outboxDao.getPending();
      // check_in + gps.ingest = 2
      final gpsOps = pending.where((p) => p.opType == 'gps.ingest').toList();
      expect(gpsOps.length, equals(1));

      final payload =
          jsonDecode(gpsOps.first.payload) as Map<String, dynamic>;
      final points = payload['points'] as List<dynamic>;
      expect(points.length, equals(1));
      final firstPoint = points.first as Map<String, dynamic>;
      expect(firstPoint['lat'], isNotEmpty);
    });

    test('ingestGps — ish vaqtidan tashqarida (check-in yo\'q) — yozilmaydi',
        () async {
      await repository.ingestGps(position: testGps);

      final pending = await outboxDao.getPending();
      expect(pending.where((p) => p.opType == 'gps.ingest'), isEmpty);
    });
  });

  // -----------------------------------------------------------------------
  // BiometricService mock testlari
  // -----------------------------------------------------------------------

  group('MockBiometricService', () {
    test('shouldSucceed=true → true qaytaradi', () async {
      final bio = MockBiometricService(); // default: shouldSucceed=true
      final result = await bio.authenticate(reason: 'test');
      expect(result, isTrue);
    });

    test('shouldSucceed=false → false qaytaradi', () async {
      final bio = MockBiometricService(shouldSucceed: false);
      final result = await bio.authenticate(reason: 'test');
      expect(result, isFalse);
    });

    test('isAvailable → true', () async {
      final bio = MockBiometricService();
      expect(await bio.isAvailable(), isTrue);
    });
  });

  // -----------------------------------------------------------------------
  // GpsService mock testlari
  // -----------------------------------------------------------------------

  group('MockGpsService', () {
    test('getCurrentPosition → berilgan pozitsiyani qaytaradi', () async {
      const expected = GpsPosition(lat: 41.3000, lng: 69.2500);
      final gps = MockGpsService(position: expected);
      final result = await gps.getCurrentPosition();
      expect(result?.lat, closeTo(expected.lat, 0.0001));
      expect(result?.lng, closeTo(expected.lng, 0.0001));
    });

    test('position=null bo\'lsa null qaytaradi', () async {
      final gps = MockGpsService(position: null);
      expect(await gps.getCurrentPosition(), isNull);
    });

    test('requestPermission → true', () async {
      final gps = MockGpsService(position: null);
      expect(await gps.requestPermission(), isTrue);
    });
  });
}
