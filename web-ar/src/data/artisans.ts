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
      // GLB: dùng cho MindAR (model nhỏ trên thẻ) + Android Scene Viewer (cỡ thật).
      modelUrl: '/models/glb/sample.glb',
      markerUrl: '/markers/sample-card.png',
      scale: 0.3,
      // offset trong hệ ảnh-mốc: X phải, Y lên (TRONG mặt phẳng card), Z nhô khỏi card.
      // Để model nằm ĐÚNG giữa mốc -> [0,0,0]. Muốn nhấc khỏi mặt card thì tăng Z (vd 0.1).
      offset: [0, 0, 0],
      // "Xem cỡ thật": iOS đọc USDZ (Quick Look), Android đọc GLB (Scene Viewer).
      // Model 2 định dạng để riêng: public/models/glb + public/models/usdz.
      modelUsdzUrl: '/models/usdz/sample.usdz',
      // Chân/đáy model chạm mặt phẳng thẻ thay vì căn tâm (nửa chìm dưới thẻ).
      groundAlign: true,
      // Khi thay model NGƯỜI thật: bật dòng dưới để dựng đứng khỏi thẻ nằm ngang.
      // Test trên máy: nếu người nằm/nghiêng -> đổi số; quay lưng -> thêm 180 ở trục Y.
      // rotationDeg: [90, 0, 0],
    },
    aiEnabled: false,
  },
];

export function getArtisanBySlug(slug: string): Artisan | undefined {
  return artisans.find((a) => a.slug === slug);
}
