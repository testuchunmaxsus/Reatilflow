import 'package:dio/dio.dart';
import 'package:firebase_messaging/firebase_messaging.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../features/auth/auth_providers.dart';

/// FCM push notification xizmati.
///
/// Vazifalar:
///   - Qurilma tokenini backend'ga ro'yxatdan o'tkazish.
///   - Token yangilanganda qayta yuborish.
///   - Foreground xabarlarni log qilish.
///   - Logout'da tokenni o'chirish.
class PushService {
  PushService({required Dio dio}) : _dio = dio;

  final Dio _dio;

  /// Qurilma FCM tokenini backend'ga yuborish.
  ///
  /// Ruxsat so'rash → token olish → PATCH /push/device-token.
  /// Ruxsat berilmasa yoki token null bo'lsa — xatosiz o'tkazib yuboradi.
  Future<void> registerDeviceToken() async {
    try {
      final settings = await FirebaseMessaging.instance.requestPermission();

      if (settings.authorizationStatus == AuthorizationStatus.denied) {
        // Foydalanuvchi rad etdi — xatosiz o'tkazib yuboramiz
        return;
      }

      final token = await FirebaseMessaging.instance.getToken();
      if (token == null) return;

      await _sendToken(token);

      // Token yangilanishlarini kuzatish
      FirebaseMessaging.instance.onTokenRefresh.listen(
        (newToken) async {
          try {
            await _sendToken(newToken);
          } catch (e) {
            // Token yangilanishi xatosi — ilovani buzmaymiz
          }
        },
        onError: (_) {
          // Stream xatosi — ilovani buzmaymiz
        },
      );

      // Foreground xabarlarni kuzatish (minimal log)
      FirebaseMessaging.onMessage.listen(
        (RemoteMessage message) {
          // ignore: avoid_print
          print(
            '[PushService] Foreground xabar: '
            'title=${message.notification?.title}, '
            'body=${message.notification?.body}',
          );
        },
        onError: (_) {
          // Stream xatosi — ilovani buzmaymiz
        },
      );
    } catch (e) {
      // Push ixtiyoriy — asosiy oqimni buzmaymiz
      // ignore: avoid_print
      print('[PushService] registerDeviceToken xatosi: $e');
    }
  }

  /// Logout'da tokenni backend'dan o'chirish.
  ///
  /// PATCH /push/device-token { device_id: null, channel: "fcm" }
  Future<void> unregister() async {
    try {
      await _dio.patch<void>(
        '/push/device-token',
        data: <String, dynamic>{
          'device_id': null,
          'channel': 'fcm',
        },
      );
    } catch (e) {
      // Push ixtiyoriy — asosiy oqimni buzmaymiz
      // ignore: avoid_print
      print('[PushService] unregister xatosi: $e');
    }
  }

  // ---- Private ----

  Future<void> _sendToken(String token) async {
    await _dio.patch<void>(
      '/push/device-token',
      data: <String, dynamic>{
        'device_id': token,
        'channel': 'fcm',
      },
    );
  }
}

/// PushService Riverpod provider.
///
/// apiClientProvider.dio orqali mavjud AuthInterceptor (JWT) ishlatiladi.
final pushServiceProvider = Provider<PushService>((ref) {
  final apiClient = ref.watch(apiClientProvider);
  return PushService(dio: apiClient.dio);
});
