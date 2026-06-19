import 'package:local_auth/local_auth.dart';

/// Qurilma-lokal biometriya xizmati abstraktsiyasi.
///
/// Qoida (ATTENDANCE.md): biometrik ma'lumot serverga BORMAYDI —
/// faqat biometric_verified=true boolean bayrog'i yuboriladi.
abstract class BiometricService {
  /// Biometrik autentifikatsiya qiladi.
  /// [reason] — foydalanuvchiga ko'rsatiladigan sabab matni.
  /// Qaytaradi: true — muvaffaqiyatli, false — rad etilgan yoki xato.
  Future<bool> authenticate({required String reason});

  /// Qurilmada biometrik mavjudligini tekshirish.
  Future<bool> isAvailable();
}

/// LocalAuth (local_auth paketi) orqali haqiqiy implementatsiya.
///
/// Android: BiometricPrompt API.
/// iOS: Face ID / Touch ID (LAContext).
///
/// Platform sozlamalari:
///   Android — AndroidManifest.xml:
///     <uses-permission android:name="android.permission.USE_BIOMETRIC"/>
///     <uses-permission android:name="android.permission.USE_FINGERPRINT"/>
///   iOS — Info.plist:
///     NSFaceIDUsageDescription
class LocalAuthBiometricService implements BiometricService {
  LocalAuthBiometricService() : _auth = LocalAuthentication();

  final LocalAuthentication _auth;

  @override
  Future<bool> authenticate({required String reason}) async {
    try {
      final canCheck = await _auth.canCheckBiometrics;
      final isDeviceSupported = await _auth.isDeviceSupported();
      if (!canCheck && !isDeviceSupported) {
        // Qurilmada biometrik yo'q — false qaytaradi (graceful)
        return false;
      }

      return await _auth.authenticate(
        localizedReason: reason,
        options: const AuthenticationOptions(
          stickyAuth: true, // foydalanuvchi app'dan chiqqanda dialog saqlanadi
        ),
      );
    } on Exception {
      // Ruxsat rad etilgan, biometrik sozlanmagan yoki boshqa platform xatosi
      return false;
    }
  }

  @override
  Future<bool> isAvailable() async {
    try {
      final canCheck = await _auth.canCheckBiometrics;
      final isDeviceSupported = await _auth.isDeviceSupported();
      return canCheck || isDeviceSupported;
    } on Exception {
      return false;
    }
  }
}

/// Test va development uchun mock implementatsiya.
///
/// Interfeys o'zgarmagan — mavjud testlar shu mock bilan ishlaydi.
class MockBiometricService implements BiometricService {
  MockBiometricService({this.shouldSucceed = true});
  final bool shouldSucceed;

  @override
  Future<bool> authenticate({required String reason}) async {
    // Kech qaytish — haqiqiy dialog simulatsiyasi
    await Future<void>.delayed(const Duration(milliseconds: 300));
    return shouldSucceed;
  }

  @override
  Future<bool> isAvailable() async => true;
}
