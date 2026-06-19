import 'package:flutter/material.dart';
import 'package:mobile_scanner/mobile_scanner.dart';

/// Barcode / QR kod skaner xizmati abstraktsiyasi.
///
/// Foydalanish: katalog ekranida MXIK yoki barcode skanerlash uchun.
///
/// Platform sozlamalari:
///   Android — AndroidManifest.xml:
///     <uses-permission android:name="android.permission.CAMERA"/>
///     <uses-feature android:name="android.hardware.camera" android:required="false"/>
///   iOS — Info.plist:
///     NSCameraUsageDescription
abstract class BarcodeScannerService {
  /// Barcode skanerini ochish va natija qaytarish.
  /// [context] — Navigator uchun kerak.
  /// Qaytaradi: skanerlangan qiymat (String), yoki null — bekor qilinsa.
  Future<String?> scan(BuildContext context);
}

/// mobile_scanner paketi orqali haqiqiy implementatsiya.
///
/// BarcodeScannerScreen — to'liq ekran scanner (push navigation).
class MobileScannerService implements BarcodeScannerService {
  const MobileScannerService();

  @override
  Future<String?> scan(BuildContext context) async {
    return Navigator.of(context).push<String>(
      MaterialPageRoute<String>(
        builder: (_) => const _BarcodeScannerScreen(),
      ),
    );
  }
}

/// To'liq ekran barcode skaner widget.
///
/// Barcode aniqlangach avtomatik yopiladi va qiymat qaytaradi.
class _BarcodeScannerScreen extends StatefulWidget {
  const _BarcodeScannerScreen();

  @override
  State<_BarcodeScannerScreen> createState() =>
      _BarcodeScannerScreenState();
}

class _BarcodeScannerScreenState extends State<_BarcodeScannerScreen> {
  late final MobileScannerController _controller;
  bool _isDetected = false;

  @override
  void initState() {
    super.initState();
    _controller = MobileScannerController();
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  void _onDetect(BarcodeCapture capture) {
    if (_isDetected) return; // Bir martadan ko'p ishlamasin
    final barcodes = capture.barcodes;
    if (barcodes.isEmpty) return;
    final value = barcodes.first.rawValue;
    if (value == null || value.isEmpty) return;

    _isDetected = true;
    Navigator.of(context).pop(value);
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Barcode skanerla'),
        backgroundColor: Colors.black,
        foregroundColor: Colors.white,
        actions: [
          // Fener tugmasi — MobileScannerController.value.torchState
          ValueListenableBuilder<MobileScannerState>(
            valueListenable: _controller,
            builder: (_, state, __) {
              final isOn = state.torchState == TorchState.on;
              return IconButton(
                icon: Icon(isOn ? Icons.flash_on : Icons.flash_off),
                onPressed: _controller.toggleTorch,
                color: Colors.white,
              );
            },
          ),
          // Kamera almashtirish
          IconButton(
            icon: const Icon(Icons.flip_camera_ios),
            onPressed: _controller.switchCamera,
            color: Colors.white,
          ),
        ],
      ),
      body: Stack(
        children: [
          MobileScanner(
            controller: _controller,
            onDetect: _onDetect,
          ),
          // Yo'naltiruvchi ramka
          Center(
            child: Container(
              width: 250,
              height: 150,
              decoration: BoxDecoration(
                border: Border.all(color: Colors.green, width: 2),
                borderRadius: BorderRadius.circular(8),
              ),
            ),
          ),
          // Yo'riqnoma matni
          const Positioned(
            bottom: 48,
            left: 0,
            right: 0,
            child: Text(
              'Barcodni ramkaga joylashtiring',
              textAlign: TextAlign.center,
              style: TextStyle(
                color: Colors.white,
                fontSize: 14,
                shadows: [Shadow(blurRadius: 4)],
              ),
            ),
          ),
        ],
      ),
      backgroundColor: Colors.black,
    );
  }
}

/// Test uchun mock implementatsiya.
class MockBarcodeScannerService implements BarcodeScannerService {
  const MockBarcodeScannerService({this.mockResult});

  final String? mockResult;

  @override
  Future<String?> scan(BuildContext context) async => mockResult;
}
