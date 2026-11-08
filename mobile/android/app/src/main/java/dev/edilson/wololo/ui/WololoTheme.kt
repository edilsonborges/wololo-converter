package dev.edilson.wololo.ui

import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color

@Composable
fun WololoTheme(content: @Composable () -> Unit) {
    val colors = if (isSystemInDarkTheme()) darkColorScheme(
        primary = Color(0xFFA0D9C0), secondary = Color(0xFFB5CCBF),
        secondaryContainer = Color(0xFF314D41), onSecondaryContainer = Color(0xFFD8F1E3),
    ) else lightColorScheme(
        primary = Color(0xFF176B52), secondary = Color(0xFF53665C),
        secondaryContainer = Color(0xFFD8EADF), onSecondaryContainer = Color(0xFF153D2D),
        background = Color(0xFFFAFBF7), surface = Color(0xFFFAFBF7),
    )
    MaterialTheme(colorScheme = colors, content = content)
}
