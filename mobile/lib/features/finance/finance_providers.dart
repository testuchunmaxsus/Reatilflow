import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../auth/auth_providers.dart';
import 'finance_models.dart';
import 'finance_repository.dart';

// ignore_for_file: use_setters_to_change_properties

// ---------------------------------------------------------------------------
// Repository

final financeRepositoryProvider = Provider<FinanceRepository>((ref) {
  final api = ref.watch(apiClientProvider);
  return FinanceRepository(apiClient: api);
});

// ---------------------------------------------------------------------------
// Balans holati

sealed class FinanceBalanceState {
  const FinanceBalanceState();
}

class FinanceBalanceLoading extends FinanceBalanceState {
  const FinanceBalanceLoading();
}

class FinanceBalanceLoaded extends FinanceBalanceState {
  const FinanceBalanceLoaded({required this.balance});
  final FinanceBalance balance;
}

class FinanceBalanceError extends FinanceBalanceState {
  const FinanceBalanceError({required this.message});
  final String message;
}

class FinanceBalanceNotifier extends StateNotifier<FinanceBalanceState> {
  FinanceBalanceNotifier(this._repository, this._storeId)
      : super(const FinanceBalanceLoading()) {
    load();
  }

  final FinanceRepository _repository;
  final String _storeId;

  Future<void> load() async {
    state = const FinanceBalanceLoading();
    try {
      final balance = await _repository.getBalance(_storeId);
      state = FinanceBalanceLoaded(balance: balance);
    } on Exception catch (e) {
      state = FinanceBalanceError(message: e.toString());
    }
  }

  Future<void> reload() => load();
}

final financeBalanceProvider = StateNotifierProvider.autoDispose
    .family<FinanceBalanceNotifier, FinanceBalanceState, String>(
  (ref, storeId) {
    final repo = ref.watch(financeRepositoryProvider);
    return FinanceBalanceNotifier(repo, storeId);
  },
);

// ---------------------------------------------------------------------------
// Ledger holati

sealed class LedgerState {
  const LedgerState();
}

class LedgerLoading extends LedgerState {
  const LedgerLoading();
}

class LedgerLoaded extends LedgerState {
  const LedgerLoaded({
    required this.page,
    required this.storeIdFilter,
    required this.typeFilter,
  });

  final LedgerPage page;
  final String? storeIdFilter;
  final String? typeFilter;
}

class LedgerError extends LedgerState {
  const LedgerError({required this.message});
  final String message;
}

/// Ledger notifier — filtr + paginatsiya boshqaruvi.
class LedgerNotifier extends StateNotifier<LedgerState> {
  LedgerNotifier(this._repository) : super(const LedgerLoading()) {
    load();
  }

  final FinanceRepository _repository;

  String? _storeIdFilter;
  String? _typeFilter;

  /// Filtrlarni o'rnatib qayta yuklash.
  Future<void> load({String? storeId, String? entryType}) async {
    _storeIdFilter = storeId;
    _typeFilter = entryType;
    state = const LedgerLoading();
    try {
      final page = await _repository.getLedger(
        storeId: storeId,
        entryType: entryType,
      );
      state = LedgerLoaded(
        page: page,
        storeIdFilter: storeId,
        typeFilter: entryType,
      );
    } on Exception catch (e) {
      state = LedgerError(message: e.toString());
    }
  }

  Future<void> reload() =>
      load(storeId: _storeIdFilter, entryType: _typeFilter);

  /// Filtr — faqat debit yoki credit.
  Future<void> filterByType(String? entryType) =>
      load(storeId: _storeIdFilter, entryType: entryType);

  /// Filtr — do'kon bo'yicha.
  Future<void> filterByStore(String? storeId) =>
      load(storeId: storeId, entryType: _typeFilter);
}

final ledgerNotifierProvider =
    StateNotifierProvider.autoDispose<LedgerNotifier, LedgerState>(
  (ref) {
    final repo = ref.watch(financeRepositoryProvider);
    return LedgerNotifier(repo);
  },
);

// ---------------------------------------------------------------------------
// Ledger yaratish holati

sealed class CreateLedgerState {
  const CreateLedgerState();
}

class CreateLedgerIdle extends CreateLedgerState {
  const CreateLedgerIdle();
}

class CreateLedgerLoading extends CreateLedgerState {
  const CreateLedgerLoading();
}

class CreateLedgerSuccess extends CreateLedgerState {
  const CreateLedgerSuccess({required this.entry});
  final LedgerEntry entry;
}

class CreateLedgerFailure extends CreateLedgerState {
  const CreateLedgerFailure({required this.message});
  final String message;
}

/// POST /finance/ledger — yangi yozuv yaratish notifier.
class CreateLedgerNotifier extends StateNotifier<CreateLedgerState> {
  CreateLedgerNotifier(this._repository) : super(const CreateLedgerIdle());

  final FinanceRepository _repository;

  Future<void> create(CreateLedgerRequest request) async {
    state = const CreateLedgerLoading();
    try {
      final entry = await _repository.createLedger(request);
      state = CreateLedgerSuccess(entry: entry);
    } on Exception catch (e) {
      state = CreateLedgerFailure(message: e.toString());
    }
  }

  void reset() => state = const CreateLedgerIdle();
}

final createLedgerProvider = StateNotifierProvider.autoDispose<
    CreateLedgerNotifier, CreateLedgerState>(
  (ref) {
    final repo = ref.watch(financeRepositoryProvider);
    return CreateLedgerNotifier(repo);
  },
);

// ---------------------------------------------------------------------------
// Ledger tasdiqlash holati

sealed class ApproveLedgerState {
  const ApproveLedgerState();
}

class ApproveLedgerIdle extends ApproveLedgerState {
  const ApproveLedgerIdle();
}

class ApproveLedgerLoading extends ApproveLedgerState {
  const ApproveLedgerLoading();
}

class ApproveLedgerSuccess extends ApproveLedgerState {
  const ApproveLedgerSuccess({required this.entry});
  final LedgerEntry entry;
}

class ApproveLedgerFailure extends ApproveLedgerState {
  const ApproveLedgerFailure({required this.message});
  final String message;
}

/// POST /finance/ledger/{id}/approve — yozuvni tasdiqlash notifier.
class ApproveLedgerNotifier extends StateNotifier<ApproveLedgerState> {
  ApproveLedgerNotifier(this._repository) : super(const ApproveLedgerIdle());

  final FinanceRepository _repository;

  Future<void> approve(String entryId) async {
    state = const ApproveLedgerLoading();
    try {
      final entry = await _repository.approveLedger(entryId);
      state = ApproveLedgerSuccess(entry: entry);
    } on Exception catch (e) {
      state = ApproveLedgerFailure(message: e.toString());
    }
  }

  void reset() => state = const ApproveLedgerIdle();
}

/// family key — ledger entry UUID.
final approveLedgerProvider = StateNotifierProvider.autoDispose.family<
    ApproveLedgerNotifier, ApproveLedgerState, String>(
  (ref, entryId) {
    final repo = ref.watch(financeRepositoryProvider);
    return ApproveLedgerNotifier(repo);
  },
);
