import 'package:flutter_test/flutter_test.dart';
import 'package:retail_mobile/features/marketplace/marketplace_models.dart';

void main() {
  // ---------------------------------------------------------------------------
  // MarketplaceBanner
  // ---------------------------------------------------------------------------

  group('MarketplaceBanner — fromJson / toJson', () {
    test('to\'liq banner parse qilinadi', () {
      final banner = MarketplaceBanner.fromJson({
        'id': 'banner-001',
        'image_url': 'https://example.com/banner.jpg',
        'target_product_id': 'prod-001',
        'target_url': 'https://example.com/promo',
        'title': 'Yozgi aksiya',
      });

      expect(banner.id, equals('banner-001'));
      expect(banner.imageUrl, equals('https://example.com/banner.jpg'));
      expect(banner.targetProductId, equals('prod-001'));
      expect(banner.targetUrl, equals('https://example.com/promo'));
      expect(banner.title, equals('Yozgi aksiya'));
    });

    test('ixtiyoriy maydonlar null bo\'lishi mumkin', () {
      final banner = MarketplaceBanner.fromJson({
        'id': 'banner-002',
        'image_url': '',
      });

      expect(banner.targetProductId, isNull);
      expect(banner.targetUrl, isNull);
      expect(banner.title, isNull);
    });

    test('toJson — round-trip', () {
      final original = MarketplaceBanner.fromJson({
        'id': 'b-1',
        'image_url': 'https://img.com/1.jpg',
        'title': 'Test',
      });
      final roundTripped = MarketplaceBanner.fromJson(original.toJson());
      expect(roundTripped.id, equals(original.id));
      expect(roundTripped.title, equals(original.title));
    });
  });

  // ---------------------------------------------------------------------------
  // MarketplacePromo
  // ---------------------------------------------------------------------------

  group('MarketplacePromo — fromJson', () {
    test('to\'liq promo parse qilinadi', () {
      final promo = MarketplacePromo.fromJson({
        'id': 'promo-001',
        'product_id': 'prod-001',
        'product_name': 'Sut',
        'supplier_name': 'Toshkent Dairy',
        'original_price': 12000.0,
        'promo_price': 9600.0,
        'discount_percent': 20.0,
        'ends_at': '2026-07-01T00:00:00.000Z',
        'image_url': 'https://img.com/sut.jpg',
      });

      expect(promo.id, equals('promo-001'));
      expect(promo.productName, equals('Sut'));
      expect(promo.supplierName, equals('Toshkent Dairy'));
      expect(promo.originalPrice, equals(12000.0));
      expect(promo.promoPrice, equals(9600.0));
      expect(promo.discountPercent, equals(20.0));
      expect(promo.endsAt, isNotNull);
      expect(promo.endsAt!.year, equals(2026));
    });

    test('ixtiyoriy maydonlar null bo\'lishi mumkin', () {
      final promo = MarketplacePromo.fromJson({
        'id': 'promo-002',
        'product_id': 'prod-002',
        'product_name': 'Yogurt',
        'supplier_name': 'Fermer',
        'original_price': 5000.0,
        'promo_price': 4000.0,
      });

      expect(promo.discountPercent, isNull);
      expect(promo.endsAt, isNull);
      expect(promo.imageUrl, isNull);
    });
  });

  // ---------------------------------------------------------------------------
  // MarketplaceProduct
  // ---------------------------------------------------------------------------

  group('MarketplaceProduct — fromJson', () {
    test('mahsulot to\'g\'ri parse qilinadi', () {
      final product = MarketplaceProduct.fromJson({
        'id': 'prod-001',
        'name': 'Qand',
        'sku': 'SUGAR-5KG',
        'unit': 'kg',
        'price': 25000.0,
        'supplier_enterprise_id': 'ent-supplier-1',
        'supplier_enterprise_name': 'Qand Fabrikasi',
        'available_qty': 500.0,
      });

      expect(product.id, equals('prod-001'));
      expect(product.name, equals('Qand'));
      expect(product.sku, equals('SUGAR-5KG'));
      expect(product.unit, equals('kg'));
      expect(product.price, equals(25000.0));
      expect(product.supplierEnterpriseId, equals('ent-supplier-1'));
      expect(product.supplierEnterpriseName, equals('Qand Fabrikasi'));
      expect(product.availableQty, equals(500.0));
    });

    test('toJson — round-trip', () {
      final original = MarketplaceProduct.fromJson({
        'id': 'p-1',
        'name': 'Un',
        'sku': 'FLOUR-1',
        'unit': 'kg',
        'price': 8000.0,
        'supplier_enterprise_id': 'ent-1',
        'supplier_enterprise_name': 'Un Fabrikasi',
      });
      final roundTripped =
          MarketplaceProduct.fromJson(original.toJson());
      expect(roundTripped.id, equals(original.id));
      expect(roundTripped.price, equals(original.price));
      expect(roundTripped.supplierEnterpriseName,
          equals(original.supplierEnterpriseName));
    });
  });

  // ---------------------------------------------------------------------------
  // MarketplaceOrderStatus
  // ---------------------------------------------------------------------------

  group('MarketplaceOrderStatus — fromString / label', () {
    test('barcha holat stringlari to\'g\'ri parse qilinadi', () {
      expect(MarketplaceOrderStatus.fromString('pending'),
          equals(MarketplaceOrderStatus.pending));
      expect(MarketplaceOrderStatus.fromString('confirmed'),
          equals(MarketplaceOrderStatus.confirmed));
      expect(MarketplaceOrderStatus.fromString('delivering'),
          equals(MarketplaceOrderStatus.delivering));
      expect(MarketplaceOrderStatus.fromString('delivered'),
          equals(MarketplaceOrderStatus.delivered));
      expect(MarketplaceOrderStatus.fromString('accepted'),
          equals(MarketplaceOrderStatus.accepted));
      expect(MarketplaceOrderStatus.fromString('cancelled'),
          equals(MarketplaceOrderStatus.cancelled));
    });

    test('noma\'lum string — pending qaytaradi', () {
      expect(MarketplaceOrderStatus.fromString('unknown'),
          equals(MarketplaceOrderStatus.pending));
    });

    test('label to\'g\'ri qaytaradi', () {
      expect(MarketplaceOrderStatus.pending.label, equals('Kutilmoqda'));
      expect(MarketplaceOrderStatus.delivered.label, equals('Yetkazildi'));
      expect(MarketplaceOrderStatus.accepted.label, equals('Qabul qilindi'));
    });
  });

  // ---------------------------------------------------------------------------
  // MarketplaceOrder
  // ---------------------------------------------------------------------------

  group('MarketplaceOrder — fromJson / canAccept', () {
    test('to\'liq buyurtma parse qilinadi', () {
      final order = MarketplaceOrder.fromJson({
        'id': 'order-001',
        'status': 'delivered',
        'supplier_enterprise_id': 'ent-sup-1',
        'supplier_enterprise_name': 'Supplier A',
        'lines': [
          {
            'line_id': 'line-001',
            'product_id': 'prod-001',
            'product_name': 'Sut',
            'qty': 10.0,
            'unit_price': 5000.0,
          },
          {
            'line_id': 'line-002',
            'product_id': 'prod-002',
            'product_name': 'Qaymoq',
            'qty': 5.0,
            'unit_price': 15000.0,
          },
        ],
        'created_at': '2026-06-20T10:00:00.000Z',
        'proof_photo_url': 'https://photos.com/proof.jpg',
      });

      expect(order.id, equals('order-001'));
      expect(order.status, equals(MarketplaceOrderStatus.delivered));
      expect(order.supplierEnterpriseName, equals('Supplier A'));
      expect(order.lines.length, equals(2));
      expect(order.lines.first.productName, equals('Sut'));
      expect(order.proofPhotoUrl, equals('https://photos.com/proof.jpg'));
      expect(order.canAccept, isTrue);
    });

    test('pending holati — canAccept false', () {
      final order = MarketplaceOrder.fromJson({
        'id': 'order-002',
        'status': 'pending',
        'supplier_enterprise_id': 'ent-1',
        'supplier_enterprise_name': 'Sup',
        'lines': <dynamic>[],
        'created_at': '2026-06-23T09:00:00.000Z',
      });

      expect(order.canAccept, isFalse);
    });

    test('accepted holati — canAccept false', () {
      final order = MarketplaceOrder.fromJson({
        'id': 'order-003',
        'status': 'accepted',
        'supplier_enterprise_id': 'ent-1',
        'supplier_enterprise_name': 'Sup',
        'lines': <dynamic>[],
        'created_at': '2026-06-23T09:00:00.000Z',
      });

      expect(order.canAccept, isFalse);
    });

    test('toJson — round-trip', () {
      final original = MarketplaceOrder.fromJson({
        'id': 'order-004',
        'status': 'confirmed',
        'supplier_enterprise_id': 'ent-1',
        'supplier_enterprise_name': 'Sup B',
        'lines': <dynamic>[],
        'created_at': '2026-06-23T10:00:00.000Z',
      });
      final roundTripped =
          MarketplaceOrder.fromJson(original.toJson());
      expect(roundTripped.id, equals(original.id));
      expect(roundTripped.status, equals(original.status));
      expect(roundTripped.supplierEnterpriseName,
          equals(original.supplierEnterpriseName));
    });
  });

  // ---------------------------------------------------------------------------
  // CreateMarketplaceOrderRequest — server-avtoritar: narx YUBORILMAYDI
  // ---------------------------------------------------------------------------

  group('CreateMarketplaceOrderRequest — toJson: faqat product_id + qty', () {
    test('narx maydoni yo\'q', () {
      const request = CreateMarketplaceOrderRequest(
        productId: 'prod-001',
        qty: 5.0,
      );

      final json = request.toJson();

      expect(json['product_id'], equals('prod-001'));
      expect(json['qty'], equals(5.0));
      // Narx maydonlari YO'Q — server hisoblaydi
      expect(json.containsKey('price'), isFalse);
      expect(json.containsKey('unit_price'), isFalse);
      expect(json.containsKey('cost_price'), isFalse);
      expect(json.length, equals(2)); // faqat 2 maydon
    });
  });

  // ---------------------------------------------------------------------------
  // AcceptOrderRequest
  // ---------------------------------------------------------------------------

  group('AcceptOrderRequest — toJson', () {
    test('lines to\'g\'ri formatda yuboriladi', () {
      final expiryDate = DateTime(2027, 3, 15);
      final request = AcceptOrderRequest(
        lines: [
          AcceptOrderLine(
            lineId: 'line-001',
            expiryDate: expiryDate,
            markupPercent: 15.0,
          ),
          AcceptOrderLine(
            lineId: 'line-002',
            expiryDate: expiryDate,
            markupPercent: 20.5,
          ),
        ],
      );

      final json = request.toJson();
      final lines = json['lines'] as List<dynamic>;

      expect(lines.length, equals(2));

      final first = lines.first as Map<String, dynamic>;
      expect(first['line_id'], equals('line-001'));
      expect(first['expiry_date'], equals('2027-03-15'));
      expect(first['markup_percent'], equals(15.0));

      final second = lines[1] as Map<String, dynamic>;
      expect(second['markup_percent'], equals(20.5));
    });

    test('expiry_date faqat sana formatida (vaqtsiz)', () {
      final expiryDate = DateTime(2026, 12, 31, 23, 59, 59);
      final line = AcceptOrderLine(
        lineId: 'line-x',
        expiryDate: expiryDate,
        markupPercent: 10.0,
      );

      final json = line.toJson();
      // Vaqt qismi bo'lmasligi kerak
      expect(json['expiry_date'], equals('2026-12-31'));
    });
  });
}
