import type { ARTarget } from '@/lib/types';
import { getArtisanBySlug } from '@/data/artisans';

// Map slug -> cấu hình AR (target, model, scale, offset).
// Hiện lấy từ data seed; sau này có thể lấy từ API/DB mà không đổi tầng AR.
export function getARConfig(slug: string): ARTarget | null {
  return getArtisanBySlug(slug)?.ar ?? null;
}
