package ru.vanitoo.nsfwanalyzer.data

import androidx.room.Entity
import androidx.room.PrimaryKey

@Entity(tableName = "image_analysis")
data class ImageAnalysisEntity(
    @PrimaryKey val mediaId: Long,
    val uri: String,
    val displayName: String,
    val dateModifiedSeconds: Long,
    val sizeBytes: Long,
    val modelVersion: String,
    val nsfwScore: Float?,
    val category: String?,
    val subcategory: String?,
    val tags: String?,
    val analyzedAtMillis: Long
)
