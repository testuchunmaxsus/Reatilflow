import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/theme/app_spacing.dart';
import '../../core/widgets/widgets.dart';
import '../../data/local/database.dart';
import '../attendance/attendance_providers.dart';
import '../attendance/gps_service.dart';
import '../home/sync_providers.dart';
import 'stores_providers.dart';

/// Do'kon tahrirlash ekrani (agent uchun).
///
/// Oqim: mavjud ma'lumotlar formaga yuklanadi → agent o'zgartiradi →
///        PATCH /customers/stores/{id} (outbox orqali offline-first) →
///        sync trigger → ekranni yopish.
class EditStoreScreen extends ConsumerStatefulWidget {
  const EditStoreScreen({super.key, required this.storeId});
  final String storeId;

  @override
  ConsumerState<EditStoreScreen> createState() => _EditStoreScreenState();
}

class _EditStoreScreenState extends ConsumerState<EditStoreScreen> {
  final _formKey = GlobalKey<FormState>();
  final _nameController = TextEditingController();
  final _ownerNameController = TextEditingController();
  final _phoneController = TextEditingController();
  final _addressController = TextEditingController();

  // GPS — ixtiyoriy: agent o'zgartirmoqchi bo'lsa yangilaydi
  GpsPosition? _newGpsPosition;
  bool _gpsLoading = false;
  bool _submitting = false;

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
    setState(() {
      _originalStore = store;
      _nameController.text = store.name;
      // owner_name lokal DB da saqlanmaydi — bo'sh qoladi
      _ownerNameController.text = '';
      _phoneController.text = store.phone ?? '';
      _addressController.text = store.address ?? '';
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

      await repo.updateStore(
        storeId: store.id,
        version: store.version,
        name: _nameController.text.trim(),
        ownerName: _ownerNameController.text.trim(),
        phone: _phoneController.text.trim().isEmpty
            ? null
            : _phoneController.text.trim(),
        address: _addressController.text.trim().isEmpty
            ? null
            : _addressController.text.trim(),
        gpsLat: _newGpsPosition?.lat,
        gpsLng: _newGpsPosition?.lng,
      );

      // Sync trigger — server bilan moslashish uchun
      await ref.read(syncNotifierProvider.notifier).triggerSync();

      if (!mounted) return;
      Navigator.of(context).pop(true); // true = o'zgarish bo'ldi
    } on Exception catch (e) {
      if (!mounted) return;
      _showSnackBar('Xatolik: $e');
    } finally {
      if (mounted) setState(() => _submitting = false);
    }
  }

  void _showSnackBar(String message) {
    final cs = Theme.of(context).colorScheme;
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text(message),
        backgroundColor: cs.error,
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    final tt = Theme.of(context).textTheme;

    if (!_loaded) {
      return Scaffold(
        appBar: AppBar(title: const Text("Do'konni tahrirlash")),
        body: Center(child: CircularProgressIndicator(color: cs.primary)),
      );
    }

    final originalGps = _originalStore != null &&
            _originalStore!.gpsLat != null &&
            _originalStore!.gpsLng != null
        ? '${_originalStore!.gpsLat!.toStringAsFixed(5)}, '
            '${_originalStore!.gpsLng!.toStringAsFixed(5)}'
        : null;

    return Scaffold(
      appBar: AppBar(
        title: const Text("Do'konni tahrirlash"),
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
              // GPS holati kartasi
              _GpsEditCard(
                originalGps: originalGps,
                newPosition: _newGpsPosition,
                loading: _gpsLoading,
                onUpdate: _fetchGps,
                cs: cs,
                tt: tt,
              ),

              const SizedBox(height: AppSpacing.xl),

              // Forma maydonlari
              AppCard(
                padding: const EdgeInsets.all(AppSpacing.lg),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    const SectionHeader(title: "Do'kon ma'lumotlari"),
                    const SizedBox(height: AppSpacing.md),

                    // Do'kon nomi (majburiy)
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

                    // Egasining ismi
                    TextFormField(
                      controller: _ownerNameController,
                      textCapitalization: TextCapitalization.words,
                      decoration: const InputDecoration(
                        labelText: 'Egasining ismi',
                        prefixIcon: Icon(Icons.person_outlined),
                      ),
                    ),

                    const SizedBox(height: AppSpacing.md),

                    // Telefon raqam
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

                    // Manzil
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

              const SizedBox(height: AppSpacing.xl),

              // Saqlash tugmasi
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
                      : const Icon(Icons.save_outlined),
                  label: Text(_submitting ? 'Saqlanmoqda...' : 'Saqlash'),
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

class _GpsEditCard extends StatelessWidget {
  const _GpsEditCard({
    required this.originalGps,
    required this.newPosition,
    required this.loading,
    required this.onUpdate,
    required this.cs,
    required this.tt,
  });

  final String? originalGps;
  final GpsPosition? newPosition;
  final bool loading;
  final VoidCallback onUpdate;
  final ColorScheme cs;
  final TextTheme tt;

  @override
  Widget build(BuildContext context) {
    final hasNew = newPosition != null;
    final newGpsText = hasNew
        ? '${newPosition!.lat.toStringAsFixed(5)}, '
            '${newPosition!.lng.toStringAsFixed(5)}'
        : null;

    return AppCard(
      padding: const EdgeInsets.all(AppSpacing.lg),
      borderColor: hasNew
          ? cs.primary.withValues(alpha: 0.4)
          : cs.outlineVariant,
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
                      strokeWidth: 2,
                      color: cs.primary,
                    ),
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
                          ? 'Yangi joylashuv'
                          : 'GPS (ixtiyoriy yangilash)',
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
                    style: tt.bodySmall?.copyWith(color: cs.onSurfaceVariant),
                  )
                else
                  Text(
                    'GPS maʼlumot yoʼq',
                    style: tt.bodySmall?.copyWith(color: cs.onSurfaceVariant),
                  ),
              ],
            ),
          ),
          if (!loading)
            TextButton.icon(
              onPressed: onUpdate,
              icon: const Icon(Icons.my_location, size: AppSpacing.iconSm),
              label: const Text('Yangilash'),
            ),
        ],
      ),
    );
  }
}
