import type { Artisan } from '@/lib/types';

// ─────────────────────────────────────────────────────────────────────────────
// FILE .MIND GỘP (multi-target): mọi nghệ nhân dùng CHUNG 1 file .mind.
// Máy quét chung mở file này 1 lần, mỗi ảnh mốc là 1 target theo thứ tự compile
// (= Artisan.targetIndex). Chĩa ảnh nào → tự động hiện nghệ nhân tương ứng,
// KHÔNG có bước chọn thủ công.
//
// Tạm thời trỏ về file mẫu 1 target (sample-card.mind) để test đường ống ngay.
// Khi có ảnh thật: xem "CÁCH THÊM NGHỆ NHÂN" cuối file.
export const TARGETS_MIND = '/targets/sample-card.mind';

// Dữ liệu seed tạm trước khi có DB/CMS.
// Khi có backend thật: thay nguồn này trong /api/artisans + api-client, không sửa component AR.
export const artisans: Artisan[] = [
  {
    slug: 'nghe-nhan-01',
    targetIndex: 0, // ảnh đầu tiên trong file .mind gộp
    name: 'Nghệ nhân mẫu 01',
    craft: 'Di sản mẫu (spike Phase 0)',
    bio: 'Bản mẫu để kiểm chứng tracking MindAR trên điện thoại thật. '
      + 'Quét card mẫu để thấy model 3D neo lên ảnh.',
    ar: {
      // GLB: dùng cho MindAR (model nhỏ trên thẻ) + Android Scene Viewer (cỡ thật).
      modelUrl: '/models/glb/sample.glb',
      markerUrl: '/markers/sample-card.png',
      scale: 0.3,
      // offset trong hệ ảnh-mốc: X phải, Y lên (TRONG mặt phẳng card), Z nhô khỏi card.
      // Để model nằm ĐÚNG giữa mốc -> [0,0,0]. Muốn nhấc khỏi mặt card thì tăng Z (vd 0.1).
      offset: [0, 0, 0],
      // "Xem cỡ thật": iOS đọc USDZ (Quick Look), Android đọc GLB (Scene Viewer).
      modelUsdzUrl: '/models/usdz/sample.usdz',
      // Chân/đáy model chạm mặt phẳng thẻ thay vì căn tâm (nửa chìm dưới thẻ).
      groundAlign: true,
      // Khi thay model NGƯỜI thật: bật dòng dưới để dựng đứng khỏi thẻ nằm ngang.
      // rotationDeg: [90, 0, 0],
    },
    aiEnabled: false,
  },

  // ── CHỪA CHỖ CHO NGHỆ NHÂN THẬT (bỏ comment + điền khi đã có ảnh mốc + model) ──
  // {
  //   slug: 'nghe-nhan-02',
  //   targetIndex: 1, // PHẢI khớp thứ tự ảnh lúc compile file .mind gộp
  //   name: 'Tên nghệ nhân 02',
  //   craft: 'Nghề / di sản',
  //   bio: 'Tiểu sử ngắn…',
  //   ar: {
  //     modelUrl: '/models/glb/nghe-nhan-02.glb',
  //     markerUrl: '/markers/nghe-nhan-02.png',
  //     scale: 0.3,
  //     offset: [0, 0, 0],
  //     modelUsdzUrl: '/models/usdz/nghe-nhan-02.usdz',
  //     groundAlign: true,
  //     // rotationDeg: [90, 0, 0],
  //   },
  //   aiEnabled: false,
  // },
];

export function getArtisanBySlug(slug: string): Artisan | undefined {
  return artisans.find((a) => a.slug === slug);
}

// ─────────────────────────────────────────────────────────────────────────────
// CÁCH THÊM NGHỆ NHÂN THẬT
// 1. Chuẩn bị ảnh mốc từng người (png/jpg, hoa văn rõ để MindAR bám tốt).
// 2. Compile 1 file .mind GỘP bằng MindAR Image Compiler
//    (https://hiukim.github.io/mind-ar-js-doc/tools/compile hoặc node compiler).
//    THỨ TỰ add ảnh = targetIndex (ảnh #1 -> index 0, ảnh #2 -> index 1, …).
//    Lưu ra public/targets/artisans.mind, rồi đổi TARGETS_MIND ở trên trỏ file này.
// 3. Bỏ model .glb (+ .usdz nếu cần "xem cỡ thật") vào public/models/…
// 4. Thêm entry vào artisans[] với targetIndex KHỚP thứ tự ảnh + đường dẫn model.
// ─────────────────────────────────────────────────────────────────────────────
