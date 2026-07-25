'use client';

import { useEffect, useRef, useState } from 'react';
import type { Artisan, ChatMessage } from '@/lib/types';
import { askAI, askAIVoice } from '@/lib/api-client';
import { getSharedAudioContext, unlockSharedAudio } from '@/lib/audioUnlock';

interface Props {
  artisan: Artisan;
  /** Có đang thực sự nhìn thấy nghệ nhân này không. CHỈ để hiện gợi ý — KHÔNG unmount panel
   *  khi mất tracking (giữ nguyên hội thoại + ghi âm xuyên suốt). */
  tracking: boolean;
  onClose: () => void;
}

// Gemini STT nhận thẳng bản ghi nén gốc (webm/opus của Chrome/Android, mp4/aac của iOS)
// nên KHÔNG cần convert WAV nữa — gửi luôn blob gốc cho nhẹ (~8KB vs ~113KB WAV).
// Chỉ cần đặt đúng đuôi file theo mime để backend/Whisper chọn demuxer chuẩn.
function extFromBlobType(type: string): string {
  const t = (type || '').toLowerCase();
  if (t.includes('mp4') || t.includes('m4a') || t.includes('aac')) return 'm4a';
  if (t.includes('ogg')) return 'ogg';
  if (t.includes('wav')) return 'wav';
  return 'webm';
}

// Chọn mimeType tốt nhất cho MediaRecorder theo thiết bị (iOS ưu tiên mp4).
function pickRecorderMime(): string {
  if (typeof MediaRecorder === 'undefined') return '';
  for (const t of ['audio/mp4', 'audio/webm;codecs=opus', 'audio/webm']) {
    if (MediaRecorder.isTypeSupported(t)) return t;
  }
  return '';
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

// Trần độ dài một mẩu phụ đề: máy hẹp nhất (~320px, text-sm) được ~32 ký tự/dòng, nên
// 90 ký tự là khoảng 3 dòng. Ô phụ đề nở theo nội dung và KHÔNG cắt cụt bằng "…" nữa —
// chữ bị nuốt mất thì du khách đọc hụt câu, mà giọng nói vẫn đọc tiếp phần không thấy.
const MAX_CAPTION_CHARS = 90;

// Cắt câu trả lời thành từng câu để chạy phụ đề. Không dùng lookbehind (iOS < 16.4
// chưa hỗ trợ) — quét thủ công: ngắt ở dấu kết câu KHI theo sau là khoảng trắng, nên
// "1.500 nghệ nhân" hay "TP.HCM" không bị cắt đôi.
function splitSentences(text: string): string[] {
  const clean = text.replace(/\s+/g, ' ').trim();
  if (!clean) return [];
  const parts: string[] = [];
  let cur = '';
  for (let i = 0; i < clean.length; i++) {
    const ch = clean[i];
    cur += ch;
    const isEnd = '.!?…'.includes(ch) && (i === clean.length - 1 || clean[i + 1] === ' ');
    if (isEnd) {
      parts.push(cur.trim());
      cur = '';
    }
  }
  if (cur.trim()) parts.push(cur.trim());

  // Gộp mẩu quá ngắn ("Vâng.", "Ừm.") vào câu trước để phụ đề không nhấp nháy.
  const merged: string[] = [];
  for (const p of parts) {
    const prev = merged[merged.length - 1];
    if (prev && (p.length < 24 || prev.length < 24) && prev.length + p.length <= MAX_CAPTION_CHARS)
      merged[merged.length - 1] = prev + ' ' + p;
    else merged.push(p);
  }
  return merged;
}

// Xẻ nhỏ câu dài quá khổ ô phụ đề. Ưu tiên ngắt ở dấu phẩy/chấm phẩy (nghỉ hơi tự
// nhiên, đọc lên vẫn thuận), không có thì ngắt ở khoảng trắng cuối cùng vừa khung.
function splitClause(sentence: string): string[] {
  if (sentence.length <= MAX_CAPTION_CHARS) return [sentence];
  const out: string[] = [];
  let rest = sentence;
  while (rest.length > MAX_CAPTION_CHARS) {
    const window = rest.slice(0, MAX_CAPTION_CHARS);
    // Chỉ nhận mốc ngắt nằm sau nửa khung, tránh đẻ ra mẩu tí hon 2-3 chữ.
    const half = Math.floor(MAX_CAPTION_CHARS / 2);
    let cut = Math.max(window.lastIndexOf(', '), window.lastIndexOf('; '), window.lastIndexOf(': '));
    if (cut >= half) cut += 1;
    else cut = window.lastIndexOf(' ');
    if (cut < half) cut = MAX_CAPTION_CHARS; // câu không có khoảng trắng -> cắt cứng
    out.push(rest.slice(0, cut).trim());
    rest = rest.slice(cut).trim();
  }
  if (rest) out.push(rest);
  return out;
}

// Danh sách mẩu phụ đề: câu -> mẩu vừa khung.
function splitCaptionChunks(text: string): string[] {
  return splitSentences(text).flatMap(splitClause);
}

// "Trọng số thời gian" của một mẩu — thời lượng TTS đọc nó, quy ra đơn vị ký tự.
// Đếm ký tự trần thì lệch, vì có những thứ tốn ÍT ký tự mà tốn NHIỀU thời gian:
//   • dấu ngắt câu: đọc tới dấu chấm/phẩy là nghỉ hơi, 1 ký tự mà cả nhịp thở;
//   • chữ số: "2009" bốn ký tự nhưng đọc thành "hai nghìn không trăm lẻ chín";
//   • từ viết tắt: "UNESCO" đọc rời từng chữ cái.
// Chỗ nào nhiều những thứ đó thì giọng nói chậm lại còn chữ vẫn chạy đều -> phụ đề
// vượt lên trước, và vượt tới đâu giữ nguyên tới đó nên càng về cuối càng lệch.
function timeWeight(chunk: string): number {
  let w = chunk.length;
  for (const ch of chunk) {
    if ('.!?…'.includes(ch)) w += 9;
    else if (',;:'.includes(ch)) w += 4;
    else if (ch >= '0' && ch <= '9') w += 4;
  }
  const acronyms = chunk.match(/[A-Z]{2,}/g);
  if (acronyms) for (const a of acronyms) w += a.length * 2;
  return w;
}

// Không có file audio (TTS lỗi/hết quota) thì vẫn chạy phụ đề theo tốc độ đọc ước
// lượng ~15 đơn vị trọng số/giây — xấp xỉ nhịp nói của giọng đọc tiếng Việt. Cố ý
// đoán hơi CHẬM: phụ đề trễ nửa nhịp thì dễ chịu, chạy trước tiếng thì rất khó chịu.
function estimateDuration(text: string): number {
  return Math.max(2.5, timeWeight(text) / 15);
}

// Đồng hồ đếm giây từ lúc gọi. Để ở module-level vì `performance.now()` là hàm không
// thuần khiết — react-hooks/purity chặn nếu gọi thẳng trong thân component.
function wallClock(): () => number {
  const t0 = performance.now();
  return () => (performance.now() - t0) / 1000;
}

interface Caption {
  shown: string; // phần chữ đã "gõ" ra
  full: string; // trọn câu hiện tại
  index: number;
  total: number;
}

// Nghệ nhân đã tự giới thiệu trong lần load trang này (theo slug) — module-level để
// đóng/mở lại panel (hoặc lia qua lại giữa 2 nghệ nhân) KHÔNG chào lại từ đầu.
const introducedSlugs = new Set<string>();

// Lời chào ĐANG bay theo slug. React Strict Mode (bật mặc định ở app router, chỉ trong
// dev) mount -> unmount -> mount lại: nếu chỉ chặn bằng introducedSlugs thì lần mount
// SỐNG SÓT bị coi là "đã chào" và bỏ qua -> panel không bao giờ có lời chào. Chia sẻ
// promise ở đây để lần mount thứ hai bám vào ĐÚNG request đó, không gọi API lần nữa.
const pendingIntros = new Map<string, Promise<ChatMessage>>();

// Câu hỏi gợi ý kèm theo câu trả lời -> nút bấm là hỏi luôn, khỏi phải gõ.
// `tone`: 'panel' nằm trong khung chat (nền tối sẵn), 'overlay' nổi trên camera.
function SuggestionChips({
  items,
  tone,
  onPick,
}: {
  items: string[];
  tone: 'panel' | 'overlay';
  onPick: (question: string) => void;
}) {
  if (items.length === 0) return null;
  return (
    <div
      className={`flex flex-wrap justify-center gap-2 ${
        tone === 'overlay' ? 'w-full max-w-md animate-[fadeIn_.25s_ease-out]' : ''
      }`}
    >
      {items.map((q) => (
        <button
          key={q}
          onClick={() => onPick(q)}
          className={`pointer-events-auto rounded-full border px-3 py-1.5 text-left text-xs leading-snug transition active:scale-95 ${
            tone === 'panel'
              ? 'border-white/20 bg-white/10 text-white/90 hover:bg-white/20'
              : 'border-white/25 bg-black/70 text-white/90 shadow-lg backdrop-blur hover:bg-black/85'
          }`}
        >
          {q}
        </button>
      ))}
    </div>
  );
}

// Khung trò chuyện với nghệ nhân. MẶC ĐỊNH là VOICE (bấm-giữ để nói); có nút tròn nhỏ
// để bung khung chat CHỮ (gõ + xem lại lịch sử). Panel tồn tại xuyên suốt phiên, không
// tắt khi camera lia khỏi model. Reset khi đổi nghệ nhân do ARScene remount qua key.
export default function ChatPanel({ artisan, tracking, onClose }: Props) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState('');
  // Khởi tạo THẲNG bằng true khi phiên này sắp chào (xem effect tự giới thiệu bên dưới):
  // gọi setBusy(true) trong thân effect sẽ tạo render thừa và bị lint chặn.
  const [busy, setBusy] = useState(() => !introducedSlugs.has(artisan.slug));
  const [error, setError] = useState<string | null>(null);
  const [recording, setRecording] = useState(false);
  const [expanded, setExpanded] = useState(false); // khung chat chữ đang mở?
  const [speaking, setSpeaking] = useState(false); // đang phát giọng nghệ nhân?
  // Phụ đề chạy TỪNG CÂU khớp với giọng nói (chế độ voice, khi chưa bung chat chữ) —
  // thay cho việc đổ nguyên bài trả lời ra màn hình che mất model.
  const [caption, setCaption] = useState<Caption | null>(null);

  const audioRef = useRef<HTMLAudioElement | null>(null);
  const activeSourceRef = useRef<AudioBufferSourceNode | null>(null);
  // Số thứ tự lượt phát: mỗi lần phát/dừng tăng 1. playAudio có nhiều await (fetch +
  // decode) ở giữa; sau mỗi await nó so token — nếu đã có lượt mới thì tự huỷ, nhờ vậy
  // hai lần bấm 🔊 liên tiếp KHÔNG tạo ra hai nguồn cùng phát (lỗi âm thanh đè nhau).
  const playTokenRef = useRef(0);
  const silentUrlRef = useRef<string | null>(null);
  const unlockedRef = useRef(false);
  const streamRef = useRef<MediaStream | null>(null);
  const recorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const scrollRef = useRef<HTMLDivElement | null>(null);
  const captionRafRef = useRef<number | null>(null);

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
      if (captionRafRef.current !== null) cancelAnimationFrame(captionRafRef.current);
      activeSourceRef.current?.stop();
      audioRef.current?.pause();
      // AudioContext là SHARED (đã unlock từ cú bấm ở màn chào) — KHÔNG close ở đây,
      // đóng rồi thì phiên chat sau mở lại sẽ mất trạng thái unlock trên iOS.
      if (silentUrlRef.current) URL.revokeObjectURL(silentUrlRef.current);
    };
  }, []);

  // Tự cuộn xuống cuối khi có tin mới (lúc mở khung chat chữ).
  useEffect(() => {
    if (expanded)
      scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: 'smooth' });
  }, [messages, busy, expanded]);

  // Mở khoá autoplay iOS — gọi TRONG cú chạm của user (bấm mic / gửi chữ).
  // Dùng AudioContext SHARED: thường đã unlock sẵn từ cú bấm "Quét AR ngay".
  function unlockAudio() {
    if (unlockedRef.current) return;
    unlockSharedAudio();
    const ctx = getSharedAudioContext();
    if (ctx) {
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

  function stopCaptions() {
    if (captionRafRef.current !== null) cancelAnimationFrame(captionRafRef.current);
    captionRafRef.current = null;
  }

  // Chạy phụ đề bám theo ĐỒNG HỒ CỦA CHÍNH ÂM THANH (`getElapsed`) chứ không phải một
  // chuỗi setTimeout: kể cả khi tab bị throttle hay decode trễ, chữ vẫn khớp tiếng nói.
  //
  // Mỗi khung hình quy tiến độ audio (`elapsed / duration`) THẲNG ra vị trí chữ trong
  // toàn bài, thay vì cấp phát mốc thời gian cố định cho từng mẩu lúc bắt đầu. Nhờ vậy
  // sai số KHÔNG cộng dồn (mỗi khung là một lần tính lại từ đầu bài) và `getDuration`
  // được đọc lại liên tục — đường <audio> có `duration` = NaN lúc mới play sẽ tự chỉnh
  // đúng nhịp ngay khi trình duyệt nạp xong metadata.
  function startCaptions(text: string, getDuration: () => number, getElapsed: () => number) {
    stopCaptions();
    const parts = splitCaptionChunks(text);
    if (parts.length === 0) return;

    // Mốc trọng số tích luỹ ở đầu mỗi mẩu + tổng trọng số cả bài.
    const weights = parts.map(timeWeight);
    const starts: number[] = [];
    let totalWeight = 0;
    for (const w of weights) {
      starts.push(totalWeight);
      totalWeight += w;
    }

    let lastShown = '';
    const tick = () => {
      const duration = Math.max(0.1, getDuration());
      const t = getElapsed();
      const target = Math.min(1, t / duration) * totalWeight; // vị trí theo trọng số

      let i = 0;
      while (i + 1 < parts.length && target >= starts[i + 1]) i++;
      const chunk = parts[i];
      const frac = weights[i] > 0 ? (target - starts[i]) / weights[i] : 1;
      // +1 ký tự: chữ nhỉnh hơn tiếng nửa nhịp, đọc theo dễ chịu hơn là chạy sau.
      const n = Math.min(chunk.length, Math.max(1, Math.ceil(frac * chunk.length) + 1));
      const shown = chunk.slice(0, n);
      // Chỉ setState khi chuỗi hiển thị đổi -> không render lại 60 lần/giây.
      if (shown !== lastShown) {
        lastShown = shown;
        setCaption({ shown, full: chunk, index: i, total: parts.length });
      }
      if (t < duration) captionRafRef.current = requestAnimationFrame(tick);
      else {
        captionRafRef.current = null;
        setCaption({ shown: chunk, full: chunk, index: i, total: parts.length });
      }
    };
    tick();
  }

  // Không có audio: chạy phụ đề theo đồng hồ thường + tốc độ đọc ước lượng.
  function startCaptionsUntimed(text: string) {
    const duration = estimateDuration(text);
    startCaptions(text, () => duration, wallClock());
  }

  // Dừng DỨT ĐIỂM mọi âm thanh đang phát (Web Audio + <audio>) và vô hiệu hoá mọi lượt
  // playAudio còn đang chờ await. Gọi trước mỗi lượt phát mới và khi bắt đầu ghi âm.
  function stopPlayback() {
    playTokenRef.current += 1; // token đổi -> các playAudio đang await sẽ tự huỷ
    stopCaptions();
    setCaption(null); // sang lượt mới -> xoá phụ đề cũ, không để chữ cũ nằm lại
    const src = activeSourceRef.current;
    if (src) {
      src.onended = null; // tránh onended cũ set speaking=false trễ, đè lượt mới
      try {
        src.stop();
      } catch {
        /* đã dừng rồi */
      }
      activeSourceRef.current = null;
    }
    if (audioRef.current) {
      audioRef.current.pause();
      audioRef.current.currentTime = 0;
    }
    setSpeaking(false);
  }

  // `text`: nội dung câu trả lời để chạy phụ đề khớp tiếng nói (bỏ trống thì không chạy).
  async function playAudio(url: string, mode: 'auto' | 'manual' = 'auto', text?: string) {
    stopPlayback(); // dừng đoạn đang phát trước khi mở lượt mới -> không phát chồng
    const token = playTokenRef.current;
    setSpeaking(true);
    // Dựng sẵn ô phụ đề RỖNG trong lúc tải + giải mã audio: nếu để trống, ô sẽ rơi về
    // bản xem trước của câu trả lời rồi mới nhảy sang phụ đề — giật một nhịp khó chịu.
    if (text) {
      const first = splitCaptionChunks(text)[0];
      if (first) setCaption({ shown: '', full: first, index: 0, total: 1 });
    }

    try {
      const ctx = getSharedAudioContext();
      if (ctx) {
        if (ctx.state === 'suspended') await ctx.resume();
        const res = await fetch(url, { cache: 'no-store' });
        if (token !== playTokenRef.current) return; // đã có lượt phát/dừng mới
        if (!res.ok) throw new Error(`audio fetch failed: ${res.status}`);
        const buffer = await decodeAudioData(ctx, await res.arrayBuffer());
        if (token !== playTokenRef.current) return; // bị thay thế khi đang decode
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
        const startedAt = ctx.currentTime;
        source.start(0);
        // Đồng hồ của AudioContext là mốc chính xác nhất cho phụ đề.
        if (text) startCaptions(text, () => buffer.duration, () => ctx.currentTime - startedAt);
        return;
      }

      if (!audioRef.current) audioRef.current = new Audio();
      const a = audioRef.current;
      a.src = url;
      await a.play();
      if (token !== playTokenRef.current) {
        a.pause(); // lượt mới đã bắt đầu khi đang chờ
        return;
      }
      if (text) {
        // `a.duration` thường còn NaN ngay sau play() -> tạm dùng ước lượng, getter đọc
        // lại mỗi khung nên nhịp tự khớp lại khi metadata về (vài chục ms sau).
        const fallback = estimateDuration(text);
        startCaptions(
          text,
          () => (Number.isFinite(a.duration) && a.duration > 0 ? a.duration : fallback),
          () => a.currentTime,
        );
      }
    } catch (err) {
      if (token !== playTokenRef.current) return; // lỗi của lượt đã bị thay thế -> bỏ qua
      console.warn('TTS playback failed', err);
      setSpeaking(false);
      // Không nghe được thì vẫn cho chữ chạy để du khách theo dõi được câu trả lời.
      if (text) startCaptionsUntimed(text);
      setError(
        mode === 'manual'
          ? 'Không phát được âm thanh. Kiểm tra kết nối hoặc định dạng file audio.'
          : 'Trình duyệt đã chặn phát giọng nói tự động. Bấm nút 🔊 để nghe lại.',
      );
    }
  }

  function pushAssistant(reply: ChatMessage) {
    setMessages((m) => [...m, reply]);
    // Có audio thì tự phát; không có (vd TTS hết quota) thì vẫn giữ câu trả lời chữ,
    // KHÔNG báo lỗi đỏ — người dùng vẫn đọc được và có thể bấm 🔊 nếu sau này có audio.
    if (reply.audioUrl) void playAudio(reply.audioUrl, 'auto', reply.content);
    else startCaptionsUntimed(reply.content);
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
    stopPlayback(); // đang nghe nghệ nhân nói mà bấm mic -> tắt tiếng đó để khỏi thu vào
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
      // Gửi thẳng bản ghi gốc (đã nén) — Gemini STT nhận webm/mp4/ogg... không cần WAV.
      const reply = await askAIVoice(
        artisan.slug,
        raw,
        `question.${extFromBlobType(raw.type)}`,
        messages,
      );
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
  // `question` có giá trị khi du khách bấm NÚT gợi ý (gửi thẳng, không qua ô nhập).
  async function sendText(question?: string) {
    const q = (question ?? input).trim();
    if (!q || busy) return;
    unlockAudio();
    if (question === undefined) setInput('');
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

  // TỰ GIỚI THIỆU: panel mount đúng lúc model vừa hiện lên (ARScene mở session khi
  // track được), nên nghệ nhân chủ động chào + kể ngắn về di sản luôn, không đợi hỏi.
  // Câu mồi KHÔNG đưa vào messages (chỉ hiện câu trả lời); giọng nói tự phát trên
  // AudioContext shared đã unlock từ nút "Quét AR ngay" (bị chặn thì đã có nút 🔊).
  // Đặt SAU pushAssistant để không tham chiếu hàm khai báo phía dưới (lint chặn).
  useEffect(() => {
    if (introducedSlugs.has(artisan.slug)) return;
    let cancelled = false;
    // Dùng lại request đang bay nếu có (Strict Mode mount lần 2), nếu chưa thì tạo mới.
    let intro = pendingIntros.get(artisan.slug);
    if (!intro) {
      intro = askAI(artisan.slug, [
        {
          role: 'user',
          content:
            `Hãy chào du khách vừa quét ảnh mốc và tự giới thiệu ngắn gọn (3-4 câu) ` +
            `về bản thân cùng di sản ${artisan.craft}, rồi mời họ đặt câu hỏi.`,
        },
      ]);
      pendingIntros.set(artisan.slug, intro);
    }
    intro
      .then((reply) => {
        // Đánh dấu "đã chào" khi câu chào THẬT SỰ hiện ra, không phải lúc gửi request.
        if (cancelled) return;
        introducedSlugs.add(artisan.slug);
        pushAssistant(reply);
      })
      .catch(() => {
        // lỗi mạng thì bỏ qua lời chào, cho phép chào lại nếu panel mở lần sau
        pendingIntros.delete(artisan.slug);
      })
      .finally(() => {
        // LUÔN mở khoá panel: nếu chỉ gỡ khi !cancelled thì lần mount bị Strict Mode huỷ
        // sẽ để busy=true vĩnh viễn -> khoá cứng ô nhập, nút gửi và nút thu âm.
        setBusy(false);
      });
    return () => {
      cancelled = true;
    };
    // chỉ chạy 1 lần khi mount; đổi nghệ nhân thì ARScene remount panel qua key
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const lastAssistant = [...messages].reverse().find((m) => m.role === 'assistant');
  // Chỉ gợi ý theo câu trả lời MỚI NHẤT: hỏi xong là chip cũ biến mất, tránh
  // chồng chất câu hỏi lỗi thời. Đang bận thì ẩn để không bấm chồng lượt.
  // Lọc thêm câu du khách ĐÃ hỏi (kể cả gõ tay trùng chữ) để không mời hỏi lại.
  const asked = new Set(
    messages.filter((m) => m.role === 'user').map((m) => m.content.trim().toLowerCase()),
  );
  // Ở chế độ voice còn phải đợi nghệ nhân NÓI XONG (`speaking`) mới mời hỏi tiếp — chip
  // bật lên giữa lúc đang nói vừa che hình vừa giục du khách cắt lời. Trong khung chat
  // chữ thì hiện ngay, vì ở đó người dùng đọc chứ không chờ nghe.
  const allSuggestions =
    !busy && !recording
      ? (lastAssistant?.suggestions ?? []).filter((q) => !asked.has(q.trim().toLowerCase()))
      : [];
  // Chế độ voice: tối đa 2 chip cho gọn, khỏi đội hết màn hình.
  const voiceSuggestions = speaking ? [] : allSuggestions.slice(0, 2);
  // Nói xong rồi thì câu cuối nằm lại chẳng để làm gì (nó là MẨU cuối, tách khỏi mạch
  // thì vô nghĩa) mà lại chiếm chỗ. Có gợi ý là NHƯỜNG hẳn chỗ đó cho câu hỏi — muốn
  // đọc lại toàn văn thì bấm 💬. Không có gợi ý thì giữ chữ để du khách còn cái mà đọc.
  const showCaption = voiceSuggestions.length === 0;

  const status = busy
    ? messages.length === 0
      ? 'Nghệ nhân đang chào bạn…' // đang tải lời tự giới thiệu lúc model vừa hiện
      : 'Đang trả lời…'
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
                        void playAudio(m.audioUrl!, 'manual', m.content);
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
            <SuggestionChips items={allSuggestions} tone="panel" onPick={(q) => void sendText(q)} />
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
              // Bọc trong arrow: onClick truyền MouseEvent, mà sendText giờ nhận
              // tham số câu hỏi -> gọi trực tiếp sẽ gửi nhầm event thành câu hỏi.
              onClick={() => sendText()}
              disabled={busy || !input.trim()}
              className="shrink-0 rounded-full bg-white px-4 py-2.5 text-sm font-medium text-black disabled:opacity-40"
            >
              Gửi
            </button>
          </div>
        </div>
      )}

      {/* Chế độ voice (CHƯA bung chat): ô nhỏ chạy phụ đề từng câu khớp giọng nói —
          cố ý KHÔNG đổ nguyên bài trả lời ra đây, model phải luôn nhìn thấy được.
          Chạm vào ô để bung khung chat chữ đọc toàn văn. */}
      {!expanded && showCaption && (status || caption || lastAssistant || !tracking) && (
        <div className="pointer-events-auto w-full max-w-md">
          {status ? (
            <p className="mx-auto w-fit rounded-full bg-black/70 px-4 py-1.5 text-xs text-white/80 shadow-lg backdrop-blur">
              {status}
            </p>
          ) : caption ? (
            <button
              onClick={() => setExpanded(true)}
              aria-label="Xem toàn văn câu trả lời"
              className="w-full rounded-2xl bg-black/70 px-4 py-2.5 text-left shadow-lg backdrop-blur transition active:scale-[0.98]"
            >
              <span className="flex items-start gap-2">
                <span className={`mt-px shrink-0 text-xs ${speaking ? 'animate-pulse' : 'opacity-40'}`}>
                  🔊
                </span>
                {/* Không cắt cụt: mẩu phụ đề đã được xẻ sẵn ≤ MAX_CAPTION_CHARS nên
                    luôn vừa ~3 dòng, ô nở theo chữ mà không lấn lên model */}
                <span className="text-sm leading-snug text-white">
                  {caption.shown}
                  {speaking && caption.shown.length < caption.full.length && (
                    <span className="animate-pulse text-white/70">▍</span>
                  )}
                </span>
              </span>
              {/* Thanh tiến độ: du khách biết còn bao nhiêu câu nữa mới hết lượt nói */}
              {caption.total > 1 && (
                <span className="mt-2 block h-0.5 w-full overflow-hidden rounded-full bg-white/15">
                  <span
                    className="block h-full rounded-full bg-white/60 transition-all duration-300"
                    style={{ width: `${((caption.index + 1) / caption.total) * 100}%` }}
                  />
                </span>
              )}
            </button>
          ) : lastAssistant ? (
            <button
              onClick={() => setExpanded(true)}
              aria-label="Xem toàn văn câu trả lời"
              className="w-full rounded-2xl bg-black/70 px-4 py-2.5 text-left shadow-lg backdrop-blur transition active:scale-[0.98]"
            >
              <span className="line-clamp-2 text-sm leading-snug text-white/80">
                {lastAssistant.content}
              </span>
            </button>
          ) : (
            <p className="mx-auto w-fit rounded-full bg-black/70 px-4 py-1.5 text-xs text-white/60 shadow-lg backdrop-blur">
              Đang tìm lại nghệ nhân… bạn vẫn có thể trò chuyện.
            </p>
          )}
        </div>
      )}

      {/* Nút gợi ý ở chế độ voice: chỉ hiện khi nghệ nhân đã nói xong; bấm là hỏi luôn */}
      {!expanded && (
        <SuggestionChips items={voiceSuggestions} tone="overlay" onPick={(q) => void sendText(q)} />
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
            // Khoá pointer vào nút: ngón tay xê dịch khi đang giữ vẫn không rời nút, nên
            // pointerup luôn bắn đúng chỗ và ghi âm không bị dừng non (bỏ onPointerLeave).
            try {
              e.currentTarget.setPointerCapture(e.pointerId);
            } catch {
              /* trình duyệt cũ không hỗ trợ -> vẫn dựa vào pointerup/cancel */
            }
            void startRecording();
          }}
          onPointerUp={(e) => {
            e.preventDefault();
            stopRecording();
          }}
          onPointerCancel={() => recording && stopRecording()}
          onContextMenu={(e) => e.preventDefault()}
          disabled={busy}
          aria-label="Giữ để nói"
          className={`flex h-16 w-16 select-none touch-none items-center justify-center rounded-full text-2xl shadow-xl transition active:scale-95 disabled:opacity-40 ${
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

      {/* Nhắc thao tác chỉ khi màn hình đang trống — có phụ đề rồi thì nhường chỗ cho chữ */}
      {!expanded && !status && !caption && !lastAssistant && (
        <p className="pointer-events-none text-center text-xs text-white/70">
          Giữ nút micro để nói với nghệ nhân
        </p>
      )}
    </div>
  );
}
