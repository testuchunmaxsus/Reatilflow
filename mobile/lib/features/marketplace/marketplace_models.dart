import 'package:flutter/material.dart';

// Marketplace — modellar va javob tiplari.
//
// Backend endpointlari:
//   GET  /marketplace/banners?limit=5                    → MarketplaceBanner ro'yxati
//   GET  /marketplace/promos?limit=20                    → MarketplacePromo ro'yxati
//   GET  /marketplace/products                           → MarketplaceProduct ro'yxati
//   POST /marketplace/orders                             → MarketplaceOrder
//   GET  /marketplace/orders/outgoing                    → MarketplaceOrder ro'yxati
//   GET  /marketplace/orders/deliveries                  → MarketplaceOrder ro'yxati (kuryer)
//   GET  /marketplace/orders/{id}                        → MarketplaceOrder
//   PATCH /marketplace/orders/{id}/accept                → MarketplaceOrder
//   POST  /marketplace/orders/{id}/proof-photo           → MarketplaceOrder (deliver)

// ---------------------------------------------------------------------------
// Banner

/// GET /marketplace/banners — reklama banneri.
class MarketplaceBanner {
  const MarketplaceBanner({
    required this.id,
    required this.imageUrl,
    this.targetProductId,
    this.targetUrl,
    this.title,
  });

  factory MarketplaceBanner.fromJson(Map<String, dynamic> json) {
    return MarketplaceBanner(
      id: json['id'] as String? ?? '',
      imageUrl: json['image_url'] as String? ?? '',
      targetProductId: json['target_product_id'] as String?,
      targetUrl: json['target_url'] as String?,
      title: json['title'] as String?,
    );
  }

  final String id;
  final String imageUrl;

  /// Bosilganda ochilishi kerak bo'lgan mahsulot ID (ixtiyoriy).
  final String? targetProductId;

  /// Bosilganda ochilishi kerak bo'lgan URL (ixtiyoriy).
  final String? targetUrl;
  final String? title;

  Map<String, dynamic> toJson() => {
        'id': id,
        'image_url': imageUrl,
        if (targetProductId != null) 'target_product_id': targetProductId,
        if (targetUrl != null) 'target_url': targetUrl,
        if (title != null) 'title': title,
      };
}

// ---------------------------------------------------------------------------
// Promo

/// GET /marketplace/promos — qaynoq aksiya.
class MarketplacePromo {
  const MarketplacePromo({
    required this.id,
    required this.productId,
    required this.productName,
    required this.supplierName,
    required this.originalPrice,
    required this.promoPrice,
    this.discountPercent,
    this.endsAt,
    this.imageUrl,
  });

  factory MarketplacePromo.fromJson(Map<String, dynamic> json) {
    return MarketplacePromo(
      id: json['id'] as String? ?? '',
      productId: json['product_id'] as String? ?? '',
      productName: json['product_name'] as String? ?? '',
      supplierName: json['supplier_name'] as String? ?? '',
      originalPrice: (json['original_price'] as num?)?.toDouble() ?? 0.0,
      promoPrice: (json['promo_price'] as num?)?.toDouble() ?? 0.0,
      discountPercent: (json['discount_percent'] as num?)?.toDouble(),
      endsAt: json['ends_at'] != null
          ? DateTime.tryParse(json['ends_at'] as String)
          : null,
      imageUrl: json['image_url'] as String?,
    );
  }

  final String id;
  final String productId;
  final String productName;
  final String supplierName;
  final double originalPrice;
  final double promoPrice;
  final double? discountPercent;
  final DateTime? endsAt;
  final String? imageUrl;

  Map<String, dynamic> toJson() => {
        'id': id,
        'product_id': productId,
        'product_name': productName,
        'supplier_name': supplierName,
        'original_price': originalPrice,
        'promo_price': promoPrice,
        if (discountPercent != null) 'discount_percent': discountPercent,
        if (endsAt != null) 'ends_at': endsAt!.toIso8601String(),
        if (imageUrl != null) 'image_url': imageUrl,
      };
}

// ---------------------------------------------------------------------------
// Product

/// GET /marketplace/products — bitta mahsulot.
///
/// Cross-tenant: supplierEnterpriseName bilan birga keladi.
class MarketplaceProduct {
  const MarketplaceProduct({
    required this.id,
    required this.name,
    required this.sku,
    required this.unit,
    required this.price,
    required this.supplierEnterpriseId,
    required this.supplierEnterpriseName,
    this.imageUrl,
    this.description,
    this.availableQty,
  });

  factory MarketplaceProduct.fromJson(Map<String, dynamic> json) {
    return MarketplaceProduct(
      id: json['id'] as String? ?? '',
      name: json['name'] as String? ?? '',
      sku: json['sku'] as String? ?? '',
      unit: json['unit'] as String? ?? 'dona',
      price: (json['price'] as num?)?.toDouble() ?? 0.0,
      supplierEnterpriseId:
          json['supplier_enterprise_id'] as String? ?? '',
      supplierEnterpriseName:
          json['supplier_enterprise_name'] as String? ?? '',
      imageUrl: json['image_url'] as String?,
      description: json['description'] as String?,
      availableQty: (json['available_qty'] as num?)?.toDouble(),
    );
  }

  final String id;
  final String name;
  final String sku;
  final String unit;

  /// Tavsiya narxi (ma'lumot uchun — buyurtmada yuborilmaydi).
  final double price;

  final String supplierEnterpriseId;
  final String supplierEnterpriseName;
  final String? imageUrl;
  final String? description;
  final double? availableQty;

  Map<String, dynamic> toJson() => {
        'id': id,
        'name': name,
        'sku': sku,
        'unit': unit,
        'price': price,
        'supplier_enterprise_id': supplierEnterpriseId,
        'supplier_enterprise_name': supplierEnterpriseName,
        if (imageUrl != null) 'image_url': imageUrl,
        if (description != null) 'description': description,
        if (availableQty != null) 'available_qty': availableQty,
      };
}

// ---------------------------------------------------------------------------
// Order

/// Buyurtma holati.
enum MarketplaceOrderStatus {
  pending,
  confirmed,
  delivering,
  delivered,
  accepted,
  cancelled;

  static MarketplaceOrderStatus fromString(String s) => switch (s) {
        'pending' => pending,
        'confirmed' => confirmed,
        'delivering' => delivering,
        'delivered' => delivered,
        'accepted' => accepted,
        'cancelled' => cancelled,
        _ => pending,
      };

  String get label => switch (this) {
        pending => 'Kutilmoqda',
        confirmed => 'Tasdiqlangan',
        delivering => 'Yetkazilmoqda',
        delivered => 'Yetkazildi',
        accepted => 'Qabul qilindi',
        cancelled => 'Bekor qilindi',
      };

  (Color, IconData) get style => switch (this) {
        pending => (const Color(0xFFF59E0B), _iconClock),
        confirmed => (const Color(0xFF3B82F6), _iconCheck),
        delivering => (const Color(0xFF8B5CF6), _iconTruck),
        delivered => (const Color(0xFF10B981), _iconDone),
        accepted => (const Color(0xFF059669), _iconDoneAll),
        cancelled => (const Color(0xFFEF4444), _iconCancel),
      };
}

// ignore: constant_identifier_names
const _iconClock = IconData(0xe192, fontFamily: 'MaterialIcons');
// ignore: constant_identifier_names
const _iconCheck = IconData(0xe156, fontFamily: 'MaterialIcons');
// ignore: constant_identifier_names
const _iconTruck = IconData(0xe558, fontFamily: 'MaterialIcons');
// ignore: constant_identifier_names
const _iconDone = IconData(0xe86c, fontFamily: 'MaterialIcons');
// ignore: constant_identifier_names
const _iconDoneAll = IconData(0xe877, fontFamily: 'MaterialIcons');
// ignore: constant_identifier_names
const _iconCancel = IconData(0xe14c, fontFamily: 'MaterialIcons');

/// Buyurtma satri (line).
class MarketplaceOrderLine {
  const MarketplaceOrderLine({
    required this.lineId,
    required this.productId,
    required this.productName,
    required this.qty,
    required this.unitPrice,
    this.expiryDate,
    this.markupPercent,
  });

  factory MarketplaceOrderLine.fromJson(Map<String, dynamic> json) {
    return MarketplaceOrderLine(
      lineId: json['line_id'] as String? ?? json['id'] as String? ?? '',
      productId: json['product_id'] as String? ?? '',
      productName: json['product_name'] as String? ?? '',
      qty: (json['qty'] as num?)?.toDouble() ?? 0.0,
      unitPrice: (json['unit_price'] as num?)?.toDouble() ?? 0.0,
      expiryDate: json['expiry_date'] != null
          ? DateTime.tryParse(json['expiry_date'] as String)
          : null,
      markupPercent: (json['markup_percent'] as num?)?.toDouble(),
    );
  }

  final String lineId;
  final String productId;
  final String productName;
  final double qty;
  final double unitPrice;

  /// Qabul qilishda kiritiladi — mahsulot muddati.
  final DateTime? expiryDate;

  /// Qabul qilishda kiritiladi — ustama foizi.
  final double? markupPercent;

  Map<String, dynamic> toJson() => {
        'line_id': lineId,
        'product_id': productId,
        'product_name': productName,
        'qty': qty,
        'unit_price': unitPrice,
        if (expiryDate != null) 'expiry_date': expiryDate!.toIso8601String(),
        if (markupPercent != null) 'markup_percent': markupPercent,
      };
}

/// Marketplace buyurtmasi.
class MarketplaceOrder {
  const MarketplaceOrder({
    required this.id,
    required this.status,
    required this.supplierEnterpriseId,
    required this.supplierEnterpriseName,
    required this.lines,
    required this.createdAt,
    this.totalAmount,
    this.proofPhotoUrl,
    this.confirmedAt,
    this.deliveredAt,
    this.acceptedAt,
    this.courierId,
    this.buyerEnterpriseId,
    this.buyerStoreId,
  });

  factory MarketplaceOrder.fromJson(Map<String, dynamic> json) {
    final linesList = (json['lines'] as List<dynamic>? ?? [])
        .map((e) =>
            MarketplaceOrderLine.fromJson(e as Map<String, dynamic>))
        .toList();
    return MarketplaceOrder(
      id: json['id'] as String? ?? '',
      status: MarketplaceOrderStatus.fromString(
          json['status'] as String? ?? 'pending'),
      supplierEnterpriseId:
          json['supplier_enterprise_id'] as String? ?? '',
      supplierEnterpriseName:
          json['supplier_enterprise_name'] as String? ?? '',
      lines: linesList,
      createdAt: DateTime.tryParse(
              json['created_at'] as String? ?? '') ??
          DateTime.now(),
      totalAmount: (json['total_amount'] as num?)?.toDouble(),
      proofPhotoUrl: json['proof_photo_url'] as String?,
      confirmedAt: json['confirmed_at'] != null
          ? DateTime.tryParse(json['confirmed_at'] as String)
          : null,
      deliveredAt: json['delivered_at'] != null
          ? DateTime.tryParse(json['delivered_at'] as String)
          : null,
      acceptedAt: json['accepted_at'] != null
          ? DateTime.tryParse(json['accepted_at'] as String)
          : null,
      courierId: json['courier_id'] as String?,
      buyerEnterpriseId: json['buyer_enterprise_id'] as String?,
      buyerStoreId: json['buyer_store_id'] as String?,
    );
  }

  final String id;
  final MarketplaceOrderStatus status;
  final String supplierEnterpriseId;
  final String supplierEnterpriseName;
  final List<MarketplaceOrderLine> lines;
  final DateTime createdAt;
  final double? totalAmount;

  /// Kuryer yuklagan dalil rasmi URL.
  final String? proofPhotoUrl;
  final DateTime? confirmedAt;
  final DateTime? deliveredAt;
  final DateTime? acceptedAt;

  /// Tayinlangan kuryer UUID (MP3 ship dan keyin to'ldiriladi).
  final String? courierId;

  /// Xaridor korxona UUID.
  final String? buyerEnterpriseId;

  /// Xaridor do'kon UUID.
  final String? buyerStoreId;

  /// Qabul qilish tugmasi ko'rsatilishi kerakmi?
  bool get canAccept => status == MarketplaceOrderStatus.delivered;

  /// Kuryer deliver qila oladimi? (delivering holat)
  bool get canDeliver => status == MarketplaceOrderStatus.delivering;

  Map<String, dynamic> toJson() => {
        'id': id,
        'status': status.name,
        'supplier_enterprise_id': supplierEnterpriseId,
        'supplier_enterprise_name': supplierEnterpriseName,
        'lines': lines.map((l) => l.toJson()).toList(),
        'created_at': createdAt.toIso8601String(),
        if (totalAmount != null) 'total_amount': totalAmount,
        if (proofPhotoUrl != null) 'proof_photo_url': proofPhotoUrl,
        if (confirmedAt != null)
          'confirmed_at': confirmedAt!.toIso8601String(),
        if (deliveredAt != null)
          'delivered_at': deliveredAt!.toIso8601String(),
        if (acceptedAt != null)
          'accepted_at': acceptedAt!.toIso8601String(),
        if (courierId != null) 'courier_id': courierId,
        if (buyerEnterpriseId != null) 'buyer_enterprise_id': buyerEnterpriseId,
        if (buyerStoreId != null) 'buyer_store_id': buyerStoreId,
      };
}

// ---------------------------------------------------------------------------
// Kuryer yetkazish so'rovi

/// POST /marketplace/orders/{id}/proof-photo javob uchun wrapper emas —
/// to'g'ridan-to'g'ri MarketplaceOrder qaytadi (endpoint).
/// Bu placeholder — deliver action uchun multipart yuboriladi.
class MarketplaceDeliverRequest {
  const MarketplaceDeliverRequest({this.proofPhotoUrl});

  final String? proofPhotoUrl;

  Map<String, dynamic> toJson() => {
        if (proofPhotoUrl != null) 'proof_photo_url': proofPhotoUrl,
      };
}

// ---------------------------------------------------------------------------
// Buyurtma yaratish

/// POST /marketplace/orders so'rovi — bitta mahsulot, qty FAQAT.
///
/// Server-avtoritar: narx YUBORILMAYDI.
/// Bitta supplier = bitta buyurtma (backend qoidasi).
class CreateMarketplaceOrderRequest {
  const CreateMarketplaceOrderRequest({
    required this.productId,
    required this.qty,
  });

  final String productId;
  final double qty;

  Map<String, dynamic> toJson() => {
        'product_id': productId,
        'qty': qty,
        // Narx YUBORILMAYDI — server hisoblaydi
      };
}

// ---------------------------------------------------------------------------
// Qabul qilish

/// PATCH /marketplace/orders/{id}/accept — har line uchun muddat + ustama.
class AcceptOrderRequest {
  const AcceptOrderRequest({required this.lines});

  final List<AcceptOrderLine> lines;

  Map<String, dynamic> toJson() => {
        'lines': lines.map((l) => l.toJson()).toList(),
      };
}

class AcceptOrderLine {
  const AcceptOrderLine({
    required this.lineId,
    required this.expiryDate,
    required this.markupPercent,
  });

  final String lineId;
  final DateTime expiryDate;
  final double markupPercent;

  Map<String, dynamic> toJson() => {
        'line_id': lineId,
        'expiry_date': expiryDate.toIso8601String().split('T').first,
        'markup_percent': markupPercent,
      };
}
