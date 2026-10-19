#import <Foundation/Foundation.h>
#import <AppKit/AppKit.h>
#import <Vision/Vision.h>
#import <PDFKit/PDFKit.h>
#import <ImageIO/ImageIO.h>

static NSString *classifyLineKind(NSString *line) {
    NSString *trimmed = [line stringByTrimmingCharactersInSet:[NSCharacterSet whitespaceAndNewlineCharacterSet]];
    if ([trimmed hasPrefix:@"1)"] || [trimmed hasPrefix:@"1."] || [trimmed hasPrefix:@"①"] || [trimmed hasPrefix:@"•"] || [trimmed hasPrefix:@"- "]) {
        return @"list_item";
    }
    if ([trimmed hasPrefix:@"#"] || [trimmed hasPrefix:@"제1장"] || [trimmed hasPrefix:@"제2장"] || [trimmed hasPrefix:@"제3장"]) {
        return @"heading";
    }
    BOOL hasDigit = ([trimmed rangeOfCharacterFromSet:[NSCharacterSet decimalDigitCharacterSet]].location != NSNotFound);
    BOOL hasSentenceEnding = ([trimmed hasSuffix:@"다"] || [trimmed hasSuffix:@"요"] || [trimmed hasSuffix:@"음"] || [trimmed hasSuffix:@"함"] || [trimmed hasSuffix:@"됨"]);
    if ([trimmed length] <= 28 &&
        ![trimmed containsString:@":"] &&
        ![trimmed containsString:@"："] &&
        ![trimmed containsString:@"."] &&
        ![trimmed containsString:@"->"] &&
        !hasDigit &&
        !hasSentenceEnding) {
        return @"heading";
    }
    return @"paragraph";
}

static NSArray<NSDictionary *> *runVisionOcrOnCGImage(CGImageRef cgImage, NSInteger pageNumber) {
    if (!cgImage) return @[];
    NSMutableArray<NSDictionary *> *blocks = [NSMutableArray array];

    void (^collectResults)(VNRequest *, NSError *) = ^(VNRequest *req, NSError *err) {
        if (err) return;
        for (VNRecognizedTextObservation *obs in req.results) {
            VNRecognizedText *top = [[obs topCandidates:1] firstObject];
            if (!top) continue;
            NSString *str = [top.string stringByTrimmingCharactersInSet:[NSCharacterSet whitespaceAndNewlineCharacterSet]];
            if ([str length] == 0) continue;
            double conf = (double)top.confidence;
            [blocks addObject:@{
                @"kind": classifyLineKind(str),
                @"text": str,
                @"page": @(pageNumber),
                @"confidence": @(conf)
            }];
        }
    };

    VNRecognizeTextRequest *request = [[VNRecognizeTextRequest alloc] initWithCompletionHandler:collectResults];
    request.recognitionLevel = VNRequestTextRecognitionLevelAccurate;
    request.usesLanguageCorrection = YES;
    request.recognitionLanguages = @[@"ko-KR", @"en-US"];

    VNImageRequestHandler *handler = [[VNImageRequestHandler alloc] initWithCGImage:cgImage options:@{}];
    NSError *performErr = nil;
    [handler performRequests:@[request] error:&performErr];

    if ([blocks count] == 0) {
        VNRecognizeTextRequest *cpuAccurateReq = [[VNRecognizeTextRequest alloc] initWithCompletionHandler:collectResults];
        cpuAccurateReq.recognitionLevel = VNRequestTextRecognitionLevelAccurate;
        cpuAccurateReq.usesLanguageCorrection = YES;
        cpuAccurateReq.recognitionLanguages = @[@"ko-KR", @"en-US"];
#pragma clang diagnostic push
#pragma clang diagnostic ignored "-Wdeprecated-declarations"
        cpuAccurateReq.usesCPUOnly = YES;
#pragma clang diagnostic pop
        [handler performRequests:@[cpuAccurateReq] error:nil];
    }
    return blocks;
}

static void emitJsonAndExit(NSDictionary *dict, int code) {
    NSData *data = [NSJSONSerialization dataWithJSONObject:dict options:0 error:nil];
    if (data) {
        fwrite([data bytes], 1, [data length], stdout);
        fwrite("\n", 1, 1, stdout);
    }
    exit(code);
}

int main(int argc, const char * argv[]) {
    @autoreleasepool {
        if (argc < 2) {
            emitJsonAndExit(@{@"ok": @NO, @"error_code": @"missing_input"}, 1);
        }
        NSString *filePath = [NSString stringWithUTF8String:argv[1]];
        NSString *mime = argc >= 3 ? [NSString stringWithUTF8String:argv[2]] : @"";
        NSURL *fileURL = [NSURL fileURLWithPath:filePath];

        BOOL isPdf = [mime isEqualToString:@"application/pdf"] || [[filePath lowercaseString] hasSuffix:@".pdf"];
        if (isPdf) {
            PDFDocument *pdfDoc = [[PDFDocument alloc] initWithURL:fileURL];
            if (!pdfDoc) {
                emitJsonAndExit(@{@"ok": @NO, @"error_code": @"corrupt_file"}, 0);
            }
            if (pdfDoc.isEncrypted && pdfDoc.isLocked) {
                emitJsonAndExit(@{@"ok": @NO, @"error_code": @"encrypted_pdf"}, 0);
            }
            NSInteger pageCount = pdfDoc.pageCount;
            if (pageCount <= 0) {
                emitJsonAndExit(@{@"ok": @NO, @"error_code": @"corrupt_file"}, 0);
            }
            if (pageCount > 50) {
                emitJsonAndExit(@{@"ok": @NO, @"error_code": @"too_many_pages", @"page_count": @(pageCount)}, 0);
            }

            NSMutableArray<NSDictionary *> *allBlocks = [NSMutableArray array];
            NSInteger ocrPages = 0;
            NSString *titleHint = pdfDoc.documentAttributes[PDFDocumentTitleAttribute] ?: @"";

            for (NSInteger i = 0; i < pageCount; i++) {
                PDFPage *page = [pdfDoc pageAtIndex:i];
                if (!page) continue;
                NSString *pageText = [[page string] stringByTrimmingCharactersInSet:[NSCharacterSet whitespaceAndNewlineCharacterSet]];
                if (pageText && [pageText length] >= 20) {
                    NSArray<NSString *> *lines = [pageText componentsSeparatedByCharactersInSet:[NSCharacterSet newlineCharacterSet]];
                    for (NSString *ln in lines) {
                        NSString *trimmed = [ln stringByTrimmingCharactersInSet:[NSCharacterSet whitespaceAndNewlineCharacterSet]];
                        if ([trimmed length] == 0) continue;
                        [allBlocks addObject:@{
                            @"kind": classifyLineKind(trimmed),
                            @"text": trimmed,
                            @"page": @(i + 1),
                            @"confidence": @(1.0)
                        }];
                    }
                } else {
                    ocrPages += 1;
                    NSRect bounds = [page boundsForBox:kPDFDisplayBoxMediaBox];
                    CGFloat scale = 2.0;
                    NSSize targetSize = NSMakeSize(MAX(400, bounds.size.width * scale), MAX(400, bounds.size.height * scale));
                    NSImage *img = [page thumbnailOfSize:targetSize forBox:kPDFDisplayBoxMediaBox];
                    CGImageRef cgImg = [img CGImageForProposedRect:NULL context:nil hints:nil];
                    NSArray<NSDictionary *> *ocrBlocks = runVisionOcrOnCGImage(cgImg, i + 1);
                    [allBlocks addObjectsFromArray:ocrBlocks];
                }
            }

            emitJsonAndExit(@{
                @"ok": @YES,
                @"source_kind": @"pdf",
                @"title_hint": titleHint,
                @"page_count": @(pageCount),
                @"ocr_pages": @(ocrPages),
                @"blocks": allBlocks
            }, 0);
        } else {
            CGImageSourceRef src = CGImageSourceCreateWithURL((__bridge CFURLRef)fileURL, NULL);
            if (!src) {
                emitJsonAndExit(@{@"ok": @NO, @"error_code": @"corrupt_file"}, 0);
            }
            CGImageRef cgImg = CGImageSourceCreateImageAtIndex(src, 0, NULL);
            CFRelease(src);
            if (!cgImg) {
                emitJsonAndExit(@{@"ok": @NO, @"error_code": @"corrupt_file"}, 0);
            }
            NSArray<NSDictionary *> *ocrBlocks = runVisionOcrOnCGImage(cgImg, 1);
            CGImageRelease(cgImg);

            emitJsonAndExit(@{
                @"ok": @YES,
                @"source_kind": @"image",
                @"title_hint": @"",
                @"page_count": @(1),
                @"ocr_pages": @(1),
                @"blocks": ocrBlocks
            }, 0);
        }
    }
    return 0;
}
