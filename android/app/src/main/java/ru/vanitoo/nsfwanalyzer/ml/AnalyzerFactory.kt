package ru.vanitoo.nsfwanalyzer.ml

import android.content.Context
import android.net.Uri

object AnalyzerFactory {
    const val NSFW_MODEL = "nsfw.onnx"
    const val GENERAL_MODEL = "general.onnx"

    fun create(context: Context): ImageAnalyzer {
        val hasNsfw = ModelAssets.exists(context, NSFW_MODEL)
        val hasGeneral = ModelAssets.exists(context, GENERAL_MODEL)

        return if (hasNsfw || hasGeneral) {
            PendingOnnxAnalyzer(hasNsfw, hasGeneral)
        } else {
            NoOpAnalyzer()
        }
    }
}

private class PendingOnnxAnalyzer(
    private val hasNsfw: Boolean,
    private val hasGeneral: Boolean
) : ImageAnalyzer {
    override val modelVersion: String =
        "onnx-pending:" + listOfNotNull(
            "nsfw".takeIf { hasNsfw },
            "general".takeIf { hasGeneral }
        ).joinToString("+")

    override suspend fun analyze(context: Context, uri: Uri): AnalysisResult =
        AnalysisResult(
            category = "ONNX подключён",
            subcategory = "нужен адаптер конкретной модели",
            tags = listOfNotNull(
                "nsfw-model".takeIf { hasNsfw },
                "general-model".takeIf { hasGeneral }
            )
        )
}
