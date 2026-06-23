import 'package:flutter_test/flutter_test.dart';
import 'package:retail_mobile/features/pos/pos_models.dart';

void main() {
  // ---------------------------------------------------------------------------
  // InventoryItem
  // ---------------------------------------------------------------------------

  group('InventoryItem — fromJson / expiry bayroqlari', () {
    test('oddiy mahsulot — expiry bayroqlari false', () {
      final item = InventoryItem.fromJson({
        'product_id': 'prod-001',
        'product_name': 'Sut',
        'sku': 'MILK-001',
        'unit': 'litr',
        'qty': 50.0,
        'cost_price': 8000.0,
        'sale_price': 10000.0,
        'is_expired': false,
        'is_near_expiry': false,
      });

      expect(item.productId, equals('prod-001'));
      expect(item.productName, equals('Sut'));
      expect(item.isExpired, isFalse);
      expect(item.isNearExpiry, isFalse);
      expect(item.hasExpiryWarning, isFalse);
    });

    test('expired mahsulot — is_expired true, hasExpiryWarning true', () {
      final item = InventoryItem.fromJson({
        'product_id': 'prod-002',
        'product_name': 'Qaymoq',
        'sku': 'CREAM-001',
        'unit': 'kg',
        'qty': 5.0,
        'cost_price': 15000.0,
        'sale_price': 20000.0,
        'is_expired': true,
        'is_near_expiry': false,
        'days_to_expiry': -3,
      });

      expect(item.isExpired, isTrue);
      expect(item.hasExpiryWarning, isTrue);
      expect(item.daysToExpiry, equals(-3));
    });

    test('near_expiry mahsulot — is_near_expiry true, hasExpiryWarning true', () {
      final item = InventoryItem.fromJson({
        'product_id': 'prod-003',
        'product_name': 'Yogurt',
        'sku': 'YOG-001',
        'unit': 'dona',
        'qty': 20.0,
        'cost_price': 5000.0,
        'sale_price': 7000.0,
        'is_expired': false,
        'is_near_expiry': true,
        'days_to_expiry': 2,
      });

      expect(item.isNearExpiry, isTrue);
      expect(item.isExpired, isFalse);
      expect(item.hasExpiryWarning, isTrue);
      expect(item.daysToExpiry, equals(2));
    });

    test('expiry_date ni to\'g\'ri parse qiladi', () {
      final item = InventoryItem.fromJson({
        'product_id': 'prod-004',
        'product_name': 'Kefir',
        'sku': 'KEF-001',
        'unit': 'litr',
        'qty': 10.0,
        'cost_price': 6000.0,
        'sale_price': 8000.0,
        'expiry_date': '2026-06-25T00:00:00.000Z',
        'is_expired': false,
        'is_near_expiry': true,
        'days_to_expiry': 2,
      });

      expect(item.expiryDate, isNotNull);
      expect(item.expiryDate!.year, equals(2026));
      expect(item.expiryDate!.month, equals(6));
    });

    test('expiry_date yo\'q bo\'lsa — null', () {
      final item = InventoryItem.fromJson({
        'product_id': 'prod-005',
        'product_name': 'Sabzi',
        'sku': 'SABZI-001',
        'unit': 'kg',
        'qty': 100.0,
        'cost_price': 3000.0,
        'sale_price': 5000.0,
        'is_expired': false,
        'is_near_expiry': false,
      });

      expect(item.expiryDate, isNull);
      expect(item.daysToExpiry, isNull);
    });

    test('toJson → fromJson round-trip', () {
      final original = InventoryItem.fromJson({
        'product_id': 'prod-006',
        'product_name': 'Tuxum',
        'sku': 'EGG-001',
        'unit': 'dona',
        'qty': 120.0,
        'cost_price': 1200.0,
        'sale_price': 1500.0,
        'is_expired': false,
        'is_near_expiry': true,
        'days_to_expiry': 3,
      });

      final roundTripped = InventoryItem.fromJson(original.toJson());

      expect(roundTripped.productId, equals(original.productId));
      expect(roundTripped.isNearExpiry, equals(original.isNearExpiry));
      expect(roundTripped.daysToExpiry, equals(original.daysToExpiry));
    });
  });

  // ---------------------------------------------------------------------------
  // PosSaleRequest — server-avtoritar: narx YUBORILMAYDI
  // ---------------------------------------------------------------------------

  group('PosSaleRequest — toJson: faqat product_id + qty', () {
    test('toJson — narx maydoni yo\'q', () {
      const request = PosSaleRequest(
        items: [
          PosSaleItem(productId: 'prod-001', qty: 3),
          PosSaleItem(productId: 'prod-002', qty: 1),
        ],
        paymentMethod: 'cash',
      );

      final json = request.toJson();

      expect(json['payment_method'], equals('cash'));
      final items = json['items'] as List<dynamic>;
      expect(items.length, equals(2));

      final first = items.first as Map<String, dynamic>;
      expect(first['product_id'], equals('prod-001'));
      expect(first['qty'], equals(3.0));
      // Narx maydoni YO'Q — server hisoblaydi
      expect(first.containsKey('price'), isFalse);
      expect(first.containsKey('unit_price'), isFalse);
      expect(first.containsKey('cost_price'), isFalse);
    });

    test('PosSaleItem — toJson: faqat product_id + qty', () {
      const item = PosSaleItem(productId: 'prod-007', qty: 2.5);
      final json = item.toJson();

      expect(json['product_id'], equals('prod-007'));
      expect(json['qty'], equals(2.5));
      expect(json.length, equals(2)); // faqat 2 maydon
    });
  });

  // ---------------------------------------------------------------------------
  // PosSaleResponse
  // ---------------------------------------------------------------------------

  group('PosSaleResponse — fromJson', () {
    test('muvaffaqiyatli javob parse qilinadi', () {
      final response = PosSaleResponse.fromJson({
        'sale_id': 'sale-uuid-001',
        'total_amount': 45000.0,
        'payment_method': 'cash',
        'created_at': '2026-06-23T10:00:00.000Z',
        'items': [
          {
            'product_id': 'prod-001',
            'product_name': 'Sut',
            'qty': 3.0,
            'unit_price': 10000.0,
            'line_total': 30000.0,
          },
          {
            'product_id': 'prod-002',
            'product_name': 'Yogurt',
            'qty': 1.0,
            'unit_price': 15000.0,
            'line_total': 15000.0,
          },
        ],
      });

      expect(response.saleId, equals('sale-uuid-001'));
      expect(response.totalAmount, equals(45000.0));
      expect(response.paymentMethod, equals('cash'));
      expect(response.items.length, equals(2));
      expect(response.items.first.productName, equals('Sut'));
      expect(response.items.first.lineTotal, equals(30000.0));
    });

    test('items bo\'sh bo\'lsa — bo\'sh ro\'yxat', () {
      final response = PosSaleResponse.fromJson({
        'sale_id': 'sale-002',
        'total_amount': 0.0,
        'payment_method': 'card',
        'created_at': '2026-06-23T10:00:00.000Z',
        'items': <dynamic>[],
      });

      expect(response.items, isEmpty);
    });

    test('id kalit nomi ham qabul qilinadi (serverga qarab)', () {
      final response = PosSaleResponse.fromJson({
        'id': 'sale-003',
        'total_amount': 10000.0,
        'payment_method': 'transfer',
        'created_at': '2026-06-23T10:00:00.000Z',
      });

      expect(response.saleId, equals('sale-003'));
    });
  });

  // ---------------------------------------------------------------------------
  // PosSummary
  // ---------------------------------------------------------------------------

  group('PosSummary — fromJson', () {
    test('kunlik hisobot to\'g\'ri parse qilinadi', () {
      final summary = PosSummary.fromJson({
        'date': '2026-06-23',
        'total_sales': 15,
        'total_amount': 350000.0,
        'by_payment_method': {
          'cash': {'count': 10, 'amount': 200000.0},
          'card': {'count': 5, 'amount': 150000.0},
        },
      });

      expect(summary.date, equals('2026-06-23'));
      expect(summary.totalSales, equals(15));
      expect(summary.totalAmount, equals(350000.0));
      expect(summary.byPaymentMethod.length, equals(2));
      expect(summary.byPaymentMethod['cash']!.count, equals(10));
      expect(summary.byPaymentMethod['cash']!.amount, equals(200000.0));
      expect(summary.byPaymentMethod['card']!.count, equals(5));
    });

    test('bo\'sh sotuv kuni — total_sales 0', () {
      final summary = PosSummary.fromJson({
        'date': '2026-06-22',
        'total_sales': 0,
        'total_amount': 0.0,
        'by_payment_method': <String, dynamic>{},
      });

      expect(summary.totalSales, equals(0));
      expect(summary.totalAmount, equals(0.0));
      expect(summary.byPaymentMethod, isEmpty);
    });
  });
}
