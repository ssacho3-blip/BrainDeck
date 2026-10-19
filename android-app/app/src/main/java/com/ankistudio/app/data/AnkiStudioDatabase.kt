package com.ankistudio.app.data

import android.content.Context
import androidx.room.Dao
import androidx.room.Database
import androidx.room.Entity
import androidx.room.ForeignKey
import androidx.room.Index
import androidx.room.Insert
import androidx.room.OnConflictStrategy
import androidx.room.PrimaryKey
import androidx.room.Query
import androidx.room.Room
import androidx.room.RoomDatabase
import androidx.room.Transaction
import androidx.room.Update
import com.ankistudio.domain.deck.DocumentDeckBuilder.SourcedCard
import com.ankistudio.domain.fsrs.Fsrs5Engine

@Entity(
    tableName = "decks",
    indices = [Index(value = ["name"], unique = true)]
)
data class DeckEntity(
    @PrimaryKey(autoGenerate = true) val id: Long = 0,
    val name: String,
    val description: String = "",
    val category: String = "general",
    val desiredRetention: Double = 0.90,
    val createdAtEpochSec: Long = System.currentTimeMillis() / 1000L
)

@Entity(
    tableName = "notes",
    foreignKeys = [
        ForeignKey(
            entity = DeckEntity::class,
            parentColumns = ["id"],
            childColumns = ["deckId"],
            onDelete = ForeignKey.CASCADE
        )
    ],
    indices = [Index(value = ["deckId"]), Index(value = ["guid"], unique = true)]
)
data class NoteEntity(
    @PrimaryKey(autoGenerate = true) val id: Long = 0,
    val guid: String,
    val deckId: Long,
    val noteType: String, // "basic" | "cloze" | "speaking"
    val front: String,
    val back: String,
    val extraContext: String,
    val tagsCsv: String,
    val sourceFilename: String,
    val sourcePage: Int,
    val sourceExcerpt: String,
    val createdAtEpochSec: Long = System.currentTimeMillis() / 1000L
)

@Entity(
    tableName = "cards",
    foreignKeys = [
        ForeignKey(
            entity = NoteEntity::class,
            parentColumns = ["id"],
            childColumns = ["noteId"],
            onDelete = ForeignKey.CASCADE
        ),
        ForeignKey(
            entity = DeckEntity::class,
            parentColumns = ["id"],
            childColumns = ["deckId"],
            onDelete = ForeignKey.CASCADE
        )
    ],
    indices = [Index(value = ["deckId", "dueEpochSec"]), Index(value = ["noteId"])]
)
data class CardEntity(
    @PrimaryKey(autoGenerate = true) val id: Long = 0,
    val noteId: Long,
    val deckId: Long,
    val ord: Int = 1,
    val state: String = "new",
    val stability: Double = 0.0,
    val difficulty: Double = 0.0,
    val dueEpochSec: Long = System.currentTimeMillis() / 1000L,
    val lastReviewEpochSec: Long? = null,
    val reps: Int = 0,
    val lapses: Int = 0,
    val scheduledDays: Double = 0.0
)

@Entity(
    tableName = "revlog",
    foreignKeys = [
        ForeignKey(
            entity = CardEntity::class,
            parentColumns = ["id"],
            childColumns = ["cardId"],
            onDelete = ForeignKey.CASCADE
        )
    ],
    indices = [Index(value = ["cardId", "reviewedAtEpochSec"])]
)
data class RevlogEntity(
    @PrimaryKey(autoGenerate = true) val id: Long = 0,
    val cardId: Long,
    val rating: Int,
    val prevState: String,
    val nextState: String,
    val prevStability: Double,
    val nextStability: Double,
    val prevDifficulty: Double,
    val nextDifficulty: Double,
    val scheduledDays: Double,
    val reviewedAtEpochSec: Long
)

data class DueReviewCardRow(
    val cardId: Long,
    val noteId: Long,
    val deckId: Long,
    val ord: Int,
    val noteType: String,
    val front: String,
    val back: String,
    val extraContext: String,
    val sourceFilename: String,
    val sourcePage: Int,
    val sourceExcerpt: String,
    val state: String,
    val stability: Double,
    val difficulty: Double,
    val dueEpochSec: Long,
    val lastReviewEpochSec: Long?,
    val reps: Int,
    val lapses: Int,
    val scheduledDays: Double
)

@Dao
interface AnkiStudioDao {

    @Query("SELECT * FROM decks ORDER BY id ASC")
    suspend fun listDecks(): List<DeckEntity>

    @Query("SELECT * FROM decks WHERE name = :name LIMIT 1")
    suspend fun findDeckByName(name: String): DeckEntity?

    @Insert(onConflict = OnConflictStrategy.ABORT)
    suspend fun insertDeck(deck: DeckEntity): Long

    @Insert(onConflict = OnConflictStrategy.ABORT)
    suspend fun insertNote(note: NoteEntity): Long

    @Insert(onConflict = OnConflictStrategy.ABORT)
    suspend fun insertCard(card: CardEntity): Long

    @Update
    suspend fun updateCard(card: CardEntity)

    @Insert(onConflict = OnConflictStrategy.ABORT)
    suspend fun insertRevlog(revlog: RevlogEntity): Long

    @Transaction
    suspend fun recordCardReview(updatedCard: CardEntity, revlog: RevlogEntity) {
        updateCard(updatedCard)
        insertRevlog(revlog)
    }

    @Query(
        """
        SELECT c.id AS cardId, c.noteId AS noteId, c.deckId AS deckId, c.ord AS ord,
               n.noteType AS noteType, n.front AS front, n.back AS back,
               n.extraContext AS extraContext, n.sourceFilename AS sourceFilename,
               n.sourcePage AS sourcePage, n.sourceExcerpt AS sourceExcerpt,
               c.state AS state, c.stability AS stability, c.difficulty AS difficulty,
               c.dueEpochSec AS dueEpochSec, c.lastReviewEpochSec AS lastReviewEpochSec,
               c.reps AS reps, c.lapses AS lapses, c.scheduledDays AS scheduledDays
        FROM cards c
        INNER JOIN notes n ON n.id = c.noteId
        WHERE c.dueEpochSec <= :nowEpochSec
          AND (:deckId IS NULL OR c.deckId = :deckId)
        ORDER BY c.dueEpochSec ASC, c.id ASC
        LIMIT :limit
        """
    )
    suspend fun getDueCards(nowEpochSec: Long, deckId: Long? = null, limit: Int = 50): List<DueReviewCardRow>

    /**
     * Atomic single-transaction deck + study cards creation.
     * Preserves sourcePage and sourceExcerpt, expands multi-ordinal Cloze cards,
     * and rolls back completely if any card fails validation.
     */
    @Transaction
    suspend fun createDeckWithGeneratedCards(
        deckName: String,
        description: String,
        category: String,
        sourceFilename: String,
        cards: List<SourcedCard>,
        nowEpochSec: Long = System.currentTimeMillis() / 1000L
    ): Long {
        val cleanDeckName = deckName.trim()
        require(cleanDeckName.isNotEmpty()) { "Deck name must not be empty" }
        require(cards.isNotEmpty()) { "Cards list must not be empty" }

        val existing = findDeckByName(cleanDeckName)
        val deckId = existing?.id ?: insertDeck(
            DeckEntity(
                name = cleanDeckName,
                description = description.trim(),
                category = category,
                createdAtEpochSec = nowEpochSec
            )
        )

        cards.forEachIndexed { idx, card ->
            val cleanFront = card.spec.frontText.trim()
            val cleanBack = card.spec.backText.trim()
            require(cleanFront.isNotEmpty() && cleanBack.isNotEmpty()) {
                "Card at index $idx has empty front or back"
            }
            val detectedOrdinals = Fsrs5Engine.extractClozeOrdinals(cleanFront)
            val effectiveNoteType = if (card.spec.noteType == "cloze" || detectedOrdinals.isNotEmpty()) {
                "cloze"
            } else {
                card.spec.noteType.ifBlank { "basic" }
            }
            val ordinals = if (effectiveNoteType == "cloze") {
                detectedOrdinals.ifEmpty { listOf(1) }
            } else {
                listOf(1)
            }

            val guid = "${deckId}_${nowEpochSec}_${idx}_${cleanFront.hashCode()}"
            val noteId = insertNote(
                NoteEntity(
                    guid = guid,
                    deckId = deckId,
                    noteType = effectiveNoteType,
                    front = cleanFront,
                    back = cleanBack,
                    extraContext = card.spec.rationale,
                    tagsCsv = card.spec.tags.joinToString(","),
                    sourceFilename = sourceFilename,
                    sourcePage = card.sourcePage,
                    sourceExcerpt = card.sourceExcerpt,
                    createdAtEpochSec = nowEpochSec
                )
            )
            for (ordinal in ordinals) {
                insertCard(
                    CardEntity(
                        noteId = noteId,
                        deckId = deckId,
                        ord = ordinal,
                        state = "new",
                        stability = 0.0,
                        difficulty = 0.0,
                        dueEpochSec = nowEpochSec
                    )
                )
            }
        }
        return deckId
    }
}

@Database(
    entities = [DeckEntity::class, NoteEntity::class, CardEntity::class, RevlogEntity::class],
    version = 1,
    exportSchema = false
)
abstract class AnkiStudioDatabase : RoomDatabase() {
    abstract fun dao(): AnkiStudioDao

    companion object {
        @Volatile
        private var INSTANCE: AnkiStudioDatabase? = null

        fun getInstance(context: Context): AnkiStudioDatabase {
            return INSTANCE ?: synchronized(this) {
                INSTANCE ?: Room.databaseBuilder(
                    context.applicationContext,
                    AnkiStudioDatabase::class.java,
                    "anki_studio.db"
                ).build().also { INSTANCE = it }
            }
        }
    }
}
