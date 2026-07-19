import { NextResponse } from 'next/server';
import type { VoiceReply } from '@/lib/types';
import { getArtisanBySlug } from '@/data/artisans';
import {
  backendAuthHeaders,
  backendBaseUrl,
  personaFields,
  toProxiedAudioUrl,
} from '@/lib/server/backend';

// Suy ra đuôi file từ MIME khi client không gửi kèm tên (phòng hờ). Whisper/FPT chọn
// bộ giải mã theo đuôi này nên phải đúng với dữ liệu thực (webm/opus vs mp4/aac...).
function extFromMime(type: string): string {
  const t = (type || '').toLowerCase();
  if (t.includes('mp4') || t.includes('m4a') || t.includes('aac')) return 'm4a';
  if (t.includes('mpeg') || t.includes('mp3')) return 'mp3';
  if (t.includes('ogg') || t.includes('opus')) return 'ogg';
  if (t.includes('wav')) return 'wav';
  return 'webm';
}

// POST /api/ai/voice  (multipart: slug, file=audio) -> VoiceReply
// Du khách hỏi bằng GIỌNG NÓI. Proxy tới backend POST /v1/audio/ask (STT + trả lời + TTS),
// nhập vai nghệ nhân theo slug.
export async function POST(req: Request) {
  const inForm = await req.formData();
  const slug = (inForm.get('slug') as string | null) ?? '';
  const history = (inForm.get('history') as string | null) ?? '';
  const file = inForm.get('file');
  if (!(file instanceof Blob)) {
    return NextResponse.json({ error: 'Thiếu file âm thanh.' }, { status: 400 });
  }

  const artisan = slug ? getArtisanBySlug(slug) : undefined;

  // Giữ NGUYÊN tên file (kèm đuôi) client gửi lên. FPT STT là endpoint OpenAI-compatible
  // (Whisper) -> nó dựa vào ĐUÔI FILE để chọn demuxer. iOS Safari thu ra audio/mp4 (đuôi
  // .m4a); nếu ép thành 'question.webm' thì Whisper mở như webm -> hỏng -> transcript rỗng
  // -> "không nhận diện được" (chỉ lỗi trên iOS, còn Android thu webm nên trùng đuôi vẫn chạy).
  const incomingName = file instanceof File ? file.name : '';
  const filename = /\.[a-z0-9]{2,4}$/i.test(incomingName)
    ? incomingName
    : `question.${extFromMime(file.type)}`;

  const outForm = new FormData();
  outForm.append('file', file, filename);
  outForm.append('synthesize', 'true');
  if (history) outForm.append('history_json', history);
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
