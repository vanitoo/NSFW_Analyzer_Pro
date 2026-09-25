package ru.vanitoo.nsfwanalyzer.data

import androidx.room.Dao
import androidx.room.Insert
import androidx.room.OnConflictStrategy
import androidx.room.Query
import kotlinx.coroutines.flow.Flow

@Dao
interface ImageAnalysisDao {
    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun upsert(item: ImageAnalysisEntity)

    @Query("SELECT * FROM image_analysis WHERE mediaId = :mediaId LIMIT 1")
    suspend fun find(mediaId: Long): ImageAnalysisEntity?

    @Query("SELECT COUNT(*) FROM image_analysis")
    fun observeCount(): Flow<Int>

    @Query("SELECT COUNT(*) FROM image_analysis WHERE nsfwScore IS NOT NULL AND nsfwScore >= :threshold")
    fun observeNsfwCount(threshold: Float = 0.7f): Flow<Int>

    @Query("DELETE FROM image_analysis")
    suspend fun clear()
}
