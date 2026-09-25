package ru.vanitoo.nsfwanalyzer.ml

import android.content.Context
import android.net.Uri

class NoOpAnalyzer : ImageAnalyzer {
    override val modelVersion: String = "no-model"

    override suspend fun analyze(context: Context, uri: Uri): AnalysisResult =
        AnalysisResult(
            category = "Не анализировано",
            tags = listOf("model-missing")
        )
}
