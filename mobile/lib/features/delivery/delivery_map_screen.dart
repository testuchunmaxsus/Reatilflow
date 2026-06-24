import 'package:flutter/material.dart';
import 'package:flutter_map/flutter_map.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:latlong2/latlong.dart';

import '../../data/local/database.dart';
import 'delivery_providers.dart';

/// Yetkazish GPS trek xaritasi ekrani.
///
/// flutter_map (OpenStreetMap — API key kerak emas) orqali ko'rsatiladi.
/// - Boshlash nuqtasi (yashil marker)
/// - Hozirgi joylashuv (ko'k marker)
/// - GPS trek polyline (yo'l chizig'i)
///
/// delivery_detail_screen'dan `context.push(routeDeliveryMap, extra: delivery)` orqali ochiladi.
class DeliveryMapScreen extends ConsumerWidget {
  const DeliveryMapScreen({super.key, required this.deliveryId});

  final String deliveryId;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final deliveryAsync = ref.watch(deliveryStreamProvider(deliveryId));
    final gpsPointsAsync = ref.watch(deliveryGpsPointsProvider(deliveryId));

    return Scaffold(
      appBar: AppBar(
        title: Text('Xarita — ${deliveryId.substring(0, 8)}...'),
      ),
      body: deliveryAsync.when(
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (e, _) => Center(child: Text('Xatolik: $e')),
        data: (delivery) {
          if (delivery == null) {
            return const Center(child: Text('Yetkazish topilmadi'));
          }
          return gpsPointsAsync.when(
            loading: () => const Center(child: CircularProgressIndicator()),
            error: (e, _) =>
                Center(child: Text('GPS ma\'lumot yuklanmadi: $e')),
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
    // Markazni hisoblash: birinchi/oxirgi nuqta yoki O'zbekiston (default)
    const defaultCenter = LatLng(41.2995, 69.2401); // Toshkent
    final center = gpsPoints.isNotEmpty ? gpsPoints.last : defaultCenter;

    return Stack(
      children: [
        FlutterMap(
          options: MapOptions(
            initialCenter: center,
            initialZoom: gpsPoints.isNotEmpty ? 15.0 : 12.0,
          ),
          children: [
            // OpenStreetMap tile layer
            TileLayer(
              urlTemplate: 'https://tile.openstreetmap.org/{z}/{x}/{y}.png',
              userAgentPackageName: 'uz.retail.mobile',
            ),

            // GPS trek polyline
            if (gpsPoints.length >= 2)
              PolylineLayer(
                polylines: [
                  Polyline(
                    points: gpsPoints,
                    color: Colors.blue.shade600,
                    strokeWidth: 4,
                  ),
                ],
              ),

            // Markerlar
            MarkerLayer(
              markers: [
                // Boshlash nuqtasi (yashil)
                if (gpsPoints.isNotEmpty)
                  Marker(
                    point: gpsPoints.first,
                    child: const _MapMarker(
                      icon: Icons.play_circle_filled,
                      color: Colors.green,
                      tooltip: 'Boshlash',
                    ),
                  ),

                // Oxirgi nuqta / joriy joylashuv (ko'k)
                if (gpsPoints.isNotEmpty)
                  Marker(
                    point: gpsPoints.last,
                    child: const _MapMarker(
                      icon: Icons.local_shipping,
                      color: Colors.blue,
                      tooltip: 'Hozirgi joylashuv',
                    ),
                  ),
              ],
            ),
          ],
        ),

        // Pastdagi holat paneli
        Positioned(
          bottom: 16,
          left: 16,
          right: 16,
          child: _StatusPanel(delivery: delivery, pointsCount: gpsPoints.length),
        ),

        // GPS nuqtalar yo'q bo'lsa — ma'lumot banneri
        if (gpsPoints.isEmpty)
          Positioned(
            top: 16,
            left: 16,
            right: 16,
            child: Container(
              padding:
                  const EdgeInsets.symmetric(horizontal: 16, vertical: 10),
              decoration: BoxDecoration(
                color: Colors.orange.shade100,
                borderRadius: BorderRadius.circular(10),
                border: Border.all(color: Colors.orange.shade300),
              ),
              child: const Row(
                children: [
                  Icon(Icons.info_outline,
                      color: Colors.orange, size: 18),
                  SizedBox(width: 8),
                  Expanded(
                    child: Text(
                      'GPS ma\'lumotlari hali yig\'ilmagan',
                      style:
                          TextStyle(color: Colors.orange, fontSize: 13),
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
    return Tooltip(
      message: tooltip,
      child: Container(
        decoration: BoxDecoration(
          color: Colors.white,
          shape: BoxShape.circle,
          boxShadow: [
            BoxShadow(
              color: color.withValues(alpha: 0.4),
              blurRadius: 6,
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
    return Card(
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
      elevation: 4,
      child: Padding(
        padding:
            const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
        child: Row(
          children: [
            const Icon(Icons.timeline, color: Colors.blue, size: 22),
            const SizedBox(width: 12),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                mainAxisSize: MainAxisSize.min,
                children: [
                  Text(
                    _statusLabel(delivery.status),
                    style: const TextStyle(fontWeight: FontWeight.w600),
                  ),
                  Text(
                    '$pointsCount ta GPS nuqta',
                    style: const TextStyle(
                        fontSize: 12, color: Colors.grey),
                  ),
                ],
              ),
            ),
            if (delivery.address != null)
              Expanded(
                child: Text(
                  delivery.address!,
                  style: const TextStyle(fontSize: 12, color: Colors.grey),
                  maxLines: 2,
                  overflow: TextOverflow.ellipsis,
                  textAlign: TextAlign.end,
                ),
              ),
          ],
        ),
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
