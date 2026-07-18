// Compile các ảnh mốc trong public/markers thành 1 file .mind GỘP đa target
// (offline, không cần trình duyệt) -> public/targets/artisans.mind
//
//   node scripts/compile-targets.mjs
//
// THỨ TỰ trong mảng MARKERS = targetIndex trong file .mind (ảnh #1 -> index 0, …).
// PHẢI khớp Artisan.targetIndex trong src/data/artisans.ts.
//
// Khi thay ảnh mốc thật: đặt PNG mới vào public/markers (cùng tên hoặc sửa danh sách
// bên dưới) rồi chạy lại lệnh này. Không cần dịch vụ web/CLI ngoài.
//
// GHI CHÚ KỸ THUẬT: mind-ar bản gốc có OfflineCompiler nhưng nó `import from 'canvas'`
// (native, không build được trên Node mới). Ta kế thừa thẳng CompilerBase và cấp canvas
// bằng @napi-rs/canvas (prebuilt, không cần compile). Phần compileTrack chép y từ
// OfflineCompiler của mind-ar.
import { CompilerBase } from 'mind-ar/src/image-target/compiler-base.js';
import { buildTrackingImageList } from 'mind-ar/src/image-target/image-list.js';
import { extractTrackingFeatures } from 'mind-ar/src/image-target/tracker/extract-utils.js';
import 'mind-ar/src/image-target/detector/kernels/cpu/index.js'; // đăng ký CPU kernels cho tfjs
import { createCanvas, loadImage } from '@napi-rs/canvas';
import { writeFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, resolve } from 'node:path';

const __dirname = dirname(fileURLToPath(import.meta.url));
const MARKERS_DIR = resolve(__dirname, '../public/markers');
const OUT = resolve(__dirname, '../public/targets/artisans.mind');

// Thứ tự = targetIndex. Giữ khớp với src/data/artisans.ts.
const MARKERS = [
  'quan-ho-nu.png',  // index 0 — nữ ca Quan họ
  'dong-ho-nam.png', // index 1 — nam tranh Đông Hồ
];

class NodeCompiler extends CompilerBase {
  createProcessCanvas(img) {
    return createCanvas(img.width, img.height);
  }
  // Chép từ OfflineCompiler: trích đặc trưng tracking cho từng ảnh (không đụng canvas).
  compileTrack({ targetImages }) {
    const list = [];
    for (let i = 0; i < targetImages.length; i++) {
      const imageList = buildTrackingImageList(targetImages[i]);
      list.push(extractTrackingFeatures(imageList, () => {}));
    }
    return Promise.resolve(list);
  }
}

const images = [];
for (const name of MARKERS) {
  const img = await loadImage(resolve(MARKERS_DIR, name));
  images.push(img);
  console.log(`• target ${images.length - 1}: ${name} (${img.width}×${img.height})`);
}

const compiler = new NodeCompiler();
console.log('Đang compile (có thể mất 1–2 phút)…');
await compiler.compileImageTargets(images, (p) => {
  process.stdout.write(`\r  tiến độ: ${p.toFixed(1)}%   `);
});
process.stdout.write('\n');

const buffer = compiler.exportData();
writeFileSync(OUT, Buffer.from(buffer));
console.log('✓ Ghi', OUT, `(${(buffer.byteLength / 1024).toFixed(0)} KB, ${MARKERS.length} target)`);
