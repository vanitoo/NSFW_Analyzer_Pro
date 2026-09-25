package ru.vanitoo.nsfwanalyzer

import android.app.Application
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import androidx.work.ExistingWorkPolicy
import androidx.work.OneTimeWorkRequestBuilder
import androidx.work.WorkInfo
import androidx.work.WorkManager
import androidx.work.getWorkInfosForUniqueWorkFlow
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import ru.vanitoo.nsfwanalyzer.data.GalleryRepository
import ru.vanitoo.nsfwanalyzer.ml.AnalyzerFactory
import ru.vanitoo.nsfwanalyzer.ml.ModelAssets
import ru.vanitoo.nsfwanalyzer.work.GalleryAnalysisWorker

data class GalleryUiState(
    val galleryCount: Int = 0,
    val analyzedCount: Int = 0,
    val nsfwCount: Int = 0,
    val current: Int = 0,
    val total: Int = 0,
    val currentFile: String = "",
    val running: Boolean = false,
    val message: String = "",
    val nsfwModelPresent: Boolean = false,
    val generalModelPresent: Boolean = false
)

class GalleryViewModel(application: Application) : AndroidViewModel(application) {
    private val repository = GalleryRepository(application)
    private val workManager = WorkManager.getInstance(application)
    private val _state = MutableStateFlow(GalleryUiState())
    val state: StateFlow<GalleryUiState> = _state.asStateFlow()

    init {
        refreshModelStatus()

        viewModelScope.launch {
            repository.dao.observeCount().collect { count ->
                _state.value = _state.value.copy(analyzedCount = count)
            }
        }

        viewModelScope.launch {
            repository.dao.observeNsfwCount().collect { count ->
                _state.value = _state.value.copy(nsfwCount = count)
            }
        }

        viewModelScope.launch {
            workManager.getWorkInfosForUniqueWorkFlow(WORK_NAME).collect { infos ->
                val info = infos.firstOrNull() ?: return@collect
                val current = info.progress.getInt("current", 0)
                val total = info.progress.getInt("total", 0)
                val file = info.progress.getString("file").orEmpty()
                val error = info.outputData.getString("error").orEmpty()
                val running =
                    info.state == WorkInfo.State.RUNNING ||
                    info.state == WorkInfo.State.ENQUEUED

                _state.value = _state.value.copy(
                    current = current,
                    total = total,
                    currentFile = file,
                    running = running,
                    message = when (info.state) {
                        WorkInfo.State.SUCCEEDED -> "Анализ завершён"
                        WorkInfo.State.FAILED -> error.ifBlank { "Ошибка анализа" }
                        WorkInfo.State.CANCELLED -> "Анализ остановлен"
                        WorkInfo.State.RUNNING -> "Анализ галереи"
                        WorkInfo.State.ENQUEUED -> "Анализ поставлен в очередь"
                        else -> _state.value.message
                    }
                )
            }
        }
    }

    fun refreshGalleryCount() {
        viewModelScope.launch(Dispatchers.IO) {
            runCatching { repository.listImages().size }
                .onSuccess { count ->
                    _state.value = _state.value.copy(
                        galleryCount = count,
                        message = "Найдено фото: " + count
                    )
                }
                .onFailure {
                    _state.value = _state.value.copy(
                        message = "Нет доступа к галерее"
                    )
                }
        }
    }

    fun refreshModelStatus() {
        val context = getApplication<Application>()
        _state.value = _state.value.copy(
            nsfwModelPresent = ModelAssets.exists(context, AnalyzerFactory.NSFW_MODEL),
            generalModelPresent = ModelAssets.exists(context, AnalyzerFactory.GENERAL_MODEL)
        )
    }

    fun startAnalysis() {
        val request = OneTimeWorkRequestBuilder<GalleryAnalysisWorker>().build()
        workManager.enqueueUniqueWork(
            WORK_NAME,
            ExistingWorkPolicy.REPLACE,
            request
        )
    }

    fun cancelAnalysis() {
        workManager.cancelUniqueWork(WORK_NAME)
    }

    fun clearCache() {
        viewModelScope.launch(Dispatchers.IO) {
            repository.dao.clear()
            _state.value = _state.value.copy(message = "Кэш анализа очищен")
        }
    }

    companion object {
        private const val WORK_NAME = "gallery-analysis"
    }
}
