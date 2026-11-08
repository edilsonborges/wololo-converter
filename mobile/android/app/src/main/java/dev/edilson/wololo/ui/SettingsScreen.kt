package dev.edilson.wololo.ui

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.unit.dp
import dev.edilson.wololo.BuildConfig
import dev.edilson.wololo.R
import dev.edilson.wololo.api.WololoApi
import dev.edilson.wololo.model.isNewerVersion
import dev.edilson.wololo.storage.DownloadRepository
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

@Composable
fun SettingsScreen(repository: DownloadRepository, modifier: Modifier = Modifier) {
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    var server by remember { mutableStateOf("") }
    var key by remember { mutableStateOf("") }
    var quality by remember { mutableStateOf("720p") }
    var videoQuality by remember { mutableStateOf("720p") }
    var message by remember { mutableStateOf<String?>(null) }
    var busy by remember { mutableStateOf(false) }
    LaunchedEffect(repository) {
        val settings = repository.currentSettings()
        server = settings.server
        quality = settings.quality
        videoQuality = settings.videoQuality
        runCatching { withContext(Dispatchers.IO) { repository.credentials.read(server) } }
            .onSuccess { key = it }.onFailure { message = it.message }
    }
    Column(modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(24.dp), verticalArrangement = Arrangement.spacedBy(20.dp)) {
        OutlinedTextField(server, onValueChange = { server = it; key = "" }, modifier = Modifier.fillMaxWidth(), singleLine = true,
            label = { Text(stringResource(R.string.server)) }, placeholder = { Text(stringResource(R.string.server_hint)) },
            keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Uri))
        OutlinedTextField(key, onValueChange = { key = it }, modifier = Modifier.fillMaxWidth(), singleLine = true,
            label = { Text(stringResource(R.string.access_key)) }, supportingText = { Text(stringResource(R.string.access_key_hint)) },
            visualTransformation = PasswordVisualTransformation(), keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Password))
        Text(stringResource(R.string.format), style = MaterialTheme.typography.titleMedium)
        Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
            FilterChip(quality != "mp3", onClick = { quality = videoQuality }, label = { Text(stringResource(R.string.video)) })
            FilterChip(quality == "mp3", onClick = { quality = "mp3" }, label = { Text(stringResource(R.string.audio)) })
        }
        if (quality != "mp3") QualityChoices(quality) { quality = it; videoQuality = it }
        Button(onClick = {
            scope.launch {
                busy = true
                try {
                    withContext(Dispatchers.IO) { repository.saveSettings(server, key, quality) }
                    message = context.getString(R.string.settings_saved)
                } catch (error: Exception) { message = error.message }
                finally { busy = false }
            }
        }, enabled = !busy, shape = MaterialTheme.shapes.small, modifier = Modifier.fillMaxWidth()) { Text(stringResource(R.string.save_settings)) }
        OutlinedButton(onClick = {
            scope.launch {
                busy = true
                message = context.getString(R.string.testing)
                try {
                    val health = WololoApi(server, key).health()
                    message = if (health.minAppVersion?.let { isNewerVersion(it, BuildConfig.VERSION_NAME) } == true)
                        context.getString(R.string.update_required) else context.getString(R.string.connected, health.version)
                } catch (error: Exception) { message = error.message }
                finally { busy = false }
            }
        }, enabled = !busy, shape = MaterialTheme.shapes.small, modifier = Modifier.fillMaxWidth()) { Text(stringResource(R.string.test_connection)) }
        message?.let { Text(it, style = MaterialTheme.typography.bodyMedium) }
        Text(stringResource(R.string.private_history), style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
        Text(stringResource(R.string.version, BuildConfig.VERSION_NAME), style = MaterialTheme.typography.labelMedium)
    }
}
