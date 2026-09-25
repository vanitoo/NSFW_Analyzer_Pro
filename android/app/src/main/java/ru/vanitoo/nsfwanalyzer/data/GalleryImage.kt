package ru.vanitoo.nsfwanalyzer.data

import android.net.Uri

data class GalleryImage(
    val id: Long,
    val uri: Uri,
    val displayName: String,
    val dateModifiedSeconds: Long,
    val sizeBytes: Long
)
