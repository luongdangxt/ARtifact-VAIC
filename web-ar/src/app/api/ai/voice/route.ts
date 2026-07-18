import { NextResponse } from 'next/server';
import type { VoiceReply } from '@/lib/types';
import { getArtisanBySlug } from '@/data/artisans';
import {
  backendAuthHeaders,
  backendBaseUrl,
  personaFields,
  toProxiedAudioUrl,
} from '@/lib/server/backend';

// POST /api/ai/voice  (multipart: slug, file=audio) -> VoiceReply
// Du khách hỏi bằng GIỌNG NÓI. Proxy tới backend POST /v1/audio/ask (STT + trả lời + TTS),
// nhập vai nghệ nhân theo slug.
export async function POST(req: Request) {
  const inForm = await req.formData();
  const slug = (inForm.get('slug') as string | null) ?? '';
  const file = inForm.get('file');
  if (!(file instanceof Blob)) {
    return NextResponse.json({ error: 'Thiếu file âm thanh.' }, { status: 400 });
  }

  const artisan = slug ? getArtisanBySlug(slug) : undefined;

  const outForm = new FormData();
  outForm.append('file', file, 'question.webm');
  outForm.append('synthesize', 'true');
  const persona = personaFields(artisan);
  if (persona.persona_name) outForm.append('persona_name', persona.persona_name);
  if (persona.persona_craft) outForm.append('persona_craft', persona.persona_craft);
  if (persona.persona_bio) outForm.append('persona_bio', persona.persona_bio);

  let res: Response;
  try {
    res = await fetch(`${backendBaseUrl()}/v1/audio/ask`, {
      method: 'POST',
      headers: { ...backendAuthHeaders() },
      body: outForm,
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

  const data = (await res.json()) as {
    answer?: string;
    transcript?: string | null;
    audio_url?: string | null;
  };
  const reply: VoiceReply = {
    role: 'assistant',
    content: data.answer ?? 'Dạ, hiện mình chưa trả lời được câu này.',
    transcript: data.transcript ?? undefined,
    audioUrl: toProxiedAudioUrl(data.audio_url),
  };
  return NextResponse.json(reply);
}
