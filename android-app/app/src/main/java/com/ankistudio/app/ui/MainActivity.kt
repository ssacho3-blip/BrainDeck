package com.ankistudio.app.ui

import android.content.Intent
import android.net.Uri
import android.os.Bundle
import android.provider.OpenableColumns
import androidx.activity.ComponentActivity
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.compose.setContent
import androidx.activity.result.PickVisualMediaRequest
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
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
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.FilterChip
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.darkColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.ViewModelProvider
import com.ankistudio.domain.catalog.BuiltInCurriculumCatalog
import com.ankistudio.domain.fsrs.Fsrs5Engine
import com.ankistudio.domain.fsrs.Fsrs5Engine.Rating

private val StudioDarkColors = darkColorScheme(
    primary = Color(0xFF38BDF8),
    secondary = Color(0xFF818CF8),
    background = Color(0xFF0B0F19),
    surface = Color(0xFF111827),
    onPrimary = Color(0xFF090D16),
    onBackground = Color(0xFFF9FAFB),
    onSurface = Color(0xFFF3F4F6)
)

private val CATEGORY_LABELS = listOf(
    "law" to "법학·행정",
    "medical" to "의학·간호",
    "engineering" to "공학·IT",
    "language" to "어학·회화",
    "exam" to "자격증·수험"
)

class MainActivity : ComponentActivity() {

    private lateinit var viewModel: AnkiStudioViewModel

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        viewModel = ViewModelProvider(
            this,
            AnkiStudioViewModel.factory(applicationContext)
        )[AnkiStudioViewModel::class.java]

        if (savedInstanceState == null) {
            handleIncomingShareIntent(intent)
        }

        setContent {
            MaterialTheme(colorScheme = StudioDarkColors) {
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
                    onSelectCategory = viewModel::selectCategoryOverride,
                    onDeckTitleChange = viewModel::updateCustomDeckTitle,
                    onToggleExamUnit = viewModel::toggleExamUnit,
                    onSelectCollection = viewModel::selectStarterCollection,
                    onGenerateExamScopeDeck = viewModel::generateExamScopeDeck,
                    onGenerateCollectionDeck = viewModel::generateCollectionDeck,
                    onUpdatePreviewCard = viewModel::updatePreviewCard,
                    onRemovePreviewCard = viewModel::removePreviewCard,
                    onSavePreviewDeck = viewModel::savePreviewAsDeck,
                    onRevealAnswer = viewModel::revealAnswer,
                    onRateCard = viewModel::submitReviewRating
                )
            }
        }
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
    onSelectCategory: (String?) -> Unit,
    onDeckTitleChange: (String) -> Unit,
    onToggleExamUnit: (String) -> Unit,
    onSelectCollection: (String) -> Unit,
    onGenerateExamScopeDeck: () -> Unit,
    onGenerateCollectionDeck: () -> Unit,
    onUpdatePreviewCard: (Int, String, String) -> Unit,
    onRemovePreviewCard: (Int) -> Unit,
    onSavePreviewDeck: () -> Unit,
    onRevealAnswer: () -> Unit,
    onRateCard: (Rating) -> Unit
) {
    val activeTextbook = BuiltInCurriculumCatalog.textbooks.firstOrNull { it.textbookId == state.selectedTextbookId }
        ?: BuiltInCurriculumCatalog.textbooks.first()

    Scaffold(
        modifier = Modifier
            .fillMaxSize()
            .background(MaterialTheme.colorScheme.background)
    ) { innerPadding ->
        LazyColumn(
            modifier = Modifier
                .fillMaxSize()
                .padding(innerPadding)
                .padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(16.dp)
        ) {
            item {
                Text(
                    text = "Anki Studio · Photo & PDF Auto-Deck",
                    fontSize = 22.sp,
                    fontWeight = FontWeight.Bold,
                    color = MaterialTheme.colorScheme.primary
                )
                Text(
                    text = "전공 요약본 사진·교재 스캔·강의안 PDF를 넣으면 온디바이스 AI가 즉시 FSRS-5 암기 덱을 생성합니다.",
                    fontSize = 13.sp,
                    color = Color(0xFF9CA3AF)
                )
            }

            state.statusBannerMessage?.let { msg ->
                item {
                    Surface(
                        color = if (state.isErrorBanner) Color(0xFF3F1D24) else Color(0xFF102A3A),
                        shape = RoundedCornerShape(10.dp),
                        modifier = Modifier.fillMaxWidth()
                    ) {
                        Text(
                            text = msg,
                            color = if (state.isErrorBanner) Color(0xFFFCA5A5) else Color(0xFF7DD3FC),
                            fontSize = 13.sp,
                            modifier = Modifier.padding(12.dp)
                        )
                    }
                }
            }

            // Textbook Exam-Scope & Hanja Grade / Starter Collections Card
            item {
                Card(
                    colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface),
                    shape = RoundedCornerShape(14.dp),
                    modifier = Modifier.fillMaxWidth()
                ) {
                    Column(
                        modifier = Modifier.padding(16.dp),
                        verticalArrangement = Arrangement.spacedBy(10.dp)
                    ) {
                        Text(
                            text = "🏫 교과서 시험범위 & 漢字 급수별·전 연령 기본 팩",
                            fontSize = 16.sp,
                            fontWeight = FontWeight.SemiBold
                        )
                        Text(
                            text = "① ${activeTextbook.title} (${activeTextbook.publisher} · ${activeTextbook.author}) 단원 선택",
                            fontSize = 13.sp,
                            color = Color(0xFF38BDF8),
                            fontWeight = FontWeight.SemiBold
                        )
                        LazyRow(
                            horizontalArrangement = Arrangement.spacedBy(8.dp),
                            modifier = Modifier.fillMaxWidth()
                        ) {
                            items(activeTextbook.units) { unit ->
                                FilterChip(
                                    selected = unit.unitId in state.selectedUnitIds,
                                    onClick = { onToggleExamUnit(unit.unitId) },
                                    label = { Text("${unit.unitId} (p.${unit.pageStart}~${unit.pageEnd})") }
                                )
                            }
                        }
                        Button(
                            onClick = onGenerateExamScopeDeck,
                            modifier = Modifier.fillMaxWidth()
                        ) {
                            Text("⚡ 선택한 시험범위 단원(${state.selectedUnitIds.size}개) 암기 덱 생성")
                        }

                        Spacer(modifier = Modifier.height(4.dp))
                        Text(
                            text = "② 한자 급수별(8급~3급) 및 전 연령 기본 학습 팩",
                            fontSize = 13.sp,
                            color = Color(0xFF38BDF8),
                            fontWeight = FontWeight.SemiBold
                        )
                        LazyRow(
                            horizontalArrangement = Arrangement.spacedBy(8.dp),
                            modifier = Modifier.fillMaxWidth()
                        ) {
                            items(BuiltInCurriculumCatalog.collections) { col ->
                                FilterChip(
                                    selected = state.selectedCollectionId == col.collectionId,
                                    onClick = { onSelectCollection(col.collectionId) },
                                    label = { Text(col.title) }
                                )
                            }
                        }
                        OutlinedButton(
                            onClick = onGenerateCollectionDeck,
                            modifier = Modifier.fillMaxWidth()
                        ) {
                            Text("📚 선택한 급수·기본 컬렉션 덱 즉시 생성")
                        }
                    }
                }
            }

            item {
                Card(
                    colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface),
                    shape = RoundedCornerShape(14.dp),
                    modifier = Modifier.fillMaxWidth()
                ) {
                    Column(
                        modifier = Modifier.padding(16.dp),
                        verticalArrangement = Arrangement.spacedBy(12.dp)
                    ) {
                        Text(
                            text = "📄 사진 & PDF 자동 덱 생성기",
                            fontSize = 16.sp,
                            fontWeight = FontWeight.SemiBold
                        )

                        Row(
                            horizontalArrangement = Arrangement.spacedBy(8.dp),
                            modifier = Modifier.fillMaxWidth()
                        ) {
                            FilterChip(
                                selected = state.selectedCategoryOverride == null,
                                onClick = { onSelectCategory(null) },
                                label = { Text("자동 감지") }
                            )
                            CATEGORY_LABELS.forEach { (catId, label) ->
                                FilterChip(
                                    selected = state.selectedCategoryOverride == catId,
                                    onClick = { onSelectCategory(catId) },
                                    label = { Text(label.substringBefore("·")) }
                                )
                            }
                        }

                        OutlinedTextField(
                            value = state.customDeckTitle,
                            onValueChange = onDeckTitleChange,
                            label = { Text("덱 제목 (비워두면 문서 제목으로 자동 설정)") },
                            singleLine = true,
                            modifier = Modifier.fillMaxWidth()
                        )

                        Row(
                            horizontalArrangement = Arrangement.spacedBy(10.dp),
                            modifier = Modifier.fillMaxWidth()
                        ) {
                            Button(
                                onClick = onPickPhoto,
                                enabled = !state.isIngesting,
                                modifier = Modifier.weight(1f)
                            ) {
                                Text("📷 사진/교재 스캔 선택")
                            }
                            OutlinedButton(
                                onClick = onPickPdf,
                                enabled = !state.isIngesting,
                                modifier = Modifier.weight(1f)
                            ) {
                                Text("📑 강의안 PDF 선택")
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
                            text = "추출된 카드 프리뷰 (${preview.cards.size}장 · ${preview.category})",
                            fontWeight = FontWeight.Bold,
                            fontSize = 15.sp
                        )
                        Button(onClick = onSavePreviewDeck) {
                            Text("⚡ 덱 일괄 생성 (${preview.cards.size}장)")
                        }
                    }
                }

                itemsIndexed(preview.cards) { idx, card ->
                    Card(
                        colors = CardDefaults.cardColors(containerColor = Color(0xFF1E293B)),
                        shape = RoundedCornerShape(10.dp),
                        modifier = Modifier.fillMaxWidth()
                    ) {
                        Column(
                            modifier = Modifier.padding(12.dp),
                            verticalArrangement = Arrangement.spacedBy(6.dp)
                        ) {
                            Row(
                                modifier = Modifier.fillMaxWidth(),
                                horizontalArrangement = Arrangement.SpaceBetween,
                                verticalAlignment = Alignment.CenterVertically
                            ) {
                                Text(
                                    text = "${card.pattern} · p.${card.sourcePage} · ${card.spec.noteType.uppercase()}",
                                    color = Color(0xFF38BDF8),
                                    fontSize = 11.sp,
                                    fontWeight = FontWeight.SemiBold
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
                                label = { Text("질문 (Front)") },
                                modifier = Modifier.fillMaxWidth()
                            )
                            OutlinedTextField(
                                value = card.spec.backText,
                                onValueChange = { updatedBack ->
                                    onUpdatePreviewCard(idx, card.spec.frontText, updatedBack)
                                },
                                label = { Text("정답 (Back)") },
                                modifier = Modifier.fillMaxWidth()
                            )
                        }
                    }
                }
            }

            // Active FSRS-5 Review Arena (Cloze-safe rendering before reveal)
            item {
                Card(
                    colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface),
                    shape = RoundedCornerShape(14.dp),
                    modifier = Modifier.fillMaxWidth()
                ) {
                    Column(
                        modifier = Modifier.padding(16.dp),
                        verticalArrangement = Arrangement.spacedBy(12.dp)
                    ) {
                        Text(
                            text = "🧠 FSRS-5 오늘의 복습 (${state.dueCards.size}장 대기)",
                            fontSize = 16.sp,
                            fontWeight = FontWeight.SemiBold
                        )
                        val currentDue = state.dueCards.firstOrNull()
                        if (currentDue == null) {
                            Text(
                                text = "현재 복습 대기 중인 카드가 없습니다. 위에서 사진이나 PDF를 추가해 새 덱을 만들어 보세요!",
                                color = Color(0xFF9CA3AF),
                                fontSize = 13.sp
                            )
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

                            Text(
                                text = "출처: ${currentDue.sourceFilename} (p.${currentDue.sourcePage})",
                                color = Color(0xFF38BDF8),
                                fontSize = 11.sp
                            )
                            Text(
                                text = questionDisplay,
                                fontSize = 17.sp,
                                fontWeight = FontWeight.Bold
                            )
                            if (!state.isAnswerRevealed) {
                                Button(
                                    onClick = onRevealAnswer,
                                    modifier = Modifier.fillMaxWidth()
                                ) {
                                    Text("정답 확인 (Space)")
                                }
                            } else {
                                Text(
                                    text = currentDue.back,
                                    fontSize = 16.sp,
                                    color = Color(0xFF6EE7B7),
                                    fontWeight = FontWeight.SemiBold
                                )
                                if (currentDue.sourceExcerpt.isNotBlank()) {
                                    Text(
                                        text = "📄 원문 발췌 (p.${currentDue.sourcePage}): ${currentDue.sourceExcerpt}",
                                        fontSize = 12.sp,
                                        color = Color(0xFF9CA3AF)
                                    )
                                }
                                Row(
                                    horizontalArrangement = Arrangement.spacedBy(8.dp),
                                    modifier = Modifier.fillMaxWidth()
                                ) {
                                    OutlinedButton(
                                        onClick = { onRateCard(Rating.AGAIN) },
                                        modifier = Modifier.weight(1f)
                                    ) { Text("Again") }
                                    OutlinedButton(
                                        onClick = { onRateCard(Rating.HARD) },
                                        modifier = Modifier.weight(1f)
                                    ) { Text("Hard") }
                                    Button(
                                        onClick = { onRateCard(Rating.GOOD) },
                                        modifier = Modifier.weight(1f)
                                    ) { Text("Good") }
                                    OutlinedButton(
                                        onClick = { onRateCard(Rating.EASY) },
                                        modifier = Modifier.weight(1f)
                                    ) { Text("Easy") }
                                }
                            }
                        }
                    }
                }
            }
        }
    }
}
