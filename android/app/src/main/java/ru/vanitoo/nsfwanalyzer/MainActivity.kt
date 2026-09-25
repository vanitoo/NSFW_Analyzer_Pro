package ru.vanitoo.nsfwanalyzer

import android.Manifest
import android.os.Build
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.result.contract.ActivityResultContracts
import androidx.activity.viewModels
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.weight
import androidx.compose.material3.Button
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp

class MainActivity : ComponentActivity() {
    private val viewModel: GalleryViewModel by viewModels()

    private val permissionLauncher = registerForActivityResult(
        ActivityResultContracts.RequestPermission()
    ) { granted ->
        if (granted) viewModel.refreshGalleryCount()
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        if (hasGalleryPermission()) {
            viewModel.refreshGalleryCount()
        }

        setContent {
            val state by viewModel.state.collectAsState()

            MaterialTheme {
                Surface(modifier = Modifier.fillMaxSize()) {
                    Column(
                        modifier = Modifier
                            .fillMaxSize()
                            .padding(20.dp),
                        verticalArrangement = Arrangement.spacedBy(12.dp)
                    ) {
                        Text(
                            text = "AI Gallery Analyzer",
                            style = MaterialTheme.typography.headlineMedium
                        )
                        Text("Локальный анализ галереи. Фото никуда не отправляются.")

                        StatRow("Фото в галерее", state.galleryCount.toString())
                        StatRow("Проанализировано", state.analyzedCount.toString())
                        StatRow("NSFW ≥ 0.70", state.nsfwCount.toString())

                        Spacer(Modifier.height(4.dp))
                        Text(
                            if (state.nsfwModelPresent)
                                "NSFW model: готова"
                            else
                                "NSFW model: не установлена"
                        )
                        Text(
                            if (state.generalModelPresent)
                                "General model: готова"
                            else
                                "General model: не установлена"
                        )

                        if (state.running || state.total > 0) {
                            val progress = if (state.total > 0) {
                                state.current.toFloat() / state.total.toFloat()
                            } else {
                                0f
                            }
                            LinearProgressIndicator(
                                progress = { progress.coerceIn(0f, 1f) },
                                modifier = Modifier.fillMaxWidth()
                            )
                            Text(state.current.toString() + " / " + state.total.toString())
                            if (state.currentFile.isNotBlank()) {
                                Text(
                                    state.currentFile,
                                    style = MaterialTheme.typography.bodySmall
                                )
                            }
                        }

                        if (state.message.isNotBlank()) {
                            Text(state.message)
                        }

                        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                            Button(
                                onClick = {
                                    if (hasGalleryPermission()) {
                                        viewModel.refreshGalleryCount()
                                        viewModel.startAnalysis()
                                    } else {
                                        permissionLauncher.launch(requiredPermission())
                                    }
                                },
                                enabled = !state.running
                            ) {
                                Text("Анализировать галерею")
                            }

                            if (state.running) {
                                OutlinedButton(onClick = viewModel::cancelAnalysis) {
                                    Text("Стоп")
                                }
                            }
                        }

                        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                            OutlinedButton(
                                onClick = {
                                    if (hasGalleryPermission()) {
                                        viewModel.refreshGalleryCount()
                                    } else {
                                        permissionLauncher.launch(requiredPermission())
                                    }
                                }
                            ) {
                                Text("Обновить галерею")
                            }

                            OutlinedButton(onClick = viewModel::clearCache) {
                                Text("Очистить кэш")
                            }
                        }

                        Spacer(Modifier.weight(1f))
                        Text(
                            "MVP: MediaStore + Room + WorkManager + ONNX Runtime",
                            style = MaterialTheme.typography.bodySmall
                        )
                    }
                }
            }
        }
    }

    private fun requiredPermission(): String =
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            Manifest.permission.READ_MEDIA_IMAGES
        } else {
            Manifest.permission.READ_EXTERNAL_STORAGE
        }

    private fun hasGalleryPermission(): Boolean =
        checkSelfPermission(requiredPermission()) ==
            android.content.pm.PackageManager.PERMISSION_GRANTED
}

@Composable
private fun StatRow(label: String, value: String) {
    Row(
        modifier = Modifier.fillMaxWidth(),
        horizontalArrangement = Arrangement.SpaceBetween
    ) {
        Text(label)
        Text(value, style = MaterialTheme.typography.titleMedium)
    }
}
