import { backendAuthHeaders, backendBaseUrl } from '@/lib/server/backend';

// GET /api/ai/audio?file=abc.wav  -> stream WAV từ backend /v1/audio/files/{file}.
// Đi qua proxy để browser phát được audio mà không lộ API_AUTH_TOKEN và không dính CORS.
export async function GET(req: Request) {
  const file = new URL(req.url).searchParams.get('file') ?? '';
  // Chỉ cho tên file .wav (chống path traversal).
  if (!/^[\w.-]+\.wav$/i.test(file)) {
    return new Response('Bad file', { status: 400 });
  }

  let res: Response;
  try {
    res = await fetch(`${backendBaseUrl()}/v1/audio/files/${encodeURIComponent(file)}`, {
      headers: { ...backendAuthHeaders() },
    });
  } catch {
    return new Response('Upstream error', { status: 502 });
  }

  if (!res.ok || !res.body) {
    return new Response('Not found', { status: 404 });
  }

  return new Response(res.body, {
    status: 200,
    headers: {
      'Content-Type': 'audio/wav',
      'Cache-Control': 'no-store',
    },
  });
}
