package dev.edilson.wololo

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import dev.edilson.wololo.ui.WololoScreen
import dev.edilson.wololo.ui.WololoTheme

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        val repository = (application as WololoApplication).repository
        setContent { WololoTheme { WololoScreen(repository) } }
    }
}
