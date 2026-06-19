import 'dart:async';

import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../data/local/database.dart';
import '../../data/local/database_provider.dart';
import '../../data/remote/api_client.dart';
import '../attendance/gps_service.dart';
import 'delivery_repository.dart';
import 'proof_photo_service.dart';

// ---------------------------------------------------------------------------
// Provayderlar

/// DeliveryRepository — lokal DB + opsional ApiClient
final deliveryRepositoryProvider = Provider<DeliveryRepository>((ref) {
  final db = ref.watch(databaseProvider);
  // ApiClient ixtiyoriy — test muhitida null bo'lishi mumkin
  ApiClient? client;
  try {
    client = ref.watch(apiClientProvider);
  } catch (_) {
    client = null;
  }
  return DeliveryRepository(db: db, apiClient: client);
});

/// ApiClient provider — app_router yoki auth bilan birga o'rnatilishi kerak.
/// Bu yerda placeholder — asosiy app'da override qilinadi.
final apiClientProvider = Provider<ApiClient>((ref) {
  throw UnimplementedError(
      'apiClientProvider override qilinmagan. '
      'ProviderScope da override qiling.');
});

/// GpsService provider (attendance_providers dan qayta ishlat)
final deliveryGpsServiceProvider = Provider<GpsService>((ref) {
  return GeolocatorGpsService();
});

/// ProofPhotoService provider (test muhitida override qilinishi mumkin)
final proofPhotoServiceProvider = Provider<ProofPhotoService>((ref) {
  return ImagePickerProofPhotoService();
});

// ---------------------------------------------------------------------------
// Yetkazish ro'yxati stream

/// Barcha yetkazishlar stream (lokal Drift)
final deliveriesStreamProvider =
    StreamProvider<List<Delivery>>((ref) {
  return ref.watch(deliveryRepositoryProvider).watchAll();
});

/// Faol yetkazishlar stream
final activeDeliveriesStreamProvider =
    StreamProvider<List<Delivery>>((ref) {
  return ref.watch(deliveryRepositoryProvider).watchActive();
});

/// Bitta yetkazish stream
final deliveryStreamProvider =
    StreamProvider.family<Delivery?, String>((ref, id) {
  return ref.watch(deliveryRepositoryProvider).watchById(id);
});

/// Faol yetkazishlar soni (dashboard badge)
final activeDeliveriesCountProvider = FutureProvider<int>((ref) {
  return ref.watch(deliveryRepositoryProvider).countActive();
});

// ---------------------------------------------------------------------------
// GPS tracking holati

/// GPS tracking faol yetkazish ID si (null = to'xtagan)
final _activeGpsDeliveryIdProvider =
    StateProvider<String?>((ref) => null);

// ---------------------------------------------------------------------------
// Holat — DeliveryDetailNotifier

sealed class DeliveryActionState {
  const DeliveryActionState();
}

class DeliveryActionIdle extends DeliveryActionState {
  const DeliveryActionIdle();
}

class DeliveryActionLoading extends DeliveryActionState {
  const DeliveryActionLoading();
}

class DeliveryActionSuccess extends DeliveryActionState {
  const DeliveryActionSuccess({required this.delivery});
  final Delivery delivery;
}

class DeliveryActionError extends DeliveryActionState {
  const DeliveryActionError({required this.message});
  final String message;
}

/// Yetkazish detail notifier — holat o'zgartirish + GPS boshqarish.
class DeliveryDetailNotifier
    extends StateNotifier<DeliveryActionState> {
  DeliveryDetailNotifier({
    required DeliveryRepository repository,
    required GpsService gpsService,
    required String deliveryId,
    required StateController<String?> activeGpsController,
  })  : _repository = repository,
        _gpsService = gpsService,
        _deliveryId = deliveryId,
        _activeGpsController = activeGpsController,
        super(const DeliveryActionIdle());

  final DeliveryRepository _repository;
  final GpsService _gpsService;
  final String _deliveryId;
  final StateController<String?> _activeGpsController;

  /// GPS interval: 30-60s (ADR §3.7 kuryerga, agent uchun 2-5 daq'dan tezroq)
  static const _gpsInterval = Duration(seconds: 45);
  Timer? _gpsTimer;

  /// Holat o'zgartirish.
  ///
  /// [newStatus] — maqsad holat.
  /// [failureReason] — failed uchun.
  ///
  /// GPS:
  ///   - started/delivering → GPS yonadi
  ///   - delivered/failed → GPS o'chadi
  Future<void> changeStatus({
    required String newStatus,
    String? failureReason,
  }) async {
    state = const DeliveryActionLoading();
    try {
      await _gpsService.requestPermission();
      final gps = await _gpsService.getCurrentPosition();

      final updated = await _repository.updateStatus(
        id: _deliveryId,
        newStatus: newStatus,
        gpsPosition: gps,
        failureReason: failureReason,
      );

      // GPS tracking boshqarish
      if (kGpsActiveStatuses.contains(newStatus)) {
        _startGpsTracking();
      } else if (kTerminalStatuses.contains(newStatus)) {
        _stopGpsTracking();
      }

      state = DeliveryActionSuccess(delivery: updated);
      // Qayta idle holatga qaytish
      await Future<void>.delayed(const Duration(milliseconds: 500));
      if (mounted) state = const DeliveryActionIdle();
    } on InvalidTransitionException catch (e) {
      state = DeliveryActionError(
          message: 'Noto\'g\'ri o\'tish: ${e.from} → ${e.to}');
    } on DeliveryNotFoundException catch (e) {
      state = DeliveryActionError(message: 'Yetkazish topilmadi: ${e.id}');
    } on Exception catch (e) {
      state = DeliveryActionError(message: e.toString());
    }
  }

  /// Yetkazish faol holatda GPS tracking boshlash.
  void startGpsTrackingIfActive(String currentStatus) {
    if (kGpsActiveStatuses.contains(currentStatus)) {
      _startGpsTracking();
    }
  }

  void _startGpsTracking() {
    _gpsTimer?.cancel();
    _activeGpsController.state = _deliveryId;
    _gpsTimer = Timer.periodic(_gpsInterval, (_) async {
      final gps = await _gpsService.getCurrentPosition();
      if (gps != null) {
        await _repository.ingestGps(
          deliveryId: _deliveryId,
          position: gps,
        );
      }
    });
  }

  void _stopGpsTracking() {
    _gpsTimer?.cancel();
    _gpsTimer = null;
    if (_activeGpsController.state == _deliveryId) {
      _activeGpsController.state = null;
    }
  }

  @override
  void dispose() {
    _stopGpsTracking();
    super.dispose();
  }
}

/// DeliveryDetailNotifier provider (delivery ID bo'yicha)
final deliveryDetailNotifierProvider = StateNotifierProvider.family<
    DeliveryDetailNotifier, DeliveryActionState, String>((ref, deliveryId) {
  return DeliveryDetailNotifier(
    repository: ref.watch(deliveryRepositoryProvider),
    gpsService: ref.watch(deliveryGpsServiceProvider),
    deliveryId: deliveryId,
    activeGpsController: ref.read(_activeGpsDeliveryIdProvider.notifier),
  );
});
