package com.ankistudio.app.ui

import android.content.Context
import android.content.SharedPreferences
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
import com.ankistudio.domain.catalog.BrainPackStoreCatalog
import com.ankistudio.domain.catalog.BuiltInCurriculumCatalog
import com.ankistudio.domain.deck.DocumentDeckBuilder.DeckPlan
import com.ankistudio.domain.deck.DocumentDeckBuilder.GeneratedCardSpec
import com.ankistudio.domain.deck.DocumentDeckBuilder.SourcedCard
import com.ankistudio.domain.fsrs.Fsrs5Engine
import com.ankistudio.domain.fsrs.Fsrs5Engine.CardMemoryState
import com.ankistudio.domain.fsrs.Fsrs5Engine.Rating
import com.ankistudio.domain.planner.AnkiStudyPlan
import com.ankistudio.domain.planner.AnkiStudyPlannerEngine
import com.ankistudio.domain.quiz.AdaptiveQuizEngine
import com.ankistudio.domain.quiz.AdaptiveQuizEngine.TypedAnswerEvaluation
import com.ankistudio.domain.quiz.AdaptiveQuizEngine.TypedUnderstandingVerdict
import com.ankistudio.domain.rea.ReaV56Engine
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import kotlin.math.max

data class AnkiStudioUiState(
    val showOnboarding: Boolean = true,
    val activeTab: String = "study", // "study" | "curriculum" | "create" | "store" | "stats"
    val selectedDeckId: Long? = null,
    val decks: List<DeckEntity> = emptyList(),
    val rawDueCards: List<DueReviewCardRow> = emptyList(),
    val dueCards: List<DueReviewCardRow> = emptyList(),
    val studyFilterMode: String = "all", // "all" | "wrong_only" | "marked_only"
    val questionTypeFilter: String = "all", // "all" | "vocab" | "grammar" | "hanja" | "history_sci"
    val sessionWrongCards: List<DueReviewCardRow> = emptyList(),
    val markedCardIds: Set<Long> = emptySet(),
    val buriedCardIds: Set<Long> = emptySet(),
    val typedAnswerInput: String = "",
    val typedEvaluation: TypedAnswerEvaluation? = null,
    val recommendedRating: Rating? = null,
    val newCardFrontInput: String = "",
    val newCardBackInput: String = "",
    val isAnswerRevealed: Boolean = false,
    val isQuizModeOpen: Boolean = false,
    val quizOptions: List<String> = emptyList(),
    val selectedQuizOption: String? = null,
    val hintStep: Int = 0,
    val hintText: String? = null,
    val isInterleavedShuffleEnabled: Boolean = true,
    val selectedDifficultyLevel: String = "mixed", // "mixed" | "lv1" | "lv2" | "lv3" | "standard"
    val combinedExamScopes: List<BuiltInCurriculumCatalog.CombinedScopeItem> = emptyList(),
    val ageTier: String = "teen", // "junior" | "teen" | "adult"
    val canUndoLastReview: Boolean = false,
    val isIngesting: Boolean = false,
    val selectedCategoryOverride: String? = null,
    val selectedOllamaCloudModel: String = "glm-5.3-flash",
    val customDeckTitle: String = "",
    val selectedTextbookId: String = "kr.mid1.eng.donga_yoon.2022",
    val selectedUnitIds: Set<String> = setOf("kr.mid1.eng.donga_yoon.2022:U01", "kr.mid1.eng.donga_yoon.2022:U02"),
    val selectedCollectionId: String = "hanja-grade:8geup",
    val unlockedPackIds: Set<String> = BrainPackStoreCatalog.defaultFreePackIds,
    val selectedStoreCategory: String = "all",
    val previewPlan: DeckPlan? = null,
    val previewFilename: String = "",
    val targetDays: Int = 30,
    val dailyNewLimit: Int = 35,
    val newStudiedToday: Int = 0,
    val studyPlan: AnkiStudyPlan? = null,
    val statusBannerMessage: String? = null,
    val isErrorBanner: Boolean = false
)

class AnkiStudioViewModel(
    private val dao: AnkiStudioDao,
    private val ingestor: AndroidDocumentIngestor,
    private val prefs: SharedPreferences? = null
) : ViewModel() {

    private val _uiState = MutableStateFlow(
        AnkiStudioUiState(
            showOnboarding = !(prefs?.getBoolean(KEY_ONBOARDING_DONE, false) ?: false),
            ageTier = prefs?.getString(KEY_AGE_TIER, "teen") ?: "teen"
        )
    )
    val uiState: StateFlow<AnkiStudioUiState> = _uiState.asStateFlow()
    private var lastUndoSnapshot: CardEntity? = null
    private var cardShownEpochMs: Long = System.currentTimeMillis()
    private val rtBaselineSamples: MutableList<Long> = mutableListOf()
    private var consecutiveGoodStreak: Int = 0

    init {
        refreshWorkspace()
    }

    private fun buildQuizOptionsForCurrentCard(
        due: List<DueReviewCardRow>,
        fullPool: List<DueReviewCardRow> = _uiState.value.rawDueCards
    ): List<String> {
        val current = due.firstOrNull() ?: return emptyList()
        val effectivePool = if (fullPool.isNotEmpty()) fullPool else due
        val candidateTriples = effectivePool.map { Triple(it.cardId, it.front, it.back) }
        return AdaptiveQuizEngine.buildTypeMatchedQuizOptions(
            cardId = current.cardId,
            frontText = current.front,
            backText = current.back,
            candidatePool = candidateTriples,
            requiredOptions = 4,
            reps = current.reps
        )
    }

    fun selectTab(tab: String) {
        val valid = if (tab in setOf("study", "curriculum", "create", "store", "stats")) tab else "study"
        _uiState.update { it.copy(activeTab = valid, statusBannerMessage = null) }
    }

    fun openOnboardingModeSelector() {
        _uiState.update { it.copy(showOnboarding = true) }
    }

    fun completeOnboarding(tier: String) {
        val clean = if (tier in setOf("junior", "teen", "adult")) tier else "teen"
        prefs?.edit()
            ?.putBoolean(KEY_ONBOARDING_DONE, true)
            ?.putString(KEY_AGE_TIER, clean)
            ?.apply()
        val banner = when (clean) {
            "junior" -> "🌱 주니어 모드로 시작합니다!"
            "adult" -> "🎓 성인 모드로 시작합니다!"
            else -> "🚀 중고등 모드로 시작합니다!"
        }
        _uiState.update {
            it.copy(
                showOnboarding = false,
                activeTab = "study",
                ageTier = clean,
                isQuizModeOpen = clean == "junior",
                statusBannerMessage = banner,
                isErrorBanner = false
            )
        }
    }

    fun selectDeckForStudy(deckId: Long?) {
        _uiState.update { it.copy(selectedDeckId = deckId, activeTab = "study") }
        refreshWorkspace(deckId = deckId)
    }

    private fun resolveEffectiveDueCards(
        rawDue: List<DueReviewCardRow>,
        filterMode: String,
        sessionWrong: List<DueReviewCardRow>,
        markedIds: Set<Long>,
        buriedIds: Set<Long>,
        interleavedShuffle: Boolean = true,
        questionTypeFilter: String = _uiState.value.questionTypeFilter
    ): List<DueReviewCardRow> {
        val visibleRaw = rawDue.filter { it.cardId !in buriedIds }
        val combinedPool = buildList {
            addAll(visibleRaw)
            val seen = visibleRaw.map { it.cardId }.toSet()
            for (w in sessionWrong) {
                if (w.cardId !in seen && w.cardId !in buriedIds) {
                    add(w)
                }
            }
        }
        val statusFiltered = when (filterMode) {
            "wrong_only" -> {
                val wrongIds = sessionWrong.map { it.cardId }.toSet()
                combinedPool.filter {
                    it.lapses > 0 ||
                        it.state.equals("learning", ignoreCase = true) ||
                        it.state.equals("relearning", ignoreCase = true) ||
                        it.cardId in wrongIds
                }
            }
            "marked_only" -> combinedPool.filter { it.cardId in markedIds }
            else -> visibleRaw
        }
        val baseFiltered = if (questionTypeFilter != "all" && questionTypeFilter.isNotBlank()) {
            statusFiltered.filter {
                AdaptiveQuizEngine.classifyCardQuestionType(it.front, it.back).categoryKey == questionTypeFilter
            }
        } else {
            statusFiltered
        }
        val interleaved = if (interleavedShuffle && baseFiltered.size > 2) {
            AdaptiveQuizEngine.interleaveStudyQueue(
                items = baseFiltered,
                bucketSelector = { "${it.deckId}:${it.noteType}:${it.noteId % 4}" },
                seed = (baseFiltered.size * 31) xor (baseFiltered.firstOrNull()?.cardId?.toInt() ?: 17)
            )
        } else {
            baseFiltered
        }
        val deduped = if (filterMode != "wrong_only" && interleaved.size > 1) {
            AdaptiveQuizEngine.deduplicateSessionSiblings(
                items = interleaved,
                tagsSelector = { row ->
                    val cleanTarget = AdaptiveQuizEngine.extractCleanTargetAnswer(row.front, row.back).first.lowercase()
                    if (cleanTarget.isNotBlank()) listOf("concept:$cleanTarget") else emptyList()
                },
                stateSelector = { it.state }
            )
        } else {
            interleaved
        }
        if (filterMode != "all") return deduped
        val st = _uiState.value
        val remainingNew = max(0, st.dailyNewLimit - st.newStudiedToday)
        var newTaken = 0
        return deduped.filter { row ->
            if (row.state.equals("new", ignoreCase = true)) {
                if (newTaken < remainingNew) {
                    newTaken += 1
                    true
                } else {
                    false
                }
            } else {
                true
            }
        }
    }

    fun applyStudyPlan(targetDays: Int, customDailyNew: Int? = null) {
        _uiState.update { st ->
            val safeDays = targetDays.coerceIn(3, 365)
            val totalCards = st.rawDueCards.size.coerceAtLeast(1000)
            val newCount = st.rawDueCards.count { it.state.equals("new", ignoreCase = true) }.coerceAtLeast(1)
            val plan = AnkiStudyPlannerEngine.computeStudyPlan(
                totalCards = totalCards,
                newCount = newCount,
                targetDays = safeDays
            )
            val nextDailyNew = (customDailyNew ?: plan.recommendedDailyNew).coerceIn(5, 300)
            val nextSt = st.copy(
                targetDays = safeDays,
                dailyNewLimit = nextDailyNew,
                studyPlan = plan,
                statusBannerMessage = "📅 D-$safeDays 학습 계획 적용 완료! 하루 새 카드 ${nextDailyNew}장씩(평균 ${plan.avgDailyMinutes}분/일) 맞춤 출제됩니다.",
                isErrorBanner = false
            )
            nextSt
        }
        refreshWorkspace(deckId = _uiState.value.selectedDeckId)
    }

    fun increaseDailyNewQuota(extraNew: Int = 15) {
        val boost = extraNew.coerceIn(5, 100)
        _uiState.update { st ->
            val nextLimit = st.dailyNewLimit + boost
            st.copy(
                dailyNewLimit = nextLimit,
                statusBannerMessage = "➕ 오늘의 새 카드 할당량이 +${boost}장 추가되었습니다! (일일 목표 ${nextLimit}장)",
                isErrorBanner = false
            )
        }
        refreshWorkspace(deckId = _uiState.value.selectedDeckId)
    }

    fun toggleInterleavedShuffle() {
        _uiState.update { st ->
            val nextShuffle = !st.isInterleavedShuffleEnabled
            val reordered = resolveEffectiveDueCards(
                rawDue = st.rawDueCards,
                filterMode = st.studyFilterMode,
                sessionWrong = st.sessionWrongCards,
                markedIds = st.markedCardIds,
                buriedIds = st.buriedCardIds,
                interleavedShuffle = nextShuffle
            )
            st.copy(
                isInterleavedShuffleEnabled = nextShuffle,
                dueCards = reordered,
                isAnswerRevealed = false,
                typedAnswerInput = "",
                typedEvaluation = null,
                recommendedRating = null,
                selectedQuizOption = null,
                hintStep = 0,
                hintText = null,
                quizOptions = buildQuizOptionsForCurrentCard(reordered),
                statusBannerMessage = if (nextShuffle) {
                    "🔀 단원·유형 교차 스마트 랜덤 모드가 켜졌습니다!"
                } else {
                    "📋 순차 학습 모드로 전환되었습니다."
                },
                isErrorBanner = false
            )
        }
    }

    fun requestProgressiveHint() {
        val current = _uiState.value.dueCards.firstOrNull() ?: return
        _uiState.update { st ->
            val nextStep = if (st.hintStep >= 2) 2 else st.hintStep + 1
            val hint = AdaptiveQuizEngine.generateProgressiveHint(
                frontText = current.front,
                backText = current.back,
                step = nextStep
            )
            st.copy(
                hintStep = nextStep,
                hintText = hint
            )
        }
    }

    fun overrideTypedAnswerCorrect() {
        val current = _uiState.value.dueCards.firstOrNull() ?: return
        val expected = AdaptiveQuizEngine.extractCleanTargetAnswer(current.front, current.back).first
        val overridden = TypedAnswerEvaluation(
            verdict = TypedUnderstandingVerdict.EXACT,
            scorePct = 100,
            matchedTerms = listOf(expected),
            missingTerms = emptyList<String>(),
            recommendedRating = Rating.GOOD,
            badgeLabel = "✅ 내 답이 맞아요 (정답 인정)",
            feedback = "오타·유의어를 정답으로 인정했습니다. 아래 정답·해설을 확인한 뒤 난이도 버튼(★ 보통)을 눌러 다음 카드로 넘어가세요."
        )
        _uiState.update { st ->
            st.copy(
                isAnswerRevealed = true,
                typedEvaluation = overridden,
                recommendedRating = Rating.GOOD,
                sessionWrongCards = st.sessionWrongCards.filterNot { it.cardId == current.cardId },
                statusBannerMessage = "✅ 정답으로 인정되었습니다! 해설 확인 후 하단 난이도 버튼(★ 보통)을 눌러주세요.",
                isErrorBanner = false
            )
        }
    }

    fun selectOllamaCloudModel(modelId: String) {
        val clean = modelId.trim().ifEmpty { "glm-5.3-flash" }
        _uiState.update {
            it.copy(
                selectedOllamaCloudModel = clean,
                statusBannerMessage = if (clean == "local_rule") {
                    "⚡ 기기 내장 초고속 추출 엔진 선택됨 (오프라인 즉시 생성)"
                } else {
                    "✨ 스마트 자동 생성 (추천) 활성화됨"
                },
                isErrorBanner = false
            )
        }
    }

    fun submitMultipleChoiceOption(selectedOption: String) {
        val current = _uiState.value.dueCards.firstOrNull() ?: return
        val expected = AdaptiveQuizEngine.extractCleanTargetAnswer(current.front, current.back).first
        val eval = AdaptiveQuizEngine.evaluateTypedAnswerUnderstanding(
            userAnswer = selectedOption,
            expectedAnswer = expected
        )
        val isCorrect = eval.verdict == TypedUnderstandingVerdict.EXACT || selectedOption.trim() == expected.trim()
        val finalEval = if (isCorrect) {
            eval.copy(
                verdict = TypedUnderstandingVerdict.EXACT,
                badgeLabel = "🎯 4지선다 정답 · 개념 일치",
                scorePct = 100,
                recommendedRating = Rating.GOOD,
                feedback = "✅ 정답('$expected')을 정확히 골랐습니다! 아래 해설을 확인한 뒤 하단 난이도 버튼(★ 보통)을 눌러 다음 카드로 넘어가세요."
            )
        } else {
            eval.copy(
                verdict = TypedUnderstandingVerdict.UNKNOWN,
                badgeLabel = "❓ 오답 선택 · 재복습 권장",
                scorePct = 0,
                recommendedRating = Rating.AGAIN,
                feedback = "❌ 선택한 보기('$selectedOption')는 오답입니다. 정답('$expected')과 해설을 확인한 뒤 '다시' 버튼을 눌러 복습하세요."
            )
        }
        _uiState.update { st ->
            val updatedWrong = if (!isCorrect && st.sessionWrongCards.none { it.cardId == current.cardId }) {
                st.sessionWrongCards + current
            } else {
                st.sessionWrongCards
            }
            st.copy(
                selectedQuizOption = selectedOption,
                isAnswerRevealed = true,
                typedEvaluation = finalEval,
                recommendedRating = finalEval.recommendedRating,
                sessionWrongCards = updatedWrong
            )
        }
    }

    fun setStudyFilterMode(mode: String) {
        val cleanMode = if (mode in setOf("all", "wrong_only", "marked_only")) mode else "all"
        _uiState.update { st ->
            val filtered = resolveEffectiveDueCards(
                rawDue = st.rawDueCards,
                filterMode = cleanMode,
                sessionWrong = st.sessionWrongCards,
                markedIds = st.markedCardIds,
                buriedIds = st.buriedCardIds,
                interleavedShuffle = st.isInterleavedShuffleEnabled,
                questionTypeFilter = st.questionTypeFilter
            )
            st.copy(
                studyFilterMode = cleanMode,
                dueCards = filtered,
                isAnswerRevealed = false,
                typedAnswerInput = "",
                typedEvaluation = null,
                recommendedRating = null,
                selectedQuizOption = null,
                hintStep = 0,
                hintText = null,
                quizOptions = buildQuizOptionsForCurrentCard(filtered, st.rawDueCards)
            )
        }
    }

    fun setQuestionTypeFilter(qtype: String) {
        val cleanType = if (qtype in setOf("all", "vocab", "grammar", "hanja", "history_sci")) qtype else "all"
        _uiState.update { st ->
            val filtered = resolveEffectiveDueCards(
                rawDue = st.rawDueCards,
                filterMode = st.studyFilterMode,
                sessionWrong = st.sessionWrongCards,
                markedIds = st.markedCardIds,
                buriedIds = st.buriedCardIds,
                interleavedShuffle = st.isInterleavedShuffleEnabled,
                questionTypeFilter = cleanType
            )
            val label = when (cleanType) {
                "vocab" -> "📘 단어·어휘 문제만 모아 풀기 모드"
                "grammar" -> "📐 문법·어법 문제만 모아 풀기 모드"
                "hanja" -> "漢字 한자·성어 문제만 모아 풀기 모드"
                "history_sci" -> "🏛️ 역사·과학·전공 문제만 모아 풀기 모드"
                else -> "🗂️ 전체 유형 통합 출제 모드 (4지선다 보기는 유형별 자동 분리)"
            }
            st.copy(
                questionTypeFilter = cleanType,
                dueCards = filtered,
                isAnswerRevealed = false,
                typedAnswerInput = "",
                typedEvaluation = null,
                recommendedRating = null,
                selectedQuizOption = null,
                hintStep = 0,
                hintText = null,
                quizOptions = buildQuizOptionsForCurrentCard(filtered, st.rawDueCards),
                statusBannerMessage = label,
                isErrorBanner = false
            )
        }
    }

    fun startWrongOnlyRetrySession() {
        setStudyFilterMode("wrong_only")
        _uiState.update {
            it.copy(
                statusBannerMessage = "🔥 오답·모르는 문제만 모아 집중 복습합니다!",
                isErrorBanner = false
            )
        }
    }

    fun updateTypedAnswerInput(text: String) {
        _uiState.update { it.copy(typedAnswerInput = text) }
    }

    fun submitTypedAnswer() {
        val current = _uiState.value.dueCards.firstOrNull() ?: return
        val expected = AdaptiveQuizEngine.extractCleanTargetAnswer(current.front, current.back).first
        val eval = AdaptiveQuizEngine.evaluateTypedAnswerUnderstanding(
            userAnswer = _uiState.value.typedAnswerInput,
            expectedAnswer = expected
        )
        _uiState.update { st ->
            val updatedWrong = if (
                (eval.verdict == TypedUnderstandingVerdict.UNKNOWN || eval.verdict == TypedUnderstandingVerdict.PARTIAL) &&
                st.sessionWrongCards.none { it.cardId == current.cardId }
            ) {
                st.sessionWrongCards + current
            } else {
                st.sessionWrongCards
            }
            st.copy(
                isAnswerRevealed = true,
                typedEvaluation = eval,
                recommendedRating = eval.recommendedRating,
                sessionWrongCards = updatedWrong
            )
        }
    }

    fun submitDontKnowQuick() {
        _uiState.update { it.copy(typedAnswerInput = "") }
        submitTypedAnswer()
    }

    fun toggleMarkCurrentCard() {
        val current = _uiState.value.dueCards.firstOrNull() ?: return
        _uiState.update { st ->
            val isAlreadyMarked = current.cardId in st.markedCardIds
            val updatedMarked = if (isAlreadyMarked) {
                st.markedCardIds - current.cardId
            } else {
                st.markedCardIds + current.cardId
            }
            val filtered = if (st.studyFilterMode == "marked_only") {
                resolveEffectiveDueCards(
                    rawDue = st.rawDueCards,
                    filterMode = st.studyFilterMode,
                    sessionWrong = st.sessionWrongCards,
                    markedIds = updatedMarked,
                    buriedIds = st.buriedCardIds,
                    interleavedShuffle = st.isInterleavedShuffleEnabled,
                    questionTypeFilter = st.questionTypeFilter
                )
            } else {
                st.dueCards
            }
            st.copy(
                markedCardIds = updatedMarked,
                dueCards = filtered,
                statusBannerMessage = if (isAlreadyMarked) "☆ 별표 표시를 해제했습니다." else "⭐ 별표 카드로 저장했습니다!",
                isErrorBanner = false
            )
        }
    }

    fun buryCurrentCardToday() {
        val current = _uiState.value.dueCards.firstOrNull() ?: return
        _uiState.update { st ->
            val updatedBuried = st.buriedCardIds + current.cardId
            val filtered = resolveEffectiveDueCards(
                rawDue = st.rawDueCards,
                filterMode = st.studyFilterMode,
                sessionWrong = st.sessionWrongCards,
                markedIds = st.markedCardIds,
                buriedIds = updatedBuried,
                interleavedShuffle = st.isInterleavedShuffleEnabled
            )
            st.copy(
                buriedCardIds = updatedBuried,
                dueCards = filtered,
                isAnswerRevealed = false,
                typedAnswerInput = "",
                typedEvaluation = null,
                recommendedRating = null,
                selectedQuizOption = null,
                hintStep = 0,
                hintText = null,
                quizOptions = buildQuizOptionsForCurrentCard(filtered),
                statusBannerMessage = "💤 이 카드를 오늘 하루 숨겼습니다.",
                isErrorBanner = false
            )
        }
    }

    fun updateNewCardFrontInput(text: String) {
        _uiState.update { it.copy(newCardFrontInput = text) }
    }

    fun updateNewCardBackInput(text: String) {
        _uiState.update { it.copy(newCardBackInput = text) }
    }

    fun insertClozeTemplateIntoFront() {
        _uiState.update { st ->
            val prefix = if (st.newCardFrontInput.isBlank()) "" else "${st.newCardFrontInput.trimEnd()} "
            st.copy(newCardFrontInput = "${prefix}{{c1::빈칸정답}}")
        }
    }

    fun addCustomCardDirect() {
        val st = _uiState.value
        val front = st.newCardFrontInput.trim()
        val back = st.newCardBackInput.trim()
        if (front.isEmpty() || back.isEmpty()) {
            _uiState.update {
                it.copy(
                    statusBannerMessage = "✏️ 앞면(질문/빈칸)과 뒷면(정답)을 모두 입력해 주세요.",
                    isErrorBanner = true
                )
            }
            return
        }
        viewModelScope.launch {
            val targetDeckName = st.customDeckTitle.ifBlank {
                st.decks.firstOrNull { d -> d.id == st.selectedDeckId }?.name ?: "✍️ 내 직접 추가 단어장"
            }
            val noteType = if (Fsrs5Engine.extractClozeOrdinals(front).isNotEmpty()) "cloze" else "basic"
            val createdDeckId = dao.createDeckWithGeneratedCards(
                deckName = targetDeckName,
                description = "User Direct Added Cards",
                category = st.selectedCategoryOverride ?: "general",
                sourceFilename = "user_direct_input",
                cards = listOf(
                    SourcedCard(
                        spec = GeneratedCardSpec(
                            noteType = noteType,
                            frontText = front,
                            backText = back,
                            tags = listOf("direct"),
                            rationale = "직접 추가"
                        ),
                        pattern = "definition",
                        sourcePage = 1,
                        sourceExcerpt = front
                    )
                )
            )
            _uiState.update {
                it.copy(
                    selectedDeckId = createdDeckId,
                    newCardFrontInput = "",
                    newCardBackInput = "",
                    statusBannerMessage = "✅ 새 카드가 '$targetDeckName'에 추가되었습니다!",
                    isErrorBanner = false
                )
            }
            refreshWorkspace(deckId = createdDeckId)
        }
    }

    fun refreshWorkspace(deckId: Long? = _uiState.value.selectedDeckId) {
        viewModelScope.launch {
            val nowSec = System.currentTimeMillis() / 1000L
            var decks = dao.listDecks()
            if (decks.isEmpty()) {
                val starterCards = BuiltInCurriculumCatalog.buildCollectionCards(
                    collectionId = "hanja-grade:8geup",
                    difficultyLevel = "mixed",
                    targetCount = 1000
                )
                if (starterCards.isNotEmpty()) {
                    dao.createDeckWithGeneratedCards(
                        deckName = "🎁 무료 기초 한자 8급",
                        description = "BrainDeck Free Starter Pack",
                        category = "language",
                        sourceFilename = "pack.free.starter_k12",
                        cards = starterCards
                    )
                    decks = dao.listDecks()
                }
            }
            val rawDue = dao.getDueCards(nowEpochSec = nowSec, deckId = deckId)
            _uiState.update { st ->
                val totalCards = rawDue.size.coerceAtLeast(1)
                val newCount = rawDue.count { it.state.equals("new", ignoreCase = true) }
                val learnCount = rawDue.count { it.state.equals("learning", ignoreCase = true) || it.state.equals("relearning", ignoreCase = true) }
                val revCount = rawDue.count { it.state.equals("review", ignoreCase = true) }
                val plan = AnkiStudyPlannerEngine.computeStudyPlan(
                    totalCards = totalCards,
                    newCount = newCount,
                    learningCount = learnCount,
                    reviewDueCount = revCount,
                    targetDays = st.targetDays
                )
                val filtered = resolveEffectiveDueCards(
                    rawDue = rawDue,
                    filterMode = st.studyFilterMode,
                    sessionWrong = st.sessionWrongCards,
                    markedIds = st.markedCardIds,
                    buriedIds = st.buriedCardIds,
                    interleavedShuffle = st.isInterleavedShuffleEnabled
                )
                val quizOpts = buildQuizOptionsForCurrentCard(filtered, rawDue)
                st.copy(
                    selectedDeckId = deckId,
                    decks = decks,
                    rawDueCards = rawDue,
                    dueCards = filtered,
                    studyPlan = plan,
                    isAnswerRevealed = false,
                    typedAnswerInput = "",
                    typedEvaluation = null,
                    recommendedRating = null,
                    selectedQuizOption = null,
                    hintStep = 0,
                    hintText = null,
                    isQuizModeOpen = st.ageTier == "junior",
                    quizOptions = quizOpts,
                    canUndoLastReview = lastUndoSnapshot != null
                )
            }
        }
    }

    fun selectAgeTier(tier: String) {
        completeOnboarding(tier)
    }

    fun toggleQuizMode() {
        _uiState.update {
            val opts = if (it.quizOptions.isEmpty()) buildQuizOptionsForCurrentCard(it.dueCards) else it.quizOptions
            it.copy(isQuizModeOpen = !it.isQuizModeOpen, quizOptions = opts)
        }
    }

    fun undoLastReview() {
        val snapshot = lastUndoSnapshot ?: run {
            _uiState.update {
                it.copy(
                    statusBannerMessage = "↩️ 되돌릴 최근 복습 기록이 없습니다.",
                    isErrorBanner = true
                )
            }
            return
        }
        viewModelScope.launch {
            dao.updateCard(snapshot)
            lastUndoSnapshot = null
            _uiState.update {
                it.copy(
                    canUndoLastReview = false,
                    statusBannerMessage = "↩️ 방금 평가를 취소했습니다.",
                    isErrorBanner = false
                )
            }
            refreshWorkspace()
        }
    }

    fun resetStudyProgress() {
        val targetDeckId = _uiState.value.selectedDeckId
        viewModelScope.launch {
            val nowSec = System.currentTimeMillis() / 1000L
            val resetCount = dao.resetCardsProgress(nowEpochSec = nowSec, deckId = targetDeckId)
            lastUndoSnapshot = null
            _uiState.update {
                it.copy(
                    studyFilterMode = "all",
                    questionTypeFilter = "all",
                    sessionWrongCards = emptyList(),
                    markedCardIds = emptySet(),
                    buriedCardIds = emptySet(),
                    canUndoLastReview = false,
                    statusBannerMessage = "🔄 학습 초기화 완료: ${resetCount}장의 카드가 초기 상태(새 카드 1번)로 복원되었습니다!",
                    isErrorBanner = false
                )
            }
            refreshWorkspace(deckId = targetDeckId)
        }
    }

    fun purchaseTop3Bundle() {
        val lockedPaid = BrainPackStoreCatalog.products.filter { !it.isFreeStarter && it.packId !in _uiState.value.unlockedPackIds }
        val top3 = lockedPaid.take(3)
        if (top3.isEmpty()) return
        val quote = BrainPackStoreCatalog.calculateBundleQuote(
            packIds = top3.map { it.packId },
            unlockedPackIds = _uiState.value.unlockedPackIds
        )
        viewModelScope.launch {
            var lastDeckId: Long? = null
            for (product in top3) {
                val targetCap = maxOf(1000, product.estimatedCardCount)
                val cards = if (product.linkKind == "textbook") {
                    BuiltInCurriculumCatalog.buildExamScopeCards(
                        textbookId = product.primaryRefId,
                        selectedUnitIds = emptySet(),
                        difficultyLevel = "mixed",
                        targetCount = targetCap
                    )
                } else {
                    BuiltInCurriculumCatalog.buildCollectionCards(
                        collectionId = product.primaryRefId,
                        difficultyLevel = "mixed",
                        targetCount = targetCap
                    )
                }
                if (cards.isNotEmpty()) {
                    lastDeckId = dao.createDeckWithGeneratedCards(
                        deckName = product.title,
                        description = "BrainPack Bundle (${product.packId})",
                        category = product.category,
                        sourceFilename = product.packId,
                        cards = cards
                    )
                }
            }
            _uiState.update { state ->
                state.copy(
                    activeTab = "study",
                    selectedDeckId = lastDeckId,
                    unlockedPackIds = state.unlockedPackIds + top3.map { it.packId },
                    statusBannerMessage = "🎁 3팩 15% 할인(₩${quote.finalPriceKrw}) 장착 완료!",
                    isErrorBanner = false
                )
            }
            refreshWorkspace(deckId = lastDeckId)
        }
    }

    fun selectCategoryOverride(category: String?) {
        _uiState.update { it.copy(selectedCategoryOverride = category) }
    }

    fun updateCustomDeckTitle(title: String) {
        _uiState.update { it.copy(customDeckTitle = title) }
    }

    fun toggleExamUnit(unitId: String) {
        _uiState.update { state ->
            val updated = if (unitId in state.selectedUnitIds) {
                state.selectedUnitIds - unitId
            } else {
                state.selectedUnitIds + unitId
            }
            state.copy(selectedUnitIds = updated)
        }
    }

    fun selectStarterCollection(collectionId: String) {
        _uiState.update { it.copy(selectedCollectionId = collectionId) }
    }

    fun selectStoreCategory(category: String) {
        _uiState.update { it.copy(selectedStoreCategory = category) }
    }

    fun purchaseBrainPack(packId: String) {
        val product = BrainPackStoreCatalog.getProductById(packId) ?: return
        viewModelScope.launch {
            val targetCap = maxOf(1000, product.estimatedCardCount)
            val cards = if (product.linkKind == "textbook") {
                BuiltInCurriculumCatalog.buildExamScopeCards(
                    textbookId = product.primaryRefId,
                    selectedUnitIds = emptySet(),
                    difficultyLevel = "mixed",
                    targetCount = targetCap
                )
            } else {
                BuiltInCurriculumCatalog.buildCollectionCards(
                    collectionId = product.primaryRefId,
                    difficultyLevel = "mixed",
                    targetCount = targetCap
                )
            }

            var createdDeckId: Long? = null
            if (cards.isNotEmpty()) {
                createdDeckId = dao.createDeckWithGeneratedCards(
                    deckName = product.title,
                    description = "BrainPack (${product.packId})",
                    category = product.category,
                    sourceFilename = product.packId,
                    cards = cards
                )
            }

            _uiState.update { state ->
                state.copy(
                    activeTab = "study",
                    selectedDeckId = createdDeckId,
                    unlockedPackIds = state.unlockedPackIds + product.packId,
                    statusBannerMessage = "🎉 '${product.title}' 바로 학습을 시작합니다!",
                    isErrorBanner = false
                )
            }
            refreshWorkspace(deckId = createdDeckId)
        }
    }

    fun selectDifficultyLevel(level: String) {
        val valid = if (level in setOf("mixed", "lv1", "lv2", "lv3", "standard")) level else "mixed"
        _uiState.update { it.copy(selectedDifficultyLevel = valid) }
    }

    fun selectTextbook(textbookId: String) {
        val tb = BuiltInCurriculumCatalog.listTextbooks().firstOrNull { it.textbookId == textbookId } ?: return
        val defaultUnits = tb.units.take(2).map { it.unitId }.toSet()
        _uiState.update {
            it.copy(
                selectedTextbookId = textbookId,
                selectedUnitIds = defaultUnits
            )
        }
    }

    fun addCurrentTextbookToCombinedScope() {
        val st = _uiState.value
        val tb = BuiltInCurriculumCatalog.listTextbooks().firstOrNull { it.textbookId == st.selectedTextbookId } ?: return
        val unitIds = st.selectedUnitIds.filter { it.startsWith("${tb.textbookId}:") }.toSet()
            .ifEmpty { tb.units.take(1).map { it.unitId }.toSet() }
        val unitLabels = tb.units.filter { it.unitId in unitIds }.joinToString(", ") { it.unitCodeLabel }
        val item = BuiltInCurriculumCatalog.CombinedScopeItem(
            sourceType = "textbook",
            refId = tb.textbookId,
            unitIds = unitIds,
            label = "${tb.title} ($unitLabels)"
        )
        _uiState.update {
            it.copy(
                combinedExamScopes = it.combinedExamScopes + item,
                statusBannerMessage = "➕ '${item.label}' 범위가 통합 시험범위 바구니에 담겼습니다!",
                isErrorBanner = false
            )
        }
    }

    fun addCurrentCollectionToCombinedScope() {
        val st = _uiState.value
        val col = BuiltInCurriculumCatalog.listCollections().firstOrNull { it.collectionId == st.selectedCollectionId } ?: return
        val item = BuiltInCurriculumCatalog.CombinedScopeItem(
            sourceType = "collection",
            refId = col.collectionId,
            unitIds = emptySet(),
            label = "컬렉션 · ${col.title}"
        )
        _uiState.update {
            it.copy(
                combinedExamScopes = it.combinedExamScopes + item,
                statusBannerMessage = "➕ '${item.label}' 팩이 통합 시험범위 바구니에 담겼습니다!",
                isErrorBanner = false
            )
        }
    }

    fun loadMidtermComboPreset() {
        val preset = listOf(
            BuiltInCurriculumCatalog.CombinedScopeItem(
                sourceType = "textbook",
                refId = "kr.mid1.eng.donga_yoon.2022",
                unitIds = setOf("kr.mid1.eng.donga_yoon.2022:U01", "kr.mid1.eng.donga_yoon.2022:U02"),
                label = "중1 영어 동아(윤) (Lesson 1, Lesson 2)"
            ),
            BuiltInCurriculumCatalog.CombinedScopeItem(
                sourceType = "textbook",
                refId = "kr.mid2.hist.miraeen.2022",
                unitIds = setOf("kr.mid2.hist.miraeen.2022:U01"),
                label = "중2 역사 미래엔 (Ⅰ-1)"
            ),
            BuiltInCurriculumCatalog.CombinedScopeItem(
                sourceType = "collection",
                refId = "hanja-grade:8geup",
                unitIds = emptySet(),
                label = "컬렉션 · 어문회 8급 기초 한자"
            )
        )
        _uiState.update {
            it.copy(
                combinedExamScopes = preset,
                statusBannerMessage = "⚡ 중간고사 다중 과목·단원 조합 예시(3개 범위)가 담겼습니다!",
                isErrorBanner = false
            )
        }
    }

    fun clearCombinedExamScopes() {
        _uiState.update {
            it.copy(
                combinedExamScopes = emptyList(),
                statusBannerMessage = "🗑️ 통합 시험범위 바구니를 비웠습니다.",
                isErrorBanner = false
            )
        }
    }

    fun generateCombinedExamScopeDeck() {
        val state = _uiState.value
        val scopes = if (state.combinedExamScopes.isNotEmpty()) {
            state.combinedExamScopes
        } else {
            val tb = BuiltInCurriculumCatalog.listTextbooks().firstOrNull { it.textbookId == state.selectedTextbookId }
            listOf(
                BuiltInCurriculumCatalog.CombinedScopeItem(
                    sourceType = "textbook",
                    refId = state.selectedTextbookId,
                    unitIds = state.selectedUnitIds,
                    label = tb?.title ?: "교과서 시험범위"
                )
            )
        }
        val cards = BuiltInCurriculumCatalog.buildCombinedExamScopeCards(
            scopes = scopes,
            difficultyLevel = state.selectedDifficultyLevel,
            interleaveShuffle = true,
            targetCount = 1000
        )
        if (cards.isEmpty()) {
            _uiState.update {
                it.copy(
                    statusBannerMessage = "출제범위를 1개 이상 담아주세요.",
                    isErrorBanner = true
                )
            }
            return
        }
        val deckTitle = state.customDeckTitle.ifBlank { "🎯 이번 중간고사 통합 출제범위 랜덤 덱" }
        viewModelScope.launch {
            val deckId = dao.createDeckWithGeneratedCards(
                deckName = deckTitle,
                description = "다중 조합 시험범위 (${scopes.size}개 범위 · ${state.selectedDifficultyLevel})",
                category = "general",
                sourceFilename = "combined_exam_scope",
                cards = cards
            )
            _uiState.update {
                it.copy(
                    activeTab = "study",
                    selectedDeckId = deckId,
                    isInterleavedShuffleEnabled = true,
                    statusBannerMessage = "🎲 '$deckTitle' (${scopes.size}개 범위 조합 · 총 ${cards.size}장 스마트 랜덤 섞기) 학습 시작!",
                    isErrorBanner = false
                )
            }
            refreshWorkspace(deckId = deckId)
        }
    }

    fun generateExamScopeDeck() {
        val state = _uiState.value
        val ent = BrainPackStoreCatalog.checkRefEntitlement(
            targetRefId = state.selectedTextbookId,
            unlockedPackIds = state.unlockedPackIds
        )
        if (!ent.allowed) {
            _uiState.update {
                it.copy(
                    activeTab = "store",
                    statusBannerMessage = "🔒 스토어에서 '${ent.requiredPackTitle}' 팩을 먼저 장착해 주세요.",
                    isErrorBanner = true
                )
            }
            return
        }
        // BuiltInCurriculumCatalog.buildExamScopeDeckPlan compatibility
        val cards = BuiltInCurriculumCatalog.buildExamScopeCards(
            textbookId = state.selectedTextbookId,
            selectedUnitIds = state.selectedUnitIds,
            difficultyLevel = state.selectedDifficultyLevel,
            targetCount = 1000
        )
        if (cards.isEmpty()) {
            _uiState.update {
                it.copy(
                    statusBannerMessage = "단원을 1개 이상 선택해 주세요.",
                    isErrorBanner = true
                )
            }
            return
        }
        val tb = BuiltInCurriculumCatalog.listTextbooks().firstOrNull { it.textbookId == state.selectedTextbookId }
        val deckTitle = state.customDeckTitle.ifBlank { "🎯 ${tb?.title ?: "교과서"} 시험범위" }
        viewModelScope.launch {
            val deckId = dao.createDeckWithGeneratedCards(
                deckName = deckTitle,
                description = "시험범위 (${state.selectedTextbookId})",
                category = tb?.subjectCode ?: "language",
                sourceFilename = state.selectedTextbookId,
                cards = cards
            )
            _uiState.update {
                it.copy(
                    activeTab = "study",
                    selectedDeckId = deckId,
                    statusBannerMessage = "🎯 '$deckTitle' (${cards.size}장) 학습 시작!",
                    isErrorBanner = false
                )
            }
            refreshWorkspace(deckId = deckId)
        }
    }

    fun generateCollectionDeck() {
        val state = _uiState.value
        val ent = BrainPackStoreCatalog.checkRefEntitlement(
            targetRefId = state.selectedCollectionId,
            unlockedPackIds = state.unlockedPackIds
        )
        if (!ent.allowed) {
            _uiState.update {
                it.copy(
                    activeTab = "store",
                    statusBannerMessage = "🔒 스토어에서 '${ent.requiredPackTitle}' 팩을 먼저 장착해 주세요.",
                    isErrorBanner = true
                )
            }
            return
        }
        // BuiltInCurriculumCatalog.buildCollectionDeckPlan compatibility
        val cards = BuiltInCurriculumCatalog.buildCollectionCards(
            collectionId = state.selectedCollectionId,
            difficultyLevel = state.selectedDifficultyLevel,
            targetCount = 1000
        )
        if (cards.isEmpty()) return
        val colMeta = BuiltInCurriculumCatalog.listCollections().firstOrNull { it.collectionId == state.selectedCollectionId }
        val deckTitle = state.customDeckTitle.ifBlank { colMeta?.title ?: state.selectedCollectionId }
        viewModelScope.launch {
            val deckId = dao.createDeckWithGeneratedCards(
                deckName = deckTitle,
                description = "컬렉션 (${state.selectedCollectionId})",
                category = colMeta?.category ?: "language",
                sourceFilename = state.selectedCollectionId,
                cards = cards
            )
            _uiState.update {
                it.copy(
                    activeTab = "study",
                    selectedDeckId = deckId,
                    statusBannerMessage = "📚 '$deckTitle' (${cards.size}장) 학습 시작!",
                    isErrorBanner = false
                )
            }
            refreshWorkspace(deckId = deckId)
        }
    }

    fun ingestDocument(uri: Uri, filename: String, mimeType: String?) {
        viewModelScope.launch {
            val selectedModel = _uiState.value.selectedOllamaCloudModel
            val aiDecision = ReaV56Engine.resolveSmartAiEngine(
                taskType = "ocr_extract",
                offlineOnly = selectedModel == "local_rule",
                manualOverride = selectedModel
            )
            val modelLabel = aiDecision.uiLabel
            _uiState.update {
                it.copy(
                    activeTab = "create",
                    isIngesting = true,
                    statusBannerMessage = "⏳ '$filename' ($modelLabel) 카드 추출 중...",
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
                    deckTitleOverride = current.customDeckTitle.takeIf { it.isNotBlank() },
                    ollamaCloudModel = aiDecision.selectedModel.ifBlank { current.selectedOllamaCloudModel }
                )
                val banner = if (plan.status == "OK") {
                    "✅ [$modelLabel] ${plan.cards.size}장의 카드를 찾았습니다."
                } else {
                    "추출할 텍스트가 부족합니다 (${plan.errorCode ?: "no_cards"})."
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
                        statusBannerMessage = "처리 실패: ${e.message}",
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
            state.copy(previewPlan = currentPlan.copy(cards = updatedCards))
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
                    description = "Generated from ${state.previewFilename}",
                    category = preview.category,
                    sourceFilename = state.previewFilename,
                    cards = preview.cards
                )
                _uiState.update {
                    it.copy(
                        activeTab = "study",
                        selectedDeckId = deckId,
                        previewPlan = null,
                        customDeckTitle = "",
                        statusBannerMessage = "🎉 '$deckTitle' (${preview.cards.size}장) 저장 완료!",
                        isErrorBanner = false
                    )
                }
                refreshWorkspace(deckId = deckId)
            } catch (e: Exception) {
                _uiState.update {
                    it.copy(
                        statusBannerMessage = "저장 오류: ${e.message}",
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
            val nowMs = System.currentTimeMillis()
            val nowSec = nowMs / 1000L
            val rtMs = max(0L, nowMs - cardShownEpochMs)
            val c4 = ReaV56Engine.applyC4ReviewCalibration(
                rawRating = rating.code,
                responseTimeMs = rtMs,
                baselineRtMsSamples = rtBaselineSamples.toList(),
                consecutiveGoodStreak = consecutiveGoodStreak
            )
            if (rtMs in 300L..60_000L) {
                rtBaselineSamples.add(rtMs)
                if (rtBaselineSamples.size > 20) {
                    rtBaselineSamples.removeAt(0)
                }
            }
            val effectiveRating = Rating.fromCode(c4.effectiveRating)
            consecutiveGoodStreak = if (effectiveRating.code >= 3) consecutiveGoodStreak + 1 else 0

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
                rating = effectiveRating,
                elapsedDays = elapsedDays
            )
            cardShownEpochMs = System.currentTimeMillis()
            val nextDueEpochSec = if (outcome.scheduledDays == 0) {
                nowSec + 600L
            } else {
                nowSec + outcome.scheduledDays.toLong() * 86400L
            }
            val nextQueue = if (outcome.scheduledDays == 0) 1 else 2
            lastUndoSnapshot = CardEntity(
                id = currentCard.cardId,
                noteId = currentCard.noteId,
                deckId = currentCard.deckId,
                ord = currentCard.ord,
                state = currentCard.state,
                queue = currentCard.queue,
                quizStage = currentCard.quizStage,
                consecutiveSuccesses = currentCard.consecutiveSuccesses,
                stability = currentCard.stability,
                difficulty = currentCard.difficulty,
                dueEpochSec = currentCard.dueEpochSec,
                lastReviewEpochSec = currentCard.lastReviewEpochSec,
                reps = currentCard.reps,
                lapses = currentCard.lapses,
                scheduledDays = currentCard.scheduledDays
            )
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
            _uiState.update { st ->
                val updatedWrong = when {
                    rating == Rating.AGAIN || rating == Rating.HARD -> {
                        if (st.sessionWrongCards.none { it.cardId == currentCard.cardId }) {
                            st.sessionWrongCards + currentCard
                        } else {
                            st.sessionWrongCards
                        }
                    }
                    st.studyFilterMode == "wrong_only" && (rating == Rating.GOOD || rating == Rating.EASY) -> {
                        st.sessionWrongCards.filterNot { it.cardId == currentCard.cardId }
                    }
                    else -> st.sessionWrongCards
                }
                val incNewToday = if (currentCard.state.equals("new", ignoreCase = true)) 1 else 0
                st.copy(
                    sessionWrongCards = updatedWrong,
                    newStudiedToday = st.newStudiedToday + incNewToday,
                    statusBannerMessage = null,
                    isErrorBanner = false
                )
            }
            refreshWorkspace()
        }
    }

    override fun onCleared() {
        super.onCleared()
        ingestor.close()
    }

    companion object {
        private const val PREFS_NAME = "braindeck_ux_prefs_v52"
        private const val KEY_ONBOARDING_DONE = "onboarding_done_v52"
        private const val KEY_AGE_TIER = "age_tier_v52"

        fun factory(context: Context): ViewModelProvider.Factory {
            val appContext = context.applicationContext
            return object : ViewModelProvider.Factory {
                @Suppress("UNCHECKED_CAST")
                override fun <T : ViewModel> create(modelClass: Class<T>): T {
                    val db = AnkiStudioDatabase.getInstance(appContext)
                    val ingestor = AndroidDocumentIngestor(appContext.contentResolver)
                    val prefs = appContext.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
                    return AnkiStudioViewModel(db.dao(), ingestor, prefs) as T
                }
            }
        }
    }
}
