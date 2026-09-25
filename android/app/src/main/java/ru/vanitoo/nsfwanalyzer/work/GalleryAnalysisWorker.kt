package ru.vanitoo.nsfwanalyzer.work

import android.content.Context
import androidx.work.CoroutineWorker
import androidx.work.WorkerParameters
import androidx.work.workDataOf
import ru.vanitoo.nsfwanalyzer.data.GalleryRepository
import ru.vanitoo.nsfwanalyzer.data.ImageAnalysisEntity
import ru.vanitoo.nsfwanalyzer.ml.AnalyzerFactory

class GalleryAnalysisWorker(
    appContext: Context,
    params: WorkerParameters
) : CoroutineWorker(appContext, params) {

    override suspend fun doWork(): Result {
        val repository = GalleryRepository(applicationContext)
        val analyzer = AnalyzerFactory.create(applicationContext)

        return try {
            val images = repository.listImages()
            setProgress(workDataOf("current" to 0, "total" to images.size))

            for ((index, image) in images.withIndex()) {
                if (isStopped) break

                val existing = repository.dao.find(image.id)
                val unchanged =
                    existing != null &&
                    existing.dateModifiedSeconds == image.dateModifiedSeconds &&
                    existing.modelVersion == analyzer.modelVersion

                if (!unchanged) {
                    val analysis = analyzer.analyze(applicationContext, image.uri)
                    repository.dao.upsert(
                        ImageAnalysisEntity(
                            mediaId = image.id,
                            uri = image.uri.toString(),
                            displayName = image.displayName,
                            dateModifiedSeconds = image.dateModifiedSeconds,
                            sizeBytes = image.sizeBytes,
                            modelVersion = analyzer.modelVersion,
                            nsfwScore = analysis.nsfwScore,
                            category = analysis.category,
                            subcategory = analysis.subcategory,
                            tags = analysis.tags.joinToString(", "),
                            analyzedAtMillis = System.currentTimeMillis()
                        )
                    )
                }

                setProgress(
                    workDataOf(
                        "current" to (index + 1),
                        "total" to images.size,
                        "file" to image.displayName
                    )
                )
            }

            Result.success(workDataOf("total" to images.size))
        } catch (security: SecurityException) {
            Result.failure(workDataOf("error" to "Нет доступа к галерее"))
        } catch (error: Throwable) {
            Result.failure(
                workDataOf(
                    "error" to (error.message ?: error.javaClass.simpleName)
                )
            )
        } finally {
            analyzer.close()
        }
    }
}
