import { NextResponse } from 'next/server';
import type { ChatMessage } from '@/lib/types';

// ⬅️ CHỪA CHỖ GIAI ĐOẠN 2.
// POST /api/ai  { slug, messages: ChatMessage[] } -> ChatMessage (assistant)
//
// Hiện trả stub. Khi có backend LLM thật:
//   const res = await fetch(`${process.env.API_BASE_URL}/chat`, { ... });
// và map câu trả lời về ChatMessage. Không cần đụng tầng AR.
export async function POST(req: Request) {
  const body = (await req.json()) as { slug?: string; messages?: ChatMessage[] };
  const last = body.messages?.at(-1)?.content ?? '';

  const reply: ChatMessage = {
    role: 'assistant',
    content:
      `(stub GĐ2) Bạn hỏi: "${last}". ` +
      `Backend AI cho nghệ nhân "${body.slug ?? '?'}" sẽ được nối ở Giai đoạn 2.`,
  };

  return NextResponse.json(reply);
}
