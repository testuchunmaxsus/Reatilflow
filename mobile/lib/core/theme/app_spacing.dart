/// Dizayn tizimi — Spacing va Radius tokenlari.
///
/// Barcha padding/margin/radius qiymatlari shu konstantalardan olinadi,
/// shunda butun ilova bo'ylab vizual izchillik ta'minlanadi.
abstract final class AppSpacing {
  // ── Spacing ──────────────────────────────────────────────────────────────

  /// 4 dp — juda kichik bo'shliq (icon ↔ text, chip padding)
  static const double xs = 4;

  /// 8 dp — kichik bo'shliq (list item vertical padding, dense gap)
  static const double sm = 8;

  /// 12 dp — o'rta-kichik (card internal gap, section spacing)
  static const double md = 12;

  /// 16 dp — asosiy bo'shliq (page padding, card padding)
  static const double lg = 16;

  /// 24 dp — katta bo'shliq (section divider, header spacing)
  static const double xl = 24;

  /// 32 dp — juda katta (hero areas, large section gaps)
  static const double xxl = 32;

  /// 48 dp — maydonga asoslangan (full-bleed sections)
  static const double xxxl = 48;

  // ── Radius ────────────────────────────────────────────────────────────────

  /// 4 dp — eng kichik yumaloqlik (chip, badge)
  static const double radiusXs = 4;

  /// 8 dp — kichik yumaloqlik (button dense, small card)
  static const double radiusSm = 8;

  /// 12 dp — o'rtacha yumaloqlik (input field, list tile)
  static const double radiusMd = 12;

  /// 16 dp — asosiy karta yumaloqligi
  static const double radiusLg = 16;

  /// 20 dp — katta karta / bottom sheet
  static const double radiusXl = 20;

  /// 28 dp — dialog / modal sheet
  static const double radiusXxl = 28;

  /// To'liq yumaloq (avatar, FAB, pill badge)
  static const double radiusFull = 9999;

  // ── Icon sizes ─────────────────────────────────────────────────────────

  /// 16 dp — chip ichidagi kichik icon
  static const double iconXs = 16;

  /// 20 dp — list tile trailing icon
  static const double iconSm = 20;

  /// 24 dp — standart icon hajmi (Material default)
  static const double iconMd = 24;

  /// 32 dp — karta ichidagi feature icon
  static const double iconLg = 32;

  /// 48 dp — empty state / hero icon
  static const double iconXl = 48;

  // ── Button ─────────────────────────────────────────────────────────────

  /// Tugma minimal balandligi (48 dp — Material 3 touch target)
  static const double buttonHeight = 48;

  /// Tugma horizontal padding
  static const double buttonPaddingH = 24;
}
