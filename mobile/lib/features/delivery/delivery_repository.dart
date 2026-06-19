import 'dart:convert';

import 'package:dio/dio.dart';
import 'package:drift/drift.dart';
import 'package:uuid/uuid.dart';

import '../../data/local/dao/deliveries_dao.dart';
import '../../data/local/dao/outbox_dao.dart';
import '../../data/local/database.dart';
import '../../data/remote/api_client.dart';
import '../attendance/gps_service.dart';

/// Yetkazish holat mashinasi — server-avtoritar (DELIVERY.md).
///
/// Mumkin o'tishlar:
///   assigned  → started, failed
///   started   → delivering, failed
///   delivering → delivered, failed
///   delivered, failed → (terminal, o'tish yo'q)
const Map<String, List<String>> kValidTransitions = {
  'assigned': ['started', 'failed'],
  'started': ['delivering', 'failed'],
  'delivering': ['delivered', 'failed'],
  'delivered': [],
  'failed': [],
};

/// Terminal holatlar — GPS to'xtaydi, boshqa o'tish yo'q.
const Set<String> kTerminalStatuses = {'delivered', 'failed'};

/// GPS faol bo'lishi kerak bo'lgan holatlar (DELIVERY.md + ADR §3.7).
const Set<String> kGpsActiveStatuses = {'started', 'delivering'};

/// Holat o'tishi ruxsat etilganligini tekshirish.
bool isValidTransition(String from, String to) {
  return kValidTransitions[from]?.contains(to) ?? false;
}

/// Yetkazish xato turlari
class InvalidTransitionException implements Exception {
  const InvalidTransitionException(this.from, this.to);
  final String from;
  final String to;

  @override
  String toString() =>
      'InvalidTransitionException: $from → $to o\'tishi ruxsat etilmagan';
}

class DeliveryNotFoundException implements Exception {
  const DeliveryNotFoundException(this.id);
  final String id;

  @override
  String toString() => 'DeliveryNotFoundException: $id topilmadi';
}

/// Yetkazish repository — offline-first.
///
/// - Holat yangilash: lokal Drift + outbox (`delivery.status_update`)
///   yoki to'g'ridan-to'g'ri `PATCH /delivery/{id}/status` (online).
/// - proof_photo: `POST /delivery/{id}/proof-photo` (multipart).
/// - GPS: faol yetkazishda 30-60s interval → outbox `gps.ingest` (delivery_id bilan).
class DeliveryRepository {
  DeliveryRepository({
    required AppDatabase db,
    ApiClient? apiClient,
  })  : _deliveriesDao = DeliveriesDao(db),
        _outboxDao = OutboxDao(db),
        _apiClient = apiClient;

  final DeliveriesDao _deliveriesDao;
  final OutboxDao _outboxDao;
  final ApiClient? _apiClient;

  static const _uuid = Uuid();

  // ---------------------------------------------------------------------------
  // Read

  /// Barcha yetkazishlarni kuzatish (lokal Drift).
  Stream<List<Delivery>> watchAll() => _deliveriesDao.watchAll();

  /// Faol yetkazishlar (terminal bo'lmagan).
  Stream<List<Delivery>> watchActive() => _deliveriesDao.watchActive();

  /// ID bo'yicha kuzatish.
  Stream<Delivery?> watchById(String id) => _deliveriesDao.watchById(id);

  /// ID bo'yicha olish.
  Future<Delivery?> getById(String id) => _deliveriesDao.getById(id);

  /// Faol yetkazishlar soni (dashboard).
  Future<int> countActive() => _deliveriesDao.countActive();

  // ---------------------------------------------------------------------------
  // Upsert (sync pull natijasi)

  Future<void> upsertFromServer(Map<String, dynamic> json) async {
    final now = DateTime.now();
    await _deliveriesDao.upsert(
      DeliveriesCompanion(
        id: Value(json['id'] as String),
        orderId: Value(json['order_id'] as String),
        courierId: Value(json['courier_id'] as String),
        status: Value(json['status'] as String? ?? 'assigned'),
        address: Value(json['address'] as String?),
        customerName: Value(json['customer_name'] as String?),
        assignedAt: Value(_parseDateTime(json['assigned_at'])),
        startedAt: Value(_parseDateTime(json['started_at'])),
        deliveredAt: Value(_parseDateTime(json['delivered_at'])),
        failureReason: Value(json['failure_reason'] as String?),
        proofPhotoUrl: Value(json['proof_photo_url'] as String?),
        version: Value(json['version'] as int? ?? 1),
        syncStatus: const Value('synced'),
        createdAt: Value(_parseDateTime(json['created_at']) ?? now),
        updatedAt: Value(_parseDateTime(json['updated_at']) ?? now),
      ),
    );
  }

  // ---------------------------------------------------------------------------
  // Status update

  /// Holat o'zgartirish — lokal Drift + outbox.
  ///
  /// [id] — yetkazish ID.
  /// [newStatus] — maqsad holat.
  /// [gpsPosition] — joriy GPS (started/delivered uchun).
  /// [failureReason] — muvaffaqiyatsizlik sababi (failed uchun).
  ///
  /// Holat mashinasi qoidasi lokal tekshiriladi.
  /// Server-avtoritar: server 422 qaytarsa, outbox.status='conflict'.
  Future<Delivery> updateStatus({
    required String id,
    required String newStatus,
    GpsPosition? gpsPosition,
    String? failureReason,
  }) async {
    final delivery = await _deliveriesDao.getById(id);
    if (delivery == null) throw DeliveryNotFoundException(id);

    // Lokal holat mashinasi tekshiruvi (server-avtoritar VALID_TRANSITIONS)
    if (!isValidTransition(delivery.status, newStatus)) {
      throw InvalidTransitionException(delivery.status, newStatus);
    }

    final clientUuid = _uuid.v4();
    final now = DateTime.now();

    // Outbox payload — PATCH /delivery/{id}/status formatida
    final payload = <String, dynamic>{
      'delivery_id': id,
      'status': newStatus,
      'version': delivery.version,
      if (gpsPosition != null) 'gps_lat': gpsPosition.lat.toStringAsFixed(7),
      if (gpsPosition != null) 'gps_lng': gpsPosition.lng.toStringAsFixed(7),
      if (failureReason != null) 'failure_reason': failureReason,
    };

    // Lokal yangilash + outbox — BITTA tranzaksiyada
    await Future.wait([
      _deliveriesDao.updateStatus(
        id,
        status: newStatus,
        failureReason: failureReason,
        version: delivery.version + 1,
        syncStatus: 'pending',
      ),
      _outboxDao.insertOp(
        OutboxQueueCompanion.insert(
          opType: 'delivery.status_update',
          clientUuid: clientUuid,
          payload: jsonEncode(payload),
          createdAt: Value(now),
        ),
      ),
    ]);

    return (await _deliveriesDao.getById(id))!;
  }

  // ---------------------------------------------------------------------------
  // Proof photo upload

  /// Dalil rasmi yuklash — `POST /delivery/{id}/proof-photo` (multipart).
  ///
  /// [imagePath] — qurilmadagi fayl yo'li.
  ///
  /// Agar apiClient yo'q yoki offline bo'lsa — xato ko'tariladi.
  /// Yuk og'ir bo'lsa — interfeys stub + izoh (T20 qoida).
  ///
  /// NOTE(T20-camera): `image_picker`/`camera` paketlari pubspec'da yo'q.
  /// Haqiqiy implementatsiya uchun qo'shing:
  ///   image_picker: ^1.1.0
  /// Keyin:
  ///   final picker = ImagePicker();
  ///   final file = await picker.pickImage(source: ImageSource.camera);
  ///   await deliveryRepository.uploadProofPhoto(id: id, imagePath: file!.path);
  Future<String> uploadProofPhoto({
    required String id,
    required String imagePath,
  }) async {
    if (_apiClient == null) {
      throw StateError('ApiClient mavjud emas — proof_photo yuklash mumkin emas');
    }

    final formData = FormData.fromMap({
      'file': await MultipartFile.fromFile(imagePath),
    });

    final response = await _apiClient.dio.post<Map<String, dynamic>>(
      '/delivery/$id/proof-photo',
      data: formData,
      options: Options(contentType: 'multipart/form-data'),
    );

    final photoUrl = response.data?['proof_photo_url'] as String? ?? '';

    // Lokal yangilash
    await _deliveriesDao.updateStatus(
      id,
      status: (await _deliveriesDao.getById(id))?.status ?? 'delivering',
      proofPhotoUrl: photoUrl,
    );

    return photoUrl;
  }

  // ---------------------------------------------------------------------------
  // GPS ingest (delivery_id bilan)

  /// GPS nuqtasini outbox'ga yozish — yetkazish faol holatda.
  ///
  /// [deliveryId] — GPS nuqtaga bog'liq yetkazish ID.
  /// [position] — joriy joylashuv.
  ///
  /// ADR §3.7: faqat started/delivering holatida chaqiriladi.
  Future<void> ingestGps({
    required String deliveryId,
    required GpsPosition position,
  }) async {
    final delivery = await _deliveriesDao.getById(deliveryId);
    if (delivery == null) return;
    if (!kGpsActiveStatuses.contains(delivery.status)) return;

    final clientUuid = _uuid.v4();
    final now = DateTime.now();

    final payload = {
      'points': [
        {
          'lat': position.lat.toStringAsFixed(7),
          'lng': position.lng.toStringAsFixed(7),
          'recorded_at': now.toUtc().toIso8601String(),
          'speed': null,
          'delivery_id': deliveryId,
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

  // ---------------------------------------------------------------------------
  // Helpers

  DateTime? _parseDateTime(dynamic value) {
    if (value == null) return null;
    if (value is DateTime) return value;
    if (value is String) return DateTime.tryParse(value);
    return null;
  }
}
