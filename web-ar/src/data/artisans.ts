import type { Artisan } from '@/lib/types';

// ─────────────────────────────────────────────────────────────────────────────
// FILE .MIND GỘP (multi-target): mọi nghệ nhân dùng CHUNG 1 file .mind.
// Máy quét chung mở file này 1 lần, mỗi ảnh mốc là 1 target theo thứ tự compile
// (= Artisan.targetIndex). Chĩa ảnh nào → tự động hiện nghệ nhân tương ứng,
// KHÔNG có bước chọn thủ công.
//
// File .mind GỘP 2 target, compile từ ảnh mốc TẠM bằng scripts/compile-targets.mjs.
// Thứ tự compile: [0] quan-ho-nam, [1] dong-ho-nam — KHỚP targetIndex bên dưới.
// (ảnh mốc #1 GIỮ NGUYÊN quan-ho-nu.png — chỉ đổi MODEL neo lên thẻ, không compile lại .mind)
// Khi có ảnh mốc THẬT: thay PNG trong public/markers rồi chạy lại
//   node scripts/gen-temp-markers.mjs   (chỉ khi cần sinh lại ảnh tạm)
//   node scripts/compile-targets.mjs    (compile lại .mind)
export const TARGETS_MIND = '/targets/artisans.mind';

// Dữ liệu seed tạm trước khi có DB/CMS.
// Khi có backend thật: thay nguồn này trong /api/artisans + api-client, không sửa component AR.
// ẢNH MỐC DỰNG ĐỨNG (trên tường/kệ), soi NGANG: Y của ảnh = hướng lên thật, pháp tuyến
// Z chĩa ra camera -> model KHÔNG cần xoay ([0,0,0]) là đã đứng thẳng + quay mặt vào camera.
// Nếu thấy model quay LƯNG lại thì đổi trục Y: rotationDeg [0,180,0]. groundAlign TẮT
// (nó đẩy theo Z, giờ Z nằm ngang) -> để model căn giữa ảnh mốc.
export const artisans: Artisan[] = [
  {
    slug: 'quan-ho-nam',
    targetIndex: 0, // ảnh mốc #1 trong file .mind gộp
    name: 'Liền anh Quan họ',
    craft: 'Dân ca Quan họ Bắc Ninh',
    bio: 'Nhân vật nam (liền anh) trong canh hát Quan họ, có animation (rig Mixamo). '
      + 'Quét ảnh mốc để thấy model 3D neo lên thẻ và chuyển động; '
      + 'bấm “Xem cỡ thật” để đặt nhân vật xuống sàn theo kích thước thật.',
    ar: {
      // GLB có animation (6 clip Mixamo) — đã nén texture WebP 2K (~2.7MB).
      // Dùng cho MindAR (model trên thẻ) + Android Scene Viewer (cỡ thật).
      modelUrl: '/models/glb/quan-ho-nam.glb',
      markerUrl: '/markers/quan-ho-nu.png', // ẢNH TẠM — thay ảnh thật sau
      scale: 2.0, // model to (~2× bề rộng ảnh mốc) để thấy rõ, khỏi đưa điện thoại lại gần
      // offset trong hệ ảnh-mốc: X phải, Y lên (TRONG mặt phẳng card), Z nhô khỏi card.
      offset: [0, -0.5, 0], // hạ xuống để đầu không quá cao, gần tầm mắt khách hơn
      // Clip 5 = cử động TẠI CHỖ (clip 0-2 có bước đi -> ra khỏi thẻ; 3-4 đứng hình).
      animationIndex: 5,
      // "Xem cỡ thật": iOS đọc USDZ (Quick Look), Android đọc GLB (Scene Viewer).
      // USDZ bản nam TĨNH, đã scale ×100 về cao ~1.77m thật (bản export gốc bị 0.01 ->
      // 1.8cm; sửa bằng scale trên /root, mpu=1.0 up=Z khớp các model khác). Quick Look
      // không phát animation Mixamo nên bản tĩnh là đủ cho "cỡ thật".
      modelUsdzUrl: '/models/usdz/quan-ho-nam.usdz',
      groundAlign: false,
      rotationDeg: [0, 0, 0], // ảnh mốc dựng đứng -> đứng thẳng, quay mặt vào camera
    },
    aiEnabled: false,
  },
  {
    slug: 'dong-ho-nam',
    targetIndex: 1, // ảnh mốc #2 — KHỚP thứ tự compile file .mind
    name: 'Ông đồ tranh Đông Hồ',
    craft: 'Tranh dân gian Đông Hồ',
    bio: 'Nhân vật nam (ông đồ) trong cảnh vẽ tranh Đông Hồ. Quét ảnh mốc để thấy model 3D; '
      + 'bấm “Xem cỡ thật” để dựng nhân vật kích thước thật trên sàn.',
    ar: {
      modelUrl: '/models/glb/dong-ho-nam.glb',
      markerUrl: '/markers/dong-ho-nam.png', // ẢNH TẠM — thay ảnh thật sau
      scale: 2.0, // model to (~2× bề rộng ảnh mốc) để thấy rõ, khỏi đưa điện thoại lại gần
      offset: [0, -0.5, 0], // hạ xuống để đầu không quá cao, gần tầm mắt khách hơn
      modelUsdzUrl: '/models/usdz/dong-ho-nam.usdz',
      groundAlign: false,
      rotationDeg: [0, 0, 0], // ảnh mốc dựng đứng -> đứng thẳng, quay mặt vào camera
    },
    aiEnabled: false,
  },
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
