// CHỈ dùng phía server (route handlers). Không import vào client component.
// Nối tới backend AI (FastAPI). Cấu hình qua env server-only:
//   API_BASE_URL   — override URL backend (vd http://localhost:8000 khi chạy backend local)
//   API_AUTH_TOKEN — nếu backend bật API_AUTH_TOKEN (Bearer)

import type { Artisan } from '@/lib/types';

// Backend production mặc định (URL public, không phải secret) -> Vercel chạy được ngay
// mà không cần set env. Đặt API_BASE_URL để trỏ sang backend khác (vd localhost khi dev).
const DEFAULT_BACKEND_URL = 'https://artifact.primeralabs.vn';

export function backendBaseUrl(): string {
  return (process.env.API_BASE_URL ?? DEFAULT_BACKEND_URL).replace(/\/$/, '');
}

export function backendAuthHeaders(): Record<string, string> {
  const token = process.env.API_AUTH_TOKEN;
  return token ? { Authorization: `Bearer ${token}` } : {};
}

/** Field persona gửi kèm để nghệ nhân "nhập vai" (khớp AskRequest phía backend). */
export function personaFields(artisan: Artisan | undefined): {
  persona_name?: string;
  persona_craft?: string;
  persona_bio?: string;
} {
  if (!artisan) return {};
  return {
    persona_name: artisan.name,
    persona_craft: artisan.craft,
    persona_bio: artisan.bio,
  };
}

// Backend nối phần gợi ý vào cuối câu trả lời bằng chuỗi CỐ ĐỊNH (report_agent.py:
// `answer += f"\n\nBạn có thể hỏi tiếp:\n{follow_ups}"`), mỗi câu 1 dòng "- ...".
// Do code Python ghép chứ không phải Gemini sinh ra nên định dạng luôn ổn định.
const FOLLOW_UP_RE = /\n+\s*Bạn có thể hỏi tiếp:\s*\n/i;

/**
 * Tách câu trả lời thành phần lời kể + danh sách câu hỏi gợi ý.
 * Phần gợi ý bị BỎ khỏi content để bong bóng chat chỉ còn lời nghệ nhân nói —
 * gợi ý được render thành nút bấm. (TTS phía backend vốn đã cắt đoạn này rồi.)
 */
export function splitSuggestions(answer: string): {
  content: string;
  suggestions: string[];
} {
  const [body, tail] = answer.split(FOLLOW_UP_RE, 2);
  if (tail === undefined) return { content: answer.trim(), suggestions: [] };

  const suggestions = tail
    .split('\n')
    .map((line) => line.replace(/^\s*[-*•]\s*/, '').trim())
    .filter(Boolean);

  // Không nhặt được câu nào -> giữ nguyên câu trả lời gốc, đừng nuốt mất chữ.
  if (suggestions.length === 0) return { content: answer.trim(), suggestions: [] };
  return { content: body.trim(), suggestions };
}

/** Đổi audio_url backend ('/v1/audio/files/abc.mp3') -> proxy Next để giấu token. */
export function toProxiedAudioUrl(audioUrl: string | null | undefined): string | undefined {
  if (!audioUrl) return undefined;
  const name = audioUrl.split('/').pop();
  if (!name || !/^[\w.-]+\.(mp3|wav)$/i.test(name)) return undefined;
  return `/api/ai/audio?file=${encodeURIComponent(name)}`;
}
