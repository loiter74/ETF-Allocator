import type { OcrTextSegment } from '../types';

export interface OcrProgress {
  fileIndex: number;
  fileCount: number;
  fileName: string;
  status: string;
  progress: number;
}

export async function recognizeBrokerScreenshots(
  files: File[],
  onProgress: (progress: OcrProgress) => void,
): Promise<OcrTextSegment[]> {
  const { createWorker } = await import('tesseract.js');
  let activeIndex = 0;
  const worker = await createWorker('chi_sim+eng', 1, {
    logger: message => {
      onProgress({
        fileIndex: activeIndex,
        fileCount: files.length,
        fileName: files[activeIndex]?.name ?? '',
        status: message.status,
        progress: Number.isFinite(message.progress) ? message.progress : 0,
      });
    },
  });
  try {
    const segments: OcrTextSegment[] = [];
    for (activeIndex = 0; activeIndex < files.length; activeIndex += 1) {
      const file = files[activeIndex];
      onProgress({ fileIndex: activeIndex, fileCount: files.length, fileName: file.name, status: '识别文字', progress: 0 });
      const result = await worker.recognize(file);
      segments.push({
        name: file.name,
        text: result.data.text.trim(),
        ocr_confidence: result.data.confidence,
      });
      onProgress({ fileIndex: activeIndex, fileCount: files.length, fileName: file.name, status: '完成', progress: 1 });
    }
    return segments;
  } finally {
    await worker.terminate();
  }
}

