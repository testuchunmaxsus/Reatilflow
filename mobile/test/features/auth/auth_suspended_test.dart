import 'package:dio/dio.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mocktail/mocktail.dart';
import 'package:retail_mobile/data/remote/api_client.dart';
import 'package:retail_mobile/data/remote/models/auth_models.dart';
import 'package:retail_mobile/data/remote/token_storage.dart';
import 'package:retail_mobile/features/auth/auth_providers.dart';
import 'package:retail_mobile/features/auth/auth_repository.dart';
import 'package:retail_mobile/features/enterprise/enterprise_model.dart';
import 'package:retail_mobile/features/enterprise/enterprise_providers.dart';
import 'package:retail_mobile/features/enterprise/enterprise_repository.dart';
import 'package:shared_preferences/shared_preferences.dart';

// ignore_for_file: avoid_redundant_argument_values

class MockApiClient extends Mock implements ApiClient {}

class MockTokenStorage extends Mock implements TokenStorage {}

class FakeLoginRequest extends Fake implements LoginRequest {}

class FakeLogoutRequest extends Fake implements LogoutRequest {}

/// InMemoryPrefs — test uchun SharedPreferences stub.
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

/// 403 DioException yasash yordamchi funktsiyasi.
DioException _make403(Map<String, dynamic> body) {
  final response = Response<Map<String, dynamic>>(
    requestOptions: RequestOptions(path: '/auth/login'),
    statusCode: 403,
    data: body,
  );
  return DioException(
    requestOptions: RequestOptions(path: '/auth/login'),
    response: response,
    type: DioExceptionType.badResponse,
  );
}

void main() {
  setUpAll(() {
    registerFallbackValue(FakeLoginRequest());
    registerFallbackValue(FakeLogoutRequest());
  });

  group('Suspended korxona — login xatosi', () {
    late MockApiClient mockApi;
    late MockTokenStorage mockStorage;
    late InMemoryPrefs prefs;

    setUp(() {
      mockApi = MockApiClient();
      mockStorage = MockTokenStorage();
      prefs = InMemoryPrefs();

      when(() => mockStorage.hasTokens()).thenAnswer((_) async => false);
      when(() => mockApi.getEnterpriseInfo())
          .thenAnswer((_) async => enterpriseAllModules);
    });

    ProviderContainer makeContainer() {
      return ProviderContainer(
        overrides: [
          authRepositoryProvider.overrideWith(
            (ref) => AuthRepository(
              apiClient: mockApi,
              tokenStorage: mockStorage,
            ),
          ),
          sharedPreferencesProvider.overrideWithValue(prefs),
          enterpriseRepositoryProvider.overrideWith(
            (ref) => EnterpriseRepository(apiClient: mockApi, prefs: prefs),
          ),
        ],
      );
    }

    test(
      'enterprise.suspended (403, message_key to\'g\'ridan) → '
      'AuthStateError + tushunarli xabar',
      () async {
        final container = makeContainer();
        addTearDown(container.dispose);

        when(() => mockApi.login(any())).thenThrow(
          _make403({'message_key': 'enterprise.suspended'}),
        );

        await container.read(authNotifierProvider.notifier).login(
              phone: '+998901234567',
              password: 'wrong',
            );

        final state = container.read(authNotifierProvider);
        expect(state, isA<AuthStateError>());
        final error = state as AuthStateError;
        expect(
          error.message,
          contains('Korxona faollashtirilmagan'),
        );
      },
    );

    test(
      'enterprise.suspended (403, detail envelope) → AuthStateError',
      () async {
        final container = makeContainer();
        addTearDown(container.dispose);

        when(() => mockApi.login(any())).thenThrow(
          _make403({
            'detail': {'message_key': 'enterprise.suspended'},
          }),
        );

        await container.read(authNotifierProvider.notifier).login(
              phone: '+998901234567',
              password: 'pass',
            );

        final state = container.read(authNotifierProvider);
        expect(state, isA<AuthStateError>());
        final error = state as AuthStateError;
        expect(error.message, contains('Korxona'));
      },
    );

    test(
      '403 boshqa sabab (masalan: not_found) → oddiy AuthStateError '
      '(suspended xabar emas)',
      () async {
        final container = makeContainer();
        addTearDown(container.dispose);

        when(() => mockApi.login(any())).thenThrow(
          _make403({'message_key': 'user.not_found'}),
        );

        await container.read(authNotifierProvider.notifier).login(
              phone: '+998901234567',
              password: 'pass',
            );

        final state = container.read(authNotifierProvider);
        expect(state, isA<AuthStateError>());
        final error = state as AuthStateError;
        // suspended xabar emas
        expect(
          error.message,
          isNot(contains('Korxona faollashtirilmagan')),
        );
      },
    );

    test(
      'oddiy 401 login xatosi → AuthStateError (suspended emas)',
      () async {
        final container = makeContainer();
        addTearDown(container.dispose);

        final resp = Response<Map<String, dynamic>>(
          requestOptions: RequestOptions(path: '/auth/login'),
          statusCode: 401,
          data: {'detail': 'Invalid credentials'},
        );
        when(() => mockApi.login(any())).thenThrow(
          DioException(
            requestOptions: RequestOptions(path: '/auth/login'),
            response: resp,
            type: DioExceptionType.badResponse,
          ),
        );

        await container.read(authNotifierProvider.notifier).login(
              phone: '+998901234567',
              password: 'wrong',
            );

        final state = container.read(authNotifierProvider);
        expect(state, isA<AuthStateError>());
        final error = state as AuthStateError;
        expect(error.message, isNot(contains('Korxona faollashtirilmagan')));
      },
    );
  });
}
