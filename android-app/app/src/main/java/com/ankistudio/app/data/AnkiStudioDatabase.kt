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
import androidx.room.migration.Migration
import androidx.sqlite.db.SupportSQLiteDatabase
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
    val queue: Int = 0, // 0:NEW, 1:INTRADAY, 2:REVIEW, 3:INTERDAY, -1:SUSPENDED, -2:USER_BURIED, -3:SIBLING_BURIED
    val quizStage: Int = 0, // 0:RECOGNITION_MC, 1:TAP_BLOCK, 2:RECALL_INPUT
    val consecutiveSuccesses: Int = 0,
    val stability: Double = 0.0,
    val difficulty: Double = 0.0,
    val dueEpochSec: Long = System.currentTimeMillis() / 1000L,
    val lastReviewEpochSec: Long? = null,
    val reps: Int = 0,
    val lapses: Int = 0,
    val scheduledDays: Double = 0.0
)

/**
 * T2: Non-cascading RevlogEntity — deleting a card or note MUST NOT cascade-delete FSRS review history.
 */
@Entity(
    tableName = "revlog",
    indices = [Index(value = ["cardId", "reviewedAtEpochSec"])]
)
data class RevlogEntity(
    @PrimaryKey(autoGenerate = true) val id: Long = 0,
    val cardId: Long,
    val interactionMode: String = "button_4",
    val evidenceClass: String = "recall",
    val attemptCount: Int = 1,
    val hintUsed: Int = 0,
    val rating: Int,
    val prevState: String,
    val nextState: String,
    val prevQuizStage: Int = 0,
    val nextQuizStage: Int = 0,
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
    val queue: Int,
    val quizStage: Int,
    val consecutiveSuccesses: Int,
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

    @Query(
        """
        UPDATE cards
        SET state = 'new',
            queue = 0,
            quizStage = 0,
            consecutiveSuccesses = 0,
            stability = 1.2,
            difficulty = 5.0,
            dueEpochSec = :nowEpochSec,
            lastReviewEpochSec = NULL,
            reps = 0,
            lapses = 0,
            scheduledDays = 0.0
        WHERE (:deckId IS NULL OR deckId = :deckId)
        """
    )
    suspend fun resetCardsProgress(nowEpochSec: Long, deckId: Long? = null): Int

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
               c.state AS state, c.queue AS queue, c.quizStage AS quizStage,
               c.consecutiveSuccesses AS consecutiveSuccesses,
               c.stability AS stability, c.difficulty AS difficulty,
               c.dueEpochSec AS dueEpochSec, c.lastReviewEpochSec AS lastReviewEpochSec,
               c.reps AS reps, c.lapses AS lapses, c.scheduledDays AS scheduledDays
        FROM cards c
        INNER JOIN notes n ON n.id = c.noteId
        WHERE c.dueEpochSec <= :nowEpochSec
          AND c.queue >= 0
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
    version = 2,
    exportSchema = false
)
abstract class AnkiStudioDatabase : RoomDatabase() {
    abstract fun dao(): AnkiStudioDao

    companion object {
        @Volatile
        private var INSTANCE: AnkiStudioDatabase? = null

        val MIGRATION_1_2: Migration = object : Migration(1, 2) {
            override fun migrate(db: SupportSQLiteDatabase) {
                db.execSQL("ALTER TABLE cards ADD COLUMN queue INTEGER NOT NULL DEFAULT 0")
                db.execSQL("ALTER TABLE cards ADD COLUMN quizStage INTEGER NOT NULL DEFAULT 0")
                db.execSQL("ALTER TABLE cards ADD COLUMN consecutiveSuccesses INTEGER NOT NULL DEFAULT 0")
                db.execSQL(
                    """
                    UPDATE cards SET queue = CASE
                        WHEN state = 'suspended' THEN -1
                        WHEN state IN ('learning', 'relearning') THEN 1
                        WHEN state = 'review' THEN 2
                        ELSE 0
                    END
                    """.trimIndent()
                )

                db.execSQL(
                    """
                    CREATE TABLE IF NOT EXISTS revlog_new (
                        id INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL,
                        cardId INTEGER NOT NULL,
                        interactionMode TEXT NOT NULL DEFAULT 'button_4',
                        evidenceClass TEXT NOT NULL DEFAULT 'recall',
                        attemptCount INTEGER NOT NULL DEFAULT 1,
                        hintUsed INTEGER NOT NULL DEFAULT 0,
                        rating INTEGER NOT NULL,
                        prevState TEXT NOT NULL,
                        nextState TEXT NOT NULL,
                        prevQuizStage INTEGER NOT NULL DEFAULT 0,
                        nextQuizStage INTEGER NOT NULL DEFAULT 0,
                        prevStability REAL NOT NULL,
                        nextStability REAL NOT NULL,
                        prevDifficulty REAL NOT NULL,
                        nextDifficulty REAL NOT NULL,
                        scheduledDays REAL NOT NULL,
                        reviewedAtEpochSec INTEGER NOT NULL
                    )
                    """.trimIndent()
                )
                db.execSQL(
                    """
                    INSERT INTO revlog_new (
                        id, cardId, interactionMode, evidenceClass, attemptCount, hintUsed,
                        rating, prevState, nextState, prevQuizStage, nextQuizStage,
                        prevStability, nextStability, prevDifficulty, nextDifficulty,
                        scheduledDays, reviewedAtEpochSec
                    )
                    SELECT id, cardId, 'button_4', 'recall', 1, 0,
                           rating, prevState, nextState, 0, 0,
                           prevStability, nextStability, prevDifficulty, nextDifficulty,
                           scheduledDays, reviewedAtEpochSec
                    FROM revlog
                    """.trimIndent()
                )
                db.execSQL("DROP TABLE revlog")
                db.execSQL("ALTER TABLE revlog_new RENAME TO revlog")
                db.execSQL("CREATE INDEX IF NOT EXISTS index_revlog_cardId_reviewedAtEpochSec ON revlog(cardId, reviewedAtEpochSec)")
            }
        }

        fun getInstance(context: Context): AnkiStudioDatabase {
            return INSTANCE ?: synchronized(this) {
                INSTANCE ?: Room.databaseBuilder(
                    context.applicationContext,
                    AnkiStudioDatabase::class.java,
                    "anki_studio.db"
                ).addMigrations(MIGRATION_1_2).build().also { INSTANCE = it }
            }
        }
    }
}
