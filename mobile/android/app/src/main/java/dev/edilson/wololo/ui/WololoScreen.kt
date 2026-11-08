package dev.edilson.wololo.ui

import android.content.ActivityNotFoundException
import android.content.Intent
import android.net.Uri
import android.widget.Toast
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import dev.edilson.wololo.R
import dev.edilson.wololo.model.DownloadRecord
import dev.edilson.wololo.storage.DownloadRepository
import kotlinx.coroutines.launch

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun WololoScreen(repository: DownloadRepository) {
    var showSettings by rememberSaveable { mutableStateOf(false) }
    val records by repository.history.collectAsStateWithLifecycle()
    val scope = rememberCoroutineScope()
    val context = LocalContext.current
    Scaffold(topBar = {
        TopAppBar(title = { Text(stringResource(if (showSettings) R.string.settings else R.string.app_name)) }, actions = {
            TextButton(onClick = { showSettings = !showSettings }) {
                Text(stringResource(if (showSettings) R.string.close else R.string.settings))
            }
        })
    }) { insets ->
        if (showSettings) SettingsScreen(repository, Modifier.padding(insets))
        else LazyColumn(Modifier.fillMaxSize().padding(insets), contentPadding = PaddingValues(24.dp), verticalArrangement = Arrangement.spacedBy(24.dp)) {
            item { Text(stringResource(R.string.save_media), style = MaterialTheme.typography.headlineLarge) }
            item { DownloadForm(repository, onEnqueued = { Toast.makeText(context, R.string.queued_message, Toast.LENGTH_SHORT).show() }) }
            item { Text(stringResource(R.string.use_responsibly), style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant) }
            item { HorizontalDivider(); Spacer(Modifier.height(24.dp)); Text(stringResource(R.string.history), style = MaterialTheme.typography.titleLarge) }
            if (records.isEmpty()) item { Text(stringResource(R.string.empty_history), color = MaterialTheme.colorScheme.onSurfaceVariant) }
            items(records, key = { it.id }) { record ->
                DownloadRow(record, onCancel = { scope.launch { repository.cancel(record.id) } }, onRetry = {
                    scope.launch {
                        try { repository.enqueue(record.url, record.quality, record.server) }
                        catch (error: Exception) { Toast.makeText(context, error.message, Toast.LENGTH_LONG).show() }
                    }
                })
            }
        }
    }
}

@Composable
private fun DownloadRow(record: DownloadRecord, onCancel: () -> Unit, onRetry: () -> Unit) {
    val context = LocalContext.current
    val state = when (record.status) {
        "queued" -> R.string.queued
        "validating" -> R.string.validating
        "downloading" -> R.string.downloading
        "converting" -> R.string.converting
        "finalizing" -> R.string.finalizing
        "saving" -> R.string.saving
        "completed" -> R.string.completed
        "cancelled" -> R.string.cancelled
        else -> R.string.failed
    }
    Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
        Text(record.title.ifBlank { Uri.parse(record.url).host.orEmpty() }, style = MaterialTheme.typography.titleMedium, maxLines = 2)
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
            Text(stringResource(state), color = MaterialTheme.colorScheme.onSurfaceVariant)
            Text(if (record.isAudio) stringResource(R.string.audio) else record.quality)
        }
        if (!record.isTerminal) {
            LinearProgressIndicator(progress = { (record.progress / 100f).coerceIn(0f, 1f) }, modifier = Modifier.fillMaxWidth())
            TextButton(onClick = onCancel) { Text(stringResource(R.string.cancel)) }
        } else {
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                record.fileUri?.let { uri ->
                    TextButton(onClick = {
                        try {
                            context.startActivity(Intent(Intent.ACTION_VIEW).setDataAndType(Uri.parse(uri), if (record.isAudio) "audio/mpeg" else "video/mp4")
                                .addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION))
                        } catch (_: ActivityNotFoundException) { Toast.makeText(context, R.string.no_player, Toast.LENGTH_LONG).show() }
                    }) { Text(stringResource(R.string.open)) }
                }
                TextButton(onClick = onRetry) { Text(stringResource(R.string.try_again)) }
                record.completedAt?.let { time -> Text(stringResource(R.string.duration, (time - record.createdAt).coerceAtLeast(0) / 1000), Modifier.padding(top = 12.dp)) }
            }
        }
        record.error?.let { Text(it, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant) }
        HorizontalDivider()
    }
}
