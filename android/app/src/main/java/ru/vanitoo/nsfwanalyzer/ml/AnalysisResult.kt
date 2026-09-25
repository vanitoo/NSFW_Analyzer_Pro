package ru.vanitoo.nsfwanalyzer.ml

data class AnalysisResult(
    val nsfwScore: Float? = null,
    val category: String? = null,
    val subcategory: String? = null,
    val tags: List<String> = emptyList()
)
