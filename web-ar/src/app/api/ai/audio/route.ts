import { backendAuthHeaders, backendBaseUrl } from '@/lib/server/backend';

function ascii(bytes: Uint8Array, offset: number, length: number): string {
  return String.fromCharCode(...bytes.subarray(offset, offset + length));
}

/**
 * FPT.AI-VITs đôi khi trả WAV có RIFF/data size lớn gấp đôi payload thật.
 * Desktop player thường bỏ qua lỗi này, còn Safari/Web Audio có thể báo
 * EncodingError. Proxy sửa cả file cũ trên production, không chỉ file mới.
 */
function normalizeWavHeader(buffer: ArrayBuffer): { buffer: ArrayBuffer; changed: boolean } {
  const bytes = new Uint8Array(buffer);
  if (
    bytes.byteLength < 44 ||
    ascii(bytes, 0, 4) !== 'RIFF' ||
    ascii(bytes, 8, 4) !== 'WAVE'
  ) {
    throw new Error('Upstream did not return a RIFF/WAVE file');
  }

  const view = new DataView(buffer);
  let changed = view.getUint32(4, true) !== bytes.byteLength - 8;
  view.setUint32(4, bytes.byteLength - 8, true);

  let offset = 12;
  while (offset + 8 <= bytes.byteLength) {
    const chunkId = ascii(bytes, offset, 4);
    const declaredSize = view.getUint32(offset + 4, true);
    const dataOffset = offset + 8;

    if (chunkId === 'data') {
      const actualSize = bytes.byteLength - dataOffset;
      if (actualSize <= 0) throw new Error('WAV data chunk is empty');
      changed ||= declaredSize !== actualSize;
      view.setUint32(offset + 4, actualSize, true);
      return { buffer, changed };
    }

    const nextOffset = dataOffset + declaredSize + (declaredSize % 2);
    if (nextOffset > bytes.byteLength) throw new Error('WAV chunk is truncated');
    offset = nextOffset;
  }

  throw new Error('WAV data chunk is missing');
}

function requestedRange(req: Request, total: number): { start: number; end: number } | null {
  const value = req.headers.get('range');
  const match = value?.match(/^bytes=(\d+)-(\d*)$/i);
  if (!match) return null;

  const start = Number(match[1]);
  const end = match[2] ? Number(match[2]) : total - 1;
  if (!Number.isSafeInteger(start) || !Number.isSafeInteger(end) || start > end || start >= total) {
    return null;
  }
  return { start, end: Math.min(end, total - 1) };
}

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

  if (!res.ok) {
    return new Response('Not found', { status: 404 });
  }

  try {
    const normalized = normalizeWavHeader(await res.arrayBuffer());
    const total = normalized.buffer.byteLength;
    const range = requestedRange(req, total);
    const headers: Record<string, string> = {
      'Accept-Ranges': 'bytes',
      'Cache-Control': 'no-store',
      'Content-Type': 'audio/wav',
      'X-Audio-Header-Normalized': normalized.changed ? 'true' : 'false',
    };

    if (range) {
      const body = normalized.buffer.slice(range.start, range.end + 1);
      headers['Content-Length'] = String(body.byteLength);
      headers['Content-Range'] = `bytes ${range.start}-${range.end}/${total}`;
      return new Response(body, { status: 206, headers });
    }

    headers['Content-Length'] = String(total);
    return new Response(normalized.buffer, { status: 200, headers });
  } catch (error) {
    console.error('Invalid upstream TTS audio', error);
    return new Response('Invalid upstream audio', { status: 502 });
  }
}
