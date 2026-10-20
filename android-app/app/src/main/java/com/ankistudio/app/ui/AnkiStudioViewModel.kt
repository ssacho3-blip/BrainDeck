package com.ankistudio.app.ui

import android.content.Context
import android.net.Uri
import androidx.lifecycle.ViewModel
import androidx.lifecycle.ViewModelProvider
import androidx.lifecycle.viewModelScope
import com.ankistudio.app.data.AnkiStudioDao
import com.ankistudio.app.data.AnkiStudioDatabase
import com.ankistudio.app.data.CardEntity
import com.ankistudio.app.data.DeckEntity
import com.ankistudio.app.data.DueReviewCardRow
import com.ankistudio.app.data.RevlogEntity
import com.ankistudio.app.ingest.AndroidDocumentIngestor
import com.ankistudio.domain.deck.DocumentDeckBuilder.DeckPlan
import com.ankistudio.domain.fsrs.Fsrs5Engine
import com.ankistudio.domain.fsrs.Fsrs5Engine.CardMemoryState
import com.ankistudio.domain.fsrs.Fsrs5Engine.Rating
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import kotlin.math.max

data class AnkiStudioUiState(
    val decks: List<DeckEntity> = emptyList(),
    val dueCards: List<DueReviewCardRow> = emptyList(),
    val isAnswerRevealed: Boolean = false,
    val isIngesting: Boolean = false,
    val selectedCategoryOverride: String? = null,
    val customDeckTitle: String = "",
    val previewPlan: DeckPlan? = null,
    val previewFilename: String = "",
    val statusBannerMessage: String? = null,
    val isErrorBanner: Boolean = false
)

class AnkiStudioViewModel(
    private val dao: AnkiStudioDao,
    private val ingestor: AndroidDocumentIngestor
) : ViewModel() {

    private val _uiState = MutableStateFlow(AnkiStudioUiState())
    val uiState: StateFlow<AnkiStudioUiState> = _uiState.asStateFlow()

    init {
        refreshWorkspace()
    }

    fun refreshWorkspace(deckId: Long? = null) {
        viewModelScope.launch {
            val nowSec = System.currentTimeMillis() / 1000L
            val decks = dao.listDecks()
            val due = dao.getDueCards(nowEpochSec = nowSec, deckId = deckId)
            _uiState.update {
                it.copy(
                    decks = decks,
                    dueCards = due,
                    isAnswerRevealed = false
                )
            }
        }
    }

    fun selectCategoryOverride(category: String?) {
        _uiState.update { it.copy(selectedCategoryOverride = category) }
    }

    fun updateCustomDeckTitle(title: String) {
        _uiState.update { it.copy(customDeckTitle = title) }
    }

    fun ingestDocument(uri: Uri, filename: String, mimeType: String?) {
        viewModelScope.launch {
            _uiState.update {
                it.copy(
                    isIngesting = true,
                    statusBannerMessage = "온디바이스 OCR 및 학습 카드 추출 중 ($filename)...",
                    isErrorBanner = false
                )
            }
            try {
                val current = _uiState.value
                val plan = ingestor.ingestUri(
                    uri = uri,
                    filename = filename,
                    mimeType = mimeType,
                    categoryOverride = current.selectedCategoryOverride,
                    deckTitleOverride = current.customDeckTitle.takeIf { it.isNotBlank() }
                )
                val banner = if (plan.status == "OK") {
                    "총 ${plan.stats.pages}쪽에서 ${plan.cards.size}장의 학습 카드를 추출했습니다."
                } else {
                    "문서 처리 차단 (${plan.errorCode ?: "insufficient_text"}): 추출 조건을 확인해 주세요."
                }
                _uiState.update {
                    it.copy(
                        isIngesting = false,
                        previewPlan = plan,
                        previewFilename = filename,
                        customDeckTitle = if (it.customDeckTitle.isBlank()) plan.deckName else it.customDeckTitle,
                        statusBannerMessage = banner,
                        isErrorBanner = plan.status != "OK"
                    )
                }
            } catch (e: Exception) {
                _uiState.update {
                    it.copy(
                        isIngesting = false,
                        statusBannerMessage = "문서 처리 실패: ${e.message}",
                        isErrorBanner = true
                    )
                }
            }
        }
    }

    fun updatePreviewCard(index: Int, newFront: String, newBack: String) {
        _uiState.update { state ->
            val currentPlan = state.previewPlan ?: return@update state
            if (index !in currentPlan.cards.indices) return@update state
            val updatedCards = currentPlan.cards.mapIndexed { idx, card ->
                if (idx == index) {
                    card.copy(
                        spec = card.spec.copy(
                            frontText = newFront,
                            backText = newBack
                        )
                    )
                } else {
                    card
                }
            }
            state.copy(previewPlan = currentPlan.copy(cards = updatedCards))
        }
    }

    fun removePreviewCard(index: Int) {
        _uiState.update { state ->
            val currentPlan = state.previewPlan ?: return@update state
            val updatedCards = currentPlan.cards.filterIndexed { idx, _ -> idx != index }
            state.copy(
                previewPlan = currentPlan.copy(cards = updatedCards)
            )
        }
    }

    fun savePreviewAsDeck() {
        val state = _uiState.value
        val preview = state.previewPlan ?: return
        if (preview.cards.isEmpty()) return

        viewModelScope.launch {
            try {
                val deckTitle = state.customDeckTitle.ifBlank { preview.deckName }
                val deckId = dao.createDeckWithGeneratedCards(
                    deckName = deckTitle,
                    description = "Generated from ${state.previewFilename} (${preview.category})",
                    category = preview.category,
                    sourceFilename = state.previewFilename,
                    cards = preview.cards
                )
                _uiState.update {
                    it.copy(
                        previewPlan = null,
                        customDeckTitle = "",
                        statusBannerMessage = "'$deckTitle' 덱에 ${preview.cards.size}장의 노트를 원자적으로 저장했습니다!",
                        isErrorBanner = false
                    )
                }
                refreshWorkspace(deckId = deckId)
            } catch (e: Exception) {
                _uiState.update {
                    it.copy(
                        statusBannerMessage = "덱 저장 중 오류 발생 (전체 롤백됨): ${e.message}",
                        isErrorBanner = true
                    )
                }
            }
        }
    }

    fun revealAnswer() {
        _uiState.update { it.copy(isAnswerRevealed = true) }
    }

    fun submitReviewRating(rating: Rating) {
        val currentCard = _uiState.value.dueCards.firstOrNull() ?: return
        viewModelScope.launch {
            val nowSec = System.currentTimeMillis() / 1000L
            val elapsedDays = if (currentCard.lastReviewEpochSec != null) {
                max(0.0, (nowSec - currentCard.lastReviewEpochSec).toDouble() / 86400.0)
            } else {
                0.0
            }
            val memory = CardMemoryState(
                difficulty = currentCard.difficulty,
                stability = currentCard.stability,
                reps = currentCard.reps,
                lapses = currentCard.lapses,
                state = currentCard.state
            )
            val outcome = Fsrs5Engine.stepFsrs(
                memory = memory,
                rating = rating,
                elapsedDays = elapsedDays
            )
            val nextDueEpochSec = if (outcome.scheduledDays == 0) {
                nowSec + 600L // 10m learning step
            } else {
                nowSec + outcome.scheduledDays.toLong() * 86400L
            }
            val nextQueue = if (outcome.scheduledDays == 0) 1 else 2
            dao.recordCardReview(
                updatedCard = CardEntity(
                    id = currentCard.cardId,
                    noteId = currentCard.noteId,
                    deckId = currentCard.deckId,
                    ord = currentCard.ord,
                    state = outcome.memory.state,
                    queue = nextQueue,
                    quizStage = currentCard.quizStage,
                    consecutiveSuccesses = currentCard.consecutiveSuccesses,
                    stability = outcome.memory.stability,
                    difficulty = outcome.memory.difficulty,
                    dueEpochSec = nextDueEpochSec,
                    lastReviewEpochSec = nowSec,
                    reps = outcome.memory.reps,
                    lapses = outcome.memory.lapses,
                    scheduledDays = outcome.scheduledDays.toDouble()
                ),
                revlog = RevlogEntity(
                    cardId = currentCard.cardId,
                    rating = rating.code,
                    prevState = currentCard.state,
                    nextState = outcome.memory.state,
                    prevQuizStage = currentCard.quizStage,
                    nextQuizStage = currentCard.quizStage,
                    prevStability = currentCard.stability,
                    nextStability = outcome.memory.stability,
                    prevDifficulty = currentCard.difficulty,
                    nextDifficulty = outcome.memory.difficulty,
                    scheduledDays = outcome.scheduledDays.toDouble(),
                    reviewedAtEpochSec = nowSec
                )
            )
            refreshWorkspace()
        }
    }

    override fun onCleared() {
        super.onCleared()
        ingestor.close()
    }

    companion object {
        fun factory(context: Context): ViewModelProvider.Factory {
            val appContext = context.applicationContext
            return object : ViewModelProvider.Factory {
                @Suppress("UNCHECKED_CAST")
                override fun <T : ViewModel> create(modelClass: Class<T>): T {
                    val db = AnkiStudioDatabase.getInstance(appContext)
                    val ingestor = AndroidDocumentIngestor(appContext.contentResolver)
                    return AnkiStudioViewModel(db.dao(), ingestor) as T
                }
            }
        }
    }
}
