import 'dart:io';

import 'package:image_picker/image_picker.dart';

/// Yetkazish dalil rasmi xizmati abstraktsiyasi.
///
/// Interfeys orqali mock qilish mumkin — testlarda real kamera chaqirilmaydi.
///
/// Platform sozlamalari:
///   Android — AndroidManifest.xml:
///     <uses-permission android:name="android.permission.CAMERA"/>
///     <uses-feature android:name="android.hardware.camera" android:required="false"/>
///   iOS — Info.plist:
///     NSCameraUsageDescription
///     NSPhotoLibraryUsageDescription (galereya uchun)
abstract class ProofPhotoService {
  /// Kameradan rasm olish.
  /// Qaytaradi: rasm fayli, yoki null — bekor qilinsa.
  Future<File?> takePhoto();

  /// Galereadan rasm tanlash.
  /// Qaytaradi: rasm fayli, yoki null — bekor qilinsa.
  Future<File?> pickFromGallery();
}

/// image_picker paketi orqali haqiqiy implementatsiya.
class ImagePickerProofPhotoService implements ProofPhotoService {
  ImagePickerProofPhotoService() : _picker = ImagePicker();

  final ImagePicker _picker;

  @override
  Future<File?> takePhoto() async {
    try {
      final XFile? image = await _picker.pickImage(
        source: ImageSource.camera,
        imageQuality: 80,   // Hajmni kamaytirish uchun
        maxWidth: 1920,
        maxHeight: 1080,
      );
      if (image == null) return null;
      return File(image.path);
    } on Exception {
      // Ruxsat rad etilgan yoki kamera mavjud emas — null (graceful)
      return null;
    }
  }

  @override
  Future<File?> pickFromGallery() async {
    try {
      final XFile? image = await _picker.pickImage(
        source: ImageSource.gallery,
        imageQuality: 80,
        maxWidth: 1920,
        maxHeight: 1080,
      );
      if (image == null) return null;
      return File(image.path);
    } on Exception {
      return null;
    }
  }
}

/// Test uchun mock implementatsiya.
class MockProofPhotoService implements ProofPhotoService {
  MockProofPhotoService({this.mockFile});
  final File? mockFile;

  @override
  Future<File?> takePhoto() async => mockFile;

  @override
  Future<File?> pickFromGallery() async => mockFile;
}
