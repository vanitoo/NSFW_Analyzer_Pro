package ru.vanitoo.nsfwanalyzer.ml

import ai.onnxruntime.OnnxTensor
import ai.onnxruntime.OrtEnvironment
import ai.onnxruntime.OrtSession
import android.content.Context
import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.graphics.Color
import android.net.Uri
import java.nio.FloatBuffer
import kotlin.math.exp
import kotlin.math.max
import kotlin.math.roundToInt

class NsfwOnnxAnalyzer(context: Context) : ImageAnalyzer {
    override val modelVersion: String = "mobilenetv4-nsfw-r224-v1"

    private val environment: OrtEnvironment
    private val session: OrtSession
    private val inputName: String

    init {
        val runtime = OnnxRuntimeFactory.createSession(context, AnalyzerFactory.NSFW_MODEL)
        environment = runtime.first
        session = runtime.second
        inputName = session.inputNames.first()
    }

    override suspend fun analyze(context: Context, uri: Uri): AnalysisResult {
        val bitmap = context.contentResolver.openInputStream(uri).use { stream ->
            requireNotNull(stream) { "Не удалось открыть изображение" }
            BitmapFactory.decodeStream(stream)
        } ?: error("Не удалось декодировать изображение")

        val input = preprocess(bitmap)
        bitmap.recycle()

        OnnxTensor.createTensor(
            environment,
            FloatBuffer.wrap(input),
            longArrayOf(1, 3, INPUT_SIZE.toLong(), INPUT_SIZE.toLong())
        ).use { tensor ->
            session.run(mapOf(inputName to tensor)).use { result ->
                val logits = flattenOutput(result[0].value)
                val probabilities = softmax(logits)

                val bestIndex = probabilities.indices.maxByOrNull { probabilities[it] } ?: 2
                val nsfwScore = listOf(1, 3, 4)
                    .filter { it < probabilities.size }
                    .sumOf { probabilities[it].toDouble() }
                    .toFloat()
                    .coerceIn(0f, 1f)

                val tags = LABELS.indices
                    .filter { it < probabilities.size }
                    .sortedByDescending { probabilities[it] }
                    .take(3)
                    .map { LABELS[it] + " " + "%.1f%%".format(probabilities[it] * 100f) }

                return AnalysisResult(
                    nsfwScore = nsfwScore,
                    category = if (nsfwScore >= 0.70f) "NSFW" else "SFW",
                    subcategory = LABELS.getOrElse(bestIndex) { "unknown" },
                    tags = tags
                )
            }
        }
    }

    private fun preprocess(source: Bitmap): FloatArray {
        val shortest = minOf(source.width, source.height).coerceAtLeast(1)
        val scale = RESIZE_SIZE.toFloat() / shortest.toFloat()
        val targetWidth = max(INPUT_SIZE, (source.width * scale).roundToInt())
        val targetHeight = max(INPUT_SIZE, (source.height * scale).roundToInt())

        val resized = Bitmap.createScaledBitmap(source, targetWidth, targetHeight, true)
        val left = ((targetWidth - INPUT_SIZE) / 2).coerceAtLeast(0)
        val top = ((targetHeight - INPUT_SIZE) / 2).coerceAtLeast(0)
        val crop = Bitmap.createBitmap(resized, left, top, INPUT_SIZE, INPUT_SIZE)
        if (resized !== source && resized !== crop) resized.recycle()

        val pixels = IntArray(INPUT_SIZE * INPUT_SIZE)
        crop.getPixels(pixels, 0, INPUT_SIZE, 0, 0, INPUT_SIZE, INPUT_SIZE)
        crop.recycle()

        val plane = INPUT_SIZE * INPUT_SIZE
        val data = FloatArray(plane * 3)
        for (index in pixels.indices) {
            val color = pixels[index]
            val r = Color.red(color) / 255f
            val g = Color.green(color) / 255f
            val b = Color.blue(color) / 255f
            data[index] = (r - MEAN[0]) / STD[0]
            data[plane + index] = (g - MEAN[1]) / STD[1]
            data[2 * plane + index] = (b - MEAN[2]) / STD[2]
        }
        return data
    }

    private fun flattenOutput(value: Any?): FloatArray = when (value) {
        is FloatArray -> value
        is Array<*> -> {
            val first = value.firstOrNull()
            when (first) {
                is FloatArray -> first
                else -> error("Неожиданный ONNX output: " + value.javaClass.name)
            }
        }
        else -> error("Неожиданный ONNX output")
    }

    private fun softmax(logits: FloatArray): FloatArray {
        if (logits.isEmpty()) return floatArrayOf()
        val maxLogit = logits.maxOrNull() ?: 0f
        val exps = DoubleArray(logits.size) { index ->
            exp((logits[index] - maxLogit).toDouble())
        }
        val sum = exps.sum().coerceAtLeast(1e-12)
        return FloatArray(logits.size) { index -> (exps[index] / sum).toFloat() }
    }

    override fun close() {
        session.close()
    }

    companion object {
        private const val INPUT_SIZE = 224
        private const val RESIZE_SIZE = 256
        private val MEAN = floatArrayOf(0.485f, 0.456f, 0.406f)
        private val STD = floatArrayOf(0.229f, 0.224f, 0.225f)
        private val LABELS = listOf("drawings", "hentai", "neutral", "porn", "sexy")
    }
}
