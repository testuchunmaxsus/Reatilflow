import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'database.dart';

/// Global baza provider'i.
/// main.dart da overrideWithValue orqali real instance beriladi.
/// Testlarda in-memory baza bilan override qilinadi.
final databaseProvider = Provider<AppDatabase>((ref) {
  throw UnimplementedError(
    'databaseProvider main.dart da override qilinishi kerak',
  );
});
