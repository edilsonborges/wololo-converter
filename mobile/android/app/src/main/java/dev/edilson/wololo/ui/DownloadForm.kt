package dev.edilson.wololo.ui

import android.Manifest
import android.content.ClipboardManager
import android.content.Context
import android.content.pm.PackageManager
import android.os.Build
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import androidx.core.content.ContextCompat
import dev.edilson.wololo.R
import dev.edilson.wololo.links.LinkParser
import dev.edilson.wololo.storage.DownloadRepository
import kotlinx.coroutines.launch

@Composable
fun DownloadForm(repository: DownloadRepository, initialText: String = "", onEnqueued: () -> Unit = {}) {
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    var text by rememberSaveable { mutableStateOf(initialText) }
    var quality by rememberSaveable { mutableStateOf("720p") }
    var videoQuality by rememberSaveable { mutableStateOf("720p") }
    var error by remember { mutableStateOf<String?>(null) }
    var busy by remember { mutableStateOf(false) }
    LaunchedEffect(repository) {
        val settings = repository.currentSettings()
        quality = settings.quality
        videoQuality = settings.videoQuality
    }
    val enqueue: () -> Unit = {
        scope.launch {
            busy = true
            error = null
            try {
                repository.rememberQuality(quality)
                repository.enqueue(text, quality)
                text = ""
                onEnqueued()
            } catch (failure: Exception) {
                error = failure.message
            } finally { busy = false }
        }
    }
    val permissions = rememberLauncherForActivityResult(ActivityResultContracts.RequestMultiplePermissions()) { granted ->
        if (Build.VERSION.SDK_INT <= 28 && granted[Manifest.permission.WRITE_EXTERNAL_STORAGE] != true) {
            error = context.getString(R.string.storage_required)
        } else enqueue()
    }
    val begin: () -> Unit = {
        if (LinkParser.first(text) == null) error = context.getString(R.string.link_required)
        else {
            val missing = buildList {
                if (Build.VERSION.SDK_INT <= 28 && ContextCompat.checkSelfPermission(context, Manifest.permission.WRITE_EXTERNAL_STORAGE) != PackageManager.PERMISSION_GRANTED) add(Manifest.permission.WRITE_EXTERNAL_STORAGE)
                if (Build.VERSION.SDK_INT >= 33 && ContextCompat.checkSelfPermission(context, Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED) add(Manifest.permission.POST_NOTIFICATIONS)
            }
            if (missing.isEmpty()) enqueue() else permissions.launch(missing.toTypedArray())
        }
    }

    Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
        OutlinedTextField(text, onValueChange = { text = it; error = null }, modifier = Modifier.fillMaxWidth(),
            label = { Text(stringResource(R.string.paste_link)) }, minLines = 2, maxLines = 4,
            trailingIcon = { TextButton(onClick = {
                val clipboard = context.getSystemService(Context.CLIPBOARD_SERVICE) as ClipboardManager
                val pasted = clipboard.primaryClip?.getItemAt(0)?.coerceToText(context)?.toString()
                if (pasted.isNullOrBlank()) error = context.getString(R.string.clipboard_empty) else text = pasted
            }) { Text(stringResource(R.string.paste)) } })
        Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
            FilterChip(selected = quality != "mp3", onClick = { quality = videoQuality }, label = { Text(stringResource(R.string.video)) })
            FilterChip(selected = quality == "mp3", onClick = { quality = "mp3" }, label = { Text(stringResource(R.string.audio)) })
        }
        if (quality != "mp3") QualityChoices(quality) { videoQuality = it; quality = it }
        error?.let { Text(it, color = MaterialTheme.colorScheme.error, style = MaterialTheme.typography.bodyMedium) }
        Button(onClick = begin, enabled = !busy && text.isNotBlank(), modifier = Modifier.fillMaxWidth().heightIn(min = 52.dp)) {
            Text(stringResource(if (busy) R.string.enqueueing else if (quality == "mp3") R.string.save_audio else R.string.save_video))
        }
    }
}

@Composable
fun QualityChoices(selected: String, onSelect: (String) -> Unit) {
    Row(Modifier.fillMaxWidth().horizontalScroll(rememberScrollState()), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
        for (quality in listOf("360p", "480p", "720p", "1080p")) {
            FilterChip(selected = selected == quality, onClick = { onSelect(quality) }, label = { Text(quality) })
        }
    }
}
