import type { Artisan } from '@/lib/types';

// Dữ liệu seed tạm trước khi có DB/CMS.
// Khi có backend thật: thay nguồn này trong /api/artisans + api-client, không sửa component AR.
//
// Phase 0/1 dùng asset mẫu (sample-card.mind + sample.glb) để kiểm chứng tracking.
// Khi có card + model thật cho từng nghệ nhân: đổi targetUrl/modelUrl sang file riêng
// (vd '/targets/nghe-nhan-01.mind', '/models/nghe-nhan-01.glb') và tinh chỉnh scale/offset.

export const artisans: Artisan[] = [
  {
    slug: 'nghe-nhan-01',
    name: 'Nghệ nhân mẫu 01',
    craft: 'Di sản mẫu (spike Phase 0)',
    bio: 'Bản mẫu để kiểm chứng tracking MindAR trên điện thoại thật. '
      + 'Quét card mẫu để thấy model 3D neo lên ảnh.',
    ar: {
      targetUrl: '/targets/sample-card.mind',
      modelUrl: '/models/sample.glb',
      markerUrl: '/markers/sample-card.png',
      scale: 0.3,
      offset: [0, 0.35, 0],
    },
    aiEnabled: false,
  },
];

export function getArtisanBySlug(slug: string): Artisan | undefined {
  return artisans.find((a) => a.slug === slug);
}
