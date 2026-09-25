package ru.vanitoo.nsfwanalyzer.ml

import android.content.Context
import java.io.File

object ModelAssets {
    private const val MODEL_DIR = "models"

    fun exists(context: Context, name: String): Boolean =
        runCatching { context.assets.open("$MODEL_DIR/$name").close() }.isSuccess

    fun copyToCache(context: Context, name: String): File {
        val target = File(context.cacheDir, name)
        if (!target.exists()) {
            target.parentFile?.mkdirs()
            context.assets.open("$MODEL_DIR/$name").use { input ->
                target.outputStream().use { output -> input.copyTo(output) }
            }
        }
        return target
    }
}
