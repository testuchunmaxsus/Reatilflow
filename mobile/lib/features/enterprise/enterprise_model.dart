/// Enterprise (korxona) holati va enabled_modules modeli.
///
/// Backend /enterprise/me → EnterpriseInfo.
/// hasModule(key) — navigatsiya va widget gating uchun.
class EnterpriseInfo {
  const EnterpriseInfo({
    required this.id,
    required this.name,
    required this.suspended,
    required this.enabledModules,
  });

  factory EnterpriseInfo.fromJson(Map<String, dynamic> json) {
    final modules = (json['enabled_modules'] as List<dynamic>? ?? [])
        .map((e) => e as String)
        .toList();
    return EnterpriseInfo(
      id: json['id'] as String? ?? '',
      name: json['name'] as String? ?? '',
      suspended: json['suspended'] as bool? ?? false,
      enabledModules: modules,
    );
  }

  final String id;
  final String name;
  final bool suspended;

  /// Faollashtirilgan modullar ro'yxati.
  /// Mumkin qiymatlar: 'delivery', 'attendance', 'gps', 'orders', 'catalog'
  final List<String> enabledModules;

  /// Modul yoqilgan-yoqilmaganligini tekshirish.
  /// [key] — modul kalit nomi (masalan: 'delivery', 'attendance').
  bool hasModule(String key) => enabledModules.contains(key);

  Map<String, dynamic> toJson() => {
        'id': id,
        'name': name,
        'suspended': suspended,
        'enabled_modules': enabledModules,
      };

  @override
  String toString() =>
      'EnterpriseInfo(id: $id, suspended: $suspended, modules: $enabledModules)';
}

/// Barcha modullar yoqilgan fallback — offline yoki hali yuklanmagan holat.
const EnterpriseInfo enterpriseAllModules = EnterpriseInfo(
  id: '',
  name: '',
  suspended: false,
  enabledModules: ['delivery', 'attendance', 'gps', 'orders', 'catalog'],
);
