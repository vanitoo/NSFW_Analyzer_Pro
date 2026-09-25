package ru.vanitoo.nsfwanalyzer.ml

import android.content.Context

object AnalyzerFactory {
    const val NSFW_MODEL = "nsfw.onnx"
    const val GENERAL_MODEL = "general.onnx"

    fun create(context: Context): ImageAnalyzer {
        return when {
            ModelAssets.exists(context, NSFW_MODEL) -> NsfwOnnxAnalyzer(context)
            else -> NoOpAnalyzer()
        }
    }
}
