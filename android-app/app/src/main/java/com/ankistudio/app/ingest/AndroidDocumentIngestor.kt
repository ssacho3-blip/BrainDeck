package com.ankistudio.app.ingest

import android.content.ContentResolver
import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.pdf.PdfRenderer
import android.net.Uri
import android.os.ParcelFileDescriptor
import com.ankistudio.domain.deck.DocumentDeckBuilder
import com.ankistudio.domain.deck.DocumentDeckBuilder.BuildStats
import com.ankistudio.domain.deck.DocumentDeckBuilder.DeckPlan
import com.ankistudio.domain.deck.DocumentDeckBuilder.DocumentBlock
import com.ankistudio.domain.deck.DocumentDeckBuilder.ExtractedDocument
import com.google.mlkit.vision.common.InputImage
import com.google.mlkit.vision.text.TextRecognition
import com.google.mlkit.vision.text.korean.KoreanTextRecognizerOptions
import java.io.Closeable
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.tasks.await
import kotlinx.coroutines.withContext
import kotlin.math.max
import kotlin.math.roundToInt

/**
 * On-Device Android Photo & PDF Document Ingestor.
 *
 * Enforces identical Fail-Closed guards as the desktop/server adapter:
 * - Max payload size: 20 MB (`too_large`)
 * - Max PDF pages: 50 (`too_many_pages` — blocks instead of silently truncating)
 * - Uses Google ML Kit Korean + Latin Text Recognition v2 completely offline.
 * - Uses Android's native [PdfRenderer] to render each page at ~200 DPI onto a white-backed
 *   [Bitmap], runs ML Kit OCR per page, and recycles each page bitmap immediately in `finally`.
 * - Implements [Closeable] so the ML Kit [TextRecognizer] is deterministically released in ViewModel.onCleared().
 */
class AndroidDocumentIngestor(
    private val contentResolver: ContentResolver
) : Closeable {

    private val recognizer = TextRecognition.getClient(
        KoreanTextRecognizerOptions.Builder().build()
    )

    companion object {
        const val MAX_DOCUMENT_BYTES = 20L * 1024L * 1024L // 20 MB
        const val MAX_PDF_PAGES = 50
        const val MAX_PAGE_DIMENSION_PX = 2200

        private val LIST_MARKER_RE = Regex("""^(?:[①②③④⑤⑥⑦⑧⑨⑩]|\(\d+\)|\d+\)|\d+\.|•|-\s).*""")
        private val CHAPTER_HEADING_RE = Regex("""^(?:#|제\s*\d+\s*[장절편]\b|(?:Chapter|Section|Part)\s+\d+\b).*""", RegexOption.IGNORE_CASE)
        private val DIGIT_RE = Regex("""\d""")
        private val SENTENCE_END_RE = Regex("""(?:다|요|음|함|됨)$""")

        fun classifyLineKind(line: String): String {
            val trimmed = line.trim()
            if (LIST_MARKER_RE.matches(trimmed)) return "list_item"
            if (CHAPTER_HEADING_RE.matches(trimmed)) return "heading"
            if (
                trimmed.length <= 28 &&
                !trimmed.contains(":") &&
                !trimmed.contains("：") &&
                !trimmed.contains(".") &&
                !trimmed.contains("->") &&
                !DIGIT_RE.containsMatchIn(trimmed) &&
                !SENTENCE_END_RE.containsMatchIn(trimmed)
            ) {
                return "heading"
            }
            return "paragraph"
        }
    }

    suspend fun ingestUri(
        uri: Uri,
        filename: String,
        mimeType: String?,
        categoryOverride: String? = null,
        deckTitleOverride: String? = null,
        maxCards: Int = 30
    ): DeckPlan = withContext(Dispatchers.IO) {
        val cleanTitleHint = filename.substringBeforeLast(".")
        val targetDeckName = deckTitleOverride?.takeIf { it.isNotBlank() } ?: cleanTitleHint
        val byteSize = resolveUriByteSizeFailClosed(uri)
            ?: return@withContext blockedPlan(
                errorCode = "corrupt_file",
                deckName = targetDeckName
            )
        if (byteSize <= 0L) {
            return@withContext blockedPlan(
                errorCode = "corrupt_file",
                deckName = targetDeckName
            )
        }
        if (byteSize > MAX_DOCUMENT_BYTES) {
            return@withContext blockedPlan(
                errorCode = "too_large",
                deckName = targetDeckName
            )
        }

        val isPdf = mimeType?.lowercase() == "application/pdf" ||
            filename.lowercase().endsWith(".pdf")

        if (isPdf) {
            extractPdfDocument(
                uri = uri,
                titleHint = cleanTitleHint,
                categoryOverride = categoryOverride,
                deckTitleOverride = deckTitleOverride,
                maxCards = maxCards
            )
        } else {
            extractImageDocument(
                uri = uri,
                titleHint = cleanTitleHint,
                categoryOverride = categoryOverride,
                deckTitleOverride = deckTitleOverride,
                maxCards = maxCards
            )
        }
    }

    /**
     * Fail-Closed URI byte size inspection:
     * 1. Uses [ParcelFileDescriptor.getStatSize] when positive.
     * 2. If `statSize` is negative/unknown (e.g. streaming ContentProvider), performs a bounded
     *    stream read capped at `MAX_DOCUMENT_BYTES + 1` so oversized streams are rejected before decoding.
     * 3. Returns `null` if the URI cannot be opened or read.
     */
    private fun resolveUriByteSizeFailClosed(uri: Uri): Long? {
        try {
            contentResolver.openFileDescriptor(uri, "r")?.use { pfd ->
                val stat = pfd.statSize
                if (stat > 0L) return stat
                if (stat == 0L) return 0L
            }
        } catch (_: Exception) {
            // Fall through to bounded stream check
        }

        return try {
            contentResolver.openInputStream(uri)?.use { stream ->
                val buffer = ByteArray(64 * 1024)
                val maxAllowed = MAX_DOCUMENT_BYTES + 1L
                var total = 0L
                while (total < maxAllowed) {
                    val toRead = minOf(buffer.size.toLong(), maxAllowed - total).toInt()
                    val read = stream.read(buffer, 0, toRead)
                    if (read <= 0) break
                    total += read.toLong()
                }
                total
            }
        } catch (_: Exception) {
            null
        }
    }

    private suspend fun extractImageDocument(
        uri: Uri,
        titleHint: String,
        categoryOverride: String?,
        deckTitleOverride: String?,
        maxCards: Int
    ): DeckPlan {
        val bitmap = decodeSampledBitmap(uri, MAX_PAGE_DIMENSION_PX)
            ?: return blockedPlan("corrupt_file", deckTitleOverride ?: titleHint)
        val blocks = try {
            runMlKitOcrOnBitmap(bitmap, pageNumber = 1)
        } finally {
            bitmap.recycle()
        }
        val doc = ExtractedDocument(
            blocks = blocks,
            titleHint = titleHint,
            sourceKind = "image",
            pageCount = 1
        )
        return DocumentDeckBuilder.buildDeckPlan(
            doc = doc,
            userDeckName = deckTitleOverride,
            categoryOverride = categoryOverride,
            maxCards = maxCards,
            ocrPages = 1
        )
    }

    private suspend fun extractPdfDocument(
        uri: Uri,
        titleHint: String,
        categoryOverride: String?,
        deckTitleOverride: String?,
        maxCards: Int
    ): DeckPlan {
        val pfd: ParcelFileDescriptor = try {
            contentResolver.openFileDescriptor(uri, "r")
        } catch (_: Exception) {
            null
        } ?: return blockedPlan("corrupt_file", deckTitleOverride ?: titleHint)

        pfd.use { descriptor ->
            val renderer = try {
                PdfRenderer(descriptor)
            } catch (_: SecurityException) {
                return blockedPlan("encrypted_pdf", deckTitleOverride ?: titleHint)
            } catch (_: Exception) {
                return blockedPlan("corrupt_file", deckTitleOverride ?: titleHint)
            }

            renderer.use { pdfRenderer ->
                val pageCount = pdfRenderer.pageCount
                if (pageCount <= 0) {
                    return blockedPlan("corrupt_file", deckTitleOverride ?: titleHint)
                }
                if (pageCount > MAX_PDF_PAGES) {
                    return blockedPlan(
                        errorCode = "too_many_pages",
                        deckName = deckTitleOverride ?: titleHint,
                        pages = pageCount
                    )
                }

                val allBlocks = mutableListOf<DocumentBlock>()
                for (pageIndex in 0 until pageCount) {
                    val pageNumber = pageIndex + 1
                    pdfRenderer.openPage(pageIndex).use { pdfPage ->
                        val rawWidth = (pdfPage.width * 2.77f).roundToInt().coerceAtLeast(1)
                        val rawHeight = (pdfPage.height * 2.77f).roundToInt().coerceAtLeast(1)
                        val largestDim = max(rawWidth, rawHeight)
                        val scale = if (largestDim > MAX_PAGE_DIMENSION_PX) {
                            MAX_PAGE_DIMENSION_PX.toFloat() / largestDim.toFloat()
                        } else {
                            1.0f
                        }
                        val targetWidth = (rawWidth * scale).roundToInt().coerceAtLeast(1)
                        val targetHeight = (rawHeight * scale).roundToInt().coerceAtLeast(1)

                        val bitmap = Bitmap.createBitmap(
                            targetWidth,
                            targetHeight,
                            Bitmap.Config.ARGB_8888
                        )
                        try {
                            val canvas = Canvas(bitmap)
                            canvas.drawColor(Color.WHITE)
                            pdfPage.render(
                                bitmap,
                                null,
                                null,
                                PdfRenderer.Page.RENDER_MODE_FOR_DISPLAY
                            )
                            val pageBlocks = runMlKitOcrOnBitmap(
                                bitmap = bitmap,
                                pageNumber = pageNumber
                            )
                            allBlocks.addAll(pageBlocks)
                        } finally {
                            bitmap.recycle()
                        }
                    }
                }

                val doc = ExtractedDocument(
                    blocks = allBlocks,
                    titleHint = titleHint,
                    sourceKind = "pdf",
                    pageCount = pageCount
                )
                return DocumentDeckBuilder.buildDeckPlan(
                    doc = doc,
                    userDeckName = deckTitleOverride,
                    categoryOverride = categoryOverride,
                    maxCards = maxCards,
                    ocrPages = pageCount
                )
            }
        }
    }

    private suspend fun runMlKitOcrOnBitmap(
        bitmap: Bitmap,
        pageNumber: Int
    ): List<DocumentBlock> {
        val image = InputImage.fromBitmap(bitmap, 0)
        val visionText = recognizer.process(image).await()
        val extracted = mutableListOf<DocumentBlock>()

        for (block in visionText.textBlocks) {
            for (line in block.lines) {
                val cleaned = line.text.trim()
                if (cleaned.isNotEmpty()) {
                    // Preserve ML Kit confidence as-is (nullable Double), never fabricate 1.0
                    val rawConfidence: Float? = line.confidence
                    val confidenceDouble: Double? = rawConfidence?.toDouble()
                    extracted.add(
                        DocumentBlock(
                            kind = classifyLineKind(cleaned),
                            text = cleaned,
                            page = pageNumber,
                            confidence = confidenceDouble
                        )
                    )
                }
            }
        }
        return extracted
    }

    private fun decodeSampledBitmap(uri: Uri, maxDimensionPx: Int): Bitmap? {
        val boundsOptions = BitmapFactory.Options().apply {
            inJustDecodeBounds = true
        }
        contentResolver.openInputStream(uri)?.use { stream ->
            BitmapFactory.decodeStream(stream, null, boundsOptions)
        }
        if (boundsOptions.outWidth <= 0 || boundsOptions.outHeight <= 0) {
            return null
        }

        var inSampleSize = 1
        while (
            (boundsOptions.outWidth / inSampleSize) > maxDimensionPx ||
            (boundsOptions.outHeight / inSampleSize) > maxDimensionPx
        ) {
            inSampleSize *= 2
        }

        val decodeOptions = BitmapFactory.Options().apply {
            this.inSampleSize = inSampleSize
            this.inPreferredConfig = Bitmap.Config.ARGB_8888
        }
        return contentResolver.openInputStream(uri)?.use { stream ->
            BitmapFactory.decodeStream(stream, null, decodeOptions)
        }
    }

    private fun blockedPlan(errorCode: String, deckName: String, pages: Int = 0): DeckPlan {
        return DeckPlan(
            status = "BLOCKED",
            errorCode = errorCode,
            deckName = deckName.ifBlank { "문서 덱" },
            category = "general",
            cards = emptyList(),
            stats = BuildStats(
                pages = pages,
                ocrPages = 0,
                lowConfidenceLines = 0,
                unmeasuredConfidenceLines = 0,
                droppedUngrounded = 0,
                duplicates = 0,
                totalChars = 0
            )
        )
    }

    override fun close() {
        recognizer.close()
    }
}
