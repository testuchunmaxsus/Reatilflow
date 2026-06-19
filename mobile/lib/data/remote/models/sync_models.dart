import 'package:json_annotation/json_annotation.dart';

part 'sync_models.g.dart';

// ---- Push ----

/// POST /sync/push so'rov qismi
@JsonSerializable()
class SyncOp {
  const SyncOp({
    required this.opType,
    required this.clientUuid,
    required this.payload,
  });

  factory SyncOp.fromJson(Map<String, dynamic> json) => _$SyncOpFromJson(json);

  @JsonKey(name: 'op_type')
  final String opType;

  @JsonKey(name: 'client_uuid')
  final String clientUuid;

  final Map<String, dynamic> payload;

  Map<String, dynamic> toJson() => _$SyncOpToJson(this);
}

/// POST /sync/push so'rovi
@JsonSerializable()
class SyncPushRequest {
  const SyncPushRequest({required this.ops});

  factory SyncPushRequest.fromJson(Map<String, dynamic> json) =>
      _$SyncPushRequestFromJson(json);

  final List<SyncOp> ops;

  Map<String, dynamic> toJson() => _$SyncPushRequestToJson(this);
}

/// Har bir op uchun natija
@JsonSerializable()
class SyncOpResult {
  const SyncOpResult({
    required this.clientUuid,
    required this.status,
    this.serverId,
    this.messageKey,
  });

  factory SyncOpResult.fromJson(Map<String, dynamic> json) =>
      _$SyncOpResultFromJson(json);

  @JsonKey(name: 'client_uuid')
  final String clientUuid;

  /// applied | duplicate | conflict | error
  final String status;

  @JsonKey(name: 'server_id')
  final String? serverId;

  @JsonKey(name: 'message_key')
  final String? messageKey;

  Map<String, dynamic> toJson() => _$SyncOpResultToJson(this);
}

/// POST /sync/push javobi
@JsonSerializable()
class SyncPushResponse {
  const SyncPushResponse({required this.results});

  factory SyncPushResponse.fromJson(Map<String, dynamic> json) =>
      _$SyncPushResponseFromJson(json);

  final List<SyncOpResult> results;

  Map<String, dynamic> toJson() => _$SyncPushResponseToJson(this);
}

// ---- Pull ----

/// GET /sync/pull javobi — bitta o'zgarish
@JsonSerializable()
class ChangeItem {
  const ChangeItem({
    required this.entityType,
    required this.entityId,
    required this.eventType,
    required this.seq,
    required this.snapshot,
  });

  factory ChangeItem.fromJson(Map<String, dynamic> json) =>
      _$ChangeItemFromJson(json);

  @JsonKey(name: 'entity_type')
  final String entityType;

  @JsonKey(name: 'entity_id')
  final String entityId;

  @JsonKey(name: 'event_type')
  final String eventType;

  /// Monoton server kursor qiymati
  final int seq;

  /// Klient upsert uchun entity holati
  final Map<String, dynamic> snapshot;

  Map<String, dynamic> toJson() => _$ChangeItemToJson(this);
}

/// GET /sync/pull javobi
@JsonSerializable()
class SyncPullResponse {
  const SyncPullResponse({
    required this.changes,
    required this.nextCursor,
    required this.hasMore,
  });

  factory SyncPullResponse.fromJson(Map<String, dynamic> json) =>
      _$SyncPullResponseFromJson(json);

  final List<ChangeItem> changes;

  @JsonKey(name: 'next_cursor')
  final int nextCursor;

  @JsonKey(name: 'has_more')
  final bool hasMore;

  Map<String, dynamic> toJson() => _$SyncPullResponseToJson(this);
}
