package uz.retailflow.retail_mobile

import io.flutter.embedding.android.FlutterFragmentActivity

// local_auth (biometrik) Android'da FlutterFragmentActivity talab qiladi —
// FlutterActivity bilan BiometricPrompt "no_fragment_activity" xatosini beradi.
class MainActivity : FlutterFragmentActivity()
