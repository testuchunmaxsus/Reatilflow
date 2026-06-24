import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:google_fonts/google_fonts.dart';

import 'app_spacing.dart';

/// Retail ilovasi uchun boy Material 3 tema tizimi.
///
/// Palitra: Chuqur indigo primary + teal secondary. Professional,
/// ishonchli retail/distribyutsiya ko'rinishi.
/// Shrift: Manrope (Google Fonts) — zamonaviy geometric grotesque,
/// offline qurilmalarda system font'ga graceful fallback.
abstract final class AppTheme {
  // ── Brend ranglar ─────────────────────────────────────────────────────────

  static const Color _primaryLight = Color(0xFF1A3C6E); // chuqur ko'k-indigo
  static const Color _primaryDark = Color(0xFF90B4E8); // ochiq ko'k (dark mode)

  static const Color _secondaryLight = Color(0xFF0D7E6B); // teal (muvaffaqiyat)
  static const Color _secondaryDark = Color(0xFF4DB8A5);

  static const Color _tertiaryLight = Color(0xFFB45309); // amber-brown (ogohlantirish)
  static const Color _tertiaryDark = Color(0xFFF59E0B);

  // Semantik ranglar — barcha widgetlar shu renferences ishlatadi
  static const Color _successLight = Color(0xFF15803D);
  static const Color _successDark = Color(0xFF4ADE80);

  static const Color _warningLight = Color(0xFFD97706);
  static const Color _warningDark = Color(0xFFFBBF24);

  static const Color _dangerLight = Color(0xFFDC2626);
  static const Color _dangerDark = Color(0xFFF87171);

  static const Color _infoLight = Color(0xFF0369A1);
  static const Color _infoDark = Color(0xFF38BDF8);

  // ── Semantik rang extensionlari ───────────────────────────────────────────

  /// Semantik ranglarni [BuildContext]dan olish uchun extension.
  static AppColors colorsOf(BuildContext context) {
    final isDark = Theme.of(context).brightness == Brightness.dark;
    return isDark ? const AppColors.dark() : const AppColors.light();
  }

  // ── ColorScheme ──────────────────────────────────────────────────────────

  static const ColorScheme _lightColorScheme = ColorScheme(
    brightness: Brightness.light,
    primary: _primaryLight,
    onPrimary: Colors.white,
    primaryContainer: Color(0xFFD6E4F7),
    onPrimaryContainer: Color(0xFF0A1F3D),
    secondary: _secondaryLight,
    onSecondary: Colors.white,
    secondaryContainer: Color(0xFFB2DFDB),
    onSecondaryContainer: Color(0xFF003D35),
    tertiary: _tertiaryLight,
    onTertiary: Colors.white,
    tertiaryContainer: Color(0xFFFFDDB3),
    onTertiaryContainer: Color(0xFF4A2000),
    error: _dangerLight,
    onError: Colors.white,
    errorContainer: Color(0xFFFFDAD6),
    onErrorContainer: Color(0xFF410002),
    surface: Color(0xFFF8FAFC),
    onSurface: Color(0xFF0F172A),
    surfaceContainerHighest: Color(0xFFE8EEF6),
    onSurfaceVariant: Color(0xFF475569),
    outline: Color(0xFFCBD5E1),
    outlineVariant: Color(0xFFE2E8F0),
    shadow: Color(0xFF000000),
    scrim: Color(0xFF000000),
    inverseSurface: Color(0xFF1E293B),
    onInverseSurface: Color(0xFFF1F5F9),
    inversePrimary: _primaryDark,
    surfaceTint: _primaryLight,
  );

  static const ColorScheme _darkColorScheme = ColorScheme(
    brightness: Brightness.dark,
    primary: _primaryDark,
    onPrimary: Color(0xFF0A1F3D),
    primaryContainer: Color(0xFF1A3C6E),
    onPrimaryContainer: Color(0xFFD6E4F7),
    secondary: _secondaryDark,
    onSecondary: Color(0xFF003D35),
    secondaryContainer: Color(0xFF004D42),
    onSecondaryContainer: Color(0xFFB2DFDB),
    tertiary: _tertiaryDark,
    onTertiary: Color(0xFF4A2000),
    tertiaryContainer: Color(0xFF7A4200),
    onTertiaryContainer: Color(0xFFFFDDB3),
    error: _dangerDark,
    onError: Color(0xFF690005),
    errorContainer: Color(0xFF93000A),
    onErrorContainer: Color(0xFFFFDAD6),
    surface: Color(0xFF0F172A),
    onSurface: Color(0xFFF1F5F9),
    surfaceContainerHighest: Color(0xFF1E293B),
    onSurfaceVariant: Color(0xFF94A3B8),
    outline: Color(0xFF334155),
    outlineVariant: Color(0xFF1E293B),
    shadow: Color(0xFF000000),
    scrim: Color(0xFF000000),
    inverseSurface: Color(0xFFF1F5F9),
    onInverseSurface: Color(0xFF1E293B),
    inversePrimary: _primaryLight,
    surfaceTint: _primaryDark,
  );

  // ── TextTheme (Manrope + Google Fonts) ───────────────────────────────────

  static TextTheme _buildTextTheme(ColorScheme colorScheme) {
    // Manrope: zamonaviy geometric grotesque, retail/fintech uchun ideal.
    // google_fonts qurilmada mavjud bo'lmasa system sans-serif'ga fallback.
    final base = GoogleFonts.manropeTextTheme();

    final onSurface = colorScheme.onSurface;
    final onSurfaceVariant = colorScheme.onSurfaceVariant;

    return TextTheme(
      // Display — katta hero sarlavhalar
      displayLarge: base.displayLarge?.copyWith(
        fontSize: 57,
        fontWeight: FontWeight.w700,
        letterSpacing: -1.5,
        color: onSurface,
        height: 1.12,
      ),
      displayMedium: base.displayMedium?.copyWith(
        fontSize: 45,
        fontWeight: FontWeight.w700,
        letterSpacing: -0.5,
        color: onSurface,
        height: 1.16,
      ),
      displaySmall: base.displaySmall?.copyWith(
        fontSize: 36,
        fontWeight: FontWeight.w600,
        letterSpacing: 0,
        color: onSurface,
        height: 1.22,
      ),

      // Headline — sahifa sarlavhalari
      headlineLarge: base.headlineLarge?.copyWith(
        fontSize: 32,
        fontWeight: FontWeight.w700,
        letterSpacing: -0.5,
        color: onSurface,
        height: 1.25,
      ),
      headlineMedium: base.headlineMedium?.copyWith(
        fontSize: 28,
        fontWeight: FontWeight.w600,
        letterSpacing: -0.25,
        color: onSurface,
        height: 1.29,
      ),
      headlineSmall: base.headlineSmall?.copyWith(
        fontSize: 24,
        fontWeight: FontWeight.w600,
        letterSpacing: 0,
        color: onSurface,
        height: 1.33,
      ),

      // Title — karta sarlavhalari, dialog sarlavhalari
      titleLarge: base.titleLarge?.copyWith(
        fontSize: 22,
        fontWeight: FontWeight.w600,
        letterSpacing: 0,
        color: onSurface,
        height: 1.27,
      ),
      titleMedium: base.titleMedium?.copyWith(
        fontSize: 16,
        fontWeight: FontWeight.w600,
        letterSpacing: 0.1,
        color: onSurface,
        height: 1.5,
      ),
      titleSmall: base.titleSmall?.copyWith(
        fontSize: 14,
        fontWeight: FontWeight.w600,
        letterSpacing: 0.1,
        color: onSurface,
        height: 1.43,
      ),

      // Body — asosiy matn
      bodyLarge: base.bodyLarge?.copyWith(
        fontSize: 16,
        fontWeight: FontWeight.w400,
        letterSpacing: 0.15,
        color: onSurface,
        height: 1.5,
      ),
      bodyMedium: base.bodyMedium?.copyWith(
        fontSize: 14,
        fontWeight: FontWeight.w400,
        letterSpacing: 0.25,
        color: onSurface,
        height: 1.43,
      ),
      bodySmall: base.bodySmall?.copyWith(
        fontSize: 12,
        fontWeight: FontWeight.w400,
        letterSpacing: 0.4,
        color: onSurfaceVariant,
        height: 1.33,
      ),

      // Label — tugmalar, chip, badge
      labelLarge: base.labelLarge?.copyWith(
        fontSize: 14,
        fontWeight: FontWeight.w600,
        letterSpacing: 0.1,
        color: onSurface,
        height: 1.43,
      ),
      labelMedium: base.labelMedium?.copyWith(
        fontSize: 12,
        fontWeight: FontWeight.w600,
        letterSpacing: 0.5,
        color: onSurfaceVariant,
        height: 1.33,
      ),
      labelSmall: base.labelSmall?.copyWith(
        fontSize: 11,
        fontWeight: FontWeight.w500,
        letterSpacing: 0.5,
        color: onSurfaceVariant,
        height: 1.45,
      ),
    );
  }

  // ── Komponent temalari ───────────────────────────────────────────────────

  static CardThemeData _cardTheme(ColorScheme cs) => CardThemeData(
        elevation: 0,
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(AppSpacing.radiusLg),
          side: BorderSide(color: cs.outlineVariant),
        ),
        color: cs.surface,
        surfaceTintColor: Colors.transparent,
        margin: EdgeInsets.zero,
        clipBehavior: Clip.antiAlias,
      );

  static AppBarTheme _appBarTheme(ColorScheme cs, TextTheme tt) => AppBarTheme(
        backgroundColor: cs.surface,
        foregroundColor: cs.onSurface,
        elevation: 0,
        scrolledUnderElevation: 1,
        centerTitle: false,
        titleTextStyle: tt.titleLarge?.copyWith(
          color: cs.onSurface,
          fontWeight: FontWeight.w700,
        ),
        iconTheme: IconThemeData(color: cs.onSurface, size: AppSpacing.iconMd),
        actionsIconTheme:
            IconThemeData(color: cs.onSurfaceVariant, size: AppSpacing.iconMd),
        systemOverlayStyle: cs.brightness == Brightness.light
            ? SystemUiOverlayStyle.dark
            : SystemUiOverlayStyle.light,
        shadowColor: cs.shadow.withValues(alpha: 0.08),
        surfaceTintColor: Colors.transparent,
      );

  static NavigationBarThemeData _navigationBarTheme(
          ColorScheme cs, TextTheme tt) =>
      NavigationBarThemeData(
        height: 68,
        backgroundColor: cs.surface,
        surfaceTintColor: Colors.transparent,
        shadowColor: cs.shadow.withValues(alpha: 0.06),
        elevation: 0,
        indicatorColor: cs.primary.withValues(alpha: 0.12),
        indicatorShape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(AppSpacing.radiusMd),
        ),
        labelTextStyle: WidgetStateProperty.resolveWith((states) {
          final base = tt.labelSmall?.copyWith(fontWeight: FontWeight.w600);
          if (states.contains(WidgetState.selected)) {
            return base?.copyWith(color: cs.primary);
          }
          return base?.copyWith(color: cs.onSurfaceVariant);
        }),
        iconTheme: WidgetStateProperty.resolveWith((states) {
          if (states.contains(WidgetState.selected)) {
            return IconThemeData(color: cs.primary, size: AppSpacing.iconMd);
          }
          return IconThemeData(
              color: cs.onSurfaceVariant, size: AppSpacing.iconMd);
        }),
        labelBehavior: NavigationDestinationLabelBehavior.alwaysShow,
      );

  static FilledButtonThemeData _filledButtonTheme(ColorScheme cs) =>
      FilledButtonThemeData(
        style: FilledButton.styleFrom(
          minimumSize: const Size.fromHeight(AppSpacing.buttonHeight),
          padding: const EdgeInsets.symmetric(
              horizontal: AppSpacing.buttonPaddingH,
              vertical: AppSpacing.sm + 2),
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(AppSpacing.radiusMd),
          ),
          textStyle: GoogleFonts.manrope(
            fontSize: 15,
            fontWeight: FontWeight.w600,
            letterSpacing: 0.1,
          ),
          elevation: 0,
        ),
      );

  static ElevatedButtonThemeData _elevatedButtonTheme(ColorScheme cs) =>
      ElevatedButtonThemeData(
        style: ElevatedButton.styleFrom(
          minimumSize: const Size.fromHeight(AppSpacing.buttonHeight),
          padding: const EdgeInsets.symmetric(
              horizontal: AppSpacing.buttonPaddingH,
              vertical: AppSpacing.sm + 2),
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(AppSpacing.radiusMd),
          ),
          elevation: 0,
          shadowColor: Colors.transparent,
          backgroundColor: cs.primaryContainer,
          foregroundColor: cs.onPrimaryContainer,
          textStyle: GoogleFonts.manrope(
            fontSize: 15,
            fontWeight: FontWeight.w600,
            letterSpacing: 0.1,
          ),
        ),
      );

  static OutlinedButtonThemeData _outlinedButtonTheme(ColorScheme cs) =>
      OutlinedButtonThemeData(
        style: OutlinedButton.styleFrom(
          minimumSize: const Size.fromHeight(AppSpacing.buttonHeight),
          padding: const EdgeInsets.symmetric(
              horizontal: AppSpacing.buttonPaddingH,
              vertical: AppSpacing.sm + 2),
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(AppSpacing.radiusMd),
          ),
          side: BorderSide(color: cs.outline),
          textStyle: GoogleFonts.manrope(
            fontSize: 15,
            fontWeight: FontWeight.w600,
            letterSpacing: 0.1,
          ),
        ),
      );

  static TextButtonThemeData _textButtonTheme(ColorScheme cs) =>
      TextButtonThemeData(
        style: TextButton.styleFrom(
          padding: const EdgeInsets.symmetric(
              horizontal: AppSpacing.md, vertical: AppSpacing.sm),
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(AppSpacing.radiusSm),
          ),
          textStyle: GoogleFonts.manrope(
            fontSize: 14,
            fontWeight: FontWeight.w600,
            letterSpacing: 0.1,
          ),
        ),
      );

  static InputDecorationTheme _inputDecorationTheme(
          ColorScheme cs, TextTheme tt) =>
      InputDecorationTheme(
        filled: true,
        fillColor: cs.surfaceContainerHighest.withValues(alpha: 0.6),
        contentPadding: const EdgeInsets.symmetric(
            horizontal: AppSpacing.lg, vertical: AppSpacing.md),
        border: OutlineInputBorder(
          borderRadius: BorderRadius.circular(AppSpacing.radiusMd),
          borderSide: BorderSide(color: cs.outline),
        ),
        enabledBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(AppSpacing.radiusMd),
          borderSide: BorderSide(color: cs.outlineVariant),
        ),
        focusedBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(AppSpacing.radiusMd),
          borderSide: BorderSide(color: cs.primary, width: 2),
        ),
        errorBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(AppSpacing.radiusMd),
          borderSide: BorderSide(color: cs.error),
        ),
        focusedErrorBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(AppSpacing.radiusMd),
          borderSide: BorderSide(color: cs.error, width: 2),
        ),
        labelStyle: tt.bodyMedium?.copyWith(color: cs.onSurfaceVariant),
        hintStyle:
            tt.bodyMedium?.copyWith(color: cs.onSurfaceVariant.withValues(alpha: 0.6)),
        errorStyle: tt.bodySmall?.copyWith(color: cs.error),
        floatingLabelStyle: tt.labelMedium?.copyWith(color: cs.primary),
        prefixIconColor: cs.onSurfaceVariant,
        suffixIconColor: cs.onSurfaceVariant,
      );

  static ChipThemeData _chipTheme(ColorScheme cs, TextTheme tt) => ChipThemeData(
        backgroundColor: cs.surfaceContainerHighest,
        selectedColor: cs.primaryContainer,
        labelStyle: tt.labelMedium?.copyWith(color: cs.onSurface),
        side: BorderSide(color: cs.outlineVariant),
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(AppSpacing.radiusSm),
        ),
        padding: const EdgeInsets.symmetric(
            horizontal: AppSpacing.sm, vertical: AppSpacing.xs),
        elevation: 0,
        pressElevation: 0,
      );

  static ListTileThemeData _listTileTheme(ColorScheme cs, TextTheme tt) =>
      ListTileThemeData(
        contentPadding: const EdgeInsets.symmetric(
            horizontal: AppSpacing.lg, vertical: AppSpacing.xs),
        titleTextStyle: tt.bodyLarge?.copyWith(color: cs.onSurface),
        subtitleTextStyle: tt.bodySmall?.copyWith(color: cs.onSurfaceVariant),
        leadingAndTrailingTextStyle: tt.labelSmall,
        iconColor: cs.onSurfaceVariant,
        tileColor: Colors.transparent,
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(AppSpacing.radiusMd),
        ),
        dense: false,
        minLeadingWidth: 24,
        minVerticalPadding: AppSpacing.sm,
      );

  static DividerThemeData _dividerTheme(ColorScheme cs) => DividerThemeData(
        color: cs.outlineVariant,
        thickness: 1,
        space: 1,
      );

  static SnackBarThemeData _snackBarTheme(ColorScheme cs, TextTheme tt) =>
      SnackBarThemeData(
        backgroundColor: cs.inverseSurface,
        contentTextStyle: tt.bodyMedium?.copyWith(color: cs.onInverseSurface),
        actionTextColor: cs.inversePrimary,
        behavior: SnackBarBehavior.floating,
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(AppSpacing.radiusMd),
        ),
        elevation: 4,
      );

  static DialogThemeData _dialogTheme(ColorScheme cs, TextTheme tt) =>
      DialogThemeData(
        backgroundColor: cs.surface,
        surfaceTintColor: Colors.transparent,
        elevation: 3,
        shadowColor: cs.shadow.withValues(alpha: 0.16),
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(AppSpacing.radiusXxl),
        ),
        titleTextStyle: tt.headlineSmall?.copyWith(color: cs.onSurface),
        contentTextStyle: tt.bodyMedium?.copyWith(color: cs.onSurfaceVariant),
      );

  static BottomSheetThemeData _bottomSheetTheme(ColorScheme cs) =>
      BottomSheetThemeData(
        backgroundColor: cs.surface,
        surfaceTintColor: Colors.transparent,
        elevation: 1,
        modalElevation: 2,
        shadowColor: cs.shadow.withValues(alpha: 0.12),
        shape: const RoundedRectangleBorder(
          borderRadius: BorderRadius.vertical(
            top: Radius.circular(AppSpacing.radiusXl),
          ),
        ),
        showDragHandle: true,
        dragHandleColor: cs.outlineVariant,
        dragHandleSize: const Size(32, 4),
        clipBehavior: Clip.antiAlias,
      );

  static FloatingActionButtonThemeData _fabTheme(ColorScheme cs) =>
      FloatingActionButtonThemeData(
        backgroundColor: cs.primary,
        foregroundColor: cs.onPrimary,
        elevation: 2,
        focusElevation: 4,
        hoverElevation: 3,
        highlightElevation: 4,
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(AppSpacing.radiusLg),
        ),
      );

  static SwitchThemeData _switchTheme(ColorScheme cs) => SwitchThemeData(
        thumbColor: WidgetStateProperty.resolveWith((states) {
          if (states.contains(WidgetState.selected)) return cs.onPrimary;
          return cs.onSurfaceVariant;
        }),
        trackColor: WidgetStateProperty.resolveWith((states) {
          if (states.contains(WidgetState.selected)) return cs.primary;
          return cs.surfaceContainerHighest;
        }),
        trackOutlineColor: WidgetStateProperty.resolveWith((states) {
          if (states.contains(WidgetState.selected)) {
            return Colors.transparent;
          }
          return cs.outline;
        }),
      );

  static PopupMenuThemeData _popupMenuTheme(ColorScheme cs, TextTheme tt) =>
      PopupMenuThemeData(
        color: cs.surface,
        surfaceTintColor: Colors.transparent,
        elevation: 3,
        shadowColor: cs.shadow.withValues(alpha: 0.12),
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(AppSpacing.radiusMd),
          side: BorderSide(color: cs.outlineVariant),
        ),
        textStyle: tt.bodyMedium?.copyWith(color: cs.onSurface),
        labelTextStyle: WidgetStateProperty.all(
          tt.bodyMedium?.copyWith(color: cs.onSurface),
        ),
      );

  // ── ThemeData builder ────────────────────────────────────────────────────

  static ThemeData _build(ColorScheme colorScheme) {
    final textTheme = _buildTextTheme(colorScheme);
    return ThemeData(
      useMaterial3: true,
      colorScheme: colorScheme,
      textTheme: textTheme,
      scaffoldBackgroundColor: colorScheme.brightness == Brightness.light
          ? const Color(0xFFF0F4F8)
          : const Color(0xFF080F1E),

      // Komponent temalari
      cardTheme: _cardTheme(colorScheme),
      appBarTheme: _appBarTheme(colorScheme, textTheme),
      navigationBarTheme: _navigationBarTheme(colorScheme, textTheme),
      filledButtonTheme: _filledButtonTheme(colorScheme),
      elevatedButtonTheme: _elevatedButtonTheme(colorScheme),
      outlinedButtonTheme: _outlinedButtonTheme(colorScheme),
      textButtonTheme: _textButtonTheme(colorScheme),
      inputDecorationTheme: _inputDecorationTheme(colorScheme, textTheme),
      chipTheme: _chipTheme(colorScheme, textTheme),
      listTileTheme: _listTileTheme(colorScheme, textTheme),
      dividerTheme: _dividerTheme(colorScheme),
      snackBarTheme: _snackBarTheme(colorScheme, textTheme),
      dialogTheme: _dialogTheme(colorScheme, textTheme),
      bottomSheetTheme: _bottomSheetTheme(colorScheme),
      floatingActionButtonTheme: _fabTheme(colorScheme),
      switchTheme: _switchTheme(colorScheme),
      popupMenuTheme: _popupMenuTheme(colorScheme, textTheme),

      // Icon tema
      iconTheme: IconThemeData(
          color: colorScheme.onSurfaceVariant, size: AppSpacing.iconMd),
      primaryIconTheme:
          IconThemeData(color: colorScheme.onPrimary, size: AppSpacing.iconMd),

      // Progress indicator
      progressIndicatorTheme: ProgressIndicatorThemeData(
        color: colorScheme.primary,
        linearTrackColor: colorScheme.surfaceContainerHighest,
        circularTrackColor: colorScheme.surfaceContainerHighest,
      ),

      // Tooltip
      tooltipTheme: TooltipThemeData(
        decoration: BoxDecoration(
          color: colorScheme.inverseSurface,
          borderRadius: BorderRadius.circular(AppSpacing.radiusSm),
        ),
        textStyle: textTheme.labelSmall
            ?.copyWith(color: colorScheme.onInverseSurface),
      ),

      // Splash / Highlight (Material ink)
      splashColor: colorScheme.primary.withValues(alpha: 0.08),
      highlightColor: colorScheme.primary.withValues(alpha: 0.04),
    );
  }

  // ── Public API ────────────────────────────────────────────────────────────

  /// Yorug' tema (default)
  static ThemeData get light => _build(_lightColorScheme);

  /// Qorong'i tema
  static ThemeData get dark => _build(_darkColorScheme);

  // ── Semantik rang yordamchilari ───────────────────────────────────────────

  /// success, warning, danger, info ranglarini statik usulda olish.
  /// (MaterialApp context talab etadi — ColorsOf orqali ishlatish afzal)
  static Color successColor(bool isDark) =>
      isDark ? _successDark : _successLight;
  static Color warningColor(bool isDark) =>
      isDark ? _warningDark : _warningLight;
  static Color dangerColor(bool isDark) => isDark ? _dangerDark : _dangerLight;
  static Color infoColor(bool isDark) => isDark ? _infoDark : _infoLight;
}

/// Semantik ranglar to'plami — ixtiyoriy widget shu class orqali
/// success/warning/danger/info ranglarini oladi.
class AppColors {
  const AppColors.light()
      : success = const Color(0xFF15803D),
        onSuccess = Colors.white,
        successContainer = const Color(0xFFDCFCE7),
        warning = const Color(0xFFD97706),
        onWarning = Colors.white,
        warningContainer = const Color(0xFFFEF3C7),
        danger = const Color(0xFFDC2626),
        onDanger = Colors.white,
        dangerContainer = const Color(0xFFFEE2E2),
        info = const Color(0xFF0369A1),
        onInfo = Colors.white,
        infoContainer = const Color(0xFFE0F2FE);

  const AppColors.dark()
      : success = const Color(0xFF4ADE80),
        onSuccess = const Color(0xFF052E16),
        successContainer = const Color(0xFF14532D),
        warning = const Color(0xFFFBBF24),
        onWarning = const Color(0xFF451A03),
        warningContainer = const Color(0xFF78350F),
        danger = const Color(0xFFF87171),
        onDanger = const Color(0xFF450A0A),
        dangerContainer = const Color(0xFF7F1D1D),
        info = const Color(0xFF38BDF8),
        onInfo = const Color(0xFF082F49),
        infoContainer = const Color(0xFF0C4A6E);

  final Color success;
  final Color onSuccess;
  final Color successContainer;
  final Color warning;
  final Color onWarning;
  final Color warningContainer;
  final Color danger;
  final Color onDanger;
  final Color dangerContainer;
  final Color info;
  final Color onInfo;
  final Color infoContainer;
}
