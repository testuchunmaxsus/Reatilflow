import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'app.dart';
import 'data/local/database.dart';
import 'data/local/database_provider.dart';
import 'features/enterprise/enterprise_providers.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();

  // Lokal bazani ishga tushirish
  final database = AppDatabase();

  // SharedPreferences (enterprise modules keshi)
  final prefs = await SharedPreferences.getInstance();

  runApp(
    ProviderScope(
      overrides: [
        databaseProvider.overrideWithValue(database),
        sharedPreferencesProvider.overrideWithValue(prefs),
      ],
      child: const RetailApp(),
    ),
  );
}
