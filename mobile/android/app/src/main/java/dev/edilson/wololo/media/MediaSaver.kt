package dev.edilson.wololo.media

import android.content.ContentValues
import android.content.Context
import android.net.Uri
import android.os.Build
import android.os.Environment
import android.provider.MediaStore
import java.io.File
import java.io.IOException
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.currentCoroutineContext
import kotlinx.coroutines.ensureActive
import kotlinx.coroutines.withContext
import okhttp3.ResponseBody

class MediaSaver(private val context: Context) {
    fun create(title: String, audio: Boolean, id: String): Uri {
        val folder = if (audio) Environment.DIRECTORY_MUSIC else Environment.DIRECTORY_MOVIES
        val extension = if (audio) ".mp3" else ".mp4"
        val name = title.removeSuffix(extension).replace(Regex("[\\p{Cntrl}/\\\\:*?\"<>|]"), "_")
            .trim().trimStart('.').take(160).ifBlank { "Wololo" } + "-${id.take(8)}" + extension
        val values = ContentValues().apply {
            put(MediaStore.MediaColumns.DISPLAY_NAME, name)
            put(MediaStore.MediaColumns.MIME_TYPE, if (audio) "audio/mpeg" else "video/mp4")
            if (Build.VERSION.SDK_INT >= 29) {
                put(MediaStore.MediaColumns.RELATIVE_PATH, "$folder/Wololo")
                put(MediaStore.MediaColumns.IS_PENDING, 1)
            } else {
                @Suppress("DEPRECATION")
                val directory = File(Environment.getExternalStoragePublicDirectory(folder), "Wololo")
                if (!directory.isDirectory && !directory.mkdirs()) throw IOException("Could not create the media folder.")
                @Suppress("DEPRECATION")
                put(MediaStore.MediaColumns.DATA, File(directory, name).absolutePath)
            }
        }
        val collection = if (audio) MediaStore.Audio.Media.EXTERNAL_CONTENT_URI else MediaStore.Video.Media.EXTERNAL_CONTENT_URI
        return context.contentResolver.insert(collection, values) ?: throw IOException("Could not create the media file.")
    }

    suspend fun write(uri: Uri, body: ResponseBody) = withContext(Dispatchers.IO) {
        val coroutine = currentCoroutineContext()
        val output = context.contentResolver.openOutputStream(uri, "w") ?: throw IOException("Could not open the media file.")
        var bytesWritten = 0L
        output.use { destination ->
            body.byteStream().use { source ->
                val buffer = ByteArray(64 * 1024)
                var count: Int
                while (source.read(buffer).also { count = it } >= 0) {
                    coroutine.ensureActive()
                    destination.write(buffer, 0, count)
                    bytesWritten += count
                }
            }
        }
        coroutine.ensureActive()
        if (bytesWritten == 0L) throw IOException("The server returned an empty file.")
        val values = ContentValues().apply {
            put(MediaStore.MediaColumns.SIZE, bytesWritten)
            if (Build.VERSION.SDK_INT >= 29) put(MediaStore.MediaColumns.IS_PENDING, 0)
        }
        context.contentResolver.update(uri, values, null, null)
    }

    fun remove(uri: String) { context.contentResolver.delete(Uri.parse(uri), null, null) }
}
