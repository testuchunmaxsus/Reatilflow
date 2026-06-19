import 'dart:convert';

import 'package:drift/native.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:retail_mobile/data/local/dao/outbox_dao.dart';
import 'package:retail_mobile/data/local/database.dart';
import 'package:retail_mobile/features/attendance/attendance_repository.dart';
import 'package:retail_mobile/features/attendance/gps_service.dart';
import 'package:retail_mobile/features/orders/order_repository.dart';

AppDatabase _makeDb() => AppDatabase.forTesting(NativeDatabase.memory());

/// T11 narx himoyasi: outbox payloadida price/discount/segment_id YO'Q.
void main() {
  group('T11 — Narx server-avtoritar himoyasi (CreateOrder)', () {
    late AppDatabase db;
    late OrderRepository repository;
    late OutboxDao outboxDao;

    setUp(() {
      db = _makeDb();
      repository = OrderRepository(db: db);
      outboxDao = OutboxDao(db);
    });
    tearDown(() => db.close());

    test(
      'outbox payload faqat product_id + qty — narx/discount/segment_id YO\'Q',
      () async {
        await repository.createOrder(
          storeId: 'store-001',
          agentId: 'agent-001',
          lines: const [
            // unitPrice local_display uchun — outbox'ga bormaydi
            OrderLineInput(productId: 'p1', qty: 5, unitPrice: 99999),
            OrderLineInput(productId: 'p2', qty: 2, unitPrice: 50000),
          ],
        );

        final pending = await outboxDao.getPending();
        expect(pending.length, equals(1));

        final payload =
            jsonDecode(pending.first.payload) as Map<String, dynamic>;
        final lines = payload['lines'] as List;

        for (final line in lines) {
          final lineMap = line as Map<String, dynamic>;
          // Faqat product_id + qty bo'lishi kerak
          expect(lineMap.containsKey('product_id'), isTrue);
          expect(lineMap.containsKey('qty'), isTrue);
          // Narx, discount, segment_id YO'Q (T11)
          expect(lineMap.containsKey('unit_price'), isFalse);
          expect(lineMap.containsKey('price'), isFalse);
          expect(lineMap.containsKey('discount'), isFalse);
          expect(lineMap.containsKey('segment_id'), isFalse);
          expect(lineMap.containsKey('line_total'), isFalse);
        }
      },
    );

    test(
      'store_id va mode outbox payloadida mavjud, narx YO\'Q',
      () async {
        await repository.createOrder(
          storeId: 'store-xyz',
          agentId: 'agent-abc',
          mode: 'oddiy',
          lines: const [OrderLineInput(productId: 'p1', qty: 1)],
        );

        final pending = await outboxDao.getPending();
        final payload =
            jsonDecode(pending.first.payload) as Map<String, dynamic>;

        expect(payload['store_id'], equals('store-xyz'));
        expect(payload['mode'], equals('oddiy'));
        // Top-level narx ham yo'q
        expect(payload.containsKey('total_amount'), isFalse);
        expect(payload.containsKey('unit_price'), isFalse);
      },
    );
  });

  // -----------------------------------------------------------------------
  // GPS ADR §3.7 — ish vaqtida GPS, tashqarisida yo'q
  // -----------------------------------------------------------------------

  group('GPS — ish vaqtida tracking (ADR §3.7)', () {
    late AppDatabase db;
    late AttendanceRepository attendanceRepository;
    late OutboxDao outboxDao;
    const testGps = GpsPosition(lat: 41.2995, lng: 69.2401);

    setUp(() {
      db = _makeDb();
      attendanceRepository = AttendanceRepository(db: db);
      outboxDao = OutboxDao(db);
    });
    tearDown(() => db.close());

    test('ish vaqtida ingestGps — gps.ingest outbox\'ga yoziladi', () async {
      // Check-in
      await attendanceRepository.checkIn(
        biometricVerified: true,
        gpsPosition: testGps,
      );

      // GPS yig'ish
      await attendanceRepository.ingestGps(position: testGps);

      final pending = await outboxDao.getPending();
      final gpsOps = pending.where((p) => p.opType == 'gps.ingest').toList();
      expect(gpsOps.length, equals(1));

      final payload =
          jsonDecode(gpsOps.first.payload) as Map<String, dynamic>;
      final points = payload['points'] as List;
      expect(points.isNotEmpty, isTrue);
      final point = points.first as Map<String, dynamic>;
      expect(point.containsKey('lat'), isTrue);
      expect(point.containsKey('lng'), isTrue);
      expect(point.containsKey('recorded_at'), isTrue);
    });

    test('ish tashqarisida (check-in yo\'q) ingestGps — yozilmaydi', () async {
      // Check-in YO'Q
      await attendanceRepository.ingestGps(position: testGps);

      final pending = await outboxDao.getPending();
      expect(pending.where((p) => p.opType == 'gps.ingest'), isEmpty);
    });

    test('check-out dan keyin ingestGps — yozilmaydi (ish tugadi)', () async {
      await attendanceRepository.checkIn(
          biometricVerified: true, gpsPosition: testGps);
      await attendanceRepository.checkOut(gpsPosition: testGps);

      // Ish tugadi — endi GPS olinmasligi kerak
      await attendanceRepository.ingestGps(position: testGps);

      final pending = await outboxDao.getPending();
      // faqat check_in + check_out bor, gps.ingest yo'q
      final gpsIngest =
          pending.where((p) => p.opType == 'gps.ingest').toList();
      expect(gpsIngest, isEmpty);
    });

    test('bir necha GPS nuqta yig\'ish — har biri alohida outbox op', () async {
      await attendanceRepository.checkIn(
          biometricVerified: true, gpsPosition: testGps);

      const positions = [
        GpsPosition(lat: 41.2995, lng: 69.2401),
        GpsPosition(lat: 41.2998, lng: 69.2405),
        GpsPosition(lat: 41.3001, lng: 69.2410),
      ];

      for (final pos in positions) {
        await attendanceRepository.ingestGps(position: pos);
      }

      final pending = await outboxDao.getPending();
      final gpsOps = pending.where((p) => p.opType == 'gps.ingest').toList();
      expect(gpsOps.length, equals(3));
    });
  });
}
