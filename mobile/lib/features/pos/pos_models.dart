// POS — modellar va javob tiplari.
//
// Backend:
//   POST /pos/sales  → PosSaleResponse
//   GET  /marketplace/inventory → InventoryItem ro'yxati
//   GET  /pos/summary?date= → PosSummary

// ---------------------------------------------------------------------------
// Inventory

/// GET /marketplace/inventory — bitta mahsulot yozuvi.
///
/// Expiry bayroqlari:
///   is_expired      — muddati o'tgan (QIZIL, sotuv taqiqlangan)
///   is_near_expiry  — muddat yaqin (QIZIL ogohlantirish)
///   days_to_expiry  — qolgan kunlar soni (null = muddat yo'q)
class InventoryItem {
  const InventoryItem({
    required this.productId,
    required this.productName,
    required this.sku,
    required this.unit,
    required this.qty,
    required this.costPrice,
    required this.salePrice,
    this.expiryDate,
    required this.isExpired,
    required this.isNearExpiry,
    this.daysToExpiry,
  });

  factory InventoryItem.fromJson(Map<String, dynamic> json) {
    return InventoryItem(
      productId: json['product_id'] as String,
      productName: json['product_name'] as String? ?? '',
      sku: json['sku'] as String? ?? '',
      unit: json['unit'] as String? ?? 'dona',
      qty: (json['qty'] as num?)?.toDouble() ?? 0.0,
      costPrice: (json['cost_price'] as num?)?.toDouble() ?? 0.0,
      salePrice: (json['sale_price'] as num?)?.toDouble() ?? 0.0,
      expiryDate: json['expiry_date'] != null
          ? DateTime.tryParse(json['expiry_date'] as String)
          : null,
      isExpired: json['is_expired'] as bool? ?? false,
      isNearExpiry: json['is_near_expiry'] as bool? ?? false,
      daysToExpiry: json['days_to_expiry'] as int?,
    );
  }

  final String productId;
  final String productName;
  final String sku;
  final String unit;

  /// Ombordagi qoldiq miqdori.
  final double qty;

  /// Tan narxi (ma'lumot uchun, yubormaydi).
  final double costPrice;

  /// Sotuv narxi (ma'lumot uchun — server hisoblaydi).
  final double salePrice;

  /// Yaroqlilik muddati (null — muddat belgilanmagan).
  final DateTime? expiryDate;

  /// Muddati o'tgan — sotuv taqiqlangan.
  final bool isExpired;

  /// Muddat yaqin — ogohlantirish ko'rsatiladi.
  final bool isNearExpiry;

  /// Muddat tugashiga qolgan kunlar (null — muddat yo'q).
  final int? daysToExpiry;

  /// Expiry xavfi bor (expired yoki near_expiry)
  bool get hasExpiryWarning => isExpired || isNearExpiry;

  Map<String, dynamic> toJson() => {
        'product_id': productId,
        'product_name': productName,
        'sku': sku,
        'unit': unit,
        'qty': qty,
        'cost_price': costPrice,
        'sale_price': salePrice,
        if (expiryDate != null) 'expiry_date': expiryDate!.toIso8601String(),
        'is_expired': isExpired,
        'is_near_expiry': isNearExpiry,
        if (daysToExpiry != null) 'days_to_expiry': daysToExpiry,
      };
}

// ---------------------------------------------------------------------------
// POS sotuv

/// POST /pos/sales so'rovi — faqat product_id + qty (server narx hisoblaydi).
class PosSaleRequest {
  const PosSaleRequest({
    required this.items,
    required this.paymentMethod,
  });

  final List<PosSaleItem> items;
  final String paymentMethod;

  Map<String, dynamic> toJson() => {
        'items': items.map((i) => i.toJson()).toList(),
        'payment_method': paymentMethod,
      };
}

/// Bitta sotuv satri — FAQAT product_id + qty.
/// Narx YUBORILMAYDI — server hisoblaydi.
class PosSaleItem {
  const PosSaleItem({
    required this.productId,
    required this.qty,
  });

  final String productId;
  final double qty;

  Map<String, dynamic> toJson() => {
        'product_id': productId,
        'qty': qty,
      };
}

/// POST /pos/sales javobi.
class PosSaleResponse {
  const PosSaleResponse({
    required this.saleId,
    required this.totalAmount,
    required this.paymentMethod,
    required this.createdAt,
    required this.items,
  });

  factory PosSaleResponse.fromJson(Map<String, dynamic> json) {
    final itemsList = (json['items'] as List<dynamic>? ?? [])
        .map((e) => PosSaleLineResponse.fromJson(e as Map<String, dynamic>))
        .toList();
    return PosSaleResponse(
      saleId: json['sale_id'] as String? ?? json['id'] as String? ?? '',
      totalAmount: (json['total_amount'] as num?)?.toDouble() ?? 0.0,
      paymentMethod: json['payment_method'] as String? ?? 'cash',
      createdAt: DateTime.tryParse(
              json['created_at'] as String? ?? '') ??
          DateTime.now(),
      items: itemsList,
    );
  }

  final String saleId;
  final double totalAmount;
  final String paymentMethod;
  final DateTime createdAt;
  final List<PosSaleLineResponse> items;

  Map<String, dynamic> toJson() => {
        'sale_id': saleId,
        'total_amount': totalAmount,
        'payment_method': paymentMethod,
        'created_at': createdAt.toIso8601String(),
        'items': items.map((i) => i.toJson()).toList(),
      };
}

class PosSaleLineResponse {
  const PosSaleLineResponse({
    required this.productId,
    required this.productName,
    required this.qty,
    required this.unitPrice,
    required this.lineTotal,
  });

  factory PosSaleLineResponse.fromJson(Map<String, dynamic> json) {
    return PosSaleLineResponse(
      productId: json['product_id'] as String? ?? '',
      productName: json['product_name'] as String? ?? '',
      qty: (json['qty'] as num?)?.toDouble() ?? 0.0,
      unitPrice: (json['unit_price'] as num?)?.toDouble() ?? 0.0,
      lineTotal: (json['line_total'] as num?)?.toDouble() ?? 0.0,
    );
  }

  final String productId;
  final String productName;
  final double qty;
  final double unitPrice;
  final double lineTotal;

  Map<String, dynamic> toJson() => {
        'product_id': productId,
        'product_name': productName,
        'qty': qty,
        'unit_price': unitPrice,
        'line_total': lineTotal,
      };
}

// ---------------------------------------------------------------------------
// Kunlik hisobot

/// GET /pos/summary?date=YYYY-MM-DD javobi.
class PosSummary {
  const PosSummary({
    required this.date,
    required this.totalSales,
    required this.totalAmount,
    required this.byPaymentMethod,
  });

  factory PosSummary.fromJson(Map<String, dynamic> json) {
    final byMethod = <String, PosSummaryByMethod>{};
    final rawMap = json['by_payment_method'] as Map<String, dynamic>? ?? {};
    for (final entry in rawMap.entries) {
      byMethod[entry.key] =
          PosSummaryByMethod.fromJson(entry.value as Map<String, dynamic>);
    }
    return PosSummary(
      date: json['date'] as String? ?? '',
      totalSales: (json['total_sales'] as num?)?.toInt() ?? 0,
      totalAmount: (json['total_amount'] as num?)?.toDouble() ?? 0.0,
      byPaymentMethod: byMethod,
    );
  }

  final String date;
  final int totalSales;
  final double totalAmount;
  final Map<String, PosSummaryByMethod> byPaymentMethod;

  Map<String, dynamic> toJson() => {
        'date': date,
        'total_sales': totalSales,
        'total_amount': totalAmount,
        'by_payment_method': byPaymentMethod.map(
          (k, v) => MapEntry(k, v.toJson()),
        ),
      };
}

class PosSummaryByMethod {
  const PosSummaryByMethod({
    required this.count,
    required this.amount,
  });

  factory PosSummaryByMethod.fromJson(Map<String, dynamic> json) {
    return PosSummaryByMethod(
      count: (json['count'] as num?)?.toInt() ?? 0,
      amount: (json['amount'] as num?)?.toDouble() ?? 0.0,
    );
  }

  final int count;
  final double amount;

  Map<String, dynamic> toJson() => {
        'count': count,
        'amount': amount,
      };
}
