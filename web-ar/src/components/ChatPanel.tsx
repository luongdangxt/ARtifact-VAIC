'use client';

import { useEffect, useRef, useState } from 'react';
import type { Artisan, ChatMessage } from '@/lib/types';
import { askAI, askAIVoice } from '@/lib/api-client';

interface Props {
  artisan: Artisan;
  onClose: () => void;
}

// Khung chat nổi trên AR: du khách hỏi bằng CHỮ hoặc GIỌNG NÓI, nghệ nhân trả lời
// (kèm giọng nói TTS). Reset hội thoại khi đổi sang nghệ nhân khác.
export default function ChatPanel({ artisan, onClose }: Props) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [recording, setRecording] = useState(false);

  const audioRef = useRef<HTMLAudioElement | null>(null);
  const recorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const scrollRef = useRef<HTMLDivElement | null>(null);

  // Reset khi đổi nghệ nhân do ARScene remount qua `key={artisan.slug}`.

  // Tự cuộn xuống cuối khi có tin mới.
  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: 'smooth' });
  }, [messages, busy]);

  // Dọn dẹp khi đóng.
  useEffect(() => {
    return () => {
      recorderRef.current?.stream.getTracks().forEach((t) => t.stop());
      audioRef.current?.pause();
    };
  }, []);

  function playAudio(url: string) {
    if (!audioRef.current) audioRef.current = new Audio();
    audioRef.current.src = url;
    void audioRef.current.play().catch(() => {});
  }

  function pushAssistant(reply: ChatMessage) {
    setMessages((m) => [...m, reply]);
    if (reply.audioUrl) playAudio(reply.audioUrl);
  }

  async function sendText() {
    const q = input.trim();
    if (!q || busy) return;
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

  async function startRecording() {
    if (busy || recording) return;
    setError(null);
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const mime = MediaRecorder.isTypeSupported('audio/webm') ? 'audio/webm' : '';
      const recorder = new MediaRecorder(stream, mime ? { mimeType: mime } : undefined);
      chunksRef.current = [];
      recorder.ondataavailable = (e) => {
        if (e.data.size > 0) chunksRef.current.push(e.data);
      };
      recorder.onstop = () => {
        stream.getTracks().forEach((t) => t.stop());
        const blob = new Blob(chunksRef.current, { type: recorder.mimeType || 'audio/webm' });
        void sendVoice(blob);
      };
      recorderRef.current = recorder;
      recorder.start();
      setRecording(true);
    } catch {
      setError('Không truy cập được micro. Hãy cho phép quyền micro.');
    }
  }

  function stopRecording() {
    if (recorderRef.current?.state === 'recording') recorderRef.current.stop();
    setRecording(false);
  }

  async function sendVoice(blob: Blob) {
    setBusy(true);
    try {
      const reply = await askAIVoice(artisan.slug, blob);
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

  return (
    <div className="pointer-events-auto absolute inset-x-0 bottom-0 z-30 flex max-h-[72vh] flex-col rounded-t-2xl bg-neutral-900/95 text-white shadow-2xl backdrop-blur">
      {/* Header */}
      <div className="flex items-center justify-between border-b border-white/10 px-4 py-3">
        <div className="min-w-0">
          <p className="truncate text-sm font-semibold">{artisan.name}</p>
          <p className="truncate text-xs text-white/60">{artisan.craft}</p>
        </div>
        <button
          onClick={onClose}
          aria-label="Đóng"
          className="rounded-full bg-white/10 px-3 py-1.5 text-sm"
        >
          ✕
        </button>
      </div>

      {/* Danh sách tin nhắn */}
      <div ref={scrollRef} className="flex-1 space-y-3 overflow-y-auto px-4 py-3">
        {messages.length === 0 && !busy && (
          <p className="py-6 text-center text-sm text-white/50">
            Chào du khách! Hãy hỏi tôi bằng chữ hoặc nhấn nút micro để nói.
          </p>
        )}
        {messages.map((m, i) => (
          <div
            key={i}
            className={`flex ${m.role === 'user' ? 'justify-end' : 'justify-start'}`}
          >
            <div
              className={`max-w-[80%] rounded-2xl px-3.5 py-2 text-sm leading-relaxed ${
                m.role === 'user' ? 'bg-white text-black' : 'bg-white/10 text-white'
              }`}
            >
              <span className="whitespace-pre-wrap">{m.content}</span>
              {m.role === 'assistant' && m.audioUrl && (
                <button
                  onClick={() => playAudio(m.audioUrl!)}
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

      {/* Ô nhập + mic */}
      <div className="flex items-center gap-2 border-t border-white/10 px-3 py-3">
        <button
          onClick={recording ? stopRecording : startRecording}
          disabled={busy}
          aria-label={recording ? 'Dừng ghi âm' : 'Ghi âm câu hỏi'}
          className={`shrink-0 rounded-full px-4 py-2.5 text-lg disabled:opacity-40 ${
            recording ? 'animate-pulse bg-red-500 text-white' : 'bg-white/10 text-white'
          }`}
        >
          {recording ? '⏺' : '🎤'}
        </button>
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && sendText()}
          disabled={busy || recording}
          placeholder={recording ? 'Đang nghe…' : 'Nhập câu hỏi…'}
          className="min-w-0 flex-1 rounded-full bg-white/10 px-4 py-2.5 text-sm outline-none placeholder:text-white/40 disabled:opacity-50"
        />
        <button
          onClick={sendText}
          disabled={busy || recording || !input.trim()}
          className="shrink-0 rounded-full bg-white px-4 py-2.5 text-sm font-medium text-black disabled:opacity-40"
        >
          Gửi
        </button>
      </div>
    </div>
  );
}
