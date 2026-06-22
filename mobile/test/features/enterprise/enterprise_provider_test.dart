import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mocktail/mocktail.dart';
import 'package:retail_mobile/data/remote/api_client.dart';
import 'package:retail_mobile/features/enterprise/enterprise_model.dart';
import 'package:retail_mobile/features/enterprise/enterprise_providers.dart';
import 'package:retail_mobile/features/enterprise/enterprise_repository.dart';
import 'package:shared_preferences/shared_preferences.dart';

// ignore_for_file: avoid_redundant_argument_values

class MockApiClient extends Mock implements ApiClient {}

/// InMemoryPrefs — test uchun SharedPreferences o'rniga.
class InMemoryPrefs implements SharedPreferences {
  final Map<String, Object> _store = {};

  @override
  String? getString(String key) => _store[key] as String?;

  @override
  Future<bool> setString(String key, String value) async {
    _store[key] = value;
    return true;
  }

  @override
  Future<bool> remove(String key) async {
    _store.remove(key);
    return true;
  }

  // --- Qolgan metodlar (ishlatilmaydi, stub) ---
  @override
  bool containsKey(String key) => _store.containsKey(key);

  @override
  Object? get(String key) => _store[key];

  @override
  bool? getBool(String key) => _store[key] as bool?;

  @override
  double? getDouble(String key) => _store[key] as double?;

  @override
  int? getInt(String key) => _store[key] as int?;

  @override
  Set<String> getKeys() => _store.keys.toSet();

  @override
  List<String>? getStringList(String key) => _store[key] as List<String>?;

  @override
  Future<bool> clear() async {
    _store.clear();
    return true;
  }

  @override
  Future<void> reload() async {}

  @override
  Future<bool> setBool(String key, bool value) async {
    _store[key] = value;
    return true;
  }

  @override
  Future<bool> setDouble(String key, double value) async {
    _store[key] = value;
    return true;
  }

  @override
  Future<bool> setInt(String key, int value) async {
    _store[key] = value;
    return true;
  }

  @override
  Future<bool> setStringList(String key, List<String> value) async {
    _store[key] = value;
    return true;
  }

  @override
  Future<bool> commit() async => true;
}

EnterpriseInfo _makeInfo(List<String> modules) => EnterpriseInfo(
      id: 'ent-001',
      name: 'Test Korxona',
      suspended: false,
      enabledModules: modules,
    );

void main() {
  group('EnterpriseModel — hasModule', () {
    test('yoqilgan modul — true', () {
      final info = _makeInfo(['delivery', 'attendance', 'gps']);
      expect(info.hasModule('delivery'), isTrue);
      expect(info.hasModule('attendance'), isTrue);
      expect(info.hasModule('gps'), isTrue);
    });

    test("o'chirilgan modul — false", () {
      final info = _makeInfo(['orders', 'catalog']);
      expect(info.hasModule('delivery'), isFalse);
      expect(info.hasModule('attendance'), isFalse);
      expect(info.hasModule('gps'), isFalse);
    });

    test('bo\'sh modullar — hamma false', () {
      final info = _makeInfo([]);
      expect(info.hasModule('delivery'), isFalse);
      expect(info.hasModule('orders'), isFalse);
    });

    test('enterpriseAllModules — barcha modullar yoqilgan', () {
      expect(enterpriseAllModules.hasModule('delivery'), isTrue);
      expect(enterpriseAllModules.hasModule('attendance'), isTrue);
      expect(enterpriseAllModules.hasModule('gps'), isTrue);
      expect(enterpriseAllModules.hasModule('orders'), isTrue);
      expect(enterpriseAllModules.hasModule('catalog'), isTrue);
    });
  });

  group('EnterpriseRepository', () {
    late MockApiClient mockApi;
    late InMemoryPrefs prefs;
    late EnterpriseRepository repository;

    setUp(() {
      mockApi = MockApiClient();
      prefs = InMemoryPrefs();
      repository = EnterpriseRepository(apiClient: mockApi, prefs: prefs);
    });

    test('fetchAndCache — serverdan oladi va keshga yozadi', () async {
      final serverInfo = _makeInfo(['delivery', 'orders']);
      when(() => mockApi.getEnterpriseInfo())
          .thenAnswer((_) async => serverInfo);

      final result = await repository.fetchAndCache();

      expect(result.enabledModules, containsAll(['delivery', 'orders']));
      expect(result.hasModule('delivery'), isTrue);
      expect(result.hasModule('attendance'), isFalse);

      // Kesh yozilganini tekshirish
      final cached = repository.getCached();
      expect(cached, isNotNull);
      expect(cached!.hasModule('delivery'), isTrue);
    });

    test('fetchAndCache — server xatosi → keshdan qaytaradi', () async {
      // Avval keshga yozamiz
      final cachedInfo = _makeInfo(['catalog']);
      when(() => mockApi.getEnterpriseInfo())
          .thenAnswer((_) async => cachedInfo);
      await repository.fetchAndCache();

      // Server xatosi
      when(() => mockApi.getEnterpriseInfo())
          .thenThrow(Exception('Network error'));

      final result = await repository.fetchAndCache();

      // Keshdan kelgan
      expect(result.hasModule('catalog'), isTrue);
    });

    test('fetchAndCache — server xatosi, kesh yo\'q → fallback', () async {
      when(() => mockApi.getEnterpriseInfo())
          .thenThrow(Exception('Offline'));

      final result = await repository.fetchAndCache();

      // Fallback — barcha modullar yoqilgan
      expect(result.hasModule('delivery'), isTrue);
      expect(result.hasModule('orders'), isTrue);
    });

    test('getCached — kesh yo\'q → null', () {
      expect(repository.getCached(), isNull);
    });

    test('clearCache — keshni o\'chiradi', () async {
      final info = _makeInfo(['delivery']);
      when(() => mockApi.getEnterpriseInfo()).thenAnswer((_) async => info);
      await repository.fetchAndCache();

      await repository.clearCache();

      expect(repository.getCached(), isNull);
    });
  });

  group('EnterpriseNotifier — Riverpod provider', () {
    late MockApiClient mockApi;
    late InMemoryPrefs prefs;

    setUp(() {
      mockApi = MockApiClient();
      prefs = InMemoryPrefs();
    });

    ProviderContainer makeContainer() {
      return ProviderContainer(
        overrides: [
          sharedPreferencesProvider.overrideWithValue(prefs),
          // apiClientProvider o'rniga MockApiClient
          enterpriseRepositoryProvider.overrideWith(
            (ref) => EnterpriseRepository(apiClient: mockApi, prefs: prefs),
          ),
        ],
      );
    }

    test('boshlang\'ich holat — fallback (barcha modullar)', () {
      final container = makeContainer();
      addTearDown(container.dispose);

      final state = container.read(enterpriseNotifierProvider);
      expect(state.hasModule('delivery'), isTrue);
    });

    test('refresh — serverdan modullar yuklanadi', () async {
      final container = makeContainer();
      addTearDown(container.dispose);

      final serverInfo = _makeInfo(['orders', 'catalog']);
      when(() => mockApi.getEnterpriseInfo())
          .thenAnswer((_) async => serverInfo);

      await container.read(enterpriseNotifierProvider.notifier).refresh();

      final state = container.read(enterpriseNotifierProvider);
      expect(state.hasModule('orders'), isTrue);
      expect(state.hasModule('catalog'), isTrue);
      // delivery o'chirilgan
      expect(state.hasModule('delivery'), isFalse);
    });

    test('delivery o\'chiq — moduleEnabledProvider false qaytaradi', () async {
      final container = makeContainer();
      addTearDown(container.dispose);

      when(() => mockApi.getEnterpriseInfo())
          .thenAnswer((_) async => _makeInfo(['attendance', 'catalog']));

      await container.read(enterpriseNotifierProvider.notifier).refresh();

      expect(container.read(moduleEnabledProvider('delivery')), isFalse);
      expect(container.read(moduleEnabledProvider('attendance')), isTrue);
    });

    test('clear — fallback holatga qaytadi', () async {
      final container = makeContainer();
      addTearDown(container.dispose);

      when(() => mockApi.getEnterpriseInfo())
          .thenAnswer((_) async => _makeInfo(['delivery']));
      await container.read(enterpriseNotifierProvider.notifier).refresh();

      // delivery yoqilgan
      expect(container.read(moduleEnabledProvider('delivery')), isTrue);

      await container.read(enterpriseNotifierProvider.notifier).clear();

      // Logout → fallback → barcha modullar
      expect(container.read(moduleEnabledProvider('delivery')), isTrue);
    });

    test('keshdan yuklash — prefs da bor → notifier keshni o\'qiydi', () async {
      // Keshga yozamiz
      final repo = EnterpriseRepository(apiClient: mockApi, prefs: prefs);
      when(() => mockApi.getEnterpriseInfo())
          .thenAnswer((_) async => _makeInfo(['gps']));
      await repo.fetchAndCache();

      // Yangi container — keshdan o'qishi kerak
      final container = makeContainer();
      addTearDown(container.dispose);

      final state = container.read(enterpriseNotifierProvider);
      expect(state.hasModule('gps'), isTrue);
      // orders keshda yo'q
      expect(state.hasModule('orders'), isFalse);
    });
  });
}
