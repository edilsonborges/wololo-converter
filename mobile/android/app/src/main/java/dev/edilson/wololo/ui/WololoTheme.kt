package dev.edilson.wololo.ui

import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color

@Composable
fun WololoTheme(content: @Composable () -> Unit) {
    val ink = Color(0xFF1A1A1A)
    val secondary = Color(0xFF4A4A4A)
    val subtle = Color(0xFFF5F5F5)
    val colors = lightColorScheme(
        primary = ink, onPrimary = Color.White,
        primaryContainer = subtle, onPrimaryContainer = ink,
        secondary = secondary, onSecondary = Color.White,
        secondaryContainer = subtle, onSecondaryContainer = ink,
        tertiary = secondary, onTertiary = Color.White,
        tertiaryContainer = subtle, onTertiaryContainer = ink,
        background = Color.White, onBackground = ink,
        surface = Color.White, onSurface = ink,
        surfaceVariant = Color(0xFFFAFAFA), onSurfaceVariant = secondary,
        surfaceTint = Color.Transparent,
        surfaceBright = Color.White, surfaceDim = Color(0xFFFAFAFA),
        surfaceContainer = Color(0xFFFAFAFA), surfaceContainerLow = Color.White,
        surfaceContainerLowest = Color.White, surfaceContainerHigh = subtle,
        surfaceContainerHighest = subtle,
        outline = Color(0xFFE5E5E5), outlineVariant = Color(0xFFE5E5E5),
        inverseSurface = ink, inverseOnSurface = Color.White, inversePrimary = Color.White,
        error = ink, onError = Color.White, errorContainer = subtle, onErrorContainer = ink,
        scrim = Color.Black,
    )
    MaterialTheme(colorScheme = colors, content = content)
}
