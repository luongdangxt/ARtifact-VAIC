import { NextResponse } from 'next/server';
import type { ChatMessage } from '@/lib/types';
import { getArtisanBySlug } from '@/data/artisans';
import {
  backendAuthHeaders,
  backendBaseUrl,
  personaFields,
  toProxiedAudioUrl,
} from '@/lib/server/backend';

// POST /api/ai  { slug, messages: ChatMessage[] } -> ChatMessage (assistant, kèm audioUrl)
// Proxy tới backend FastAPI POST /v1/ask, nhập vai nghệ nhân theo slug. Chạy server-side
// nên không dính CORS và giữ token phía server.
export async function POST(req: Request) {
  const body = (await req.json()) as { slug?: string; messages?: ChatMessage[] };
  const question = body.messages?.at(-1)?.content?.trim() ?? '';
  if (!question) {
    return NextResponse.json({ error: 'Thiếu câu hỏi.' }, { status: 400 });
  }

  const artisan = body.slug ? getArtisanBySlug(body.slug) : undefined;

  let res: Response;
  try {
    res = await fetch(`${backendBaseUrl()}/v1/ask`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ...backendAuthHeaders() },
      body: JSON.stringify({
        question,
        synthesize: true,
        ...personaFields(artisan),
      }),
    });
  } catch {
    return NextResponse.json(
      { error: 'Không kết nối được tới máy chủ AI.' },
      { status: 502 },
    );
  }

  if (!res.ok) {
    return NextResponse.json({ error: `Backend AI lỗi (${res.status}).` }, { status: 502 });
  }

  const data = (await res.json()) as { answer?: string; audio_url?: string | null };
  const reply: ChatMessage = {
    role: 'assistant',
    content: data.answer ?? 'Dạ, hiện mình chưa trả lời được câu này.',
    audioUrl: toProxiedAudioUrl(data.audio_url),
  };
  return NextResponse.json(reply);
}
