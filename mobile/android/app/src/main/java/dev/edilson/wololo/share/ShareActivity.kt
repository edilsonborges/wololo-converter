package dev.edilson.wololo.share

import android.content.Intent
import android.os.Bundle
import android.widget.Toast
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import dev.edilson.wololo.R
import dev.edilson.wololo.WololoApplication
import dev.edilson.wololo.ui.DownloadForm
import dev.edilson.wololo.ui.WololoTheme

class ShareActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val text = if (intent.action == Intent.ACTION_SEND) intent.getCharSequenceExtra(Intent.EXTRA_TEXT)?.toString().orEmpty() else ""
        val repository = (application as WololoApplication).repository
        setContent {
            WololoTheme {
                Box(Modifier.fillMaxSize(), contentAlignment = Alignment.BottomCenter) {
                    Surface(shape = MaterialTheme.shapes.extraLarge) {
                        Column(Modifier.navigationBarsPadding().padding(24.dp).verticalScroll(rememberScrollState()), verticalArrangement = Arrangement.spacedBy(16.dp)) {
                            Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
                                Text(stringResource(R.string.shared_link), Modifier.weight(1f), style = MaterialTheme.typography.headlineSmall)
                                TextButton(onClick = { finish() }) { Text(stringResource(R.string.close)) }
                            }
                            DownloadForm(repository, initialText = text, onEnqueued = {
                                Toast.makeText(this@ShareActivity, R.string.queued_message, Toast.LENGTH_SHORT).show()
                                finish()
                            })
                            Text(stringResource(R.string.share_hint), style = MaterialTheme.typography.bodySmall)
                        }
                    }
                }
            }
        }
    }
}
