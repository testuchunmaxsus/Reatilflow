import 'package:json_annotation/json_annotation.dart';

part 'auth_models.g.dart';

/// POST /auth/login so'rovi
@JsonSerializable()
class LoginRequest {
  const LoginRequest({required this.phone, required this.password});

  factory LoginRequest.fromJson(Map<String, dynamic> json) =>
      _$LoginRequestFromJson(json);

  final String phone;
  final String password;

  Map<String, dynamic> toJson() => _$LoginRequestToJson(this);
}

/// Login va refresh javobi
@JsonSerializable()
class TokenPair {
  const TokenPair({
    required this.accessToken,
    required this.refreshToken,
    required this.tokenType,
  });

  factory TokenPair.fromJson(Map<String, dynamic> json) =>
      _$TokenPairFromJson(json);

  @JsonKey(name: 'access_token')
  final String accessToken;

  @JsonKey(name: 'refresh_token')
  final String refreshToken;

  @JsonKey(name: 'token_type')
  final String tokenType;

  Map<String, dynamic> toJson() => _$TokenPairToJson(this);
}

/// POST /auth/refresh so'rovi
@JsonSerializable()
class RefreshRequest {
  const RefreshRequest({required this.refreshToken});

  factory RefreshRequest.fromJson(Map<String, dynamic> json) =>
      _$RefreshRequestFromJson(json);

  @JsonKey(name: 'refresh_token')
  final String refreshToken;

  Map<String, dynamic> toJson() => _$RefreshRequestToJson(this);
}

/// POST /auth/logout so'rovi
@JsonSerializable()
class LogoutRequest {
  const LogoutRequest({required this.refreshToken});

  factory LogoutRequest.fromJson(Map<String, dynamic> json) =>
      _$LogoutRequestFromJson(json);

  @JsonKey(name: 'refresh_token')
  final String refreshToken;

  Map<String, dynamic> toJson() => _$LogoutRequestToJson(this);
}

/// GET /auth/me javobi
@JsonSerializable()
class MeResponse {
  const MeResponse({
    required this.id,
    required this.phone,
    required this.fullName,
    required this.role,
    this.branchId,
    required this.locale,
    required this.isActive,
    required this.biometricEnrolled,
  });

  factory MeResponse.fromJson(Map<String, dynamic> json) =>
      _$MeResponseFromJson(json);

  final String id;
  final String phone;

  @JsonKey(name: 'full_name')
  final String fullName;

  /// administrator | agent | courier | accountant | store
  final String role;

  @JsonKey(name: 'branch_id')
  final String? branchId;

  final String locale;

  @JsonKey(name: 'is_active')
  final bool isActive;

  @JsonKey(name: 'biometric_enrolled')
  final bool biometricEnrolled;

  Map<String, dynamic> toJson() => _$MeResponseToJson(this);
}
