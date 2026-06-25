import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/theme/app_spacing.dart';
import '../../core/widgets/widgets.dart';
import '../attendance/attendance_providers.dart';
import '../attendance/gps_service.dart';
import '../auth/auth_providers.dart';
import '../home/sync_providers.dart';

/// Yangi do'kon yaratish ekrani (agent uchun).
///
/// Oqim: forma to'ldirish → GPS olish → POST /customers/stores →
///        sync trigger → ekranni yopish.
/// Backend agent_id ni JWT tokenidan avtomatik o'rnatadi.
class CreateStoreScreen extends ConsumerStatefulWidget {
  const CreateStoreScreen({super.key});

  @override
  ConsumerState<CreateStoreScreen> createState() => _CreateStoreScreenState();
}

class _CreateStoreScreenState extends ConsumerState<CreateStoreScreen> {
  final _formKey = GlobalKey<FormState>();
  final _nameController = TextEditingController();
  final _ownerNameController = TextEditingController();
  final _phoneController = TextEditingController();

  GpsPosition? _gpsPosition;
  bool _gpsLoading = false;
  bool _submitting = false;

  @override
  void initState() {
    super.initState();
    // Ekran ochilganda GPS ni avtomatik olishga urinish
    WidgetsBinding.instance.addPostFrameCallback((_) => _fetchGps());
  }

  @override
  void dispose() {
    _nameController.dispose();
    _ownerNameController.dispose();
    _phoneController.dispose();
    super.dispose();
  }

  Future<void> _fetchGps() async {
    if (!mounted) return;
    setState(() => _gpsLoading = true);

    final gpsService = ref.read(gpsServiceProvider);
    // Ruxsat so'rash, keyin joylashuvni olish
    await gpsService.requestPermission();
    final position = await gpsService.getCurrentPosition();

    if (!mounted) return;
    setState(() {
      _gpsPosition = position;
      _gpsLoading = false;
    });

    if (position == null) {
      _showSnackBar('GPS joylashuv olinmadi. Ruxsat berilganini tekshiring.');
    }
  }

  Future<void> _submit() async {
    if (!_formKey.currentState!.validate()) return;
    if (_gpsPosition == null) {
      _showSnackBar('Avval joylashuvni oling');
      return;
    }

    setState(() => _submitting = true);

    try {
      final apiClient = ref.read(apiClientProvider);
      await apiClient.createStore(
        name: _nameController.text.trim(),
        ownerName: _ownerNameController.text.trim(),
        phone: _phoneController.text.trim(),
        gpsLat: _gpsPosition!.lat.toStringAsFixed(7),
        gpsLng: _gpsPosition!.lng.toStringAsFixed(7),
      );

      // Sync trigger — yangi do'kon ro'yxat va xaritada ko'rinishi uchun
      await ref.read(syncNotifierProvider.notifier).triggerSync();

      if (!mounted) return;
      Navigator.of(context).pop();
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

    return Scaffold(
      appBar: AppBar(
        title: const Text("Yangi do'kon"),
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
              _GpsStatusCard(
                position: _gpsPosition,
                loading: _gpsLoading,
                onRefresh: _fetchGps,
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
                        hintText: "Masalan: Baxt do'koni",
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
                        hintText: 'Masalan: Alisher Karimov',
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
                        helperText: '+998 bilan boshlanadi',
                      ),
                      validator: (v) {
                        if (v == null || v.trim().isEmpty) return null;
                        final digits = v.trim().replaceAll(RegExp(r'\D'), '');
                        if (digits.length < 9) {
                          return "Noto'g'ri telefon raqam formati";
                        }
                        return null;
                      },
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

class _GpsStatusCard extends StatelessWidget {
  const _GpsStatusCard({
    required this.position,
    required this.loading,
    required this.onRefresh,
    required this.cs,
    required this.tt,
  });

  final GpsPosition? position;
  final bool loading;
  final VoidCallback onRefresh;
  final ColorScheme cs;
  final TextTheme tt;

  @override
  Widget build(BuildContext context) {
    return AppCard(
      padding: const EdgeInsets.all(AppSpacing.lg),
      borderColor: position != null
          ? cs.primary.withValues(alpha: 0.4)
          : cs.outlineVariant,
      child: Row(
        children: [
          Container(
            width: 44,
            height: 44,
            decoration: BoxDecoration(
              color: position != null
                  ? cs.primaryContainer
                  : cs.surfaceContainerHighest,
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
                    position != null
                        ? Icons.my_location
                        : Icons.location_off_outlined,
                    color: position != null ? cs.primary : cs.onSurfaceVariant,
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
                      : position != null
                          ? 'Joylashuv olindi'
                          : 'Joylashuv olinmadi',
                  style: tt.titleSmall?.copyWith(
                    fontWeight: FontWeight.w600,
                    color: position != null ? cs.primary : cs.onSurface,
                  ),
                ),
                if (position != null)
                  Text(
                    '${position!.lat.toStringAsFixed(5)}, '
                    '${position!.lng.toStringAsFixed(5)}',
                    style: tt.bodySmall?.copyWith(
                      color: cs.onSurfaceVariant,
                    ),
                  )
                else if (!loading)
                  Text(
                    'GPS ruxsatini tekshiring',
                    style: tt.bodySmall?.copyWith(
                      color: cs.onSurfaceVariant,
                    ),
                  ),
              ],
            ),
          ),
          if (!loading)
            IconButton(
              onPressed: onRefresh,
              icon: const Icon(Icons.refresh),
              tooltip: 'Joylashuvni yangilash',
              color: cs.onSurfaceVariant,
            ),
        ],
      ),
    );
  }
}
