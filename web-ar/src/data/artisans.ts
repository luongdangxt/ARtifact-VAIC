import type { Artisan } from '@/lib/types';

// ─────────────────────────────────────────────────────────────────────────────
// FILE .MIND GỘP (multi-target): mọi nghệ nhân dùng CHUNG 1 file .mind.
// Máy quét chung mở file này 1 lần, mỗi ảnh mốc là 1 target theo thứ tự compile
// (= Artisan.targetIndex). Chĩa ảnh nào → tự động hiện nghệ nhân tương ứng,
// KHÔNG có bước chọn thủ công.
//
// File .mind GỘP 5 target, compile bằng scripts/compile-targets.mjs.
// Thứ tự compile: [0] quan-ho-nam, [1] ong-do, [2] đờn ca, [3] nhã nhạc, [4] xòe Thái
// — KHỚP targetIndex bên dưới. Target 0-1 dùng ảnh mốc TẠM, 2-4 là ảnh mốc THẬT.
// Khi đổi/thêm ảnh mốc: đặt PNG vào public/markers, sửa mảng MARKERS trong
//   scripts/compile-targets.mjs (thứ tự = targetIndex) rồi chạy lại
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
      + 'Quét ảnh mốc để thấy model 3D neo lên thẻ và chuyển động.',
    ar: {
      // GLB có animation (6 clip Mixamo) — đã nén texture WebP 2K (~2.7MB).
      modelUrl: '/models/glb/quan-ho-nam.glb',
      markerUrl: '/markers/quan-ho-nu.png', // ẢNH TẠM — thay ảnh thật sau
      scale: 2.0, // model to (~2× bề rộng ảnh mốc) để thấy rõ, khỏi đưa điện thoại lại gần
      // offset trong hệ ảnh-mốc: X phải, Y lên (TRONG mặt phẳng card), Z nhô khỏi card.
      offset: [0, -0.5, 0], // hạ xuống để đầu không quá cao, gần tầm mắt khách hơn
      // Clip 5 = cử động TẠI CHỖ (clip 0-2 có bước đi -> ra khỏi thẻ; 3-4 đứng hình).
      animationIndex: 5,
      groundAlign: false,
      rotationDeg: [0, 0, 0], // ảnh mốc dựng đứng -> đứng thẳng, quay mặt vào camera
    },
    aiEnabled: true,
  },
  {
    slug: 'ong-do',
    targetIndex: 1, // ảnh mốc #2 — KHỚP thứ tự compile file .mind
    name: 'Ông đồ tranh Đông Hồ',
    craft: 'Tranh dân gian Đông Hồ',
    bio: 'Nhân vật nam (ông đồ) trong cảnh vẽ tranh Đông Hồ, có animation (rig Mixamo). '
      + 'Quét ảnh mốc để thấy model 3D neo lên thẻ và chuyển động.',
    ar: {
      // GLB có animation (7 clip Mixamo) — đã nén texture WebP 2K (~3.2MB).
      modelUrl: '/models/glb/ong-do.glb',
      markerUrl: '/markers/dong-ho-nam.png', // ẢNH TẠM — thay ảnh thật sau
      scale: 2.0, // model to (~2× bề rộng ảnh mốc) để thấy rõ, khỏi đưa điện thoại lại gần
      offset: [0, -0.5, 0], // hạ xuống để đầu không quá cao, gần tầm mắt khách hơn
      // Clip 5 = cử động TẠI CHỖ (clip 0-2 có bước đi -> ra khỏi thẻ; 3-4 đứng hình; 5-6 tại chỗ).
      animationIndex: 5,
      groundAlign: false,
      rotationDeg: [0, 0, 0], // ảnh mốc dựng đứng -> đứng thẳng, quay mặt vào camera
    },
    aiEnabled: true,
  },
  // ───────────────────────────────────────────────────────────────────────────
  // 3 di sản UNESCO dưới đây dùng ẢNH MỐC THẬT (hoạ tiết nhạc cụ/thổ cẩm).
  // slug = ĐÚNG id trong dataset RAG của Ai-backend và craft = ĐÚNG trường "name"
  // của di sản đó, để persona_craft gửi sang /v1/ask khớp nguồn tư liệu.
  // Model từ artifact-3d-model/*-Android.glb, đã nén texture WebP 2K (~2.7-3.3MB).
  {
    slug: 'don-ca-tai-tu-nam-bo',
    targetIndex: 2, // ảnh mốc #3 — KHỚP thứ tự compile file .mind
    name: 'Tài tử Đờn ca Nam Bộ',
    craft: 'Đờn ca tài tử Nam Bộ',
    bio: 'Nghệ nhân đờn ca tài tử miền sông nước Nam Bộ, chơi đờn kìm và đờn bầu trong '
      + 'các buổi tài tử tri âm. Quét ảnh mốc để thấy model 3D neo lên thẻ và chuyển động.',
    ar: {
      modelUrl: '/models/glb/don-ca.glb',
      markerUrl: '/markers/don-ca-tai-tu-nam-bo.png',
      scale: 2.0,
      offset: [0, -0.5, 0],
      animationIndex: 0, // 2 clip, cả hai đều là cử động nói chuyện TẠI CHỖ
      groundAlign: false,
      rotationDeg: [0, 0, 0],
    },
    aiEnabled: true,
  },
  {
    slug: 'nha-nhac-cung-dinh-hue',
    targetIndex: 3, // ảnh mốc #4
    name: 'Nhạc công Nhã nhạc cung đình',
    craft: 'Nhã nhạc cung đình Huế',
    bio: 'Nhạc công trong dàn Nhã nhạc cung đình Huế thời Nguyễn, diễn tấu ở các đại lễ '
      + 'nơi hoàng cung. Quét ảnh mốc để thấy model 3D neo lên thẻ và chuyển động.',
    ar: {
      modelUrl: '/models/glb/nha-nhac.glb',
      markerUrl: '/markers/nha-nhac-cung-dinh-hue.png',
      scale: 2.0,
      offset: [0, -0.5, 0],
      animationIndex: 0, // 3 clip, đều là cử động nói chuyện TẠI CHỖ
      groundAlign: false,
      rotationDeg: [0, 0, 0],
    },
    aiEnabled: true,
  },
  {
    slug: 'nghe-thuat-xoe-thai',
    targetIndex: 4, // ảnh mốc #5
    name: 'Nghệ nhân Xòe Thái',
    craft: 'Nghệ thuật Xòe Thái',
    bio: 'Nghệ nhân người Thái vùng Tây Bắc, giữ điệu xòe vòng trong hội bản mường. '
      + 'Quét ảnh mốc để thấy model 3D neo lên thẻ và chuyển động.',
    ar: {
      modelUrl: '/models/glb/xoe-thai.glb',
      markerUrl: '/markers/nghe-thuat-xoe-thai.png',
      scale: 2.0,
      offset: [0, -0.5, 0],
      animationIndex: 0, // chỉ có 1 clip
      groundAlign: false,
      rotationDeg: [0, 0, 0],
    },
    aiEnabled: true,
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
// 3. Bỏ model .glb vào public/models/…
// 4. Thêm entry vào artisans[] với targetIndex KHỚP thứ tự ảnh + đường dẫn model.
// ─────────────────────────────────────────────────────────────────────────────
