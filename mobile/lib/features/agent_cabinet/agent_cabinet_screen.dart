import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/theme/app_spacing.dart';
import '../../core/widgets/widgets.dart';
import '../../data/local/database.dart';
import '../../data/remote/models/auth_models.dart';
import '../auth/auth_providers.dart';
import '../auth/auth_repository.dart';
import '../enterprise/enterprise_providers.dart';
import '../stores/stores_providers.dart';

/// Profil tahrirlash — bottom sheet ochuvchi yordamchi funksiya.
Future<void> _showEditProfileSheet(
  BuildContext context,
  WidgetRef ref,
  MeResponse user,
) async {
  await showModalBottomSheet<void>(
    context: context,
    isScrollControlled: true,
    useSafeArea: true,
    shape: const RoundedRectangleBorder(
      borderRadius: BorderRadius.vertical(
        top: Radius.circular(AppSpacing.radiusXxl),
      ),
    ),
    builder: (_) => _EditProfileSheet(user: user, ref: ref),
  );
}

/// Agent kabineti ekrani — profil + biriktirilgan do'konlar.
///
/// Faqat `agent` roli ko'rishi mumkin.
class AgentCabinetScreen extends ConsumerWidget {
  const AgentCabinetScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final authState = ref.watch(authNotifierProvider);
    final user = switch (authState) {
      AuthStateAuthenticated(:final user) => user,
      _ => null,
    };

    if (user == null) {
      return const Scaffold(
        body: Center(child: CircularProgressIndicator()),
      );
    }

    return Scaffold(
      appBar: AppBar(
        title: const Text('Mening kabinetim'),
        actions: [
          IconButton(
            icon: const Icon(Icons.logout_outlined),
            tooltip: 'Chiqish',
            onPressed: () async {
              await ref.read(authNotifierProvider.notifier).logout();
            },
          ),
        ],
      ),
      body: RefreshIndicator(
        onRefresh: () async {
          await ref.read(enterpriseNotifierProvider.notifier).refresh();
        },
        child: SingleChildScrollView(
          physics: const AlwaysScrollableScrollPhysics(),
          padding: const EdgeInsets.all(AppSpacing.lg),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              _ProfileCard(user: user),

              const SizedBox(height: AppSpacing.lg),

              _ModulesCard(),

              const SizedBox(height: AppSpacing.lg),

              _AttachedStoresSection(agentId: user.id),

              const SizedBox(height: AppSpacing.xl),
            ],
          ),
        ),
      ),
    );
  }
}

// ---------------------------------------------------------------------------

class _ProfileCard extends ConsumerWidget {
  const _ProfileCard({required this.user});
  final MeResponse user;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final cs = Theme.of(context).colorScheme;
    final tt = Theme.of(context).textTheme;

    return AppCard(
      padding: const EdgeInsets.all(AppSpacing.lg),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // Sarlavha + tahrirlash tugmasi
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              Text(
                'Profil',
                style: tt.labelMedium?.copyWith(color: cs.onSurfaceVariant),
              ),
              IconButton(
                icon: const Icon(Icons.edit_outlined),
                iconSize: AppSpacing.iconSm,
                tooltip: 'Profilni tahrirlash',
                color: cs.primary,
                visualDensity: VisualDensity.compact,
                onPressed: () =>
                    _showEditProfileSheet(context, ref, user),
              ),
            ],
          ),
          const SizedBox(height: AppSpacing.sm),
          // Profil tarkibi: avatar + ma'lumotlar
          Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              // Avatar
              Container(
                width: 64,
                height: 64,
                decoration: BoxDecoration(
                  gradient: LinearGradient(
                    colors: [cs.primary, cs.primary.withValues(alpha: 0.8)],
                    begin: Alignment.topLeft,
                    end: Alignment.bottomRight,
                  ),
                  shape: BoxShape.circle,
                ),
                child: Center(
                  child: Text(
                    _initials(user.fullName),
                    style: tt.titleMedium?.copyWith(
                      color: cs.onPrimary,
                      fontWeight: FontWeight.w700,
                    ),
                  ),
                ),
              ),
              const SizedBox(width: AppSpacing.lg),

              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      user.fullName,
                      style: tt.titleLarge?.copyWith(fontWeight: FontWeight.w700),
                    ),
                    const SizedBox(height: AppSpacing.xs),
                    _InfoLine(icon: Icons.phone_outlined, value: user.phone),
                    _InfoLine(
                        icon: Icons.badge_outlined,
                        value: _roleLabel(user.role)),
                    _InfoLine(
                      icon: Icons.language_outlined,
                      value: user.locale == 'uz' ? "O'zbek" : 'Русский',
                    ),
                    if (user.branchId != null)
                      _InfoLine(
                        icon: Icons.business_outlined,
                        value: 'Filial: ${user.branchId!.substring(0, 8)}...',
                      ),
                    const SizedBox(height: AppSpacing.sm),
                    Wrap(
                      spacing: AppSpacing.xs,
                      runSpacing: AppSpacing.xs,
                      children: [
                        StatusBadge(
                          status: user.isActive ? 'Faol' : 'Nofaol',
                          variant: user.isActive
                              ? StatusVariant.success
                              : StatusVariant.danger,
                        ),
                        if (user.biometricEnrolled)
                          const StatusBadge(
                            status: 'Biometrik',
                            variant: StatusVariant.info,
                            icon: Icons.fingerprint,
                          ),
                      ],
                    ),
                  ],
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }

  String _initials(String fullName) {
    final parts = fullName.trim().split(' ');
    if (parts.isEmpty) return '?';
    if (parts.length == 1) return parts.first[0].toUpperCase();
    return '${parts.first[0]}${parts[1][0]}'.toUpperCase();
  }

  String _roleLabel(String role) => switch (role) {
        'agent' => 'Agent',
        'courier' => 'Kuryer',
        'store' => "Do'kon",
        'accountant' => 'Buxgalter',
        'administrator' => 'Administrator',
        _ => role,
      };
}

class _InfoLine extends StatelessWidget {
  const _InfoLine({required this.icon, required this.value});
  final IconData icon;
  final String value;

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    final tt = Theme.of(context).textTheme;
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 2),
      child: Row(
        children: [
          Icon(icon, size: AppSpacing.iconXs, color: cs.onSurfaceVariant),
          const SizedBox(width: AppSpacing.xs),
          Expanded(
            child: Text(
              value,
              style: tt.bodySmall?.copyWith(color: cs.onSurfaceVariant),
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
            ),
          ),
        ],
      ),
    );
  }
}

// ---------------------------------------------------------------------------

class _ModulesCard extends ConsumerWidget {
  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final modules = ref.watch(enabledModulesProvider);
    final cs = Theme.of(context).colorScheme;

    return AppCard(
      padding: const EdgeInsets.all(AppSpacing.lg),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const SectionHeader(title: 'Faol modullar'),
          const SizedBox(height: AppSpacing.md),
          if (modules.isEmpty)
            Text(
              'Modul faollashtirilinmagan',
              style: Theme.of(context)
                  .textTheme
                  .bodyMedium
                  ?.copyWith(color: cs.onSurfaceVariant),
            )
          else
            Wrap(
              spacing: AppSpacing.sm,
              runSpacing: AppSpacing.sm,
              children: modules.map((m) => _ModuleChip(module: m)).toList(),
            ),
        ],
      ),
    );
  }
}

class _ModuleChip extends StatelessWidget {
  const _ModuleChip({required this.module});
  final String module;

  @override
  Widget build(BuildContext context) {
    final (icon, variant) = _moduleInfo(module);
    return StatusBadge(
      status: _moduleLabel(module),
      variant: variant,
      icon: icon,
    );
  }

  (IconData, StatusVariant) _moduleInfo(String module) => switch (module) {
        'catalog' => (Icons.inventory_2_outlined, StatusVariant.warning),
        'orders' => (Icons.receipt_long_outlined, StatusVariant.info),
        'attendance' => (Icons.fingerprint, StatusVariant.neutral),
        'delivery' => (Icons.local_shipping_outlined, StatusVariant.success),
        'pos' => (Icons.point_of_sale_outlined, StatusVariant.info),
        'marketplace' => (Icons.storefront_outlined, StatusVariant.neutral),
        'finance' => (Icons.account_balance_wallet_outlined, StatusVariant.success),
        _ => (Icons.extension_outlined, StatusVariant.neutral),
      };

  String _moduleLabel(String module) => switch (module) {
        'catalog' => 'Katalog',
        'orders' => 'Buyurtmalar',
        'attendance' => 'Davomat',
        'delivery' => 'Yetkazish',
        'pos' => 'POS',
        'marketplace' => 'Marketplace',
        'finance' => 'Moliya',
        _ => module,
      };
}

// ---------------------------------------------------------------------------

class _AttachedStoresSection extends ConsumerWidget {
  const _AttachedStoresSection({required this.agentId});
  final String agentId;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final storesAsync = ref.watch(filteredStoresProvider(agentId));

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        SectionHeader(
          title: "Biriktirilgan do'konlar",
          actionLabel: 'Hammasi',
          onAction: () => context.push('/home/stores'),
        ),
        const SizedBox(height: AppSpacing.md),
        storesAsync.when(
          loading: () => const Center(child: CircularProgressIndicator()),
          error: (e, _) => EmptyState(
            icon: Icons.error_outline,
            title: 'Xatolik',
            message: e.toString(),
            compact: true,
          ),
          data: (stores) {
            if (stores.isEmpty) {
              return const EmptyState(
                icon: Icons.store_outlined,
                title: "Biriktirilgan do'konlar topilmadi",
                compact: true,
              );
            }
            return Column(
              children: stores
                  .take(5)
                  .map((s) => _StoreCard(store: s))
                  .toList(),
            );
          },
        ),
      ],
    );
  }
}

class _StoreCard extends StatelessWidget {
  const _StoreCard({required this.store});
  final Store store;

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    final tt = Theme.of(context).textTheme;

    return AppCard(
      margin: const EdgeInsets.only(bottom: AppSpacing.sm),
      padding: const EdgeInsets.symmetric(
          horizontal: AppSpacing.lg, vertical: AppSpacing.md),
      onTap: () => context.push('/home/stores/${store.id}'),
      child: Row(
        children: [
          Container(
            width: 40,
            height: 40,
            decoration: BoxDecoration(
              color: cs.primaryContainer,
              borderRadius: BorderRadius.circular(AppSpacing.radiusSm),
            ),
            child: Icon(Icons.store_outlined,
                color: cs.primary, size: AppSpacing.iconSm),
          ),
          const SizedBox(width: AppSpacing.md),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  store.name,
                  style: tt.titleSmall?.copyWith(fontWeight: FontWeight.w600),
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                ),
                if (store.address != null)
                  Text(
                    store.address!,
                    style: tt.bodySmall?.copyWith(color: cs.onSurfaceVariant),
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                  ),
              ],
            ),
          ),
          Icon(Icons.chevron_right,
              size: AppSpacing.iconSm, color: cs.onSurfaceVariant),
        ],
      ),
    );
  }
}

// ---------------------------------------------------------------------------
// Profil tahrirlash — bottom sheet

/// Profilni tahrirlash bottom sheet (full_name + locale).
///
/// PATCH /auth/me orqali faqat full_name va locale o'zgartiriladi.
/// [ref] tashqaridan beriladi — bo'lmasa `ConsumerStatefulWidget` kerak bo'lardi.
class _EditProfileSheet extends StatefulWidget {
  const _EditProfileSheet({required this.user, required this.ref});
  final MeResponse user;
  final WidgetRef ref;

  @override
  State<_EditProfileSheet> createState() => _EditProfileSheetState();
}

class _EditProfileSheetState extends State<_EditProfileSheet> {
  late final TextEditingController _nameCtrl;
  late String _locale;
  bool _loading = false;
  String? _error;

  @override
  void initState() {
    super.initState();
    _nameCtrl = TextEditingController(text: widget.user.fullName);
    _locale = widget.user.locale;
  }

  @override
  void dispose() {
    _nameCtrl.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    final name = _nameCtrl.text.trim();
    if (name.length < 2) {
      setState(() => _error = 'Ism kamida 2 belgi bo\'lishi kerak');
      return;
    }
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      await widget.ref.read(authNotifierProvider.notifier).updateProfile(
            fullName: name,
            locale: _locale,
          );
      if (mounted) Navigator.of(context).pop();
    } on Exception catch (e) {
      setState(() {
        _loading = false;
        _error = e.toString();
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    final tt = Theme.of(context).textTheme;
    final bottomPadding = MediaQuery.viewInsetsOf(context).bottom;

    return Padding(
      padding: EdgeInsets.fromLTRB(
        AppSpacing.lg,
        AppSpacing.lg,
        AppSpacing.lg,
        AppSpacing.lg + bottomPadding,
      ),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          // Sarlavha + yopish tugmasi
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              Text(
                'Profilni tahrirlash',
                style: tt.titleMedium?.copyWith(fontWeight: FontWeight.w700),
              ),
              IconButton(
                icon: const Icon(Icons.close),
                visualDensity: VisualDensity.compact,
                onPressed: () => Navigator.of(context).pop(),
              ),
            ],
          ),
          const SizedBox(height: AppSpacing.lg),

          // Ism maydoni
          TextFormField(
            controller: _nameCtrl,
            decoration: InputDecoration(
              labelText: 'To\'liq ism',
              prefixIcon: const Icon(Icons.person_outline),
              border: OutlineInputBorder(
                borderRadius: BorderRadius.circular(AppSpacing.radiusMd),
              ),
            ),
            textCapitalization: TextCapitalization.words,
            maxLength: 255,
            onChanged: (_) {
              if (_error != null) setState(() => _error = null);
            },
          ),
          const SizedBox(height: AppSpacing.md),

          // Til tanlash
          Text('Til', style: tt.labelMedium?.copyWith(color: cs.onSurfaceVariant)),
          const SizedBox(height: AppSpacing.xs),
          SegmentedButton<String>(
            segments: const [
              ButtonSegment(value: 'uz', label: Text("O'zbek")),
              ButtonSegment(value: 'ru', label: Text('Русский')),
            ],
            selected: {_locale},
            onSelectionChanged: (v) => setState(() => _locale = v.first),
            showSelectedIcon: false,
          ),
          const SizedBox(height: AppSpacing.md),

          // Xato xabari
          if (_error != null) ...[
            Text(
              _error!,
              style: tt.bodySmall?.copyWith(color: cs.error),
            ),
            const SizedBox(height: AppSpacing.sm),
          ],

          // Saqlash tugmasi
          FilledButton(
            onPressed: _loading ? null : _submit,
            child: _loading
                ? const SizedBox(
                    height: 20,
                    width: 20,
                    child: CircularProgressIndicator(strokeWidth: 2),
                  )
                : const Text('Saqlash'),
          ),
        ],
      ),
    );
  }
}
