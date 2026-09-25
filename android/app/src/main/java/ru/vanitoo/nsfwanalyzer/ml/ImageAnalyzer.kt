package ru.vanitoo.nsfwanalyzer.ml

import android.content.Context
import android.net.Uri

interface ImageAnalyzer : AutoCloseable {
    val modelVersion: String
    suspend fun analyze(context: Context, uri: Uri): AnalysisResult
    override fun close() = Unit
}
