package dev.edilson.wololo.worker

import android.Manifest
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.content.pm.ServiceInfo
import android.net.Uri
import android.os.Build
import androidx.core.app.NotificationCompat
import androidx.core.app.NotificationManagerCompat
import androidx.core.content.ContextCompat
import androidx.work.ForegroundInfo
import dev.edilson.wololo.MainActivity
import dev.edilson.wololo.R
import dev.edilson.wololo.model.DownloadRecord

class DownloadNotifications(private val context: Context, private val id: String) {
    private val channel = "downloads"
    private val notificationId = id.hashCode()

    init {
        context.getSystemService(NotificationManager::class.java).createNotificationChannel(
            NotificationChannel(channel, context.getString(R.string.downloads), NotificationManager.IMPORTANCE_LOW),
        )
    }

    fun foreground(title: String, progress: Int): ForegroundInfo {
        val cancel = Intent(context, CancelDownloadReceiver::class.java).putExtra("record_id", id)
        val action = PendingIntent.getBroadcast(context, notificationId, cancel, PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT)
        val notification = builder(title)
            .setContentText(context.getString(R.string.downloading))
            .setOngoing(true)
            .setOnlyAlertOnce(true)
            .setProgress(100, progress.coerceIn(0, 100), progress <= 0)
            .addAction(0, context.getString(R.string.cancel), action)
            .build()
        return if (Build.VERSION.SDK_INT >= 29) ForegroundInfo(notificationId, notification, ServiceInfo.FOREGROUND_SERVICE_TYPE_DATA_SYNC)
        else ForegroundInfo(notificationId, notification)
    }

    fun finish(record: DownloadRecord) {
        if (Build.VERSION.SDK_INT >= 33 && ContextCompat.checkSelfPermission(context, Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED) return
        val notification = builder(record.title.ifBlank { context.getString(R.string.app_name) })
            .setContentText(if (record.status == "completed" && record.fileUri != null) context.getString(R.string.saved) else record.error ?: context.getString(R.string.download_failed))
            .setAutoCancel(true)
        record.fileUri?.let { value ->
            val intent = Intent(Intent.ACTION_VIEW).setDataAndType(Uri.parse(value), if (record.isAudio) "audio/mpeg" else "video/mp4")
                .addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION or Intent.FLAG_ACTIVITY_NEW_TASK)
            if (intent.resolveActivity(context.packageManager) != null) {
                notification.setContentIntent(PendingIntent.getActivity(context, notificationId, intent, PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT))
            }
        }
        NotificationManagerCompat.from(context).notify(notificationId xor 0x40000000, notification.build())
    }

    private fun builder(title: String): NotificationCompat.Builder {
        val open = PendingIntent.getActivity(context, notificationId, Intent(context, MainActivity::class.java), PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT)
        return NotificationCompat.Builder(context, channel)
            .setSmallIcon(R.drawable.ic_download)
            .setContentTitle(title)
            .setContentIntent(open)
    }
}
