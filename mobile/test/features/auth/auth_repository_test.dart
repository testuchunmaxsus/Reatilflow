import 'package:flutter_test/flutter_test.dart';
import 'package:mocktail/mocktail.dart';
import 'package:retail_mobile/data/remote/api_client.dart';
import 'package:retail_mobile/data/remote/models/auth_models.dart';
import 'package:retail_mobile/data/remote/token_storage.dart';
import 'package:retail_mobile/features/auth/auth_repository.dart';
// ignore_for_file: avoid_redundant_argument_values

// Mocktail mock'lari
class MockApiClient extends Mock implements ApiClient {}

class MockTokenStorage extends Mock implements TokenStorage {}

// Fallback qiymatlar mocktail uchun
class FakeLoginRequest extends Fake implements LoginRequest {}

class FakeLogoutRequest extends Fake implements LogoutRequest {}

void main() {
  setUpAll(() {
    registerFallbackValue(FakeLoginRequest());
    registerFallbackValue(FakeLogoutRequest());
  });

  group('AuthRepository', () {
    late MockApiClient mockApi;
    late MockTokenStorage mockStorage;
    late AuthRepository repository;

    const testUser = MeResponse(
      id: 'user-001',
      phone: '+998901234567',
      fullName: 'Test Agent',
      role: 'agent',
      branchId: 'branch-001',
      locale: 'uz',
      isActive: true,
      biometricEnrolled: false,
    );

    setUp(() {
      mockApi = MockApiClient();
      mockStorage = MockTokenStorage();
      repository = AuthRepository(
        apiClient: mockApi,
        tokenStorage: mockStorage,
      );
    });

    test('login — token saqlanadi, user qaytariladi', () async {
      when(() => mockApi.login(any())).thenAnswer(
        (_) async => const TokenPair(
          accessToken: 'access-jwt',
          refreshToken: 'refresh-jwt',
          tokenType: 'bearer',
        ),
      );
      when(
        () => mockStorage.saveTokens(
          accessToken: any(named: 'accessToken'),
          refreshToken: any(named: 'refreshToken'),
        ),
      ).thenAnswer((_) async {});
      when(() => mockApi.getMe()).thenAnswer((_) async => testUser);

      final user = await repository.login(
        phone: '+998901234567',
        password: 'secret123',
      );

      expect(user.role, equals('agent'));
      expect(user.id, equals('user-001'));

      // Token saqlandi
      verify(
        () => mockStorage.saveTokens(
          accessToken: 'access-jwt',
          refreshToken: 'refresh-jwt',
        ),
      ).called(1);
    });

    test('tryAutoLogin — token yo\'q bo\'lsa null qaytaradi', () async {
      when(() => mockStorage.hasTokens()).thenAnswer((_) async => false);

      final user = await repository.tryAutoLogin();
      expect(user, isNull);
      verifyNever(() => mockApi.getMe());
    });

    test('tryAutoLogin — token bor, server xatosi → null', () async {
      when(() => mockStorage.hasTokens()).thenAnswer((_) async => true);
      when(() => mockApi.getMe()).thenThrow(Exception('Unauthorized'));

      final user = await repository.tryAutoLogin();
      expect(user, isNull);
    });

    test('tryAutoLogin — token bor, user qaytariladi', () async {
      when(() => mockStorage.hasTokens()).thenAnswer((_) async => true);
      when(() => mockApi.getMe()).thenAnswer((_) async => testUser);

      final user = await repository.tryAutoLogin();
      expect(user?.id, equals('user-001'));
    });

    test('logout — server chaqiriladi va token o\'chiriladi', () async {
      when(() => mockStorage.getRefreshToken())
          .thenAnswer((_) async => 'refresh-jwt');
      when(() => mockApi.logout(any())).thenAnswer((_) async {});
      when(() => mockStorage.clearTokens()).thenAnswer((_) async {});

      // Avval login state
      when(() => mockStorage.hasTokens()).thenAnswer((_) async => true);
      when(() => mockApi.getMe()).thenAnswer((_) async => testUser);
      when(() => mockApi.login(any())).thenAnswer(
        (_) async => const TokenPair(
          accessToken: 'a',
          refreshToken: 'refresh-jwt',
          tokenType: 'bearer',
        ),
      );
      when(
        () => mockStorage.saveTokens(
          accessToken: any(named: 'accessToken'),
          refreshToken: any(named: 'refreshToken'),
        ),
      ).thenAnswer((_) async {});

      await repository.login(phone: '+99890', password: 'pass');
      await repository.logout();

      verify(() => mockStorage.clearTokens()).called(1);
      expect(repository.currentUser, isNull);
    });

    test('logout — server xatosi bo\'lsa ham lokal token o\'chiriladi',
        () async {
      when(() => mockStorage.getRefreshToken())
          .thenAnswer((_) async => 'refresh-jwt');
      when(() => mockApi.logout(any())).thenThrow(Exception('500'));
      when(() => mockStorage.clearTokens()).thenAnswer((_) async {});

      await repository.logout();

      // Token baribir o'chirildi
      verify(() => mockStorage.clearTokens()).called(1);
    });

    test('userRole — login dan keyin rol qaytaradi', () async {
      when(() => mockApi.login(any())).thenAnswer(
        (_) async => const TokenPair(
          accessToken: 'a',
          refreshToken: 'r',
          tokenType: 'bearer',
        ),
      );
      when(
        () => mockStorage.saveTokens(
          accessToken: any(named: 'accessToken'),
          refreshToken: any(named: 'refreshToken'),
        ),
      ).thenAnswer((_) async {});
      when(() => mockApi.getMe()).thenAnswer((_) async => testUser);

      await repository.login(phone: '+99890', password: 'pass');

      expect(repository.userRole, equals('agent'));
    });
  });
}
