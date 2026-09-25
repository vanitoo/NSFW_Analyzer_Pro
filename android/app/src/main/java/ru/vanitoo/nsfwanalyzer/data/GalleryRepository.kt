package ru.vanitoo.nsfwanalyzer.data

import android.content.ContentUris
import android.content.Context
import android.provider.MediaStore
import androidx.room.Room

class GalleryRepository(context: Context) {
    private val appContext = context.applicationContext
    private val database = Room.databaseBuilder(
        appContext,
        AppDatabase::class.java,
        "gallery-analysis.db"
    ).build()

    val dao: ImageAnalysisDao = database.imageAnalysisDao()

    fun listImages(): List<GalleryImage> {
        val result = ArrayList<GalleryImage>()
        val collection = MediaStore.Images.Media.EXTERNAL_CONTENT_URI
        val projection = arrayOf(
            MediaStore.Images.Media._ID,
            MediaStore.Images.Media.DISPLAY_NAME,
            MediaStore.Images.Media.DATE_MODIFIED,
            MediaStore.Images.Media.SIZE
        )
        val order = MediaStore.Images.Media.DATE_MODIFIED + " DESC"

        appContext.contentResolver.query(
            collection,
            projection,
            null,
            null,
            order
        )?.use { cursor ->
            val idColumn = cursor.getColumnIndexOrThrow(MediaStore.Images.Media._ID)
            val nameColumn = cursor.getColumnIndexOrThrow(MediaStore.Images.Media.DISPLAY_NAME)
            val modifiedColumn = cursor.getColumnIndexOrThrow(MediaStore.Images.Media.DATE_MODIFIED)
            val sizeColumn = cursor.getColumnIndexOrThrow(MediaStore.Images.Media.SIZE)

            while (cursor.moveToNext()) {
                val id = cursor.getLong(idColumn)
                result += GalleryImage(
                    id = id,
                    uri = ContentUris.withAppendedId(collection, id),
                    displayName = cursor.getString(nameColumn) ?: ("image_" + id),
                    dateModifiedSeconds = cursor.getLong(modifiedColumn),
                    sizeBytes = cursor.getLong(sizeColumn)
                )
            }
        }
        return result
    }
}
