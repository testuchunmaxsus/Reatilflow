import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/theme/app_spacing.dart';
import '../../core/widgets/widgets.dart';
import '../../data/local/database.dart';
import '../attendance/attendance_providers.dart';
import '../attendance/gps_service.dart';
import '../auth/auth_providers.dart';
import '../auth/auth_repository.dart';
import '../home/sync_providers.dart';
import 'stores_providers.dart';

/// Do'kon onboarding ekrani (agent uchun).
///
/// Oqim:
///   1. Mavjud do'kon ma'lumotlari yuklanadi.
///   2. Agent kontakt/manzil/GPS yangilaydi → outbox `store.update`.
///   3. Kerak bo'lsa do'konga o'zini biriktiradi → outbox `store.assign_agent`.
///   4. Sync trigger → saqlab chiqish.
class StoreOnboardingScreen extends ConsumerStatefulWidget {
  const StoreOnboardingScreen({super.key, required this.storeId});
  final String storeId;

  @override
  ConsumerState<StoreOnboardingScreen> createState() =>
      _StoreOnboardingScreenState();
}

class _StoreOnboardingScreenState
    extends ConsumerState<StoreOnboardingScreen> {
  final _formKey = GlobalKey<FormState>();
  final _nameController = TextEditingController();
  final _ownerNameController = TextEditingController();
  final _phoneController = TextEditingController();
  final _addressController = TextEditingController();

  GpsPosition? _newGpsPosition;
  bool _gpsLoading = false;
  bool _submitting = false;
  bool _assignSelf = false;

  Store? _originalStore;
  bool _loaded = false;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) => _loadStore());
  }

  @override
  void dispose() {
    _nameController.dispose();
    _ownerNameController.dispose();
    _phoneController.dispose();
    _addressController.dispose();
    super.dispose();
  }

  Future<void> _loadStore() async {
    final repo = ref.read(storeRepositoryProvider);
    final store = await repo.getById(widget.storeId);
    if (!mounted) return;
    if (store == null) {
      _showSnackBar("Do'kon topilmadi");
      Navigator.of(context).pop();
      return;
    }
    final authState = ref.read(authNotifierProvider);
    final currentUserId = switch (authState) {
      AuthStateAuthenticated(:final user) => user.id,
      _ => null,
    };
    setState(() {
      _originalStore = store;
      _nameController.text = store.name;
      _phoneController.text = store.phone ?? '';
      _addressController.text = store.address ?? '';
      // O'zini biriktirish: agent biriktirilmagan bo'lsa taklif qilish
      _assignSelf = store.agentId == null ||
          (currentUserId != null && store.agentId != currentUserId);
      _loaded = true;
    });
  }

  Future<void> _fetchGps() async {
    if (!mounted) return;
    setState(() => _gpsLoading = true);
    final gpsService = ref.read(gpsServiceProvider);
    await gpsService.requestPermission();
    final position = await gpsService.getCurrentPosition();
    if (!mounted) return;
    setState(() {
      _newGpsPosition = position;
      _gpsLoading = false;
    });
    if (position == null) {
      _showSnackBar('GPS joylashuv olinmadi. Ruxsat berilganini tekshiring.');
    }
  }

  Future<void> _submit() async {
    if (!_formKey.currentState!.validate()) return;
    final store = _originalStore;
    if (store == null) return;

    setState(() => _submitting = true);

    try {
      final repo = ref.read(storeRepositoryProvider);
      final authState = ref.read(authNotifierProvider);
      final currentUserId = switch (authState) {
        AuthStateAuthenticated(:final user) => user.id,
        _ => null,
      };

      // 1. Do'kon ma'lumotlarini yangilash
      await repo.updateStore(
        storeId: store.id,
        version: store.version,
        name: _nameController.text.trim(),
        ownerName: _ownerNameController.text.trim().isEmpty
            ? null
            : _ownerNameController.text.trim(),
        phone: _phoneController.text.trim().isEmpty
            ? null
            : _phoneController.text.trim(),
        address: _addressController.text.trim().isEmpty
            ? null
            : _addressController.text.trim(),
        gpsLat: _newGpsPosition?.lat,
        gpsLng: _newGpsPosition?.lng,
      );

      // 2. Agentni biriktirish (tanlangan bo'lsa)
      if (_assignSelf && currentUserId != null) {
        await repo.assignAgent(
          storeId: store.id,
          agentId: currentUserId,
        );
      }

      // 3. Sync trigger
      await ref.read(syncNotifierProvider.notifier).triggerSync();

      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(
            _assignSelf
                ? "Do'kon yangilandi va siz biriktirildi"
                : "Do'kon ma'lumotlari saqlandi",
          ),
          backgroundColor:
              Theme.of(context).colorScheme.primary,
        ),
      );
      Navigator.of(context).pop(true);
    } on Exception catch (e) {
      if (!mounted) return;
      _showSnackBar('Xatolik: $e');
    } finally {
      if (mounted) setState(() => _submitting = false);
    }
  }

  void _showSnackBar(String message) {
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text(message),
        backgroundColor: Theme.of(context).colorScheme.error,
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    final tt = Theme.of(context).textTheme;

    if (!_loaded) {
      return Scaffold(
        appBar: AppBar(title: const Text("Do'kon onboarding")),
        body: Center(child: CircularProgressIndicator(color: cs.primary)),
      );
    }

    final originalGps =
        _originalStore?.gpsLat != null && _originalStore?.gpsLng != null
            ? '${_originalStore!.gpsLat!.toStringAsFixed(5)}, '
                '${_originalStore!.gpsLng!.toStringAsFixed(5)}'
            : null;

    return Scaffold(
      appBar: AppBar(
        title: const Text("Do'kon onboarding"),
        actions: [
          if (_submitting)
            Padding(
              padding: const EdgeInsets.all(AppSpacing.md),
              child: SizedBox(
                width: 20,
                height: 20,
                child: CircularProgressIndicator(
                  strokeWidth: 2,
                  color: cs.primary,
                ),
              ),
            )
          else
            TextButton(
              onPressed: _submit,
              child: const Text('Saqlash'),
            ),
        ],
      ),
      body: SingleChildScrollView(
        padding: const EdgeInsets.all(AppSpacing.lg),
        child: Form(
          key: _formKey,
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              // GPS kartasi
              _GpsCard(
                originalGps: originalGps,
                newPosition: _newGpsPosition,
                loading: _gpsLoading,
                onUpdate: _fetchGps,
              ),

              const SizedBox(height: AppSpacing.lg),

              // Ma'lumotlar
              AppCard(
                padding: const EdgeInsets.all(AppSpacing.lg),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    const SectionHeader(title: "Do'kon ma'lumotlari"),
                    const SizedBox(height: AppSpacing.md),

                    TextFormField(
                      controller: _nameController,
                      textCapitalization: TextCapitalization.words,
                      decoration: const InputDecoration(
                        labelText: "Do'kon nomi *",
                        prefixIcon: Icon(Icons.store_outlined),
                      ),
                      validator: (v) {
                        if (v == null || v.trim().isEmpty) {
                          return "Do'kon nomi majburiy";
                        }
                        if (v.trim().length < 2) {
                          return 'Kamida 2 ta belgi kiriting';
                        }
                        return null;
                      },
                    ),

                    const SizedBox(height: AppSpacing.md),

                    TextFormField(
                      controller: _ownerNameController,
                      textCapitalization: TextCapitalization.words,
                      decoration: const InputDecoration(
                        labelText: 'Egasining ismi',
                        prefixIcon: Icon(Icons.person_outlined),
                      ),
                    ),

                    const SizedBox(height: AppSpacing.md),

                    TextFormField(
                      controller: _phoneController,
                      keyboardType: TextInputType.phone,
                      decoration: const InputDecoration(
                        labelText: 'Telefon raqam',
                        hintText: '+998901234567',
                        prefixIcon: Icon(Icons.phone_outlined),
                      ),
                      validator: (v) {
                        if (v == null || v.trim().isEmpty) return null;
                        final digits =
                            v.trim().replaceAll(RegExp(r'\D'), '');
                        if (digits.length < 9) {
                          return "Noto'g'ri telefon raqam formati";
                        }
                        return null;
                      },
                    ),

                    const SizedBox(height: AppSpacing.md),

                    TextFormField(
                      controller: _addressController,
                      textCapitalization: TextCapitalization.sentences,
                      decoration: const InputDecoration(
                        labelText: 'Manzil',
                        prefixIcon: Icon(Icons.location_on_outlined),
                      ),
                    ),
                  ],
                ),
              ),

              const SizedBox(height: AppSpacing.lg),

              // Agentni biriktirish
              AppCard(
                padding: const EdgeInsets.all(AppSpacing.lg),
                borderColor: _assignSelf
                    ? cs.primary.withValues(alpha: 0.4)
                    : cs.outlineVariant,
                child: Row(
                  children: [
                    Container(
                      width: 44,
                      height: 44,
                      decoration: BoxDecoration(
                        color: _assignSelf
                            ? cs.primaryContainer
                            : cs.surfaceContainerHighest,
                        borderRadius:
                            BorderRadius.circular(AppSpacing.radiusMd),
                      ),
                      child: Icon(
                        Icons.badge_outlined,
                        color: _assignSelf
                            ? cs.primary
                            : cs.onSurfaceVariant,
                        size: AppSpacing.iconMd,
                      ),
                    ),
                    const SizedBox(width: AppSpacing.md),
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(
                            "O'zingizni biriktirish",
                            style: tt.titleSmall?.copyWith(
                              fontWeight: FontWeight.w600,
                            ),
                          ),
                          Text(
                            _assignSelf
                                ? "Bu do'kon sizga biriktiriladi"
                                : "Siz allaqachon biriktirilgansiz",
                            style: tt.bodySmall?.copyWith(
                              color: cs.onSurfaceVariant,
                            ),
                          ),
                        ],
                      ),
                    ),
                    Switch(
                      value: _assignSelf,
                      onChanged: (v) => setState(() => _assignSelf = v),
                    ),
                  ],
                ),
              ),

              const SizedBox(height: AppSpacing.xl),

              SizedBox(
                width: double.infinity,
                child: FilledButton.icon(
                  onPressed: _submitting ? null : _submit,
                  icon: _submitting
                      ? SizedBox(
                          width: 18,
                          height: 18,
                          child: CircularProgressIndicator(
                            strokeWidth: 2,
                            color: cs.onPrimary,
                          ),
                        )
                      : const Icon(Icons.check_circle_outline),
                  label: Text(
                    _submitting ? 'Saqlanmoqda...' : 'Onboardingni yakunlash',
                  ),
                  style: FilledButton.styleFrom(
                    minimumSize:
                        const Size.fromHeight(AppSpacing.buttonHeight),
                  ),
                ),
              ),

              const SizedBox(height: AppSpacing.xl),
            ],
          ),
        ),
      ),
    );
  }
}

// ---------------------------------------------------------------------------

class _GpsCard extends StatelessWidget {
  const _GpsCard({
    required this.originalGps,
    required this.newPosition,
    required this.loading,
    required this.onUpdate,
  });

  final String? originalGps;
  final GpsPosition? newPosition;
  final bool loading;
  final VoidCallback onUpdate;

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    final tt = Theme.of(context).textTheme;
    final hasNew = newPosition != null;
    final newGpsText = hasNew
        ? '${newPosition!.lat.toStringAsFixed(5)}, '
            '${newPosition!.lng.toStringAsFixed(5)}'
        : null;

    return AppCard(
      padding: const EdgeInsets.all(AppSpacing.lg),
      borderColor:
          hasNew ? cs.primary.withValues(alpha: 0.4) : cs.outlineVariant,
      child: Row(
        children: [
          Container(
            width: 44,
            height: 44,
            decoration: BoxDecoration(
              color: hasNew ? cs.primaryContainer : cs.surfaceContainerHighest,
              borderRadius: BorderRadius.circular(AppSpacing.radiusMd),
            ),
            child: loading
                ? Padding(
                    padding: const EdgeInsets.all(AppSpacing.sm),
                    child: CircularProgressIndicator(
                        strokeWidth: 2, color: cs.primary),
                  )
                : Icon(
                    hasNew ? Icons.my_location : Icons.location_on_outlined,
                    color: hasNew ? cs.primary : cs.onSurfaceVariant,
                    size: AppSpacing.iconMd,
                  ),
          ),
          const SizedBox(width: AppSpacing.md),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  loading
                      ? 'Joylashuv olinmoqda...'
                      : hasNew
                          ? 'Yangi joylashuv olindi'
                          : 'GPS joylashuv (majburiy)',
                  style: tt.titleSmall?.copyWith(
                    fontWeight: FontWeight.w600,
                    color: hasNew ? cs.primary : cs.onSurface,
                  ),
                ),
                if (newGpsText != null)
                  Text(
                    newGpsText,
                    style: tt.bodySmall?.copyWith(color: cs.primary),
                  )
                else if (originalGps != null)
                  Text(
                    'Joriy: $originalGps',
                    style:
                        tt.bodySmall?.copyWith(color: cs.onSurfaceVariant),
                  )
                else
                  Text(
                    "GPS ma'lumot yo'q — Yangilang",
                    style: tt.bodySmall
                        ?.copyWith(color: cs.error.withValues(alpha: 0.8)),
                  ),
              ],
            ),
          ),
          if (!loading)
            TextButton.icon(
              onPressed: onUpdate,
              icon: const Icon(Icons.my_location, size: AppSpacing.iconSm),
              label: const Text('Olish'),
            ),
        ],
      ),
    );
  }
}
