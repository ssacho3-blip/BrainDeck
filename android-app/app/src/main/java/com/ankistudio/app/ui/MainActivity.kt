package com.ankistudio.app.ui

import android.content.Intent
import android.net.Uri
import android.os.Bundle
import android.provider.OpenableColumns
import android.speech.tts.TextToSpeech
import androidx.activity.ComponentActivity
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.compose.setContent
import androidx.activity.result.PickVisualMediaRequest
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.LazyRow
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.itemsIndexed
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.FilterChip
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.NavigationBar
import androidx.compose.material3.NavigationBarItem
import androidx.compose.material3.NavigationBarItemDefaults
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.ViewModelProvider
import com.ankistudio.domain.catalog.BrainPackStoreCatalog
import com.ankistudio.domain.catalog.BuiltInCurriculumCatalog
import com.ankistudio.domain.fsrs.Fsrs5Engine
import com.ankistudio.domain.planner.AnkiCardSnapshot
import com.ankistudio.domain.planner.AnkiStudyPlannerEngine
import com.ankistudio.domain.fsrs.Fsrs5Engine.CardMemoryState
import com.ankistudio.domain.fsrs.Fsrs5Engine.Rating
import com.ankistudio.domain.quiz.AdaptiveQuizEngine
import com.ankistudio.domain.rea.ReaV56Engine
import com.ankistudio.domain.quiz.AdaptiveQuizEngine.TypedUnderstandingVerdict
import java.util.Locale

// Toss / 말해보카 / 듀오링고 스타일 클린 라이트 컬러 시스템 (네온 제거 + WCAG AA 4.5:1 명도비 준수)
private val TossCleanLightColors = lightColorScheme(
    primary = Color(0xFF1B64DA),       // Toss Accessible Deep Blue (5.3:1 on White)
    onPrimary = Color(0xFFFFFFFF),
    secondary = Color(0xFF008A50),     // Accessible Emerald Green
    background = Color(0xFFF2F4F6),    // Soft Warm Off-White Background
    surface = Color(0xFFFFFFFF),       // Crisp Pure White Card Surface
    onBackground = Color(0xFF191F28),  // Deep Charcoal Primary Text
    onSurface = Color(0xFF191F28),
    surfaceVariant = Color(0xFFF9FAFB)
)

private val TextPrimary = Color(0xFF191F28)
private val TextSecondary = Color(0xFF4E5968)
private val TextMuted = Color(0xFF6B7684)
private val TossBlue = Color(0xFF1B64DA)
private val TossBlueSoft = Color(0xFFE8F3FF)
private val MintGreen = Color(0xFF008A50)
private val MintGreenSoft = Color(0xFFE8FAF0)
private val CoralRed = Color(0xFFBE123C)
private val CoralRedSoft = Color(0xFFFFF0F0)

private val CATEGORY_LABELS = listOf(
    "law" to "법학",
    "medical" to "의학",
    "engineering" to "공학",
    "language" to "어학",
    "exam" to "수험"
)

private val NAV_TABS = listOf(
    Triple("study", "🏠", "학습"),
    Triple("curriculum", "🏫", "시험·급수"),
    Triple("create", "➕", "만들기"),
    Triple("store", "🛒", "스토어"),
    Triple("stats", "📊", "내 정보")
)

class MainActivity : ComponentActivity() {

    private lateinit var viewModel: AnkiStudioViewModel
    private var tts: TextToSpeech? = null

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        tts = TextToSpeech(this) { status ->
            if (status == TextToSpeech.SUCCESS) {
                tts?.language = Locale.KOREAN
            }
        }

        viewModel = ViewModelProvider(
            this,
            AnkiStudioViewModel.factory(applicationContext)
        )[AnkiStudioViewModel::class.java]

        if (savedInstanceState == null) {
            handleIncomingShareIntent(intent)
        }

        setContent {
            MaterialTheme(colorScheme = TossCleanLightColors) {
                val state by viewModel.uiState.collectAsState()

                val photoPickerLauncher = rememberLauncherForActivityResult(
                    contract = ActivityResultContracts.PickVisualMedia()
                ) { uri: Uri? ->
                    if (uri != null) {
                        val name = resolveDisplayName(uri) ?: "photo_study.jpg"
                        val mime = contentResolver.getType(uri) ?: "image/jpeg"
                        viewModel.ingestDocument(uri, name, mime)
                    }
                }

                val pdfPickerLauncher = rememberLauncherForActivityResult(
                    contract = ActivityResultContracts.OpenDocument()
                ) { uri: Uri? ->
                    if (uri != null) {
                        val name = resolveDisplayName(uri) ?: "lecture_document.pdf"
                        val mime = contentResolver.getType(uri) ?: "application/pdf"
                        viewModel.ingestDocument(uri, name, mime)
                    }
                }

                AnkiStudioScreen(
                    state = state,
                    onPickPhoto = {
                        photoPickerLauncher.launch(
                            PickVisualMediaRequest(ActivityResultContracts.PickVisualMedia.ImageOnly)
                        )
                    },
                    onPickPdf = {
                        pdfPickerLauncher.launch(arrayOf("application/pdf", "image/*"))
                    },
                    onSelectTab = viewModel::selectTab,
                    onOpenOnboarding = viewModel::openOnboardingModeSelector,
                    onCompleteOnboarding = viewModel::completeOnboarding,
                    onSelectDeckForStudy = viewModel::selectDeckForStudy,
                    onSelectAgeTier = viewModel::selectAgeTier,
                    onUndoLastReview = viewModel::undoLastReview,
                    onResetStudyProgress = viewModel::resetStudyProgress,
                    onToggleQuizMode = viewModel::toggleQuizMode,
                    onSetStudyFilterMode = viewModel::setStudyFilterMode,
                    onSetQuestionTypeFilter = viewModel::setQuestionTypeFilter,
                    onStartWrongOnlyRetry = viewModel::startWrongOnlyRetrySession,
                    onUpdateTypedAnswer = viewModel::updateTypedAnswerInput,
                    onSubmitTypedAnswer = viewModel::submitTypedAnswer,
                    onOverrideTypedAnswerCorrect = viewModel::overrideTypedAnswerCorrect,
                    onSubmitDontKnowQuick = viewModel::submitDontKnowQuick,
                    onToggleMarkCard = viewModel::toggleMarkCurrentCard,
                    onBuryCardToday = viewModel::buryCurrentCardToday,
                    onSpeakText = { textToSpeak ->
                        val clean = textToSpeak.replace(Regex("[【】\\[\\]]"), " ")
                        val hasKorean = Regex("[가-힣]").containsMatchIn(clean)
                        tts?.language = if (hasKorean) Locale.KOREAN else Locale.US
                        tts?.speak(clean, TextToSpeech.QUEUE_FLUSH, null, "braindeck_tts")
                    },
                    onUpdateNewCardFront = viewModel::updateNewCardFrontInput,
                    onUpdateNewCardBack = viewModel::updateNewCardBackInput,
                    onInsertClozeTemplate = viewModel::insertClozeTemplateIntoFront,
                    onAddCustomCardDirect = viewModel::addCustomCardDirect,
                    onPurchaseTop3Bundle = viewModel::purchaseTop3Bundle,
                    onSelectCategory = viewModel::selectCategoryOverride,
                    onSelectOllamaCloudModel = viewModel::selectOllamaCloudModel,
                    onDeckTitleChange = viewModel::updateCustomDeckTitle,
                    onToggleExamUnit = viewModel::toggleExamUnit,
                    onSelectCollection = viewModel::selectStarterCollection,
                    onSelectStoreCategory = viewModel::selectStoreCategory,
                    onPurchaseBrainPack = viewModel::purchaseBrainPack,
                    onGenerateExamScopeDeck = viewModel::generateExamScopeDeck,
                    onGenerateCollectionDeck = viewModel::generateCollectionDeck,
                    onToggleInterleavedShuffle = viewModel::toggleInterleavedShuffle,
                    onRequestHint = viewModel::requestProgressiveHint,
                    onSelectQuizOption = viewModel::submitMultipleChoiceOption,
                    onSelectDifficultyLevel = viewModel::selectDifficultyLevel,
                    onSelectTextbook = viewModel::selectTextbook,
                    onAddTextbookToCombo = viewModel::addCurrentTextbookToCombinedScope,
                    onAddCollectionToCombo = viewModel::addCurrentCollectionToCombinedScope,
                    onLoadMidtermComboPreset = viewModel::loadMidtermComboPreset,
                    onClearComboScopes = viewModel::clearCombinedExamScopes,
                    onGenerateCombinedExamDeck = viewModel::generateCombinedExamScopeDeck,
                    onUpdatePreviewCard = viewModel::updatePreviewCard,
                    onRemovePreviewCard = viewModel::removePreviewCard,
                    onSavePreviewDeck = viewModel::savePreviewAsDeck,
                    onApplyStudyPlan = viewModel::applyStudyPlan,
                    onIncreaseDailyNewQuota = viewModel::increaseDailyNewQuota,
                    onSetStageFilter = viewModel::setStageFilter,
                    onToggleDeckExplorer = viewModel::toggleDeckExplorer,
                    onUpdateExplorerQuery = viewModel::updateExplorerQuery,
                    onSetExplorerBucket = viewModel::setExplorerBucketFilter,
                    onJumpToExplorerCard = viewModel::jumpToCardFromExplorer,
                    onRevealAnswer = viewModel::revealAnswer,
                    onRateCard = viewModel::submitReviewRating
                )
            }
        }
    }

    override fun onDestroy() {
        tts?.stop()
        tts?.shutdown()
        super.onDestroy()
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        setIntent(intent)
        handleIncomingShareIntent(intent)
    }

    private fun handleIncomingShareIntent(intent: Intent?) {
        if (intent?.action == Intent.ACTION_SEND) {
            @Suppress("DEPRECATION")
            val sharedUri = intent.getParcelableExtra<Uri>(Intent.EXTRA_STREAM) ?: return
            val name = resolveDisplayName(sharedUri) ?: "shared_study_material"
            val mime = intent.type ?: contentResolver.getType(sharedUri)
            viewModel.ingestDocument(sharedUri, name, mime)
        }
    }

    private fun resolveDisplayName(uri: Uri): String? {
        return contentResolver.query(uri, null, null, null, null)?.use { cursor ->
            val nameIndex = cursor.getColumnIndex(OpenableColumns.DISPLAY_NAME)
            if (nameIndex >= 0 && cursor.moveToFirst()) {
                cursor.getString(nameIndex)
            } else {
                null
            }
        }
    }
}

@Composable
fun AnkiStudioScreen(
    state: AnkiStudioUiState,
    onPickPhoto: () -> Unit,
    onPickPdf: () -> Unit,
    onSelectTab: (String) -> Unit = {},
    onOpenOnboarding: () -> Unit = {},
    onCompleteOnboarding: (String) -> Unit = {},
    onSelectDeckForStudy: (Long?) -> Unit = {},
    onSelectAgeTier: (String) -> Unit = {},
    onUndoLastReview: () -> Unit = {},
    onResetStudyProgress: () -> Unit = {},
    onToggleQuizMode: () -> Unit = {},
    onSetStudyFilterMode: (String) -> Unit = {},
    onSetQuestionTypeFilter: (String) -> Unit = {},
    onStartWrongOnlyRetry: () -> Unit = {},
    onUpdateTypedAnswer: (String) -> Unit = {},
    onSubmitTypedAnswer: () -> Unit = {},
    onOverrideTypedAnswerCorrect: () -> Unit = {},
    onSubmitDontKnowQuick: () -> Unit = {},
    onToggleMarkCard: () -> Unit = {},
    onBuryCardToday: () -> Unit = {},
    onSpeakText: (String) -> Unit = {},
    onUpdateNewCardFront: (String) -> Unit = {},
    onUpdateNewCardBack: (String) -> Unit = {},
    onInsertClozeTemplate: () -> Unit = {},
    onAddCustomCardDirect: () -> Unit = {},
    onPurchaseTop3Bundle: () -> Unit = {},
    onSelectCategory: (String?) -> Unit,
    onSelectOllamaCloudModel: (String) -> Unit = {},
    onDeckTitleChange: (String) -> Unit,
    onToggleExamUnit: (String) -> Unit,
    onSelectCollection: (String) -> Unit,
    onSelectStoreCategory: (String) -> Unit = {},
    onPurchaseBrainPack: (String) -> Unit = {},
    onGenerateExamScopeDeck: () -> Unit,
    onGenerateCollectionDeck: () -> Unit,
    onToggleInterleavedShuffle: () -> Unit = {},
    onRequestHint: () -> Unit = {},
    onSelectQuizOption: (String) -> Unit = {},
    onSelectDifficultyLevel: (String) -> Unit = {},
    onSelectTextbook: (String) -> Unit = {},
    onAddTextbookToCombo: () -> Unit = {},
    onAddCollectionToCombo: () -> Unit = {},
    onLoadMidtermComboPreset: () -> Unit = {},
    onClearComboScopes: () -> Unit = {},
    onGenerateCombinedExamDeck: () -> Unit = {},
    onUpdatePreviewCard: (Int, String, String) -> Unit,
    onRemovePreviewCard: (Int) -> Unit,
    onSavePreviewDeck: () -> Unit,
    onApplyStudyPlan: (Int, Int?) -> Unit = { _, _ -> },
    onIncreaseDailyNewQuota: (Int) -> Unit = {},
    onSetStageFilter: (String) -> Unit = {},
    onToggleDeckExplorer: (Boolean?) -> Unit = {},
    onUpdateExplorerQuery: (String) -> Unit = {},
    onSetExplorerBucket: (String) -> Unit = {},
    onJumpToExplorerCard: (Long) -> Unit = {},
    onRevealAnswer: () -> Unit,
    onRateCard: (Rating) -> Unit
) {
    // 1. Dedicated Full-Screen Initial Setup (Junior / Teen / Adult Mode Selector)
    if (state.showOnboarding) {
        OnboardingModeSelectorScreen(
            onSelectMode = onCompleteOnboarding
        )
        return
    }

    val tierBadgeLabel = when (state.ageTier) {
        "junior" -> "🌱 주니어"
        "adult" -> "🎓 성인"
        else -> "🚀 중고등"
    }

    // 2. Multi-Page Scaffold with Clean White Bottom Navigation Bar
    Scaffold(
        modifier = Modifier
            .fillMaxSize()
            .background(Color(0xFFF2F4F6)),
        containerColor = Color(0xFFF2F4F6),
        bottomBar = {
            NavigationBar(
                containerColor = Color(0xFFFFFFFF),
                contentColor = TextPrimary,
                tonalElevation = 8.dp
            ) {
                NAV_TABS.forEach { (tabId, icon, label) ->
                    NavigationBarItem(
                        selected = state.activeTab == tabId,
                        onClick = { onSelectTab(tabId) },
                        icon = { Text(text = icon, fontSize = 19.sp) },
                        label = {
                            Text(
                                text = label,
                                fontSize = 11.sp,
                                fontWeight = if (state.activeTab == tabId) FontWeight.ExtraBold else FontWeight.Medium
                            )
                        },
                        colors = NavigationBarItemDefaults.colors(
                            selectedIconColor = TossBlue,
                            selectedTextColor = TossBlue,
                            indicatorColor = TossBlueSoft,
                            unselectedIconColor = TextMuted,
                            unselectedTextColor = TextMuted
                        )
                    )
                }
            }
        }
    ) { innerPadding ->
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(innerPadding)
                .padding(horizontal = 18.dp, vertical = 14.dp)
        ) {
            // Minimal, Clean Toss-Style Top Header Bar
            Row(
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(bottom = 12.dp),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically
            ) {
                Row(
                    verticalAlignment = Alignment.CenterVertically,
                    horizontalArrangement = Arrangement.spacedBy(8.dp)
                ) {
                    Text(
                        text = "브레인덱",
                        fontSize = 21.sp,
                        fontWeight = FontWeight.ExtraBold,
                        color = TextPrimary
                    )
                    Surface(
                        color = TossBlueSoft,
                        shape = RoundedCornerShape(999.dp),
                        modifier = Modifier.clickable { onOpenOnboarding() }
                    ) {
                        Text(
                            text = "$tierBadgeLabel ▾",
                            color = TossBlue,
                            fontSize = 12.sp,
                            fontWeight = FontWeight.Bold,
                            modifier = Modifier.padding(horizontal = 11.dp, vertical = 5.dp)
                        )
                    }
                }
                Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                    if (state.canUndoLastReview) {
                        OutlinedButton(
                            onClick = onUndoLastReview,
                            shape = RoundedCornerShape(12.dp)
                        ) {
                            Text("↩️ 되돌리기", fontSize = 12.sp, color = TextSecondary)
                        }
                    }
                    OutlinedButton(
                        onClick = onResetStudyProgress,
                        shape = RoundedCornerShape(12.dp)
                    ) {
                        Text("🔄 초기화", fontSize = 12.sp, color = CoralRed)
                    }
                }
            }

            // Soft Pastel Toast Banner
            state.statusBannerMessage?.let { msg ->
                Surface(
                    color = if (state.isErrorBanner) CoralRedSoft else TossBlueSoft,
                    shape = RoundedCornerShape(14.dp),
                    modifier = Modifier
                        .fillMaxWidth()
                        .padding(bottom = 12.dp)
                ) {
                    Text(
                        text = msg,
                        color = if (state.isErrorBanner) CoralRed else TossBlue,
                        fontSize = 13.sp,
                        fontWeight = FontWeight.Bold,
                        modifier = Modifier.padding(horizontal = 14.dp, vertical = 11.dp)
                    )
                }
            }

            // Dedicated Single-Focus Page Content per Navigation Tab
            Box(modifier = Modifier.fillMaxSize()) {
                when (state.activeTab) {
                    "study" -> StudyTabScreen(
                        state = state,
                        onSelectDeckForStudy = onSelectDeckForStudy,
                        onToggleQuizMode = onToggleQuizMode,
                        onSetStudyFilterMode = onSetStudyFilterMode,
                        onSetQuestionTypeFilter = onSetQuestionTypeFilter,
                        onToggleInterleavedShuffle = onToggleInterleavedShuffle,
                        onStartWrongOnlyRetry = onStartWrongOnlyRetry,
                        onUpdateTypedAnswer = onUpdateTypedAnswer,
                        onSubmitTypedAnswer = onSubmitTypedAnswer,
                        onOverrideTypedAnswerCorrect = onOverrideTypedAnswerCorrect,
                        onSubmitDontKnowQuick = onSubmitDontKnowQuick,
                        onRequestHint = onRequestHint,
                        onSelectQuizOption = onSelectQuizOption,
                        onToggleMarkCard = onToggleMarkCard,
                        onBuryCardToday = onBuryCardToday,
                        onSpeakText = onSpeakText,
                        onRevealAnswer = onRevealAnswer,
                        onRateCard = onRateCard,
                        onApplyStudyPlan = onApplyStudyPlan,
                        onIncreaseDailyNewQuota = onIncreaseDailyNewQuota,
                        onSetStageFilter = onSetStageFilter,
                        onToggleDeckExplorer = onToggleDeckExplorer,
                        onUpdateExplorerQuery = onUpdateExplorerQuery,
                        onSetExplorerBucket = onSetExplorerBucket,
                        onJumpToExplorerCard = onJumpToExplorerCard,
                        onGoToStore = { onSelectTab("store") },
                        onGoToCurriculum = { onSelectTab("curriculum") }
                    )
                    "curriculum" -> CurriculumTabScreen(
                        state = state,
                        onSelectDifficultyLevel = onSelectDifficultyLevel,
                        onSelectTextbook = onSelectTextbook,
                        onToggleExamUnit = onToggleExamUnit,
                        onGenerateExamScopeDeck = onGenerateExamScopeDeck,
                        onSelectCollection = onSelectCollection,
                        onGenerateCollectionDeck = onGenerateCollectionDeck,
                        onAddTextbookToCombo = onAddTextbookToCombo,
                        onAddCollectionToCombo = onAddCollectionToCombo,
                        onLoadMidtermComboPreset = onLoadMidtermComboPreset,
                        onClearComboScopes = onClearComboScopes,
                        onGenerateCombinedExamDeck = onGenerateCombinedExamDeck
                    )
                    "create" -> CreateDeckTabScreen(
                        state = state,
                        onSelectCategory = onSelectCategory,
                        onSelectOllamaCloudModel = onSelectOllamaCloudModel,
                        onDeckTitleChange = onDeckTitleChange,
                        onPickPhoto = onPickPhoto,
                        onPickPdf = onPickPdf,
                        onUpdateNewCardFront = onUpdateNewCardFront,
                        onUpdateNewCardBack = onUpdateNewCardBack,
                        onInsertClozeTemplate = onInsertClozeTemplate,
                        onAddCustomCardDirect = onAddCustomCardDirect,
                        onUpdatePreviewCard = onUpdatePreviewCard,
                        onRemovePreviewCard = onRemovePreviewCard,
                        onSavePreviewDeck = onSavePreviewDeck
                    )
                    "store" -> StoreTabScreen(
                        state = state,
                        onPurchaseTop3Bundle = onPurchaseTop3Bundle,
                        onSelectStoreCategory = onSelectStoreCategory,
                        onPurchaseBrainPack = onPurchaseBrainPack
                    )
                    "stats" -> StatsAndModeTabScreen(
                        state = state,
                        onSelectDeckForStudy = onSelectDeckForStudy,
                        onSelectAgeTier = onSelectAgeTier,
                        onOpenOnboarding = onOpenOnboarding
                    )
                }
            }
        }
    }
}

@Composable
private fun OnboardingModeSelectorScreen(
    onSelectMode: (String) -> Unit
) {
    val modes = listOf(
        Triple("junior", "🌱 주니어 (초등)", "큰 글씨 · 쉬운 3버튼 · 4지선다 퀴즈"),
        Triple("teen", "🚀 중고등 (내신·수능)", "학교 교과서 시험범위 · 스피드 암기"),
        Triple("adult", "🎓 성인 (자격증·어학·전공)", "핵심 요약 · 정밀 복습 · 고밀도 카드")
    )

    Surface(
        color = Color(0xFFF2F4F6),
        modifier = Modifier.fillMaxSize()
    ) {
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(24.dp),
            verticalArrangement = Arrangement.Center,
            horizontalAlignment = Alignment.CenterHorizontally
        ) {
            Surface(
                color = TossBlueSoft,
                shape = RoundedCornerShape(999.dp)
            ) {
                Text(
                    text = "맞춤 학습 세팅",
                    color = TossBlue,
                    fontSize = 13.sp,
                    fontWeight = FontWeight.Bold,
                    modifier = Modifier.padding(horizontal = 14.dp, vertical = 6.dp)
                )
            }
            Spacer(modifier = Modifier.height(14.dp))
            Text(
                text = "누가 학습하나요?",
                fontSize = 26.sp,
                fontWeight = FontWeight.ExtraBold,
                color = TextPrimary
            )
            Spacer(modifier = Modifier.height(6.dp))
            Text(
                text = "선택한 모드에 맞춰 글자 크기와 퀴즈가 세팅됩니다.",
                fontSize = 14.sp,
                color = TextSecondary,
                textAlign = TextAlign.Center
            )
            Spacer(modifier = Modifier.height(26.dp))

            modes.forEach { (tierCode, title, desc) ->
                Card(
                    colors = CardDefaults.cardColors(containerColor = Color(0xFFFFFFFF)),
                    elevation = CardDefaults.cardElevation(defaultElevation = 2.dp),
                    shape = RoundedCornerShape(22.dp),
                    modifier = Modifier
                        .fillMaxWidth()
                        .padding(vertical = 7.dp)
                        .clickable { onSelectMode(tierCode) }
                ) {
                    Row(
                        modifier = Modifier
                            .fillMaxWidth()
                            .padding(20.dp),
                        horizontalArrangement = Arrangement.SpaceBetween,
                        verticalAlignment = Alignment.CenterVertically
                    ) {
                        Column(
                            verticalArrangement = Arrangement.spacedBy(5.dp),
                            modifier = Modifier.weight(1f)
                        ) {
                            Text(
                                text = title,
                                fontSize = 18.sp,
                                fontWeight = FontWeight.ExtraBold,
                                color = TextPrimary
                            )
                            Text(
                                text = desc,
                                fontSize = 13.sp,
                                color = TextSecondary
                            )
                        }
                        Text(
                            text = "선택 ➔",
                            fontSize = 14.sp,
                            fontWeight = FontWeight.Bold,
                            color = TossBlue
                        )
                    }
                }
            }
        }
    }
}

@Composable
private fun StudyTabScreen(
    state: AnkiStudioUiState,
    onSelectDeckForStudy: (Long?) -> Unit,
    onToggleQuizMode: () -> Unit,
    onSetStudyFilterMode: (String) -> Unit,
    onSetQuestionTypeFilter: (String) -> Unit = {},
    onToggleInterleavedShuffle: () -> Unit = {},
    onStartWrongOnlyRetry: () -> Unit,
    onUpdateTypedAnswer: (String) -> Unit,
    onSubmitTypedAnswer: () -> Unit,
    onOverrideTypedAnswerCorrect: () -> Unit = {},
    onSubmitDontKnowQuick: () -> Unit,
    onRequestHint: () -> Unit = {},
    onSelectQuizOption: (String) -> Unit = {},
    onToggleMarkCard: () -> Unit,
    onBuryCardToday: () -> Unit,
    onSpeakText: (String) -> Unit,
    onRevealAnswer: () -> Unit,
    onRateCard: (Rating) -> Unit,
    onApplyStudyPlan: (Int, Int?) -> Unit = { _, _ -> },
    onIncreaseDailyNewQuota: (Int) -> Unit = {},
    onSetStageFilter: (String) -> Unit = {},
    onToggleDeckExplorer: (Boolean?) -> Unit = {},
    onUpdateExplorerQuery: (String) -> Unit = {},
    onSetExplorerBucket: (String) -> Unit = {},
    onJumpToExplorerCard: (Long) -> Unit = {},
    onGoToStore: () -> Unit,
    onGoToCurriculum: () -> Unit
) {
    val activeRaw = state.rawDueCards.filter { it.cardId !in state.buriedCardIds }
    val dp = state.deckProgress
    val totalDeckCards = dp?.totalCards ?: state.allDeckCards.size.coerceAtLeast(activeRaw.size)
    val qCounts = AdaptiveQuizEngine.computeAnkiQueueCounts(
        activeRaw.map { it.state to it.lapses }
    )
    val wrongCount = buildSet {
        activeRaw.filter {
            it.lapses > 0 ||
                it.state.equals("learning", ignoreCase = true) ||
                it.state.equals("relearning", ignoreCase = true)
        }.forEach { add(it.cardId) }
        state.sessionWrongCards.forEach { if (it.cardId !in state.buriedCardIds) add(it.cardId) }
    }.size

    var showSummarySheet by remember { mutableStateOf(false) }
    var showStudyToolsDrawer by remember { mutableStateOf(false) }
    var revealedIndices by remember { mutableStateOf(setOf<Int>()) }
    val toolsSummary = ReaV56Engine.computeStudyToolsSummary(
        studyFilter = state.studyFilterMode,
        qtypeFilter = state.questionTypeFilter
    )

    LazyColumn(
        modifier = Modifier.fillMaxSize(),
        verticalArrangement = Arrangement.spacedBy(12.dp)
    ) {
        item {
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.spacedBy(8.dp),
                verticalAlignment = Alignment.CenterVertically
            ) {
                LazyRow(
                    horizontalArrangement = Arrangement.spacedBy(8.dp),
                    modifier = Modifier.weight(1f)
                ) {
                    item {
                        FilterChip(
                            selected = state.selectedDeckId == null,
                            onClick = { onSelectDeckForStudy(null) },
                            label = { Text("전체 (${totalDeckCards}장 · 진도 ${dp?.coveragePct ?: 0.0}%)") }
                        )
                    }
                    items(state.decks) { deck ->
                        FilterChip(
                            selected = state.selectedDeckId == deck.id,
                            onClick = { onSelectDeckForStudy(deck.id) },
                            label = { Text(deck.name) }
                        )
                    }
                }
                FilterChip(
                    selected = showStudyToolsDrawer || !toolsSummary.isDefault,
                    onClick = { showStudyToolsDrawer = !showStudyToolsDrawer },
                    label = {
                        Text(
                            if (toolsSummary.isDefault) "🎛️ 필터·도구"
                            else "🎛️ ${toolsSummary.summaryBadgeText}",
                            fontSize = 11.sp,
                            fontWeight = FontWeight.Bold
                        )
                    }
                )
            }
        }

        // Always-Visible D-Day Study Planner & Daily Quota Bar
        item {
            val plan = state.studyPlan
            val remNew = (state.dailyNewLimit - state.newStudiedToday).coerceAtLeast(0)
            Surface(
                color = Color(0xFFEEF2FF),
                shape = RoundedCornerShape(16.dp),
                modifier = Modifier.fillMaxWidth()
            ) {
                Column(
                    modifier = Modifier.padding(horizontal = 14.dp, vertical = 10.dp),
                    verticalArrangement = Arrangement.spacedBy(6.dp)
                ) {
                    Text(
                        text = "📅 D-${state.targetDays} 학습 계획 · 오늘 목표 ${dp?.today?.targetCount ?: state.dueCards.size}장 (새 카드 ${state.dailyNewLimit}장 중 남은 ${remNew}장 · 전체 ${totalDeckCards}장)",
                        fontSize = 12.sp,
                        fontWeight = FontWeight.ExtraBold,
                        color = Color(0xFF1D4ED8)
                    )
                    if (plan != null) {
                        Text(
                            text = "💡 진도 ${plan.newIntakeDays}일 + 총정리 복습 ${plan.consolidationDays}일 · 일평균 약 ${plan.avgDailyMinutes}분 소요",
                            fontSize = 11.sp,
                            color = Color(0xFF1E3A8A)
                        )
                    }
                    LazyRow(
                        horizontalArrangement = Arrangement.spacedBy(6.dp),
                        modifier = Modifier.fillMaxWidth()
                    ) {
                        val dayPresets = listOf(7 to "D-7 단기", 14 to "D-14 집중", 30 to "D-30 표준", 60 to "D-60 완주")
                        items(dayPresets) { (days, label) ->
                            FilterChip(
                                selected = state.targetDays == days,
                                onClick = { onApplyStudyPlan(days, null) },
                                label = { Text(label, fontSize = 11.sp, fontWeight = FontWeight.Bold) }
                            )
                        }
                        val quotaPresets = listOf(20 to "하루 20장", 30 to "하루 30장", 50 to "하루 50장")
                        items(quotaPresets) { (qLimit, qLabel) ->
                            FilterChip(
                                selected = state.dailyNewLimit == qLimit,
                                onClick = { onApplyStudyPlan(state.targetDays, qLimit) },
                                label = { Text(qLabel, fontSize = 11.sp, fontWeight = FontWeight.Bold) }
                            )
                        }
                        item {
                            FilterChip(
                                selected = false,
                                onClick = { onIncreaseDailyNewQuota(15) },
                                label = { Text("➕ 오늘 +15장", fontSize = 11.sp, fontWeight = FontWeight.Bold) }
                            )
                        }
                    }
                }
            }
        }

        // IMPL-V61: 0.5-Second Multi-Dimensional Progress & Mastery Dashboard (Today % + 1,000-Card Coverage % + 4-Tier Maturity Bar + Lv1~Lv4 Stage Filter)
        if (dp != null) {
            item {
                Card(
                    colors = CardDefaults.cardColors(containerColor = Color.White),
                    elevation = CardDefaults.cardElevation(defaultElevation = 1.dp),
                    shape = RoundedCornerShape(16.dp),
                    modifier = Modifier.fillMaxWidth()
                ) {
                    Column(
                        modifier = Modifier.padding(14.dp),
                        verticalArrangement = Arrangement.spacedBy(8.dp)
                    ) {
                        Row(
                            modifier = Modifier.fillMaxWidth(),
                            horizontalArrangement = Arrangement.SpaceBetween,
                            verticalAlignment = Alignment.CenterVertically
                        ) {
                            Text(
                                text = "🎯 오늘 목표: ${dp.today.completedCount}/${dp.today.targetCount}장 완료 (${dp.today.percent}%)",
                                fontSize = 12.sp,
                                fontWeight = FontWeight.ExtraBold,
                                color = TossBlue
                            )
                            Text(
                                text = if (dp.today.remainingCount > 0) "⏱️ 남은 ${dp.today.remainingCount}장 (약 ${dp.today.estimatedRemainingMinutes}분)" else "✅ 오늘 목표 100% 달성!",
                                fontSize = 11.sp,
                                fontWeight = FontWeight.Bold,
                                color = TextSecondary
                            )
                        }
                        Box(
                            modifier = Modifier
                                .fillMaxWidth()
                                .height(8.dp)
                                .background(Color(0xFFE2E8F0), RoundedCornerShape(999.dp))
                        ) {
                            val fillRatio = (dp.today.percent.toFloat() / 100f).coerceIn(0f, 1f)
                            Box(
                                modifier = Modifier
                                    .fillMaxWidth(fillRatio)
                                    .height(8.dp)
                                    .background(TossBlue, RoundedCornerShape(999.dp))
                            )
                        }
                        Row(
                            modifier = Modifier.fillMaxWidth(),
                            horizontalArrangement = Arrangement.SpaceBetween,
                            verticalAlignment = Alignment.CenterVertically
                        ) {
                            Text(
                                text = "📊 전체 진도율 ${dp.coveragePct}% (${dp.touchedCards}/${dp.totalCards}장) · 🧠 마스터리 ${dp.masteryPct}%",
                                fontSize = 12.sp,
                                fontWeight = FontWeight.ExtraBold,
                                color = Color(0xFF047857)
                            )
                            Text(
                                text = if (dp.milestone.cardsToNext > 0) "🏁 ${dp.milestone.nextPct}%까지 ${dp.milestone.cardsToNext}장" else "🎉 100% 달성",
                                fontSize = 11.sp,
                                fontWeight = FontWeight.Bold,
                                color = Color(0xFF0F766E)
                            )
                        }
                        // 4-Color Stacked Maturity Bar (Mature / Young / Learning / Unseen)
                        val activeDen = dp.activeCards.coerceAtLeast(1).toFloat()
                        val wMature = (dp.buckets.mature.toFloat() / activeDen).coerceIn(0f, 1f)
                        val wYoung = (dp.buckets.young.toFloat() / activeDen).coerceIn(0f, 1f)
                        val wLearn = (dp.buckets.learning.toFloat() / activeDen).coerceIn(0f, 1f)
                        val wUnseen = (dp.buckets.unseen.toFloat() / activeDen).coerceIn(0f, 1f)
                        Row(
                            modifier = Modifier
                                .fillMaxWidth()
                                .height(8.dp)
                                .background(Color(0xFFE2E8F0), RoundedCornerShape(999.dp))
                        ) {
                            if (wMature > 0f) {
                                Box(modifier = Modifier.weight(wMature).height(8.dp).background(Color(0xFF10B981)))
                            }
                            if (wYoung > 0f) {
                                Box(modifier = Modifier.weight(wYoung).height(8.dp).background(Color(0xFF3B82F6)))
                            }
                            if (wLearn > 0f) {
                                Box(modifier = Modifier.weight(wLearn).height(8.dp).background(Color(0xFFF59E0B)))
                            }
                            if (wUnseen > 0f) {
                                Box(modifier = Modifier.weight(wUnseen).height(8.dp).background(Color(0xFFE2E8F0)))
                            }
                        }
                        LazyRow(
                            horizontalArrangement = Arrangement.spacedBy(6.dp),
                            modifier = Modifier.fillMaxWidth()
                        ) {
                            item {
                                FilterChip(
                                    selected = state.explorerBucketFilter == "unseen" && state.isDeckExplorerOpen,
                                    onClick = { onSetExplorerBucket("unseen") },
                                    label = { Text("⚪ 미학습 ${dp.buckets.unseen}장", fontSize = 11.sp) }
                                )
                            }
                            item {
                                FilterChip(
                                    selected = state.explorerBucketFilter == "learning" && state.isDeckExplorerOpen,
                                    onClick = { onSetExplorerBucket("learning") },
                                    label = { Text("🟠 학습·오답 ${dp.buckets.learning}장", fontSize = 11.sp) }
                                )
                            }
                            item {
                                FilterChip(
                                    selected = state.explorerBucketFilter == "young" && state.isDeckExplorerOpen,
                                    onClick = { onSetExplorerBucket("young") },
                                    label = { Text("🔵 단기암기 ${dp.buckets.young}장", fontSize = 11.sp) }
                                )
                            }
                            item {
                                FilterChip(
                                    selected = state.explorerBucketFilter == "mature" && state.isDeckExplorerOpen,
                                    onClick = { onSetExplorerBucket("mature") },
                                    label = { Text("🟢 장기마스터 ${dp.buckets.mature}장", fontSize = 11.sp) }
                                )
                            }
                            item {
                                FilterChip(
                                    selected = state.isDeckExplorerOpen,
                                    onClick = { onToggleDeckExplorer(null) },
                                    label = { Text("🔍 전체 카드 진도표·검색", fontSize = 11.sp, fontWeight = FontWeight.Bold) }
                                )
                            }
                        }
                        LazyRow(
                            horizontalArrangement = Arrangement.spacedBy(6.dp),
                            modifier = Modifier.fillMaxWidth()
                        ) {
                            item {
                                FilterChip(
                                    selected = state.stageFilter == "all",
                                    onClick = { onSetStageFilter("all") },
                                    label = { Text("🪜 전체 단계", fontSize = 11.sp, fontWeight = FontWeight.Bold) }
                                )
                            }
                            val stageKeys = listOf("lv1", "lv2", "lv3", "lv4")
                            items(stageKeys) { stKey ->
                                val stInfo = dp.byStage[stKey]
                                val stText = if (stInfo != null) {
                                    "${stInfo.label} (${stInfo.coveragePct.toInt()}% · ${stInfo.touched}/${stInfo.total})"
                                } else {
                                    stKey
                                }
                                FilterChip(
                                    selected = state.stageFilter == stKey,
                                    onClick = { onSetStageFilter(stKey) },
                                    label = { Text(stText, fontSize = 11.sp, fontWeight = FontWeight.Bold) }
                                )
                            }
                        }
                    }
                }
            }
        }

        if (state.isDeckExplorerOpen) {
            val allSnapshots = state.allDeckCards.map { row ->
                val cleanT = AdaptiveQuizEngine.extractCleanTargetAnswer(row.front, row.back)
                AnkiCardSnapshot(
                    cardId = row.cardId.toString(),
                    noteId = row.noteId.toString(),
                    state = row.state,
                    stability = row.stability,
                    difficulty = row.difficulty,
                    reps = row.reps,
                    lapses = row.lapses,
                    dueDays = row.scheduledDays.toInt(),
                    tags = row.tagsCsv.split(",").map { it.trim() }.filter { it.isNotEmpty() },
                    frontText = row.front,
                    backText = row.back,
                    targetAnswer = cleanT.first,
                    extraExplanation = cleanT.second
                )
            }
            val expRes = AnkiStudyPlannerEngine.filterCardsForExplorer(
                cards = allSnapshots,
                query = state.explorerQuery,
                bucketFilter = state.explorerBucketFilter,
                stageFilter = state.explorerStageFilter,
                limit = 40
            )
            item {
                Card(
                    colors = CardDefaults.cardColors(containerColor = Color(0xFFF8FAFC)),
                    shape = RoundedCornerShape(18.dp),
                    modifier = Modifier.fillMaxWidth()
                ) {
                    Column(
                        modifier = Modifier.padding(14.dp),
                        verticalArrangement = Arrangement.spacedBy(8.dp)
                    ) {
                        Row(
                            modifier = Modifier.fillMaxWidth(),
                            horizontalArrangement = Arrangement.SpaceBetween,
                            verticalAlignment = Alignment.CenterVertically
                        ) {
                            Text(
                                text = "🔍 전체 카드 진도표·검색 (${expRes.matchedCount}/${expRes.totalCount}장)",
                                fontSize = 13.sp,
                                fontWeight = FontWeight.ExtraBold,
                                color = Color(0xFF312E81)
                            )
                            OutlinedButton(onClick = { onToggleDeckExplorer(false) }) {
                                Text("닫기", fontSize = 11.sp)
                            }
                        }
                        OutlinedTextField(
                            value = state.explorerQuery,
                            onValueChange = onUpdateExplorerQuery,
                            label = { Text("단어·뜻·예문 검색", fontSize = 12.sp) },
                            singleLine = true,
                            modifier = Modifier.fillMaxWidth()
                        )
                        expRes.cards.take(15).forEachIndexed { idx, snap ->
                            val bKey = AnkiStudyPlannerEngine.classifyCardMaturityBucket(snap)
                            val bLabel = when (bKey) {
                                "mature" -> "🟢 마스터"
                                "young" -> "🔵 단기"
                                "learning" -> "🟠 학습"
                                else -> "⚪ 미학습"
                            }
                            Row(
                                modifier = Modifier
                                    .fillMaxWidth()
                                    .background(Color.White, RoundedCornerShape(10.dp))
                                    .clickable { snap.cardId.toLongOrNull()?.let { onJumpToExplorerCard(it) } }
                                    .padding(horizontal = 10.dp, vertical = 8.dp),
                                horizontalArrangement = Arrangement.SpaceBetween,
                                verticalAlignment = Alignment.CenterVertically
                            ) {
                                Text(
                                    text = "$bLabel #${idx + 1} ${snap.frontText.take(36)} ➔ ${snap.targetAnswer.take(22)}",
                                    fontSize = 12.sp,
                                    fontWeight = FontWeight.Bold,
                                    color = TextPrimary,
                                    modifier = Modifier.weight(1f)
                                )
                                Text(
                                    text = "🎯 풀기",
                                    fontSize = 11.sp,
                                    fontWeight = FontWeight.ExtraBold,
                                    color = TossBlue
                                )
                            }
                        }
                    }
                }
            }
        }

        if (showStudyToolsDrawer) {
            // Study Filter Mode Bar (전체 학습 · 🔥 오답·모르는 것만 · ⭐ 별표 카드만)
            item {
                LazyRow(
                    horizontalArrangement = Arrangement.spacedBy(8.dp),
                    modifier = Modifier.fillMaxWidth()
                ) {
                    item {
                        FilterChip(
                            selected = state.studyFilterMode == "all",
                            onClick = { onSetStudyFilterMode("all") },
                            label = { Text("📚 전체 학습 (${activeRaw.size})") }
                        )
                    }
                    item {
                        FilterChip(
                            selected = state.studyFilterMode == "wrong_only",
                            onClick = { onSetStudyFilterMode("wrong_only") },
                            label = { Text("🔥 오답·모르는 것만 ($wrongCount)") }
                        )
                    }
                    item {
                        FilterChip(
                            selected = state.studyFilterMode == "marked_only",
                            onClick = { onSetStudyFilterMode("marked_only") },
                            label = { Text("⭐ 별표만 (${state.markedCardIds.size})") }
                        )
                    }
                    item {
                        FilterChip(
                            selected = state.isInterleavedShuffleEnabled,
                            onClick = onToggleInterleavedShuffle,
                            label = {
                                Text(
                                    if (state.isInterleavedShuffleEnabled) "🔀 스마트 랜덤 ON" else "📋 순차 학습"
                                )
                            }
                        )
                    }
                    item {
                        FilterChip(
                            selected = showSummarySheet,
                            onClick = { showSummarySheet = !showSummarySheet },
                            label = { Text("🟥 전자 셀로판지 요약시트") }
                        )
                    }
                }
            }

            // Gate T43: Question-Type Filter Bar (전체 유형 | 단어·어휘만 | 문법·구문만 | 한자·성어만 | 역사·과학·전공)
            item {
                LazyRow(
                    horizontalArrangement = Arrangement.spacedBy(6.dp),
                    modifier = Modifier.fillMaxWidth()
                ) {
                    val qtypeChips = listOf(
                        "all" to "🗂️ 전체 유형",
                        "vocab" to "📘 단어·어휘만",
                        "grammar" to "📐 문법·구문만",
                        "hanja" to "漢字 한자·성어만",
                        "history_sci" to "🏛️ 역사·과학·전공"
                    )
                    items(qtypeChips) { (code, label) ->
                        FilterChip(
                            selected = state.questionTypeFilter == code,
                            onClick = { onSetQuestionTypeFilter(code) },
                            label = { Text(label, fontSize = 11.sp, fontWeight = FontWeight.Bold) }
                        )
                    }
                }
            }
        }

        if (showSummarySheet && activeRaw.isNotEmpty()) {
            val summaryRows = ReaV56Engine.buildSummarySheetRows(
                activeRaw.take(30).map { it.front to it.back }
            )
            item {
                Card(
                    colors = CardDefaults.cardColors(containerColor = Color(0xFFFFF5F5)),
                    shape = RoundedCornerShape(18.dp),
                    modifier = Modifier.fillMaxWidth()
                ) {
                    Column(
                        modifier = Modifier.padding(14.dp),
                        verticalArrangement = Arrangement.spacedBy(8.dp)
                    ) {
                        Row(
                            modifier = Modifier.fillMaxWidth(),
                            horizontalArrangement = Arrangement.SpaceBetween,
                            verticalAlignment = Alignment.CenterVertically
                        ) {
                            Text(
                                "🟥 전자 셀로판지 요약시트 (탭하여 확인)",
                                fontWeight = FontWeight.ExtraBold,
                                fontSize = 13.sp,
                                color = Color(0xFFBE123C)
                            )
                            OutlinedButton(
                                onClick = {
                                    revealedIndices = if (revealedIndices.size == summaryRows.size) {
                                        emptySet()
                                    } else {
                                        summaryRows.map { it.index }.toSet()
                                    }
                                }
                            ) {
                                Text("전체 보기/가리기", fontSize = 11.sp)
                            }
                        }
                        summaryRows.forEach { r ->
                            val isRev = r.index in revealedIndices
                            Row(
                                modifier = Modifier
                                    .fillMaxWidth()
                                    .background(Color.White, RoundedCornerShape(10.dp))
                                    .clickable {
                                        revealedIndices = if (isRev) revealedIndices - r.index else revealedIndices + r.index
                                    }
                                    .padding(horizontal = 10.dp, vertical = 8.dp),
                                horizontalArrangement = Arrangement.SpaceBetween,
                                verticalAlignment = Alignment.CenterVertically
                            ) {
                                Text(
                                    "${r.index}. ${r.prompt}",
                                    fontSize = 12.sp,
                                    fontWeight = FontWeight.Bold,
                                    color = Color(0xFF191F28),
                                    modifier = Modifier.weight(1f)
                                )
                                Box(
                                    modifier = Modifier
                                        .background(
                                            if (isRev) Color(0xFFFFF0F0) else Color(0xFFBE123C),
                                            RoundedCornerShape(8.dp)
                                        )
                                        .padding(horizontal = 10.dp, vertical = 4.dp)
                                ) {
                                    Text(
                                        r.cleanAnswer,
                                        fontSize = 12.sp,
                                        fontWeight = FontWeight.ExtraBold,
                                        color = Color(0xFFBE123C)
                                    )
                                }
                            }
                        }
                    }
                }
            }
        }

        item {
            Card(
                colors = CardDefaults.cardColors(containerColor = Color(0xFFFFFFFF)),
                elevation = CardDefaults.cardElevation(defaultElevation = 2.dp),
                shape = RoundedCornerShape(24.dp),
                modifier = Modifier.fillMaxWidth()
            ) {
                Column(
                    modifier = Modifier.padding(22.dp),
                    verticalArrangement = Arrangement.spacedBy(16.dp)
                ) {
                    // Anki 3-Color Queue Counter Pills + 4-Choice Quiz Toggle
                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.SpaceBetween,
                        verticalAlignment = Alignment.CenterVertically
                    ) {
                        Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                            Surface(color = TossBlueSoft, shape = RoundedCornerShape(999.dp)) {
                                Text(
                                    text = "새 카드 ${qCounts.newCount}",
                                    fontSize = 11.sp,
                                    fontWeight = FontWeight.ExtraBold,
                                    color = TossBlue,
                                    modifier = Modifier.padding(horizontal = 9.dp, vertical = 5.dp)
                                )
                            }
                            Surface(color = CoralRedSoft, shape = RoundedCornerShape(999.dp)) {
                                Text(
                                    text = "학습·오답 $wrongCount",
                                    fontSize = 11.sp,
                                    fontWeight = FontWeight.ExtraBold,
                                    color = CoralRed,
                                    modifier = Modifier.padding(horizontal = 9.dp, vertical = 5.dp)
                                )
                            }
                            Surface(color = MintGreenSoft, shape = RoundedCornerShape(999.dp)) {
                                Text(
                                    text = "복습 ${qCounts.reviewCount}",
                                    fontSize = 11.sp,
                                    fontWeight = FontWeight.ExtraBold,
                                    color = MintGreen,
                                    modifier = Modifier.padding(horizontal = 9.dp, vertical = 5.dp)
                                )
                            }
                        }
                        OutlinedButton(
                            onClick = onToggleQuizMode,
                            shape = RoundedCornerShape(12.dp)
                        ) {
                            Text(
                                text = if (state.isQuizModeOpen) "기본" else "🎯 퀴즈",
                                fontSize = 11.sp,
                                fontWeight = FontWeight.Bold,
                                color = TossBlue
                            )
                        }
                    }

                    val currentDue = state.dueCards.firstOrNull()
                    if (currentDue == null) {
                        Spacer(modifier = Modifier.height(8.dp))
                        Text(
                            text = if (state.studyFilterMode == "wrong_only") {
                                "🎉 오답·모르는 문제를 모두 정복했어요!"
                            } else {
                                "🎉 오늘 학습을 모두 마쳤어요!"
                            },
                            fontSize = 21.sp,
                            fontWeight = FontWeight.ExtraBold,
                            color = TextPrimary
                        )

                        if (wrongCount > 0 && state.studyFilterMode != "wrong_only") {
                            Surface(
                                color = CoralRedSoft,
                                shape = RoundedCornerShape(16.dp),
                                modifier = Modifier.fillMaxWidth()
                            ) {
                                Column(
                                    modifier = Modifier.padding(16.dp),
                                    verticalArrangement = Arrangement.spacedBy(10.dp)
                                ) {
                                    Text(
                                        text = "🔥 방금 학습 중 모르거나 헷갈린 카드가 ${wrongCount}장 있어요!",
                                        fontSize = 14.sp,
                                        fontWeight = FontWeight.Bold,
                                        color = CoralRed
                                    )
                                    Button(
                                        onClick = onStartWrongOnlyRetry,
                                        colors = ButtonDefaults.buttonColors(
                                            containerColor = CoralRed,
                                            contentColor = Color.White
                                        ),
                                        shape = RoundedCornerShape(14.dp),
                                        modifier = Modifier.fillMaxWidth().height(48.dp)
                                    ) {
                                        Text("🔥 틀린·모르는 ${wrongCount}장만 다시 복습하기", fontWeight = FontWeight.Bold)
                                    }
                                }
                            }
                        } else {
                            Text(
                                text = "새로운 시험범위나 단어를 추가해 볼까요?",
                                fontSize = 14.sp,
                                color = TextSecondary
                            )
                        }

                        Row(
                            horizontalArrangement = Arrangement.spacedBy(10.dp),
                            modifier = Modifier.fillMaxWidth()
                        ) {
                            Button(
                                onClick = onGoToCurriculum,
                                shape = RoundedCornerShape(14.dp),
                                modifier = Modifier.weight(1f).height(48.dp)
                            ) {
                                Text("🏫 시험·급수 덱", fontWeight = FontWeight.Bold)
                            }
                            OutlinedButton(
                                onClick = onGoToStore,
                                shape = RoundedCornerShape(14.dp),
                                modifier = Modifier.weight(1f).height(48.dp)
                            ) {
                                Text("🛒 스토어", fontWeight = FontWeight.Bold)
                            }
                        }
                    } else {
                        val questionDisplay = if (currentDue.noteType == "cloze") {
                            Fsrs5Engine.renderClozeCard(
                                frontText = currentDue.front,
                                ordinal = currentDue.ord,
                                reveal = state.isAnswerRevealed
                            )
                        } else {
                            currentDue.front
                        }

                        val currentQType = AdaptiveQuizEngine.classifyCardQuestionType(
                            frontText = currentDue.front,
                            backText = currentDue.back
                        )
                        val isMarked = currentDue.cardId in state.markedCardIds
                        // In-Card Live Progress Bar & Percentage Header (Always Visible Inside Flashcard)
                        Surface(
                            color = Color(0xFFF8FAFC),
                            shape = RoundedCornerShape(12.dp),
                            modifier = Modifier.fillMaxWidth()
                        ) {
                            Column(
                                modifier = Modifier.padding(horizontal = 12.dp, vertical = 9.dp),
                                verticalArrangement = Arrangement.spacedBy(5.dp)
                            ) {
                                Row(
                                    modifier = Modifier.fillMaxWidth(),
                                    horizontalArrangement = Arrangement.SpaceBetween,
                                    verticalAlignment = Alignment.CenterVertically
                                ) {
                                    Text(
                                        text = "🎯 오늘 진척률 ${dp?.today?.percent ?: 0.0}% (${dp?.today?.completedCount ?: 0}/${dp?.today?.targetCount ?: state.dueCards.size}장 · 현재 ${dp?.today?.currentCardOrdinal ?: 1}번째)",
                                        fontSize = 11.sp,
                                        fontWeight = FontWeight.ExtraBold,
                                        color = TossBlue
                                    )
                                    Text(
                                        text = "📊 전체 진도 ${dp?.coveragePct ?: 0.0}% (${dp?.touchedCards ?: 0}/${dp?.totalCards ?: totalDeckCards}장)",
                                        fontSize = 11.sp,
                                        fontWeight = FontWeight.ExtraBold,
                                        color = Color(0xFF047857)
                                    )
                                }
                                Box(
                                    modifier = Modifier
                                        .fillMaxWidth()
                                        .height(6.dp)
                                        .background(Color(0xFFE2E8F0), RoundedCornerShape(999.dp))
                                ) {
                                    val inCardFill = ((dp?.today?.percent ?: 0.0).toFloat() / 100f).coerceIn(0f, 1f)
                                    Box(
                                        modifier = Modifier
                                            .fillMaxWidth(inCardFill)
                                            .height(6.dp)
                                            .background(TossBlue, RoundedCornerShape(999.dp))
                                    )
                                }
                            }
                        }

                        // Anki Core Action Bar: Question Type Badge + TTS (발음), Hint (힌트), Star (별표), Bury (오늘 숨김)
                        Row(
                            modifier = Modifier.fillMaxWidth(),
                            horizontalArrangement = Arrangement.SpaceBetween,
                            verticalAlignment = Alignment.CenterVertically
                        ) {
                            Text(
                                text = currentQType.badgeLabel,
                                fontSize = 12.sp,
                                color = TossBlue,
                                fontWeight = FontWeight.Bold,
                                modifier = Modifier.weight(1f)
                            )
                            Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                                Surface(
                                    color = if (state.hintStep > 0) Color(0xFFFFF8E6) else Color(0xFFF9FAFB),
                                    shape = RoundedCornerShape(10.dp),
                                    modifier = Modifier.clickable { onRequestHint() }
                                ) {
                                    Text(
                                        text = if (state.hintStep == 0) "💡 힌트" else "💡 힌트 ${state.hintStep}/2",
                                        fontSize = 12.sp,
                                        fontWeight = FontWeight.Bold,
                                        color = if (state.hintStep > 0) Color(0xFFD97706) else TossBlue,
                                        modifier = Modifier.padding(horizontal = 9.dp, vertical = 5.dp)
                                    )
                                }
                                Surface(
                                    color = Color(0xFFF9FAFB),
                                    shape = RoundedCornerShape(10.dp),
                                    modifier = Modifier.clickable {
                                        onSpeakText(if (state.isAnswerRevealed) currentDue.back else questionDisplay)
                                    }
                                ) {
                                    Text(
                                        text = "🔊 발음",
                                        fontSize = 12.sp,
                                        fontWeight = FontWeight.Bold,
                                        color = TextSecondary,
                                        modifier = Modifier.padding(horizontal = 9.dp, vertical = 5.dp)
                                    )
                                }
                                Surface(
                                    color = if (isMarked) Color(0xFFFFF8E6) else Color(0xFFF9FAFB),
                                    shape = RoundedCornerShape(10.dp),
                                    modifier = Modifier.clickable { onToggleMarkCard() }
                                ) {
                                    Text(
                                        text = if (isMarked) "⭐ 별표됨" else "☆ 별표",
                                        fontSize = 12.sp,
                                        fontWeight = FontWeight.Bold,
                                        color = if (isMarked) Color(0xFFD97706) else TextSecondary,
                                        modifier = Modifier.padding(horizontal = 9.dp, vertical = 5.dp)
                                    )
                                }
                                Surface(
                                    color = Color(0xFFF9FAFB),
                                    shape = RoundedCornerShape(10.dp),
                                    modifier = Modifier.clickable { onBuryCardToday() }
                                ) {
                                    Text(
                                        text = "💤 숨김",
                                        fontSize = 12.sp,
                                        fontWeight = FontWeight.Bold,
                                        color = TextSecondary,
                                        modifier = Modifier.padding(horizontal = 9.dp, vertical = 5.dp)
                                    )
                                }
                            }
                        }

                        state.hintText?.let { hintMsg ->
                            Surface(
                                color = Color(0xFFFFF8E6),
                                shape = RoundedCornerShape(12.dp),
                                modifier = Modifier.fillMaxWidth()
                            ) {
                                Text(
                                    text = hintMsg,
                                    fontSize = 13.sp,
                                    fontWeight = FontWeight.Bold,
                                    color = Color(0xFFB45309),
                                    modifier = Modifier.padding(horizontal = 14.dp, vertical = 10.dp)
                                )
                            }
                        }

                        Text(
                            text = questionDisplay,
                            fontSize = if (state.ageTier == "junior") 25.sp else 21.sp,
                            fontWeight = FontWeight.ExtraBold,
                            color = TextPrimary,
                            lineHeight = if (state.ageTier == "junior") 33.sp else 29.sp
                        )

                        val (conciseAnswer, extraExplanation) = AdaptiveQuizEngine.extractCleanTargetAnswer(
                            frontText = currentDue.front,
                            backText = currentDue.back
                        )

                        // Frame 2: 1-Card 1-Mode Active Solve Mode Resolution (Choice OR Typing, never both simultaneously)
                        val activeSolveMode = if (state.isQuizModeOpen) {
                            "choice"
                        } else {
                            AdaptiveQuizEngine.resolveCardSolveMode(
                                solveMode = if (state.ageTier == "junior") "choice" else "adaptive",
                                reps = currentDue.reps,
                                lapses = currentDue.lapses,
                                state = currentDue.state
                            )
                        }

                        if (!state.isAnswerRevealed) {
                            if (activeSolveMode == "choice" && state.quizOptions.isNotEmpty()) {
                                Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                                    Text(
                                        text = "🎯 [1단계: 4지선다 인지 모드] 알맞은 정답을 골라보세요",
                                        fontSize = 12.sp,
                                        fontWeight = FontWeight.Bold,
                                        color = TossBlue
                                    )
                                    state.quizOptions.forEachIndexed { idx, optText ->
                                        Surface(
                                            color = Color(0xFFF9FAFB),
                                            shape = RoundedCornerShape(14.dp),
                                            modifier = Modifier
                                                .fillMaxWidth()
                                                .clickable { onSelectQuizOption(optText) }
                                        ) {
                                            Text(
                                                text = "${idx + 1}.  $optText",
                                                fontSize = 15.sp,
                                                fontWeight = FontWeight.SemiBold,
                                                color = TextPrimary,
                                                modifier = Modifier.padding(16.dp)
                                            )
                                        }
                                    }
                                    Row(
                                        horizontalArrangement = Arrangement.spacedBy(8.dp),
                                        modifier = Modifier.fillMaxWidth()
                                    ) {
                                        Button(
                                            onClick = onSubmitDontKnowQuick,
                                            colors = ButtonDefaults.buttonColors(
                                                containerColor = CoralRedSoft,
                                                contentColor = CoralRed
                                            ),
                                            shape = RoundedCornerShape(12.dp),
                                            modifier = Modifier.weight(1f).height(44.dp)
                                        ) {
                                            Text("❓ 모름 (정답 확인)", fontSize = 13.sp, fontWeight = FontWeight.Bold)
                                        }
                                        OutlinedButton(
                                            onClick = onRevealAnswer,
                                            shape = RoundedCornerShape(12.dp),
                                            modifier = Modifier.weight(1f).height(44.dp)
                                        ) {
                                            Text("정답 보기", fontSize = 13.sp, fontWeight = FontWeight.Bold)
                                        }
                                    }
                                }
                            } else {
                                Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                                    Text(
                                        text = "✍️ [2단계: 서술형 능동 인출 모드] 정답을 직접 떠올려 입력해 보세요",
                                        fontSize = 12.sp,
                                        fontWeight = FontWeight.Bold,
                                        color = TossBlue
                                    )
                                    OutlinedTextField(
                                        value = state.typedAnswerInput,
                                        onValueChange = onUpdateTypedAnswer,
                                        label = { Text("✍️ 정답을 타이핑해 이해도를 체크해보세요") },
                                        singleLine = true,
                                        shape = RoundedCornerShape(14.dp),
                                        modifier = Modifier.fillMaxWidth()
                                    )
                                    Row(
                                        horizontalArrangement = Arrangement.spacedBy(8.dp),
                                        modifier = Modifier.fillMaxWidth()
                                    ) {
                                        Button(
                                            onClick = onSubmitDontKnowQuick,
                                            colors = ButtonDefaults.buttonColors(
                                                containerColor = CoralRedSoft,
                                                contentColor = CoralRed
                                            ),
                                            shape = RoundedCornerShape(12.dp),
                                            modifier = Modifier.weight(1f).height(44.dp)
                                        ) {
                                            Text("❓ 모름 (바로 정답)", fontSize = 13.sp, fontWeight = FontWeight.Bold)
                                        }
                                        Button(
                                            onClick = onSubmitTypedAnswer,
                                            colors = ButtonDefaults.buttonColors(
                                                containerColor = TossBlue,
                                                contentColor = Color.White
                                            ),
                                            shape = RoundedCornerShape(12.dp),
                                            modifier = Modifier.weight(1f).height(44.dp)
                                        ) {
                                            Text("🎯 타이핑 채점 확인", fontSize = 13.sp, fontWeight = FontWeight.Bold)
                                        }
                                    }
                                }
                            }
                        } else {
                            if (state.selectedQuizOption != null && state.quizOptions.isNotEmpty()) {
                                val targetClean = conciseAnswer.ifBlank { currentDue.back }.trim()
                                Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
                                    state.quizOptions.forEachIndexed { idx, optText ->
                                        val isTarget = optText.trim().equals(targetClean, ignoreCase = true) ||
                                            (optText == state.selectedQuizOption && state.typedEvaluation?.verdict == TypedUnderstandingVerdict.EXACT)
                                        val isChosenWrong = optText == state.selectedQuizOption && !isTarget
                                        val optBg = when {
                                            isTarget -> MintGreenSoft
                                            isChosenWrong -> CoralRedSoft
                                            else -> Color(0xFFF9FAFB)
                                        }
                                        val optFg = when {
                                            isTarget -> MintGreen
                                            isChosenWrong -> CoralRed
                                            else -> TextSecondary
                                        }
                                        val prefix = when {
                                            isTarget -> "✅ ${idx + 1}.  "
                                            isChosenWrong -> "❌ ${idx + 1}.  "
                                            else -> "${idx + 1}.  "
                                        }
                                        Surface(
                                            color = optBg,
                                            shape = RoundedCornerShape(12.dp),
                                            modifier = Modifier.fillMaxWidth()
                                        ) {
                                            Text(
                                                text = "$prefix$optText",
                                                fontSize = 14.sp,
                                                fontWeight = if (isTarget || isChosenWrong) FontWeight.ExtraBold else FontWeight.Medium,
                                                color = optFg,
                                                modifier = Modifier.padding(horizontal = 14.dp, vertical = 11.dp)
                                            )
                                        }
                                    }
                                }
                            }
                            // 3-Tier Understanding Verdict Badge (shown after reveal)
                            state.typedEvaluation?.let { ev ->
                                val badgeBg = when (ev.verdict) {
                                    TypedUnderstandingVerdict.EXACT -> MintGreenSoft
                                    TypedUnderstandingVerdict.PARTIAL -> Color(0xFFFFF8E6)
                                    TypedUnderstandingVerdict.UNKNOWN -> CoralRedSoft
                                }
                                val badgeFg = when (ev.verdict) {
                                    TypedUnderstandingVerdict.EXACT -> MintGreen
                                    TypedUnderstandingVerdict.PARTIAL -> Color(0xFFB45309)
                                    TypedUnderstandingVerdict.UNKNOWN -> CoralRed
                                }
                                Surface(
                                    color = badgeBg,
                                    shape = RoundedCornerShape(14.dp),
                                    modifier = Modifier.fillMaxWidth()
                                ) {
                                    Column(
                                        modifier = Modifier.padding(14.dp),
                                        verticalArrangement = Arrangement.spacedBy(4.dp)
                                    ) {
                                        Text(
                                            text = "${ev.badgeLabel} (${ev.scorePct}%)",
                                            fontSize = 14.sp,
                                            fontWeight = FontWeight.ExtraBold,
                                            color = badgeFg
                                        )
                                        Text(
                                            text = ev.feedback,
                                            fontSize = 12.sp,
                                            fontWeight = FontWeight.Medium,
                                            color = TextPrimary
                                        )
                                        if (ev.verdict != TypedUnderstandingVerdict.EXACT) {
                                            Spacer(modifier = Modifier.height(6.dp))
                                            OutlinedButton(
                                                onClick = onOverrideTypedAnswerCorrect,
                                                shape = RoundedCornerShape(10.dp),
                                                modifier = Modifier.fillMaxWidth()
                                            ) {
                                                Text(
                                                    text = "✅ 내 답이 맞아요 (정답 인정)",
                                                    fontSize = 12.sp,
                                                    fontWeight = FontWeight.ExtraBold,
                                                    color = MintGreen
                                                )
                                            }
                                        }
                                    }
                                }
                            }
                            Surface(
                                color = MintGreenSoft,
                                shape = RoundedCornerShape(16.dp),
                                modifier = Modifier.fillMaxWidth()
                            ) {
                                Column(modifier = Modifier.padding(18.dp)) {
                                    Text(
                                        text = "🎯 핵심 정답",
                                        fontSize = 12.sp,
                                        color = MintGreen,
                                        fontWeight = FontWeight.Bold
                                    )
                                    Spacer(modifier = Modifier.height(4.dp))
                                    Text(
                                        text = conciseAnswer.ifBlank { currentDue.back },
                                        fontSize = 19.sp,
                                        color = TextPrimary,
                                        fontWeight = FontWeight.ExtraBold
                                    )
                                }
                            }
                            if (extraExplanation.isNotBlank()) {
                                Surface(
                                    color = TossBlueSoft,
                                    shape = RoundedCornerShape(14.dp),
                                    modifier = Modifier.fillMaxWidth()
                                ) {
                                    Column(modifier = Modifier.padding(14.dp)) {
                                        Text(
                                            text = "💡 해설 및 문맥 예문",
                                            fontSize = 12.sp,
                                            color = TossBlue,
                                            fontWeight = FontWeight.ExtraBold
                                        )
                                        Spacer(modifier = Modifier.height(4.dp))
                                        Text(
                                            text = extraExplanation,
                                            fontSize = 13.sp,
                                            color = TextPrimary,
                                            fontWeight = FontWeight.Medium
                                        )
                                    }
                                }
                            }

                            // Compute Exact FSRS Next Interval Previews for Rating Buttons
                            val mem = CardMemoryState(
                                difficulty = currentDue.difficulty,
                                stability = currentDue.stability,
                                reps = currentDue.reps,
                                lapses = currentDue.lapses,
                                state = currentDue.state
                            )
                            val lblAgain = Fsrs5Engine.stepFsrs(mem, Rating.AGAIN).scheduledLabel
                            val lblHard = Fsrs5Engine.stepFsrs(mem, Rating.HARD).scheduledLabel
                            val lblGood = Fsrs5Engine.stepFsrs(mem, Rating.GOOD).scheduledLabel
                            val lblEasy = Fsrs5Engine.stepFsrs(mem, Rating.EASY).scheduledLabel

                            // Frame 3: EvidenceRatingGuard (Metacognitive Calibration)
                            val tierEnum = when (state.ageTier) {
                                "junior" -> AdaptiveQuizEngine.AgeTier.JUNIOR
                                "teen" -> AdaptiveQuizEngine.AgeTier.TEEN
                                else -> AdaptiveQuizEngine.AgeTier.ADULT
                            }
                            val ratingGuard = AdaptiveQuizEngine.resolveAllowedRatings(
                                isRevealed = state.isAnswerRevealed,
                                typedVerdict = state.typedEvaluation?.verdict,
                                hintStep = state.hintStep,
                                ageTier = tierEnum
                            )
                            val rec = ratingGuard.recommendedRating ?: state.recommendedRating

                            if (ratingGuard.bannerText.isNotBlank()) {
                                Text(
                                    text = ratingGuard.bannerText,
                                    fontSize = 11.sp,
                                    color = TextSecondary,
                                    fontWeight = FontWeight.SemiBold
                                )
                            }

                            Row(
                                horizontalArrangement = Arrangement.spacedBy(8.dp),
                                modifier = Modifier.fillMaxWidth()
                            ) {
                                if (state.ageTier == "junior") {
                                    Button(
                                        onClick = { onRateCard(Rating.AGAIN) },
                                        enabled = Rating.AGAIN in ratingGuard.allowedRatings,
                                        colors = ButtonDefaults.buttonColors(
                                            containerColor = CoralRedSoft,
                                            contentColor = CoralRed
                                        ),
                                        shape = RoundedCornerShape(14.dp),
                                        modifier = Modifier.weight(1f).height(54.dp)
                                    ) {
                                        Text(
                                            text = "${if (rec == Rating.AGAIN) "★ " else ""}다시\n$lblAgain",
                                            fontSize = 12.sp,
                                            fontWeight = FontWeight.Bold,
                                            textAlign = TextAlign.Center
                                        )
                                    }
                                    Button(
                                        onClick = { onRateCard(Rating.HARD) },
                                        enabled = Rating.HARD in ratingGuard.allowedRatings,
                                        colors = ButtonDefaults.buttonColors(
                                            containerColor = Color(0xFFFFF8E6),
                                            contentColor = Color(0xFFD97706)
                                        ),
                                        shape = RoundedCornerShape(14.dp),
                                        modifier = Modifier.weight(1f).height(54.dp)
                                    ) {
                                        Text(
                                            text = "${if (rec == Rating.HARD) "★ " else ""}헷갈림\n$lblHard",
                                            fontSize = 12.sp,
                                            fontWeight = FontWeight.Bold,
                                            textAlign = TextAlign.Center
                                        )
                                    }
                                    Button(
                                        onClick = { onRateCard(Rating.GOOD) },
                                        enabled = Rating.GOOD in ratingGuard.allowedRatings,
                                        colors = ButtonDefaults.buttonColors(
                                            containerColor = TossBlue,
                                            contentColor = Color.White
                                        ),
                                        shape = RoundedCornerShape(14.dp),
                                        modifier = Modifier.weight(1f).height(54.dp)
                                    ) {
                                        Text(
                                            text = "${if (rec == Rating.GOOD || rec == Rating.EASY) "★ " else ""}맞혔어요\n$lblGood",
                                            fontSize = 12.sp,
                                            fontWeight = FontWeight.Bold,
                                            textAlign = TextAlign.Center
                                        )
                                    }
                                } else {
                                    Button(
                                        onClick = { onRateCard(Rating.AGAIN) },
                                        enabled = Rating.AGAIN in ratingGuard.allowedRatings,
                                        colors = ButtonDefaults.buttonColors(
                                            containerColor = CoralRedSoft,
                                            contentColor = CoralRed
                                        ),
                                        shape = RoundedCornerShape(14.dp),
                                        modifier = Modifier.weight(1f).height(54.dp)
                                    ) {
                                        Text(
                                            text = "${if (rec == Rating.AGAIN) "★ " else ""}다시\n$lblAgain",
                                            fontSize = 12.sp,
                                            fontWeight = FontWeight.Bold,
                                            textAlign = TextAlign.Center
                                        )
                                    }
                                    Button(
                                        onClick = { onRateCard(Rating.HARD) },
                                        enabled = Rating.HARD in ratingGuard.allowedRatings,
                                        colors = ButtonDefaults.buttonColors(
                                            containerColor = Color(0xFFFFF8E6),
                                            contentColor = Color(0xFFD97706)
                                        ),
                                        shape = RoundedCornerShape(14.dp),
                                        modifier = Modifier.weight(1f).height(54.dp)
                                    ) {
                                        Text(
                                            text = "${if (rec == Rating.HARD) "★ " else ""}어려움\n$lblHard",
                                            fontSize = 12.sp,
                                            fontWeight = FontWeight.Bold,
                                            textAlign = TextAlign.Center
                                        )
                                    }
                                    Button(
                                        onClick = { onRateCard(Rating.GOOD) },
                                        enabled = Rating.GOOD in ratingGuard.allowedRatings,
                                        colors = ButtonDefaults.buttonColors(
                                            containerColor = TossBlue,
                                            contentColor = Color.White
                                        ),
                                        shape = RoundedCornerShape(14.dp),
                                        modifier = Modifier.weight(1f).height(54.dp)
                                    ) {
                                        Text(
                                            text = "${if (rec == Rating.GOOD) "★ " else ""}알맞음\n$lblGood",
                                            fontSize = 12.sp,
                                            fontWeight = FontWeight.Bold,
                                            textAlign = TextAlign.Center
                                        )
                                    }
                                    Button(
                                        onClick = { onRateCard(Rating.EASY) },
                                        enabled = Rating.EASY in ratingGuard.allowedRatings,
                                        colors = ButtonDefaults.buttonColors(
                                            containerColor = TossBlueSoft,
                                            contentColor = TossBlue
                                        ),
                                        shape = RoundedCornerShape(14.dp),
                                        modifier = Modifier.weight(1f).height(54.dp)
                                    ) {
                                        Text(
                                            text = "${if (rec == Rating.EASY) "★ " else ""}쉬움\n$lblEasy",
                                            fontSize = 12.sp,
                                            fontWeight = FontWeight.Bold,
                                            textAlign = TextAlign.Center
                                        )
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
    }
}

@Composable
private fun CurriculumTabScreen(
    state: AnkiStudioUiState,
    onSelectDifficultyLevel: (String) -> Unit = {},
    onSelectTextbook: (String) -> Unit = {},
    onToggleExamUnit: (String) -> Unit,
    onGenerateExamScopeDeck: () -> Unit,
    onSelectCollection: (String) -> Unit,
    onGenerateCollectionDeck: () -> Unit,
    onAddTextbookToCombo: () -> Unit = {},
    onAddCollectionToCombo: () -> Unit = {},
    onLoadMidtermComboPreset: () -> Unit = {},
    onClearComboScopes: () -> Unit = {},
    onGenerateCombinedExamDeck: () -> Unit = {}
) {
    val allTextbooks = BuiltInCurriculumCatalog.listTextbooks()
    val activeTextbook = allTextbooks.firstOrNull { it.textbookId == state.selectedTextbookId }
        ?: allTextbooks.first()
    val difficultyModes = listOf(
        "mixed" to "🔥 통합 (Lv.1~3)",
        "lv1" to "🌱 Lv.1 기초",
        "lv2" to "🚀 Lv.2 빈칸",
        "lv3" to "🎓 Lv.3 심화",
        "standard" to "📋 표준"
    )
    var curriculumSegment by remember { mutableStateOf("textbook") }
    val segState = ReaV56Engine.resolveCurriculumSegmentState(
        segment = curriculumSegment,
        combinedScopeCount = state.combinedExamScopes.size
    )

    LazyColumn(
        modifier = Modifier.fillMaxSize(),
        verticalArrangement = Arrangement.spacedBy(14.dp)
    ) {
        // 0. 3-Segment Switcher + Compact Difficulty Selector (v5.8 Simple Is Best C3)
        item {
            Card(
                colors = CardDefaults.cardColors(containerColor = Color(0xFFFFFFFF)),
                elevation = CardDefaults.cardElevation(defaultElevation = 2.dp),
                shape = RoundedCornerShape(22.dp),
                modifier = Modifier.fillMaxWidth()
            ) {
                Column(
                    modifier = Modifier.padding(18.dp),
                    verticalArrangement = Arrangement.spacedBy(10.dp)
                ) {
                    Row(
                        horizontalArrangement = Arrangement.spacedBy(8.dp),
                        modifier = Modifier.fillMaxWidth()
                    ) {
                        val segmentTabs = listOf(
                            "textbook" to "🏫 교과서 단원",
                            "collection" to "📚 교육부·급수",
                            "combined" to segState.combinedTabLabel
                        )
                        segmentTabs.forEach { (segId, segLabel) ->
                            FilterChip(
                                selected = segState.activeSegment == segId,
                                onClick = { curriculumSegment = segId },
                                label = { Text(segLabel, fontSize = 11.sp, fontWeight = FontWeight.Bold) }
                            )
                        }
                    }
                    LazyRow(
                        horizontalArrangement = Arrangement.spacedBy(8.dp),
                        modifier = Modifier.fillMaxWidth()
                    ) {
                        items(difficultyModes) { (modeId, label) ->
                            FilterChip(
                                selected = state.selectedDifficultyLevel == modeId,
                                onClick = { onSelectDifficultyLevel(modeId) },
                                label = { Text(label, fontSize = 11.sp) }
                            )
                        }
                    }
                }
            }
        }

        // 1. Multi-Combination Exam-Scope Random Deck Builder
        if (segState.visiblePanels["combined"] == true) {
            item {
                Card(
                    colors = CardDefaults.cardColors(containerColor = Color(0xFFFFFFFF)),
                    elevation = CardDefaults.cardElevation(defaultElevation = 2.dp),
                    shape = RoundedCornerShape(22.dp),
                    modifier = Modifier.fillMaxWidth()
                ) {
                    Column(
                        modifier = Modifier.padding(20.dp),
                        verticalArrangement = Arrangement.spacedBy(10.dp)
                    ) {
                        Row(
                            modifier = Modifier.fillMaxWidth(),
                            horizontalArrangement = Arrangement.SpaceBetween,
                            verticalAlignment = Alignment.CenterVertically
                        ) {
                            Text(
                                text = "🎯 다중 조합 시험범위 랜덤 덱",
                                fontSize = 18.sp,
                                fontWeight = FontWeight.ExtraBold,
                                color = TextPrimary
                            )
                            Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                                OutlinedButton(
                                    onClick = onLoadMidtermComboPreset,
                                    shape = RoundedCornerShape(10.dp)
                                ) {
                                    Text("⚡ 중간고사 예시", fontSize = 11.sp, fontWeight = FontWeight.Bold, color = TossBlue)
                                }
                                if (state.combinedExamScopes.isNotEmpty()) {
                                    OutlinedButton(
                                        onClick = onClearComboScopes,
                                        shape = RoundedCornerShape(10.dp)
                                    ) {
                                        Text("비우기", fontSize = 11.sp, color = TextSecondary)
                                    }
                                }
                            }
                        }
                        Text(
                            text = "여러 과목·단원·한자 급수를 한 바구니에 담으면 같은 단원이 뭉치지 않게 지능형 교차 랜덤(Interleaved Shuffle)으로 출제합니다.",
                            fontSize = 12.sp,
                            color = TextSecondary
                        )
                        Surface(
                            color = Color(0xFFF9FAFB),
                            shape = RoundedCornerShape(14.dp),
                            modifier = Modifier.fillMaxWidth()
                        ) {
                            Column(
                                modifier = Modifier.padding(12.dp),
                                verticalArrangement = Arrangement.spacedBy(6.dp)
                            ) {
                                if (state.combinedExamScopes.isEmpty()) {
                                    Text(
                                        text = "아직 담긴 범위가 없습니다. 교과서/급수 탭에서 [➕ 범위 담기]나 [⚡ 중간고사 예시]를 눌러보세요.",
                                        fontSize = 12.sp,
                                        color = TextMuted
                                    )
                                } else {
                                    state.combinedExamScopes.forEachIndexed { idx, item ->
                                        Text(
                                            text = "${idx + 1}. 📚 ${item.label}",
                                            fontSize = 13.sp,
                                            fontWeight = FontWeight.Bold,
                                            color = TossBlue
                                        )
                                    }
                                }
                            }
                        }
                        Button(
                            onClick = onGenerateCombinedExamDeck,
                            shape = RoundedCornerShape(14.dp),
                            colors = ButtonDefaults.buttonColors(containerColor = TossBlue),
                            modifier = Modifier.fillMaxWidth().height(50.dp)
                        ) {
                            Text(
                                text = "🎲 조합 출제범위(${maxOf(1, state.combinedExamScopes.size)}개) 랜덤 통합 덱 생성",
                                fontWeight = FontWeight.Bold
                            )
                        }
                    }
                }
            }
        }

        // 2. School Textbook Selector & Unit Picker
        if (segState.visiblePanels["textbook"] == true) {
            item {
                Card(
                    colors = CardDefaults.cardColors(containerColor = Color(0xFFFFFFFF)),
                    elevation = CardDefaults.cardElevation(defaultElevation = 2.dp),
                    shape = RoundedCornerShape(22.dp),
                    modifier = Modifier.fillMaxWidth()
                ) {
                    Column(
                        modifier = Modifier.padding(20.dp),
                        verticalArrangement = Arrangement.spacedBy(12.dp)
                    ) {
                        Text(
                            text = "🏫 학교 교과서 시험범위",
                            fontSize = 18.sp,
                            fontWeight = FontWeight.ExtraBold,
                            color = TextPrimary
                        )
                        LazyRow(
                            horizontalArrangement = Arrangement.spacedBy(8.dp),
                            modifier = Modifier.fillMaxWidth()
                        ) {
                            items(allTextbooks) { tb ->
                                FilterChip(
                                    selected = tb.textbookId == activeTextbook.textbookId,
                                    onClick = { onSelectTextbook(tb.textbookId) },
                                    label = { Text(tb.title) }
                                )
                            }
                        }
                        Text(
                            text = activeTextbook.title,
                            fontSize = 14.sp,
                            color = TossBlue,
                            fontWeight = FontWeight.Bold
                        )
                        LazyRow(
                            horizontalArrangement = Arrangement.spacedBy(8.dp),
                            modifier = Modifier.fillMaxWidth()
                        ) {
                            items(activeTextbook.units) { unit ->
                                FilterChip(
                                    selected = unit.unitId in state.selectedUnitIds,
                                    onClick = { onToggleExamUnit(unit.unitId) },
                                    label = { Text(unit.unitCodeLabel) }
                                )
                            }
                        }
                        Row(
                            horizontalArrangement = Arrangement.spacedBy(8.dp),
                            modifier = Modifier.fillMaxWidth()
                        ) {
                            Button(
                                onClick = onGenerateExamScopeDeck,
                                shape = RoundedCornerShape(14.dp),
                                modifier = Modifier.weight(1f).height(50.dp)
                            ) {
                                Text("단원(${state.selectedUnitIds.size}개) 학습 시작", fontWeight = FontWeight.Bold)
                            }
                            OutlinedButton(
                                onClick = {
                                    onAddTextbookToCombo()
                                    curriculumSegment = "combined"
                                },
                                shape = RoundedCornerShape(14.dp),
                                modifier = Modifier.height(50.dp)
                            ) {
                                Text("➕ 범위 담기", fontWeight = FontWeight.Bold, color = TossBlue)
                            }
                        }
                    }
                }
            }
        }

        // 3. Collections (Hanja, Korean History, Idioms, MOE 2022)
        if (segState.visiblePanels["collection"] == true) {
            item {
                Card(
                    colors = CardDefaults.cardColors(containerColor = Color(0xFFFFFFFF)),
                    elevation = CardDefaults.cardElevation(defaultElevation = 2.dp),
                    shape = RoundedCornerShape(22.dp),
                    modifier = Modifier.fillMaxWidth()
                ) {
                    Column(
                        modifier = Modifier.padding(20.dp),
                        verticalArrangement = Arrangement.spacedBy(12.dp)
                    ) {
                        Text(
                            text = "📚 교육부 필수 · 급수 한자 · 한국사 팩",
                            fontSize = 18.sp,
                            fontWeight = FontWeight.ExtraBold,
                            color = TextPrimary
                        )
                        LazyRow(
                            horizontalArrangement = Arrangement.spacedBy(8.dp),
                            modifier = Modifier.fillMaxWidth()
                        ) {
                            items(BuiltInCurriculumCatalog.listCollections()) { col ->
                                FilterChip(
                                    selected = state.selectedCollectionId == col.collectionId,
                                    onClick = { onSelectCollection(col.collectionId) },
                                    label = { Text(col.title) }
                                )
                            }
                        }
                        Row(
                            horizontalArrangement = Arrangement.spacedBy(8.dp),
                            modifier = Modifier.fillMaxWidth()
                        ) {
                            Button(
                                onClick = onGenerateCollectionDeck,
                                shape = RoundedCornerShape(14.dp),
                                modifier = Modifier.weight(1f).height(50.dp)
                            ) {
                                Text("선택한 팩 학습 시작", fontWeight = FontWeight.Bold)
                            }
                            OutlinedButton(
                                onClick = {
                                    onAddCollectionToCombo()
                                    curriculumSegment = "combined"
                                },
                                shape = RoundedCornerShape(14.dp),
                                modifier = Modifier.height(50.dp)
                            ) {
                                Text("➕ 범위 담기", fontWeight = FontWeight.Bold, color = TossBlue)
                            }
                        }
                    }
                }
            }
        }
    }
}

@Composable
private fun CreateDeckTabScreen(
    state: AnkiStudioUiState,
    onSelectCategory: (String?) -> Unit,
    onSelectOllamaCloudModel: (String) -> Unit = {},
    onDeckTitleChange: (String) -> Unit,
    onPickPhoto: () -> Unit,
    onPickPdf: () -> Unit,
    onUpdateNewCardFront: (String) -> Unit,
    onUpdateNewCardBack: (String) -> Unit,
    onInsertClozeTemplate: () -> Unit,
    onAddCustomCardDirect: () -> Unit,
    onUpdatePreviewCard: (Int, String, String) -> Unit,
    onRemovePreviewCard: (Int) -> Unit,
    onSavePreviewDeck: () -> Unit
) {
    val smartGenModes = listOf(
        "glm-5.3-flash" to "✨ 스마트 자동 생성 (추천)",
        "local_rule" to "⚡ 오프라인 빠른 생성"
    )
    LazyColumn(
        modifier = Modifier.fillMaxSize(),
        verticalArrangement = Arrangement.spacedBy(14.dp)
    ) {
        // 1. Direct Card Add (Basic + {{c1::빈칸}} Cloze)
        item {
            Card(
                colors = CardDefaults.cardColors(containerColor = Color(0xFFFFFFFF)),
                elevation = CardDefaults.cardElevation(defaultElevation = 2.dp),
                shape = RoundedCornerShape(22.dp),
                modifier = Modifier.fillMaxWidth()
            ) {
                Column(
                    modifier = Modifier.padding(20.dp),
                    verticalArrangement = Arrangement.spacedBy(10.dp)
                ) {
                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.SpaceBetween,
                        verticalAlignment = Alignment.CenterVertically
                    ) {
                        Text(
                            text = "✍️ 카드 직접 추가",
                            fontSize = 18.sp,
                            fontWeight = FontWeight.ExtraBold,
                            color = TextPrimary
                        )
                        OutlinedButton(
                            onClick = onInsertClozeTemplate,
                            shape = RoundedCornerShape(12.dp)
                        ) {
                            Text("+ {{c1::빈칸}}", fontSize = 12.sp, fontWeight = FontWeight.Bold, color = TossBlue)
                        }
                    }
                    OutlinedTextField(
                        value = state.newCardFrontInput,
                        onValueChange = onUpdateNewCardFront,
                        label = { Text("앞면 질문 또는 {{c1::빈칸}} 문장") },
                        shape = RoundedCornerShape(14.dp),
                        modifier = Modifier.fillMaxWidth()
                    )
                    OutlinedTextField(
                        value = state.newCardBackInput,
                        onValueChange = onUpdateNewCardBack,
                        label = { Text("뒷면 정답 또는 해설") },
                        shape = RoundedCornerShape(14.dp),
                        modifier = Modifier.fillMaxWidth()
                    )
                    Button(
                        onClick = onAddCustomCardDirect,
                        shape = RoundedCornerShape(14.dp),
                        modifier = Modifier.fillMaxWidth().height(48.dp)
                    ) {
                        Text("➕ 단어장에 카드 추가하기", fontWeight = FontWeight.Bold)
                    }
                }
            }
        }

        // 2. Photo / PDF Auto-Deck Builder
        item {
            Card(
                colors = CardDefaults.cardColors(containerColor = Color(0xFFFFFFFF)),
                elevation = CardDefaults.cardElevation(defaultElevation = 2.dp),
                shape = RoundedCornerShape(22.dp),
                modifier = Modifier.fillMaxWidth()
            ) {
                Column(
                    modifier = Modifier.padding(20.dp),
                    verticalArrangement = Arrangement.spacedBy(12.dp)
                ) {
                    Text(
                        text = "➕ 사진 · PDF로 나만의 단어장",
                        fontSize = 18.sp,
                        fontWeight = FontWeight.ExtraBold,
                        color = TextPrimary
                    )

                    Text(
                        text = "✨ 생성 방식 (사진·PDF 문서 핵심 개념 정밀 추출)",
                        fontSize = 12.sp,
                        fontWeight = FontWeight.Bold,
                        color = TossBlue
                    )
                    LazyRow(
                        horizontalArrangement = Arrangement.spacedBy(8.dp),
                        modifier = Modifier.fillMaxWidth()
                    ) {
                        items(smartGenModes) { (modelId, label) ->
                            FilterChip(
                                selected = if (modelId == "local_rule") {
                                    state.selectedOllamaCloudModel == "local_rule"
                                } else {
                                    state.selectedOllamaCloudModel != "local_rule"
                                },
                                onClick = { onSelectOllamaCloudModel(modelId) },
                                label = { Text(label, fontSize = 11.sp, fontWeight = FontWeight.Bold) }
                            )
                        }
                    }

                    LazyRow(
                        horizontalArrangement = Arrangement.spacedBy(8.dp),
                        modifier = Modifier.fillMaxWidth()
                    ) {
                        item {
                            FilterChip(
                                selected = state.selectedCategoryOverride == null,
                                onClick = { onSelectCategory(null) },
                                label = { Text("자동") }
                            )
                        }
                        items(CATEGORY_LABELS) { (catId, label) ->
                            FilterChip(
                                selected = state.selectedCategoryOverride == catId,
                                onClick = { onSelectCategory(catId) },
                                label = { Text(label) }
                            )
                        }
                    }

                    OutlinedTextField(
                        value = state.customDeckTitle,
                        onValueChange = onDeckTitleChange,
                        label = { Text("단어장 이름 (선택)") },
                        singleLine = true,
                        shape = RoundedCornerShape(14.dp),
                        modifier = Modifier.fillMaxWidth()
                    )

                    Row(
                        horizontalArrangement = Arrangement.spacedBy(10.dp),
                        modifier = Modifier.fillMaxWidth()
                    ) {
                        Button(
                            onClick = onPickPhoto,
                            enabled = !state.isIngesting,
                            shape = RoundedCornerShape(14.dp),
                            modifier = Modifier.weight(1f).height(50.dp)
                        ) {
                            Text("📷 사진 선택", fontWeight = FontWeight.Bold)
                        }
                        OutlinedButton(
                            onClick = onPickPdf,
                            enabled = !state.isIngesting,
                            shape = RoundedCornerShape(14.dp),
                            modifier = Modifier.weight(1f).height(50.dp)
                        ) {
                            Text("📄 PDF 선택", fontWeight = FontWeight.Bold)
                        }
                    }
                }
            }
        }

        val preview = state.previewPlan
        if (preview != null && preview.cards.isNotEmpty()) {
            item {
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.SpaceBetween,
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    Text(
                        text = "추출된 카드 (${preview.cards.size}장)",
                        fontWeight = FontWeight.ExtraBold,
                        fontSize = 16.sp,
                        color = TextPrimary
                    )
                    Button(
                        onClick = onSavePreviewDeck,
                        shape = RoundedCornerShape(12.dp)
                    ) {
                        Text("저장하기", fontWeight = FontWeight.Bold)
                    }
                }
            }

            itemsIndexed(preview.cards) { idx, card ->
                Card(
                    colors = CardDefaults.cardColors(containerColor = Color(0xFFFFFFFF)),
                    elevation = CardDefaults.cardElevation(defaultElevation = 1.dp),
                    shape = RoundedCornerShape(16.dp),
                    modifier = Modifier.fillMaxWidth()
                ) {
                    Column(
                        modifier = Modifier.padding(14.dp),
                        verticalArrangement = Arrangement.spacedBy(8.dp)
                    ) {
                        Row(
                            modifier = Modifier.fillMaxWidth(),
                            horizontalArrangement = Arrangement.SpaceBetween,
                            verticalAlignment = Alignment.CenterVertically
                        ) {
                            Text(
                                text = "카드 #${idx + 1}",
                                color = TossBlue,
                                fontSize = 12.sp,
                                fontWeight = FontWeight.Bold
                            )
                            OutlinedButton(onClick = { onRemovePreviewCard(idx) }) {
                                Text("제외", fontSize = 11.sp)
                            }
                        }
                        OutlinedTextField(
                            value = card.spec.frontText,
                            onValueChange = { updatedFront ->
                                onUpdatePreviewCard(idx, updatedFront, card.spec.backText)
                            },
                            label = { Text("질문") },
                            modifier = Modifier.fillMaxWidth()
                        )
                        OutlinedTextField(
                            value = card.spec.backText,
                            onValueChange = { updatedBack ->
                                onUpdatePreviewCard(idx, card.spec.frontText, updatedBack)
                            },
                            label = { Text("정답") },
                            modifier = Modifier.fillMaxWidth()
                        )
                    }
                }
            }
        }
    }
}

@Composable
private fun StoreTabScreen(
    state: AnkiStudioUiState,
    onPurchaseTop3Bundle: () -> Unit,
    onSelectStoreCategory: (String) -> Unit,
    onPurchaseBrainPack: (String) -> Unit
) {
    val storePacks = BrainPackStoreCatalog.filterCatalog(categoryFilter = state.selectedStoreCategory)
    val lockedPaidCount = BrainPackStoreCatalog.products.count { !it.isFreeStarter && it.packId !in state.unlockedPackIds }

    LazyColumn(
        modifier = Modifier.fillMaxSize(),
        verticalArrangement = Arrangement.spacedBy(10.dp)
    ) {
        item {
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically
            ) {
                Text(
                    text = "🛒 브레인팩 스토어",
                    fontSize = 20.sp,
                    fontWeight = FontWeight.ExtraBold,
                    color = TextPrimary
                )
                Surface(
                    color = TossBlueSoft,
                    shape = RoundedCornerShape(999.dp)
                ) {
                    Text(
                        text = "보유 ${state.unlockedPackIds.size}/${BrainPackStoreCatalog.products.size}",
                        fontSize = 12.sp,
                        color = TossBlue,
                        fontWeight = FontWeight.Bold,
                        modifier = Modifier.padding(horizontal = 10.dp, vertical = 5.dp)
                    )
                }
            }
        }

        if (lockedPaidCount >= 3) {
            item {
                Button(
                    onClick = onPurchaseTop3Bundle,
                    shape = RoundedCornerShape(16.dp),
                    modifier = Modifier.fillMaxWidth().height(50.dp)
                ) {
                    Text("🎁 3팩 골라담기 15% 자동 할인 장착", fontWeight = FontWeight.Bold)
                }
            }
        }

        item {
            LazyRow(
                horizontalArrangement = Arrangement.spacedBy(8.dp),
                modifier = Modifier.fillMaxWidth()
            ) {
                val storeTabs = listOf(
                    "all" to "전체",
                    "moe_curriculum" to "📚 교육부 필수(9종)",
                    "starter_free" to "🎁 무료",
                    "k12_textbook" to "🏫 교과서·학령",
                    "hanja_history" to "漢字 한자·역사",
                    "language_exam" to "🗣️ 어학",
                    "pro_cert" to "⚖️ 자격증"
                )
                items(storeTabs) { (catCode, catLabel) ->
                    FilterChip(
                        selected = state.selectedStoreCategory == catCode,
                        onClick = { onSelectStoreCategory(catCode) },
                        label = { Text(catLabel) }
                    )
                }
            }
        }

        items(storePacks) { pack ->
            val isUnlocked = pack.isFreeStarter || pack.packId in state.unlockedPackIds
            Card(
                colors = CardDefaults.cardColors(containerColor = Color(0xFFFFFFFF)),
                elevation = CardDefaults.cardElevation(defaultElevation = 2.dp),
                shape = RoundedCornerShape(18.dp),
                modifier = Modifier.fillMaxWidth()
            ) {
                Row(
                    modifier = Modifier
                        .fillMaxWidth()
                        .padding(16.dp),
                    horizontalArrangement = Arrangement.SpaceBetween,
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    Column(modifier = Modifier.weight(1f).padding(end = 10.dp)) {
                        Text(
                            text = pack.title,
                            fontSize = 15.sp,
                            fontWeight = FontWeight.Bold,
                            color = TextPrimary
                        )
                        Spacer(modifier = Modifier.height(3.dp))
                        Text(
                            text = "${pack.estimatedCardCount}문항 · ${pack.priceLabel}",
                            fontSize = 12.sp,
                            color = TextSecondary
                        )
                    }
                    Button(
                        onClick = { onPurchaseBrainPack(pack.packId) },
                        colors = ButtonDefaults.buttonColors(
                            containerColor = if (isUnlocked) TossBlueSoft else TossBlue,
                            contentColor = if (isUnlocked) TossBlue else Color.White
                        ),
                        shape = RoundedCornerShape(12.dp)
                    ) {
                        Text(
                            text = if (isUnlocked) "바로 학습" else pack.priceLabel,
                            fontSize = 12.sp,
                            fontWeight = FontWeight.Bold
                        )
                    }
                }
            }
        }
    }
}

@Composable
private fun StatsAndModeTabScreen(
    state: AnkiStudioUiState,
    onSelectDeckForStudy: (Long?) -> Unit,
    onSelectAgeTier: (String) -> Unit,
    onOpenOnboarding: () -> Unit
) {
    LazyColumn(
        modifier = Modifier.fillMaxSize(),
        verticalArrangement = Arrangement.spacedBy(14.dp)
    ) {
        item {
            Row(
                horizontalArrangement = Arrangement.spacedBy(12.dp),
                modifier = Modifier.fillMaxWidth()
            ) {
                Card(
                    colors = CardDefaults.cardColors(containerColor = Color(0xFFFFFFFF)),
                    elevation = CardDefaults.cardElevation(defaultElevation = 2.dp),
                    shape = RoundedCornerShape(20.dp),
                    modifier = Modifier.weight(1f)
                ) {
                    Column(modifier = Modifier.padding(18.dp)) {
                        Text("오늘 남은 카드", fontSize = 13.sp, color = TextSecondary)
                        Spacer(modifier = Modifier.height(6.dp))
                        Text("${state.dueCards.size}장", fontSize = 24.sp, fontWeight = FontWeight.ExtraBold, color = TossBlue)
                    }
                }
                Card(
                    colors = CardDefaults.cardColors(containerColor = Color(0xFFFFFFFF)),
                    elevation = CardDefaults.cardElevation(defaultElevation = 2.dp),
                    shape = RoundedCornerShape(20.dp),
                    modifier = Modifier.weight(1f)
                ) {
                    Column(modifier = Modifier.padding(18.dp)) {
                        Text("내 단어장", fontSize = 13.sp, color = TextSecondary)
                        Spacer(modifier = Modifier.height(6.dp))
                        Text("${state.decks.size}개", fontSize = 24.sp, fontWeight = FontWeight.ExtraBold, color = TextPrimary)
                    }
                }
            }
        }

        item {
            Card(
                colors = CardDefaults.cardColors(containerColor = Color(0xFFFFFFFF)),
                elevation = CardDefaults.cardElevation(defaultElevation = 2.dp),
                shape = RoundedCornerShape(20.dp),
                modifier = Modifier.fillMaxWidth()
            ) {
                Column(
                    modifier = Modifier.padding(18.dp),
                    verticalArrangement = Arrangement.spacedBy(12.dp)
                ) {
                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.SpaceBetween,
                        verticalAlignment = Alignment.CenterVertically
                    ) {
                        Text("👤 학습자 모드", fontSize = 16.sp, fontWeight = FontWeight.ExtraBold, color = TextPrimary)
                        OutlinedButton(
                            onClick = onOpenOnboarding,
                            shape = RoundedCornerShape(12.dp)
                        ) {
                            Text("모드 선택 화면 열기", fontSize = 12.sp)
                        }
                    }
                    Row(
                        horizontalArrangement = Arrangement.spacedBy(8.dp),
                        modifier = Modifier.fillMaxWidth()
                    ) {
                        val tiers = listOf(
                            "junior" to "🌱 주니어",
                            "teen" to "🚀 중고등",
                            "adult" to "🎓 성인"
                        )
                        tiers.forEach { (code, label) ->
                            FilterChip(
                                selected = state.ageTier == code,
                                onClick = { onSelectAgeTier(code) },
                                label = { Text(label) }
                            )
                        }
                    }
                }
            }
        }

        item {
            Text(
                text = "📚 내 단어장 (터치하여 바로 학습)",
                fontSize = 16.sp,
                fontWeight = FontWeight.ExtraBold,
                color = TextPrimary
            )
        }

        items(state.decks) { deck ->
            Card(
                colors = CardDefaults.cardColors(containerColor = Color(0xFFFFFFFF)),
                elevation = CardDefaults.cardElevation(defaultElevation = 1.dp),
                shape = RoundedCornerShape(18.dp),
                modifier = Modifier
                    .fillMaxWidth()
                    .clickable { onSelectDeckForStudy(deck.id) }
            ) {
                Row(
                    modifier = Modifier
                        .fillMaxWidth()
                        .padding(18.dp),
                    horizontalArrangement = Arrangement.SpaceBetween,
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    Text(
                        text = deck.name,
                        fontSize = 15.sp,
                        fontWeight = FontWeight.Bold,
                        color = TextPrimary
                    )
                    Text(
                        text = "학습 ➔",
                        fontSize = 13.sp,
                        color = TossBlue,
                        fontWeight = FontWeight.Bold
                    )
                }
            }
        }
    }
}
