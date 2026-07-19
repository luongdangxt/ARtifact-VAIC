// AudioContext DÙNG CHUNG toàn app để phát giọng TTS.
//
// iOS/Safari chỉ cho phát âm thanh trên AudioContext đã được resume TRONG một cú
// chạm của user. Lời giới thiệu của nghệ nhân tự phát NGAY KHI model hiện lên —
// lúc đó không có cú chạm nào — nên phải mượn cú bấm "Quét AR ngay" ở màn chào:
// unlock sẵn context tại đó, ChatPanel về sau phát trên CHÍNH context này.
let sharedCtx: AudioContext | null = null;

function audioContextCtor(): typeof AudioContext | undefined {
  if (typeof window === 'undefined') return undefined;
  return (
    window.AudioContext ??
    (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext
  );
}

/** AudioContext dùng chung (tạo lười). null khi chạy server / browser không hỗ trợ. */
export function getSharedAudioContext(): AudioContext | null {
  const AC = audioContextCtor();
  if (!AC) return null;
  sharedCtx ??= new AC();
  return sharedCtx;
}

/**
 * Gọi TRONG user-gesture (bấm nút). Phát 1 buffer câm + resume để iOS đánh dấu
 * context "đã được user cho phép"; các lần phát sau không cần gesture nữa.
 */
export function unlockSharedAudio(): void {
  const ctx = getSharedAudioContext();
  if (!ctx) return;
  try {
    const source = ctx.createBufferSource();
    source.buffer = ctx.createBuffer(1, 1, ctx.sampleRate);
    source.connect(ctx.destination);
    source.start(0);
  } catch {
    /* noop */
  }
  void ctx.resume().catch(() => {});
}
