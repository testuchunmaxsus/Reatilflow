import 'package:flutter/material.dart';
import 'package:flutter_map/flutter_map.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:latlong2/latlong.dart';

import '../../core/theme/app_spacing.dart';
import '../../core/theme/app_theme.dart';
import '../../core/widgets/widgets.dart';
import '../../data/local/database.dart';
import 'delivery_providers.dart';

/// Yetkazish GPS trek xaritasi ekrani.
///
/// flutter_map (OpenStreetMap — API key kerak emas) orqali ko'rsatiladi.
/// - Boshlash nuqtasi (yashil marker)
/// - Hozirgi joylashuv (ko'k marker)
/// - GPS trek polyline (yo'l chizig'i)
class DeliveryMapScreen extends ConsumerWidget {
  const DeliveryMapScreen({super.key, required this.deliveryId});

  final String deliveryId;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final deliveryAsync = ref.watch(deliveryStreamProvider(deliveryId));
    final gpsPointsAsync = ref.watch(deliveryGpsPointsProvider(deliveryId));
    final cs = Theme.of(context).colorScheme;

    return Scaffold(
      appBar: AppBar(
        title: Text('Xarita — ${deliveryId.substring(0, 8)}...'),
      ),
      body: deliveryAsync.when(
        loading: () =>
            Center(child: CircularProgressIndicator(color: cs.primary)),
        error: (e, _) => EmptyState(
          icon: Icons.error_outline,
          title: 'Xatolik yuz berdi',
          message: e.toString(),
        ),
        data: (delivery) {
          if (delivery == null) {
            return const EmptyState(
              icon: Icons.local_shipping_outlined,
              title: 'Yetkazish topilmadi',
            );
          }
          return gpsPointsAsync.when(
            loading: () =>
                Center(child: CircularProgressIndicator(color: cs.primary)),
            error: (e, _) => EmptyState(
              icon: Icons.gps_off,
              title: "GPS ma'lumot yuklanmadi",
              message: e.toString(),
            ),
            data: (points) =>
                _MapBody(delivery: delivery, gpsPoints: points),
          );
        },
      ),
    );
  }
}

// ---------------------------------------------------------------------------

class _MapBody extends StatelessWidget {
  const _MapBody({
    required this.delivery,
    required this.gpsPoints,
  });

  final Delivery delivery;
  final List<LatLng> gpsPoints;

  @override
  Widget build(BuildContext context) {
    const defaultCenter = LatLng(41.2995, 69.2401); // Toshkent
    final center = gpsPoints.isNotEmpty ? gpsPoints.last : defaultCenter;
    final cs = Theme.of(context).colorScheme;

    return Stack(
      children: [
        FlutterMap(
          options: MapOptions(
            initialCenter: center,
            initialZoom: gpsPoints.isNotEmpty ? 15.0 : 12.0,
          ),
          children: [
            TileLayer(
              urlTemplate: 'https://tile.openstreetmap.org/{z}/{x}/{y}.png',
              userAgentPackageName: 'uz.retail.mobile',
            ),

            if (gpsPoints.length >= 2)
              PolylineLayer(
                polylines: [
                  Polyline(
                    points: gpsPoints,
                    color: cs.primary,
                    strokeWidth: 4,
                  ),
                ],
              ),

            MarkerLayer(
              markers: [
                if (gpsPoints.isNotEmpty)
                  Marker(
                    point: gpsPoints.first,
                    child: _MapMarker(
                      icon: Icons.play_circle_filled,
                      color: AppTheme.colorsOf(context).success,
                      tooltip: 'Boshlash',
                    ),
                  ),

                if (gpsPoints.isNotEmpty)
                  Marker(
                    point: gpsPoints.last,
                    child: _MapMarker(
                      icon: Icons.local_shipping,
                      color: cs.primary,
                      tooltip: 'Hozirgi joylashuv',
                    ),
                  ),
              ],
            ),
          ],
        ),

        // Pastdagi holat paneli
        Positioned(
          bottom: AppSpacing.lg,
          left: AppSpacing.lg,
          right: AppSpacing.lg,
          child:
              _StatusPanel(delivery: delivery, pointsCount: gpsPoints.length),
        ),

        // GPS nuqtalar yo'q bo'lsa — info banneri
        if (gpsPoints.isEmpty)
          Positioned(
            top: AppSpacing.lg,
            left: AppSpacing.lg,
            right: AppSpacing.lg,
            child: AppCard(
              padding: const EdgeInsets.symmetric(
                  horizontal: AppSpacing.lg, vertical: AppSpacing.md),
              color: AppTheme.colorsOf(context)
                  .warningContainer
                  .withValues(alpha: 0.5),
              borderColor: AppTheme.colorsOf(context)
                  .warning
                  .withValues(alpha: 0.4),
              child: Row(
                children: [
                  Icon(Icons.info_outline,
                      color: AppTheme.colorsOf(context).warning,
                      size: AppSpacing.iconSm),
                  const SizedBox(width: AppSpacing.sm),
                  Expanded(
                    child: Text(
                      "GPS ma'lumotlari hali yig'ilmagan",
                      style: Theme.of(context).textTheme.bodySmall?.copyWith(
                            color: AppTheme.colorsOf(context).warning,
                          ),
                    ),
                  ),
                ],
              ),
            ),
          ),
      ],
    );
  }
}

// ---------------------------------------------------------------------------

class _MapMarker extends StatelessWidget {
  const _MapMarker({
    required this.icon,
    required this.color,
    required this.tooltip,
  });

  final IconData icon;
  final Color color;
  final String tooltip;

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    return Tooltip(
      message: tooltip,
      child: Container(
        decoration: BoxDecoration(
          color: cs.surface,
          shape: BoxShape.circle,
          boxShadow: [
            BoxShadow(
              color: color.withValues(alpha: 0.4),
              blurRadius: 8,
              spreadRadius: 1,
            ),
          ],
        ),
        child: Icon(icon, color: color, size: 28),
      ),
    );
  }
}

// ---------------------------------------------------------------------------

class _StatusPanel extends StatelessWidget {
  const _StatusPanel({
    required this.delivery,
    required this.pointsCount,
  });

  final Delivery delivery;
  final int pointsCount;

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    final tt = Theme.of(context).textTheme;

    return AppCard(
      padding: const EdgeInsets.symmetric(
          horizontal: AppSpacing.lg, vertical: AppSpacing.md),
      child: Row(
        children: [
          Container(
            width: 40,
            height: 40,
            decoration: BoxDecoration(
              color: cs.primaryContainer,
              borderRadius: BorderRadius.circular(AppSpacing.radiusSm),
            ),
            child: Icon(Icons.timeline_outlined,
                color: cs.primary, size: AppSpacing.iconSm),
          ),
          const SizedBox(width: AppSpacing.md),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              mainAxisSize: MainAxisSize.min,
              children: [
                StatusBadge(status: _statusLabel(delivery.status)),
                const SizedBox(height: 2),
                Text(
                  '$pointsCount ta GPS nuqta',
                  style: tt.bodySmall?.copyWith(color: cs.onSurfaceVariant),
                ),
              ],
            ),
          ),
          if (delivery.address != null)
            Expanded(
              child: Text(
                delivery.address!,
                style: tt.bodySmall?.copyWith(color: cs.onSurfaceVariant),
                maxLines: 2,
                overflow: TextOverflow.ellipsis,
                textAlign: TextAlign.end,
              ),
            ),
        ],
      ),
    );
  }

  String _statusLabel(String status) => switch (status) {
        'assigned' => 'Tayinlangan',
        'started' => 'Boshlandi',
        'delivering' => 'Yetkazilmoqda',
        'delivered' => 'Yetkazildi',
        'failed' => 'Muvaffaqiyatsiz',
        _ => status,
      };
}
