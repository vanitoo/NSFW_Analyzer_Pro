package ru.vanitoo.nsfwanalyzer.ml

import android.content.Context
import ai.onnxruntime.OrtEnvironment
import ai.onnxruntime.OrtSession

object OnnxRuntimeFactory {
    fun createSession(context: Context, assetName: String): Pair<OrtEnvironment, OrtSession> {
        val environment = OrtEnvironment.getEnvironment()
        val modelFile = ModelAssets.copyToCache(context, assetName)
        val options = OrtSession.SessionOptions().apply {
            addNnapi()
            setOptimizationLevel(OrtSession.SessionOptions.OptLevel.ALL_OPT)
        }
        return environment to environment.createSession(modelFile.absolutePath, options)
    }
}
