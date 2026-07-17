import { NextResponse } from 'next/server';
import { artisans, getArtisanBySlug } from '@/data/artisans';

// GET /api/artisans            -> danh sách nghệ nhân
// GET /api/artisans?slug=xxx   -> chi tiết 1 nghệ nhân (404 nếu không có)
// Hiện trả mock từ data/artisans. Sau này nối DB/CMS tại đây, client không đổi.
export async function GET(req: Request) {
  const { searchParams } = new URL(req.url);
  const slug = searchParams.get('slug');

  if (slug) {
    const artisan = getArtisanBySlug(slug);
    if (!artisan) {
      return NextResponse.json({ error: 'not found' }, { status: 404 });
    }
    return NextResponse.json(artisan);
  }

  return NextResponse.json(artisans);
}
