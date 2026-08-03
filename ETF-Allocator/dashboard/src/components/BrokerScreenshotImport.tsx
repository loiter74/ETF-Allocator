import { useEffect, useMemo, useRef, useState } from 'react';
import { ImagePlus, ShieldCheck, Trash2, WandSparkles } from 'lucide-react';
import { useSnapshotImport } from '../hooks/useSnapshotImport';
import { recognizeBrokerScreenshots, type OcrProgress } from '../lib/browserOcr';
import type {
  SnapshotImportDraft,
  SnapshotImportField,
  SnapshotImportPosition,
} from '../types';

interface SelectedImage {
  id: string;
  file: File;
  previewUrl: string;
}

interface BrokerScreenshotImportProps {
  snapshotDate: string;
  onApply: (draft: SnapshotImportDraft) => void;
}

const REVIEW_INPUT = `w-full rounded-lg border border-[var(--color-border)] bg-white/80 px-2 py-1.5
  text-xs tabular-nums text-[#1F2937] outline-none focus:border-[var(--color-accent)]`;

function sourceLabel(source: string): string {
  return {
    deepseek: 'DeepSeek',
    local_parser: '本地规则',
    market_data: '行情补齐',
    user: '人工修改',
    missing: '未识别',
  }[source] ?? source;
}

function fieldClass(field: SnapshotImportField<unknown>): string {
  return field.value == null || field.confidence < 0.75
    ? 'border-[var(--color-warn)]/50 bg-[var(--color-warn)]/10'
    : 'border-[var(--color-safe)]/30 bg-[var(--color-safe)]/5';
}

function editField<T extends number | string>(field: SnapshotImportField<T>, value: T | null): SnapshotImportField<T> {
  return { ...field, value, confidence: 1, source: 'user', evidence: '人工核对修改' };
}

function consistencyWarning(position: SnapshotImportPosition): string | null {
  const shares = position.shares.value;
  const price = position.price.value;
  const marketValue = position.market_value.value;
  if (shares == null || price == null || marketValue == null) return null;
  const expected = shares * price;
  const relativeError = Math.abs(marketValue - expected) / Math.max(marketValue, expected, 1);
  if (relativeError <= 0.08) return null;
  return `${position.asset.value ?? '该持仓'}识别市值与份额×现价相差${Math.round(relativeError * 100)}%，必须修改后才能应用`;
}

export function BrokerScreenshotImport({ snapshotDate, onApply }: BrokerScreenshotImportProps) {
  const [images, setImages] = useState<SelectedImage[]>([]);
  const [pasteText, setPasteText] = useState('');
  const [localError, setLocalError] = useState<string | null>(null);
  const [ocrProgress, setOcrProgress] = useState<OcrProgress | null>(null);
  const [ocrLoading, setOcrLoading] = useState(false);
  const [applied, setApplied] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);
  const imagesRef = useRef<SelectedImage[]>([]);
  const { config, data, loading, error, parseText, setData } = useSnapshotImport();

  useEffect(() => {
    imagesRef.current = images;
  }, [images]);

  useEffect(() => () => {
    imagesRef.current.forEach(image => URL.revokeObjectURL(image.previewUrl));
  }, []);

  const totalBytes = useMemo(() => images.reduce((sum, image) => sum + image.file.size, 0), [images]);
  const unreviewedCount = useMemo(() => {
    if (!data) return 0;
    const fields: SnapshotImportField<number>[] = [
      data.draft.account_cash,
      ...data.draft.positions.flatMap(position => [
        position.shares, position.price, position.average_cost, position.market_value,
      ]),
    ];
    return fields.filter(field => field.value != null && field.confidence < 0.75).length;
  }, [data]);
  const consistencyIssueCount = useMemo(
    () => data?.draft.positions.filter(position => consistencyWarning(position) !== null).length ?? 0,
    [data],
  );

  const addFiles = (selected: File[]) => {
    setApplied(false);
    setLocalError(null);
    const combined = [...images.map(image => image.file), ...selected];
    if (combined.length > config.max_files) {
      setLocalError(`最多上传 ${config.max_files} 张截图。`);
      return;
    }
    const invalidType = selected.find(file => !config.accepted_image_types.includes(file.type));
    if (invalidType) {
      setLocalError(`${invalidType.name} 格式不支持，请使用 PNG、JPEG 或 WebP。`);
      return;
    }
    const oversized = selected.find(file => file.size > config.max_file_bytes);
    if (oversized) {
      setLocalError(`${oversized.name} 超过单张 ${(config.max_file_bytes / 1024 / 1024).toFixed(0)}MB 限制。`);
      return;
    }
    if (combined.reduce((sum, file) => sum + file.size, 0) > config.max_total_bytes) {
      setLocalError(`截图合计不能超过 ${(config.max_total_bytes / 1024 / 1024).toFixed(0)}MB。`);
      return;
    }
    const next = selected.map(file => ({
      id: `${file.name}-${file.size}-${file.lastModified}-${crypto.randomUUID?.() ?? Math.random()}`,
      file,
      previewUrl: URL.createObjectURL(file),
    }));
    setImages(current => [...current, ...next]);
  };

  const removeImage = (id: string) => {
    setImages(current => current.filter(image => {
      if (image.id === id) URL.revokeObjectURL(image.previewUrl);
      return image.id !== id;
    }));
  };

  const handleRecognize = async () => {
    if (!images.length) {
      setLocalError('请先选择券商持仓截图。');
      return;
    }
    setApplied(false);
    setLocalError(null);
    setOcrLoading(true);
    try {
      const segments = await recognizeBrokerScreenshots(images.map(image => image.file), setOcrProgress);
      if (!segments.some(segment => segment.text.trim())) throw new Error('没有识别到文字，请换清晰截图或粘贴 OCR 文字。');
      setPasteText(segments.map(segment => segment.text).join('\n\n'));
      await parseText({ snapshot_date: snapshotDate, ocr_texts: segments });
    } catch (cause) {
      setLocalError((cause as Error).message);
    } finally {
      setOcrLoading(false);
    }
  };

  const handleParsePaste = () => {
    if (!pasteText.trim()) {
      setLocalError('请先粘贴 OCR 文字。');
      return;
    }
    setApplied(false);
    setLocalError(null);
    void parseText({
      snapshot_date: snapshotDate,
      ocr_texts: [{ name: '粘贴文字', text: pasteText.trim() }],
    });
  };

  const updateCash = (raw: string) => {
    if (!data) return;
    const value = raw === '' ? null : Math.max(0, Number(raw));
    setData({ ...data, draft: { ...data.draft, account_cash: editField(data.draft.account_cash, value) } });
  };

  const updatePosition = (index: number, key: 'shares' | 'price' | 'average_cost' | 'market_value', raw: string) => {
    if (!data) return;
    const value = raw === '' ? null : Math.max(0, Number(raw));
    const original = data.draft.positions[index];
    const warningPrefix = `${String(original.asset.value ?? '该持仓')}识别市值与份额×现价`;
    let newWarning: string | null = null;
    const positions = data.draft.positions.map((position, positionIndex) => {
      if (positionIndex !== index) return position;
      const updated = { ...position, [key]: editField(position[key], value) };
      newWarning = consistencyWarning(updated);
      return {
        ...updated,
        warnings: [
          ...updated.warnings.filter(warning => !warning.startsWith(warningPrefix)),
          ...(newWarning ? [newWarning] : []),
        ],
      };
    });
    setData({
      ...data,
      warnings: [
        ...data.warnings.filter(warning => !warning.startsWith(warningPrefix)),
        ...(newWarning ? [newWarning] : []),
      ],
      draft: { ...data.draft, positions },
    });
  };

  const confirmPosition = (index: number) => {
    if (!data) return;
    const positions = data.draft.positions.map((position, positionIndex) => {
      if (positionIndex !== index) return position;
      return {
        ...position,
        shares: position.shares.value == null ? position.shares : editField(position.shares, position.shares.value),
        price: position.price.value == null ? position.price : editField(position.price, position.price.value),
        average_cost: position.average_cost.value == null ? position.average_cost : editField(position.average_cost, position.average_cost.value),
        market_value: position.market_value.value == null ? position.market_value : editField(position.market_value, position.market_value.value),
      };
    });
    setData({ ...data, draft: { ...data.draft, positions } });
  };

  const confirmCash = () => {
    if (!data || data.draft.account_cash.value == null) return;
    setData({
      ...data,
      draft: {
        ...data.draft,
        account_cash: editField(data.draft.account_cash, data.draft.account_cash.value),
      },
    });
  };

  const handleApply = () => {
    if (!data) return;
    onApply(data.draft);
    setApplied(true);
  };

  return (
    <section className="space-y-3 rounded-xl border border-[var(--color-accent-light)] bg-[var(--color-chromatic-50)]/60 p-3" data-testid="broker-screenshot-import">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <div className="flex items-center gap-2 text-sm font-semibold text-[#1F2937]">
            <ImagePlus size={16} /> 截图自动填充
          </div>
          <p className="mt-1 text-[11px] leading-5 text-[var(--color-muted)]">
            先裁掉姓名和账号。图片只在本浏览器 OCR，服务器和 DeepSeek 都收不到原图。
          </p>
        </div>
        <span className="rounded-full bg-white/70 px-2 py-1 text-[10px] text-[var(--color-muted)]">
          {config.deepseek_enabled ? `DeepSeek ${config.model ?? ''} 增强` : '本地规则模式'}
        </span>
      </div>

      <div
        className="rounded-xl border border-dashed border-[var(--color-accent-light)] bg-white/55 p-4 text-center"
        onDragOver={event => event.preventDefault()}
        onDrop={event => {
          event.preventDefault();
          addFiles(Array.from(event.dataTransfer.files));
        }}
      >
        <input ref={inputRef} aria-label="选择券商截图" type="file" className="hidden" multiple
          accept={config.accepted_image_types.join(',')}
          onChange={event => addFiles(Array.from(event.target.files ?? []))} />
        <button type="button" onClick={() => inputRef.current?.click()}
          className="rounded-lg border border-[var(--color-border)] bg-white/80 px-4 py-2 text-xs font-semibold text-[var(--color-accent)]">
          选择或拖入持仓截图
        </button>
        <div className="mt-2 text-[10px] text-[var(--color-muted)]">
          最多 {config.max_files} 张 · 单张 {(config.max_file_bytes / 1024 / 1024).toFixed(0)}MB · 当前 {(totalBytes / 1024 / 1024).toFixed(1)}MB
        </div>
      </div>

      {images.length > 0 && (
        <div className="grid gap-2 sm:grid-cols-3">
          {images.map(image => (
            <div key={image.id} className="relative overflow-hidden rounded-lg border border-[var(--color-border)] bg-white/70 p-2">
              <img src={image.previewUrl} alt={image.file.name} className="h-24 w-full rounded object-contain" />
              <div className="mt-1 truncate pr-6 text-[10px] text-[var(--color-muted)]">{image.file.name}</div>
              <button type="button" aria-label={`删除 ${image.file.name}`} onClick={() => removeImage(image.id)}
                className="absolute bottom-1.5 right-1.5 rounded bg-white/90 p-1 text-[var(--color-dang)]">
                <Trash2 size={13} />
              </button>
            </div>
          ))}
        </div>
      )}

      <div className="flex flex-wrap items-center gap-2">
        <button type="button" onClick={handleRecognize} disabled={ocrLoading || loading || !images.length}
          className="inline-flex items-center gap-1.5 rounded-lg bg-[var(--color-accent)] px-4 py-2 text-xs font-semibold text-white disabled:opacity-50">
          <WandSparkles size={14} /> {ocrLoading ? '本地识别中…' : loading ? '结构化中…' : '识别并整理'}
        </button>
        {ocrProgress && ocrLoading && (
          <div className="min-w-48 flex-1 text-[10px] text-[var(--color-muted)]">
            <div className="mb-1 flex justify-between gap-2"><span className="truncate">{ocrProgress.fileName} · {ocrProgress.status}</span><span>{Math.round(ocrProgress.progress * 100)}%</span></div>
            <div className="h-1.5 overflow-hidden rounded-full bg-white/80"><div className="h-full bg-[var(--color-accent)] transition-all" style={{ width: `${ocrProgress.progress * 100}%` }} /></div>
          </div>
        )}
      </div>

      <details className="rounded-lg border border-[var(--color-border)] bg-white/45">
        <summary className="cursor-pointer px-3 py-2 text-xs text-[var(--color-accent)]">OCR 失败？粘贴文字继续</summary>
        <div className="space-y-2 border-t border-[var(--color-border)] p-3">
          <textarea aria-label="OCR文字" value={pasteText} onChange={event => setPasteText(event.target.value)} rows={5}
            placeholder="粘贴手机系统或其他 OCR 工具识别出的持仓文字"
            className="w-full rounded-lg border border-[var(--color-border)] bg-white/80 p-2 text-xs outline-none focus:border-[var(--color-accent)]" />
          <button type="button" onClick={handleParsePaste} disabled={loading}
            className="rounded-lg border border-[var(--color-accent-light)] bg-white/80 px-3 py-1.5 text-xs font-semibold text-[var(--color-accent)]">
            {loading ? '整理中…' : '整理粘贴文字'}
          </button>
        </div>
      </details>

      {(localError || error) && <div role="alert" className="rounded-lg bg-[var(--color-dang)]/10 px-3 py-2 text-xs text-[var(--color-dang)]">{localError || error}</div>}

      {data && (
        <div className="space-y-3 rounded-xl border border-[var(--color-border)] bg-white/65 p-3" data-testid="snapshot-import-review">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div>
              <div className="text-xs font-semibold text-[#1F2937]">核对识别结果</div>
              <div className="mt-0.5 text-[10px] text-[var(--color-muted)]">黄色或空白字段必须核对；识别结果不会自动扫描交易。</div>
            </div>
            <span className="rounded-full bg-[var(--color-surface-2)] px-2 py-1 text-[10px] text-[var(--color-muted)]">
              {data.provider === 'deepseek' ? `DeepSeek · ${data.model}` : '本地规则解析'}
            </span>
          </div>

          <div className={`block rounded-lg border p-2 text-[10px] text-[var(--color-muted)] ${fieldClass(data.draft.account_cash)}`}>
            <span className="flex items-center justify-between gap-2">
              <span>账户现金 · {sourceLabel(data.draft.account_cash.source)} · 置信度 {Math.round(data.draft.account_cash.confidence * 100)}%</span>
              {data.draft.account_cash.value != null && data.draft.account_cash.confidence < 0.75 && (
                <button type="button" onClick={confirmCash} className="rounded bg-white/80 px-2 py-1 font-semibold text-[var(--color-accent)]">确认现金</button>
              )}
            </span>
            <input aria-label="识别账户现金" type="number" min="0" value={data.draft.account_cash.value ?? ''}
              onChange={event => updateCash(event.target.value)} className={`${REVIEW_INPUT} mt-1`} />
          </div>

          <div className="overflow-x-auto rounded-lg border border-[var(--color-border)]">
            <table className="w-full min-w-[760px] text-left text-xs">
              <thead className="bg-[var(--color-surface-2)] text-[10px] text-[var(--color-muted)]">
                <tr><th className="px-2 py-2">资产</th><th className="px-2 py-2">份额</th><th className="px-2 py-2">现价</th><th className="px-2 py-2">平均成本</th><th className="px-2 py-2">市值</th><th className="px-2 py-2">证据</th></tr>
              </thead>
              <tbody className="divide-y divide-[var(--color-border)]">
                {data.draft.positions.map((position: SnapshotImportPosition, index) => (
                  <tr key={`${String(position.asset.value)}-${index}`}>
                    <td className="px-2 py-2 font-medium text-[#1F2937]">{position.asset.value ?? '未知'}<div className="text-[9px] font-normal text-[var(--color-muted)]">{position.code.value}</div></td>
                    {(['shares', 'price', 'average_cost', 'market_value'] as const).map(key => (
                      <td key={key} className={`px-2 py-2 ${fieldClass(position[key])}`}>
                        <input aria-label={`${position.asset.value ?? '未知'}${key}`} type="number" min="0" value={position[key].value ?? ''}
                          onChange={event => updatePosition(index, key, event.target.value)} className={REVIEW_INPUT} />
                        <div className="mt-1 text-[9px] text-[var(--color-muted)]">{sourceLabel(position[key].source)} · {Math.round(position[key].confidence * 100)}%</div>
                      </td>
                    ))}
                    <td className="max-w-40 px-2 py-2 text-[9px] leading-4 text-[var(--color-muted)]">
                      <div>{position.asset.evidence || position.shares.evidence || '—'}</div>
                      {[position.shares, position.price, position.average_cost, position.market_value].some(field => field.value != null && field.confidence < 0.75) && (
                        <button type="button" onClick={() => confirmPosition(index)} className="mt-1 rounded bg-[var(--color-warn)]/15 px-2 py-1 font-semibold text-[var(--color-warn)]">确认本行</button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {data.warnings.length > 0 && <div className="rounded-lg bg-[var(--color-warn)]/10 px-3 py-2 text-[10px] leading-5 text-[#6B5724]">{data.warnings.map(warning => <div key={warning}>⚠ {warning}</div>)}</div>}
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div className="text-[10px] text-[var(--color-muted)]">
              <span className="inline-flex items-center gap-1"><ShieldCheck size={13} />只应用到表单，不会产生交易或写入策略状态。</span>
              {unreviewedCount > 0 && <div className="mt-1 font-semibold text-[var(--color-warn)]">仍有 {unreviewedCount} 个黄色字段待确认或修改。</div>}
              {consistencyIssueCount > 0 && <div className="mt-1 font-semibold text-[var(--color-dang)]">仍有 {consistencyIssueCount} 行市值校验不通过，不能直接接受错误 OCR。</div>}
            </div>
            <button type="button" onClick={handleApply} disabled={unreviewedCount > 0 || consistencyIssueCount > 0}
              className="rounded-lg bg-[var(--color-safe)] px-4 py-2 text-xs font-semibold text-white disabled:cursor-not-allowed disabled:opacity-45">应用到持仓快照</button>
          </div>
          {applied && <div role="status" className="rounded-lg bg-[var(--color-safe)]/10 px-3 py-2 text-xs text-[var(--color-safe)]">已带入表单，尚未扫描交易计划；请先核对下方数值。</div>}
        </div>
      )}
    </section>
  );
}
