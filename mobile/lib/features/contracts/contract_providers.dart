import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../data/local/database_provider.dart';
import '../auth/auth_providers.dart';
import 'contract_models.dart';
import 'contract_repository.dart';

// ---------------------------------------------------------------------------
// Repository

final contractRepositoryProvider = Provider<ContractRepository>((ref) {
  final db = ref.watch(databaseProvider);
  final api = ref.watch(apiClientProvider);
  return ContractRepository(db: db, apiClient: api);
});

// ---------------------------------------------------------------------------
// Shartnoma yaratish

sealed class CreateContractState {
  const CreateContractState();
}

class CreateContractIdle extends CreateContractState {
  const CreateContractIdle();
}

class CreateContractLoading extends CreateContractState {
  const CreateContractLoading();
}

class CreateContractSuccess extends CreateContractState {
  const CreateContractSuccess({required this.clientUuid});
  final String clientUuid;
}

class CreateContractFailure extends CreateContractState {
  const CreateContractFailure({required this.message});
  final String message;
}

class CreateContractNotifier extends StateNotifier<CreateContractState> {
  CreateContractNotifier(this._repository) : super(const CreateContractIdle());

  final ContractRepository _repository;

  Future<void> create(CreateContractRequest request) async {
    state = const CreateContractLoading();
    try {
      final clientUuid = await _repository.createContract(request);
      state = CreateContractSuccess(clientUuid: clientUuid);
    } on Exception catch (e) {
      state = CreateContractFailure(message: e.toString());
    }
  }

  void reset() => state = const CreateContractIdle();
}

final createContractProvider = StateNotifierProvider.autoDispose<
    CreateContractNotifier, CreateContractState>(
  (ref) {
    final repo = ref.watch(contractRepositoryProvider);
    return CreateContractNotifier(repo);
  },
);

// ---------------------------------------------------------------------------
// Shartnomalar ro'yxati (store bo'yicha)

sealed class ContractListState {
  const ContractListState();
}

class ContractListLoading extends ContractListState {
  const ContractListLoading();
}

class ContractListLoaded extends ContractListState {
  const ContractListLoaded({
    required this.contracts,
    required this.pending,
  });
  final List<Contract> contracts;
  final List<PendingContract> pending;
}

class ContractListError extends ContractListState {
  const ContractListError({required this.message, this.pending = const []});
  final String message;
  final List<PendingContract> pending;
}

class ContractListNotifier extends StateNotifier<ContractListState> {
  ContractListNotifier(this._repository, this._storeId)
      : super(const ContractListLoading()) {
    load();
  }

  final ContractRepository _repository;
  final String _storeId;

  Future<void> load() async {
    state = const ContractListLoading();

    // Pending outbox'dan (offline holat)
    final pendingList = await _repository.getPendingContracts(_storeId);

    try {
      final contracts = await _repository.getContracts(storeId: _storeId);
      state = ContractListLoaded(contracts: contracts, pending: pendingList);
    } on Exception catch (e) {
      state = ContractListError(
        message: 'Tarmoq xatosi: ${e.toString()}',
        pending: pendingList,
      );
    }
  }
}

final contractListProvider = StateNotifierProvider.autoDispose.family<
    ContractListNotifier, ContractListState, String>(
  (ref, storeId) {
    final repo = ref.watch(contractRepositoryProvider);
    return ContractListNotifier(repo, storeId);
  },
);
