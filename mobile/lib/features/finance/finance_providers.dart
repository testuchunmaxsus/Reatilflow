import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../auth/auth_providers.dart';
import 'finance_models.dart';
import 'finance_repository.dart';

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
