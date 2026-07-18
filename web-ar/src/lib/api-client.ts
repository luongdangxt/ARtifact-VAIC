import type { Artisan, ChatMessage, VoiceReply } from '@/lib/types';

// Lớp trung gian giữa UI và nguồn dữ liệu.
// Đổi mock -> backend thật: chỉ cần sửa các route /api/* mà file này gọi tới.

function baseUrl(): string {
  // Trên server (SSR/route handler) fetch tương đối không hoạt động -> cần URL tuyệt đối.
  // Trên client dùng đường dẫn tương đối.
  if (typeof window !== 'undefined') return '';
  return process.env.NEXT_PUBLIC_SITE_URL ?? 'http://localhost:3000';
}

export async function fetchArtisans(): Promise<Artisan[]> {
  const res = await fetch(`${baseUrl()}/api/artisans`, { cache: 'no-store' });
  if (!res.ok) throw new Error(`fetchArtisans failed: ${res.status}`);
  return res.json();
}

export async function fetchArtisan(slug: string): Promise<Artisan | null> {
  const res = await fetch(`${baseUrl()}/api/artisans?slug=${encodeURIComponent(slug)}`, {
    cache: 'no-store',
  });
  if (res.status === 404) return null;
  if (!res.ok) throw new Error(`fetchArtisan failed: ${res.status}`);
  return res.json();
}

// Hỏi bằng CHỮ: gửi lịch sử hội thoại, nhận câu trả lời (kèm audioUrl để phát giọng).
export async function askAI(
  slug: string,
  messages: ChatMessage[],
): Promise<ChatMessage> {
  const res = await fetch(`${baseUrl()}/api/ai`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ slug, messages }),
  });
  if (!res.ok) throw new Error(`askAI failed: ${res.status}`);
  return res.json();
}

// Hỏi bằng GIỌNG NÓI: gửi audio thu từ mic -> backend STT + trả lời + TTS.
// Trả về câu trả lời (audioUrl) và transcript (câu du khách vừa nói).
export async function askAIVoice(
  slug: string,
  audio: Blob,
): Promise<VoiceReply> {
  const form = new FormData();
  form.append('slug', slug);
  // Tên file có đuôi để backend/FPT nhận đúng định dạng.
  const ext = audio.type.includes('mp4') || audio.type.includes('mpeg') ? 'm4a' : 'webm';
  form.append('file', audio, `question.${ext}`);
  const res = await fetch(`${baseUrl()}/api/ai/voice`, {
    method: 'POST',
    body: form,
  });
  if (!res.ok) throw new Error(`askAIVoice failed: ${res.status}`);
  return res.json();
}
