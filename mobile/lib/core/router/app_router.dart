import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../features/attendance/attendance_screen.dart';
import '../../features/auth/auth_providers.dart';
import '../../features/auth/auth_repository.dart';
import '../../features/auth/login_screen.dart';
import '../../features/catalog/catalog_screen.dart';
import '../../features/dashboard/accountant_dashboard.dart';
import '../../features/dashboard/agent_dashboard.dart';
import '../../features/dashboard/courier_dashboard.dart';
import '../../features/delivery/delivery_detail_screen.dart';
import '../../features/delivery/delivery_list_screen.dart';
import '../../features/finance/finance_screen.dart';
import '../../features/home/home_shell.dart';
import '../../features/marketplace/courier_mp_deliveries_screen.dart';
import '../../features/marketplace/marketplace_accept_screen.dart';
import '../../features/marketplace/marketplace_browse_screen.dart';
import '../../features/marketplace/marketplace_cart_screen.dart';
import '../../features/marketplace/marketplace_orders_screen.dart';
import '../../features/orders/create_order_screen.dart';
import '../../features/orders/order_list_screen.dart';
import '../../features/pos/pos_inventory_screen.dart';
import '../../features/pos/pos_sale_screen.dart';
import '../../features/pos/pos_summary_screen.dart';
import '../../features/pos/store_dashboard.dart';
import '../../features/stores/store_detail_screen.dart';
import '../../features/stores/store_list_screen.dart';

/// Yo'llar
const String routeLogin = '/login';
const String routeHome = '/home';
const String routeAgent = '/home/agent';
const String routeCourier = '/home/courier';
const String routeStore = '/home/store';
const String routeAccountant = '/home/accountant';

// Accountant routes
const String routeAccountantFinance = '/home/accountant/finance';

// Agent routes
const String routeStores = '/home/stores';
const String routeStoreDetail = '/home/stores/:storeId';
const String routeCatalog = '/home/catalog';
const String routeOrders = '/home/orders';
const String routeOrderCreate = '/home/orders/create';
const String routeAttendance = '/home/attendance';

// Courier routes
const String routeDeliveries = '/home/deliveries';
const String routeDeliveryDetail = '/home/deliveries/:deliveryId';

// Courier Marketplace routes
const String routeCourierMpDeliveries = '/home/courier/mp-deliveries';
const String routeCourierMpDeliveryDetail =
    '/home/courier/mp-deliveries/:orderId';

// Store POS routes
const String routePosSale = '/home/pos/sale';
const String routePosInventory = '/home/pos/inventory';
const String routePosSummary = '/home/pos/summary';

// Store Marketplace routes
const String routeMarketplace = '/home/marketplace';
const String routeMarketplaceCart = '/home/marketplace/cart';
const String routeMarketplaceOrders = '/home/marketplace/orders';
const String routeMarketplaceOrderDetail = '/home/marketplace/orders/:orderId';
const String routeMarketplaceAccept =
    '/home/marketplace/orders/:orderId/accept';

final appRouterProvider = Provider<GoRouter>((ref) {
  final authState = ref.watch(authNotifierProvider);

  return GoRouter(
    initialLocation: routeLogin,
    redirect: (context, state) {
      final isLoading = authState is AuthStateLoading;
      final isAuthenticated = authState is AuthStateAuthenticated;
      final onLogin = state.matchedLocation == routeLogin;

      if (isLoading) return null;
      if (!isAuthenticated && !onLogin) return routeLogin;
      if (isAuthenticated && onLogin) {
        if (authState case final AuthStateAuthenticated s) {
          return switch (s.user.role) {
            'agent' => routeAgent,
            'courier' => routeCourier,
            'store' => routeStore,
            'accountant' => routeAccountant,
            _ => routeHome,
          };
        }
      }
      return null;
    },
    routes: [
      GoRoute(
        path: routeLogin,
        builder: (context, state) => const LoginScreen(),
      ),
      ShellRoute(
        builder: (context, state, child) => HomeShell(child: child),
        routes: [
          // --- Bosh sahifalar ---
          GoRoute(
            path: routeHome,
            builder: (context, state) => const Center(child: Text('Bosh sahifa')),
          ),
          GoRoute(
            path: routeAgent,
            builder: (context, state) => const AgentDashboard(),
          ),
          GoRoute(
            path: routeCourier,
            builder: (context, state) => const CourierDashboard(),
          ),
          GoRoute(
            path: routeStore,
            builder: (context, state) => const StoreDashboard(),
          ),

          // --- Buxgalter ---
          GoRoute(
            path: routeAccountant,
            builder: (context, state) => const AccountantDashboard(),
          ),
          GoRoute(
            path: routeAccountantFinance,
            builder: (context, state) => const FinanceScreen(),
          ),

          // --- Do'konlar ---
          GoRoute(
            path: routeStores,
            builder: (context, state) => const StoreListScreen(),
            routes: [
              GoRoute(
                path: ':storeId',
                builder: (context, state) => StoreDetailScreen(
                  storeId: state.pathParameters['storeId']!,
                ),
              ),
            ],
          ),

          // --- Katalog ---
          GoRoute(
            path: routeCatalog,
            builder: (context, state) => const CatalogScreen(),
          ),

          // --- Buyurtmalar ---
          GoRoute(
            path: routeOrders,
            builder: (context, state) => const OrderListScreen(),
          ),
          GoRoute(
            path: routeOrderCreate,
            builder: (context, state) {
              final storeId = state.uri.queryParameters['storeId'];
              return CreateOrderScreen(preselectedStoreId: storeId);
            },
          ),

          // --- Davomat ---
          GoRoute(
            path: routeAttendance,
            builder: (context, state) => const AttendanceScreen(),
          ),

          // --- Do'kon: POS ---
          GoRoute(
            path: routePosSale,
            builder: (context, state) => const PosSaleScreen(),
          ),
          GoRoute(
            path: routePosInventory,
            builder: (context, state) => const PosInventoryScreen(),
          ),
          GoRoute(
            path: routePosSummary,
            builder: (context, state) => const PosSummaryScreen(),
          ),

          // --- Do'kon: Marketplace ---
          GoRoute(
            path: routeMarketplace,
            builder: (context, state) =>
                const MarketplaceBrowseScreen(),
            routes: [
              GoRoute(
                path: 'cart',
                builder: (context, state) =>
                    const MarketplaceCartScreen(),
              ),
              GoRoute(
                path: 'orders',
                builder: (context, state) =>
                    const MarketplaceOrdersScreen(),
                routes: [
                  GoRoute(
                    path: ':orderId/accept',
                    builder: (context, state) =>
                        MarketplaceAcceptScreen(
                      orderId: state.pathParameters['orderId']!,
                    ),
                  ),
                ],
              ),
            ],
          ),

          // --- Kuryer: Yetkazishlar ---
          GoRoute(
            path: routeDeliveries,
            builder: (context, state) => const DeliveryListScreen(),
            routes: [
              GoRoute(
                path: ':deliveryId',
                builder: (context, state) => DeliveryDetailScreen(
                  deliveryId: state.pathParameters['deliveryId']!,
                ),
              ),
            ],
          ),

          // --- Kuryer: Marketplace Yetkazish ---
          GoRoute(
            path: routeCourierMpDeliveries,
            builder: (context, state) =>
                const CourierMpDeliveriesScreen(),
            routes: [
              GoRoute(
                path: ':orderId',
                builder: (context, state) =>
                    CourierMpDeliveryDetailScreen(
                  orderId: state.pathParameters['orderId']!,
                ),
              ),
            ],
          ),
        ],
      ),
    ],
  );
});

