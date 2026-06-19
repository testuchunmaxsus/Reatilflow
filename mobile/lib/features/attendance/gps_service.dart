import 'package:geolocator/geolocator.dart';

/// GPS joylashuv xizmati abstraktsiyasi.
///
/// ADR §3.7: Ish vaqtida (check-in dan check-out gacha) GPS olinadi.
/// Agent uchun interval: 3 daqiqa (attendance_providers.dart).
/// Kuryer uchun interval: 45s (delivery_providers.dart).
class GpsPosition {
  const GpsPosition({required this.lat, required this.lng});
  final double lat;
  final double lng;

  Map<String, String> toJson() => {
        'lat': lat.toStringAsFixed(7),
        'lng': lng.toStringAsFixed(7),
      };
}

/// GPS xizmati abstraktsiyasi.
abstract class GpsService {
  /// Joriy joylashuvni olish.
  /// Ruxsat berilmagan yoki GPS o'chiq bo'lsa — null qaytaradi.
  Future<GpsPosition?> getCurrentPosition();

  /// GPS ruxsatini so'rash.
  /// Qaytaradi: true — ruxsat berildi, false — rad etildi.
  Future<bool> requestPermission();
}

/// Geolocator paketi orqali haqiqiy implementatsiya.
///
/// Platform sozlamalari:
///   Android — AndroidManifest.xml:
///     <uses-permission android:name="android.permission.ACCESS_FINE_LOCATION"/>
///     <uses-permission android:name="android.permission.ACCESS_COARSE_LOCATION"/>
///   iOS — Info.plist:
///     NSLocationWhenInUseUsageDescription
///     NSLocationAlwaysAndWhenInUseUsageDescription (opsional)
class GeolocatorGpsService implements GpsService {
  @override
  Future<GpsPosition?> getCurrentPosition() async {
    try {
      // Oldin joriy ruxsatni tekshir
      final LocationPermission permission = await Geolocator.checkPermission();
      if (permission == LocationPermission.denied ||
          permission == LocationPermission.deniedForever) {
        return null;
      }

      final pos = await Geolocator.getCurrentPosition(
        locationSettings: const LocationSettings(
          accuracy: LocationAccuracy.high,
          timeLimit: Duration(seconds: 15),
        ),
      );
      return GpsPosition(lat: pos.latitude, lng: pos.longitude);
    } on LocationServiceDisabledException {
      // GPS o'chirilgan — null qaytaradi (graceful)
      return null;
    } on PermissionDeniedException {
      return null;
    } on Exception {
      return null;
    }
  }

  @override
  Future<bool> requestPermission() async {
    try {
      // GPS xizmati yoqilganini tekshir
      final serviceEnabled = await Geolocator.isLocationServiceEnabled();
      if (!serviceEnabled) {
        return false;
      }

      LocationPermission permission = await Geolocator.checkPermission();

      if (permission == LocationPermission.deniedForever) {
        // Foydalanuvchi sozlamalardan o'zi o'zgartirishi kerak
        return false;
      }

      if (permission == LocationPermission.denied) {
        permission = await Geolocator.requestPermission();
        if (permission == LocationPermission.denied ||
            permission == LocationPermission.deniedForever) {
          return false;
        }
      }

      return permission == LocationPermission.always ||
          permission == LocationPermission.whileInUse;
    } on Exception {
      return false;
    }
  }
}

/// Test uchun mock implementatsiya.
///
/// Interfeys o'zgarmagan — mavjud testlar shu mock bilan ishlaydi.
class MockGpsService implements GpsService {
  MockGpsService({
    this.position = const GpsPosition(lat: 41.2995, lng: 69.2401),
  });
  final GpsPosition? position;

  @override
  Future<GpsPosition?> getCurrentPosition() async {
    await Future<void>.delayed(const Duration(milliseconds: 50));
    return position;
  }

  @override
  Future<bool> requestPermission() async => true;
}
