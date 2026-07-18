'use client';

import { useEffect, useRef, useState } from 'react';
import type { Artisan, ChatMessage } from '@/lib/types';
import { askAI, askAIVoice } from '@/lib/api-client';

interface Props {
  artisan: Artisan;
  /** Có đang thực sự nhìn thấy nghệ nhân này không. CHỈ để hiện gợi ý — KHÔNG unmount panel
   *  khi mất tracking (giữ nguyên hội thoại + ghi âm xuyên suốt). */
  tracking: boolean;
  onClose: () => void;
}

// FPT STT (FPT.AI-whisper-large-v3-turbo) CHỈ nhận WAV (PCM) — đã kiểm chứng trực tiếp:
// gửi webm/opus (Android) hay mp4/aac (iOS) đều bị 503 "Transcription service unavailable".
// Vì MediaRecorder KHÔNG xuất WAV, ta giải mã bản ghi bằng Web Audio rồi tự đóng gói WAV
// 16-bit mono ngay trong trình duyệt trước khi gửi. Không cần đụng backend.
function encodeWav(samples: Float32Array, sampleRate: number): Blob {
  const dataLen = samples.length * 2;
  const view = new DataView(new ArrayBuffer(44 + dataLen));
  const w = (o: number, s: string) => {
    for (let i = 0; i < s.length; i++) view.setUint8(o + i, s.charCodeAt(i));
  };
  w(0, 'RIFF');
  view.setUint32(4, 36 + dataLen, true);
  w(8, 'WAVE');
  w(12, 'fmt ');
  view.setUint32(16, 16, true);
  view.setUint16(20, 1, true); // PCM
  view.setUint16(22, 1, true); // mono
  view.setUint32(24, sampleRate, true);
  view.setUint32(28, sampleRate * 2, true); // byte rate
  view.setUint16(32, 2, true); // block align
  view.setUint16(34, 16, true); // bits/sample
  w(36, 'data');
  view.setUint32(40, dataLen, true);
  let off = 44;
  for (let i = 0; i < samples.length; i++) {
    const s = Math.max(-1, Math.min(1, samples[i]));
    view.setInt16(off, s < 0 ? s * 0x8000 : s * 0x7fff, true);
    off += 2;
  }
  return new Blob([view], { type: 'audio/wav' });
}

// Giải mã blob thu được (webm/mp4/…) -> gộp về mono -> WAV. decodeAudioData tự giải nén
// container (Safari đọc mp4/aac, Chrome đọc webm/opus) nên chạy được trên cả 2 nền tảng.
async function blobToWav(blob: Blob): Promise<Blob> {
  const AC: typeof AudioContext =
    window.AudioContext ?? (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext;
  const ctx = new AC();
  try {
    const decoded = await ctx.decodeAudioData(await blob.arrayBuffer());
    const ch = decoded.numberOfChannels;
    const n = decoded.length;
    const mono = new Float32Array(n);
    for (let c = 0; c < ch; c++) {
      const data = decoded.getChannelData(c);
      for (let i = 0; i < n; i++) mono[i] += data[i] / ch;
    }
    return encodeWav(mono, decoded.sampleRate);
  } finally {
    void ctx.close();
  }
}

// Chọn mimeType tốt nhất cho MediaRecorder theo thiết bị (iOS ưu tiên mp4).
function pickRecorderMime(): string {
  if (typeof MediaRecorder === 'undefined') return '';
  for (const t of ['audio/mp4', 'audio/webm;codecs=opus', 'audio/webm']) {
    if (MediaRecorder.isTypeSupported(t)) return t;
  }
  return '';
}

function getAudioContextCtor(): typeof AudioContext | undefined {
  return window.AudioContext ?? (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;
}

function decodeAudioData(ctx: AudioContext, data: ArrayBuffer): Promise<AudioBuffer> {
  return new Promise((resolve, reject) => {
    const result = ctx.decodeAudioData(data, resolve, reject);
    if (result) result.then(resolve, reject);
  });
}

// Tạo 1 file WAV im lặng cực ngắn làm fallback cho <audio>. Đường phát chính dùng
// AudioContext đã được resume trong cú chạm của user, ổn định hơn trên iOS/Safari.
function makeSilentWavUrl(): string {
  const samples = 256;
  const buf = new ArrayBuffer(44 + samples);
  const view = new DataView(buf);
  const put = (o: number, s: string) => {
    for (let i = 0; i < s.length; i++) view.setUint8(o + i, s.charCodeAt(i));
  };
  put(0, 'RIFF');
  view.setUint32(4, 36 + samples, true);
  put(8, 'WAVE');
  put(12, 'fmt ');
  view.setUint32(16, 16, true);
  view.setUint16(20, 1, true); // PCM
  view.setUint16(22, 1, true); // mono
  view.setUint32(24, 8000, true);
  view.setUint32(28, 8000, true);
  view.setUint16(32, 1, true);
  view.setUint16(34, 8, true); // 8-bit
  put(36, 'data');
  view.setUint32(40, samples, true);
  for (let i = 0; i < samples; i++) view.setUint8(44 + i, 128); // 8-bit silence
  return URL.createObjectURL(new Blob([buf], { type: 'audio/wav' }));
}

// Khung trò chuyện với nghệ nhân. MẶC ĐỊNH là VOICE (bấm-giữ để nói); có nút tròn nhỏ
// để bung khung chat CHỮ (gõ + xem lại lịch sử). Panel tồn tại xuyên suốt phiên, không
// tắt khi camera lia khỏi model. Reset khi đổi nghệ nhân do ARScene remount qua key.
export default function ChatPanel({ artisan, tracking, onClose }: Props) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [recording, setRecording] = useState(false);
  const [expanded, setExpanded] = useState(false); // khung chat chữ đang mở?
  const [speaking, setSpeaking] = useState(false); // đang phát giọng nghệ nhân?

  const audioRef = useRef<HTMLAudioElement | null>(null);
  const audioCtxRef = useRef<AudioContext | null>(null);
  const activeSourceRef = useRef<AudioBufferSourceNode | null>(null);
  const silentUrlRef = useRef<string | null>(null);
  const unlockedRef = useRef(false);
  const streamRef = useRef<MediaStream | null>(null);
  const recorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const scrollRef = useRef<HTMLDivElement | null>(null);

  // Xin quyền micro NGAY khi vào phiên (Android/desktop cho phép; iOS thường đòi cú chạm ->
  // sẽ tự xin lại ở lần bấm mic đầu tiên). Giữ luôn stream để bấm-nói tức thì, không hỏi lại.
  useEffect(() => {
    silentUrlRef.current = makeSilentWavUrl();
    audioRef.current = new Audio();
    audioRef.current.addEventListener('ended', () => setSpeaking(false));
    let cancelled = false;
    navigator.mediaDevices
      ?.getUserMedia({ audio: true })
      .then((s) => {
        if (cancelled) s.getTracks().forEach((t) => t.stop());
        else streamRef.current = s;
      })
      .catch(() => {
        /* iOS: để dành lần bấm mic đầu tiên (có user-gesture) mới xin */
      });
    return () => {
      cancelled = true;
      streamRef.current?.getTracks().forEach((t) => t.stop());
      if (recorderRef.current?.state === 'recording') recorderRef.current.stop();
      activeSourceRef.current?.stop();
      audioRef.current?.pause();
      void audioCtxRef.current?.close();
      if (silentUrlRef.current) URL.revokeObjectURL(silentUrlRef.current);
    };
  }, []);

  // Tự cuộn xuống cuối khi có tin mới (lúc mở khung chat chữ).
  useEffect(() => {
    if (expanded)
      scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: 'smooth' });
  }, [messages, busy, expanded]);

  // Mở khoá autoplay iOS — gọi TRONG cú chạm của user (bấm mic / gửi chữ).
  function unlockAudio() {
    if (unlockedRef.current) return;
    const AC = getAudioContextCtor();
    if (AC) {
      const ctx = audioCtxRef.current ?? new AC();
      audioCtxRef.current = ctx;

      const source = ctx.createBufferSource();
      source.buffer = ctx.createBuffer(1, 1, ctx.sampleRate);
      source.connect(ctx.destination);
      source.start(0);

      void ctx
        .resume()
        .then(() => {
          unlockedRef.current = ctx.state === 'running';
        })
        .catch((err) => {
          console.warn('AudioContext unlock failed', err);
        });
    }

    if (!audioRef.current || !silentUrlRef.current) return;
    const a = audioRef.current;
    a.src = silentUrlRef.current;
    a.muted = false;
    a.volume = 0.01;
    a.play()
      .then(() => {
        a.pause();
        a.currentTime = 0;
        a.volume = 1;
        unlockedRef.current = true;
      })
      .catch((err) => {
        a.volume = 1;
        console.warn('HTMLAudioElement unlock failed', err);
      });
  }

  async function playAudio(url: string, mode: 'auto' | 'manual' = 'auto') {
    activeSourceRef.current?.stop();
    activeSourceRef.current = null;
    audioRef.current?.pause();
    setSpeaking(true);

    try {
      const AC = getAudioContextCtor();
      const ctx = audioCtxRef.current ?? (AC ? new AC() : null);
      if (ctx) {
        audioCtxRef.current = ctx;
        if (ctx.state === 'suspended') await ctx.resume();
        const res = await fetch(url, { cache: 'no-store' });
        if (!res.ok) throw new Error(`audio fetch failed: ${res.status}`);
        const buffer = await decodeAudioData(ctx, await res.arrayBuffer());
        const source = ctx.createBufferSource();
        source.buffer = buffer;
        source.connect(ctx.destination);
        source.onended = () => {
          if (activeSourceRef.current === source) {
            activeSourceRef.current = null;
            setSpeaking(false);
          }
        };
        activeSourceRef.current = source;
        source.start(0);
        return;
      }

      if (!audioRef.current) audioRef.current = new Audio();
      const a = audioRef.current;
      a.src = url;
      await a.play();
    } catch (err) {
      console.warn('TTS playback failed', err);
      setSpeaking(false);
      setError(
        mode === 'manual'
          ? 'Không phát được âm thanh. Kiểm tra kết nối hoặc định dạng file audio.'
          : 'Trình duyệt đã chặn phát giọng nói tự động. Bấm nút 🔊 để nghe lại.',
      );
    }
  }

  function pushAssistant(reply: ChatMessage) {
    setMessages((m) => [...m, reply]);
    if (reply.audioUrl) {
      void playAudio(reply.audioUrl);
    } else {
      setError('AI đã trả lời bằng chữ nhưng backend chưa trả về file âm thanh.');
    }
  }

  async function ensureStream(): Promise<MediaStream> {
    if (streamRef.current && streamRef.current.getAudioTracks().some((t) => t.readyState === 'live'))
      return streamRef.current;
    const s = await navigator.mediaDevices.getUserMedia({ audio: true });
    streamRef.current = s;
    return s;
  }

  // ── VOICE: bấm-GIỮ để nói ───────────────────────────────────────────────
  async function startRecording() {
    if (busy || recording) return;
    setError(null);
    unlockAudio(); // dùng chính cú chạm này để mở khoá loa cho TTS sau đó
    try {
      const stream = await ensureStream();
      const mime = pickRecorderMime();
      const recorder = new MediaRecorder(stream, mime ? { mimeType: mime } : undefined);
      chunksRef.current = [];
      recorder.ondataavailable = (e) => {
        if (e.data.size > 0) chunksRef.current.push(e.data);
      };
      recorder.onstop = () => {
        const type = recorder.mimeType || mime || 'audio/webm';
        const blob = new Blob(chunksRef.current, { type });
        // Bấm quá nhanh -> blob bé xíu (gần như không có tiếng) -> nhắc giữ lâu hơn.
        if (blob.size < 1200) {
          setError('Giữ nút micro và nói lâu hơn một chút nhé.');
          return;
        }
        void sendVoice(blob);
      };
      recorderRef.current = recorder;
      recorder.start(250); // timeslice: iOS phát ondataavailable đều đặn, tránh blob rỗng
      setRecording(true);
    } catch {
      setError('Không truy cập được micro. Hãy cho phép quyền micro trong cài đặt trình duyệt.');
    }
  }

  function stopRecording() {
    if (recorderRef.current?.state === 'recording') recorderRef.current.stop();
    setRecording(false);
  }

  async function sendVoice(raw: Blob) {
    setBusy(true);
    setError(null);
    try {
      // FPT STT chỉ nhận WAV -> chuyển đổi ngay trên máy trước khi gửi.
      const wav = await blobToWav(raw);
      const reply = await askAIVoice(artisan.slug, wav, 'question.wav', messages);
      const spoken = reply.transcript?.trim();
      setMessages((m) => [
        ...m,
        { role: 'user', content: spoken || '🎤 (câu hỏi bằng giọng nói)' } as ChatMessage,
      ]);
      pushAssistant(reply);
    } catch {
      setError('Không nhận diện được giọng nói. Thử lại hoặc gõ chữ.');
    } finally {
      setBusy(false);
    }
  }

  // ── TEXT: gõ chữ ────────────────────────────────────────────────────────
  async function sendText() {
    const q = input.trim();
    if (!q || busy) return;
    unlockAudio();
    setInput('');
    setError(null);
    const next = [...messages, { role: 'user', content: q } as ChatMessage];
    setMessages(next);
    setBusy(true);
    try {
      pushAssistant(await askAI(artisan.slug, next));
    } catch {
      setError('Không gửi được câu hỏi. Kiểm tra kết nối máy chủ AI.');
    } finally {
      setBusy(false);
    }
  }

  const lastAssistant = [...messages].reverse().find((m) => m.role === 'assistant');
  const status = busy
    ? 'Đang trả lời…'
    : recording
      ? 'Đang nghe… (thả tay để gửi)'
      : null;

  return (
    <div className="pointer-events-none absolute inset-x-0 bottom-0 z-30 flex flex-col items-center gap-3 p-4">
      {/* Khung chat CHỮ (bung khi bấm nút tròn) */}
      {expanded && (
        <div className="pointer-events-auto flex max-h-[60vh] w-full max-w-md flex-col overflow-hidden rounded-2xl bg-neutral-900/95 text-white shadow-2xl backdrop-blur">
          <div className="flex items-center justify-between border-b border-white/10 px-4 py-3">
            <div className="min-w-0">
              <p className="truncate text-sm font-semibold">{artisan.name}</p>
              <p className="truncate text-xs text-white/60">{artisan.craft}</p>
            </div>
            <button
              onClick={() => setExpanded(false)}
              aria-label="Thu gọn"
              className="rounded-full bg-white/10 px-3 py-1.5 text-sm"
            >
              ⌄
            </button>
          </div>

          <div ref={scrollRef} className="flex-1 space-y-3 overflow-y-auto px-4 py-3">
            {messages.length === 0 && !busy && (
              <p className="py-6 text-center text-sm text-white/50">
                Hãy hỏi tôi bằng chữ, hoặc đóng khung này và giữ nút micro để nói.
              </p>
            )}
            {messages.map((m, i) => (
              <div key={i} className={`flex ${m.role === 'user' ? 'justify-end' : 'justify-start'}`}>
                <div
                  className={`max-w-[80%] rounded-2xl px-3.5 py-2 text-sm leading-relaxed ${
                    m.role === 'user' ? 'bg-white text-black' : 'bg-white/10 text-white'
                  }`}
                >
                  <span className="whitespace-pre-wrap">{m.content}</span>
                  {m.role === 'assistant' && m.audioUrl && (
                    <button
                      onClick={() => {
                        unlockAudio();
                        void playAudio(m.audioUrl!, 'manual');
                      }}
                      aria-label="Nghe lại"
                      className="ml-2 align-middle text-xs text-white/70"
                    >
                      🔊
                    </button>
                  )}
                </div>
              </div>
            ))}
            {busy && (
              <div className="flex justify-start">
                <div className="rounded-2xl bg-white/10 px-3.5 py-2 text-sm text-white/70">
                  Đang trả lời…
                </div>
              </div>
            )}
          </div>

          {error && <p className="px-4 pb-1 text-xs text-red-300">{error}</p>}

          <div className="flex items-center gap-2 border-t border-white/10 px-3 py-3">
            <input
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && sendText()}
              disabled={busy}
              placeholder="Nhập câu hỏi…"
              className="min-w-0 flex-1 rounded-full bg-white/10 px-4 py-2.5 text-sm outline-none placeholder:text-white/40 disabled:opacity-50"
            />
            <button
              onClick={sendText}
              disabled={busy || !input.trim()}
              className="shrink-0 rounded-full bg-white px-4 py-2.5 text-sm font-medium text-black disabled:opacity-40"
            >
              Gửi
            </button>
          </div>
        </div>
      )}

      {/* Câu trả lời mới nhất / trạng thái (chế độ voice, khi CHƯA bung chat) */}
      {!expanded && (status || lastAssistant || !tracking) && (
        <div className="pointer-events-auto max-w-md rounded-2xl bg-black/75 px-4 py-3 text-center text-sm text-white shadow-lg backdrop-blur">
          {status ? (
            <span className="text-white/80">{status}</span>
          ) : lastAssistant ? (
            <span className="flex items-start gap-2">
              {speaking && <span className="animate-pulse">🔊</span>}
              <span className="whitespace-pre-wrap text-left">{lastAssistant.content}</span>
              {lastAssistant.audioUrl && (
                <button
                  onClick={() => {
                    unlockAudio();
                    void playAudio(lastAssistant.audioUrl!, 'manual');
                  }}
                  aria-label="Nghe lại"
                  className="shrink-0 text-xs text-white/70"
                >
                  🔊
                </button>
              )}
            </span>
          ) : (
            <span className="text-white/60">Đang tìm lại nghệ nhân… bạn vẫn có thể trò chuyện.</span>
          )}
        </div>
      )}

      {error && !expanded && (
        <p className="pointer-events-auto rounded-full bg-black/70 px-3 py-1 text-xs text-red-300">
          {error}
        </p>
      )}

      {/* Hàng điều khiển: [💬 mở chat chữ] [MIC bấm-giữ] [✕ đóng] */}
      <div className="pointer-events-auto flex items-center gap-4">
        <button
          onClick={() => setExpanded((v) => !v)}
          aria-label={expanded ? 'Đóng khung chat' : 'Mở khung chat chữ'}
          className="flex h-11 w-11 items-center justify-center rounded-full bg-white/15 text-lg text-white shadow-lg backdrop-blur active:scale-95"
        >
          💬
        </button>

        {/* Bấm-GIỮ để nói: pointer events phủ cả chuột lẫn cảm ứng */}
        <button
          onPointerDown={(e) => {
            e.preventDefault();
            void startRecording();
          }}
          onPointerUp={(e) => {
            e.preventDefault();
            stopRecording();
          }}
          onPointerLeave={() => recording && stopRecording()}
          onPointerCancel={() => recording && stopRecording()}
          onContextMenu={(e) => e.preventDefault()}
          disabled={busy}
          aria-label="Giữ để nói"
          className={`flex h-20 w-20 select-none touch-none items-center justify-center rounded-full text-3xl shadow-xl transition active:scale-95 disabled:opacity-40 ${
            recording ? 'scale-110 animate-pulse bg-red-500 text-white' : 'bg-white text-black'
          }`}
        >
          {recording ? '⏺' : '🎤'}
        </button>

        <button
          onClick={onClose}
          aria-label="Kết thúc trò chuyện"
          className="flex h-11 w-11 items-center justify-center rounded-full bg-white/15 text-lg text-white shadow-lg backdrop-blur active:scale-95"
        >
          ✕
        </button>
      </div>

      {!expanded && !status && (
        <p className="pointer-events-none text-center text-xs text-white/70">
          Giữ nút micro để nói với nghệ nhân
        </p>
      )}
    </div>
  );
}
