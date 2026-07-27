// Nén texture GLB cho web: PNG lossless (nặng) -> WebP q90, giới hạn 2048px.
// Hình học GIỮ NGUYÊN (chỉ ~50k tam giác, không cần Draco). Trên điện thoại gần như
// không thấy khác, nhưng dung lượng giảm ~10 lần -> tải nhanh trên 4G.
//
//   node scripts/compress-glb.mjs                 # nén các model CHƯA nén (mặc định)
//   node scripts/compress-glb.mjs a.glb b.glb     # chỉ định file
//
// Nguồn = bản trong public/models/glb (copy từ Assets / artifact-3d-model). Ghi ĐÈ chính
// nó. Bản gốc chất lượng tối đa vẫn nằm ngoài repo-public nên luôn khôi phục lại được.
// CHÚ Ý: chạy lại trên file ĐÃ nén = nén lossy chồng lossy -> chỉ truyền tên file mới.
import { NodeIO } from '@gltf-transform/core';
import { ALL_EXTENSIONS } from '@gltf-transform/extensions';
import { textureCompress } from '@gltf-transform/functions';
import sharp from 'sharp';
import { fileURLToPath } from 'node:url';
import { dirname, resolve } from 'node:path';
import { statSync } from 'node:fs';

const __dirname = dirname(fileURLToPath(import.meta.url));
const GLB_DIR = resolve(__dirname, '../public/models/glb');

// Mặc định = 3 model di sản mới (PNG 4K thô). quan-ho-*/ong-do đã nén từ trước.
const DEFAULT_FILES = ['don-ca.glb', 'nha-nhac.glb', 'xoe-thai.glb'];
const FILES = process.argv.slice(2).length ? process.argv.slice(2) : DEFAULT_FILES;
const MAX_SIZE = 2048; // cạnh dài tối đa của texture
const QUALITY = 90;    // WebP q90 — gần như không thấy mất mát

const io = new NodeIO().registerExtensions(ALL_EXTENSIONS);
const mb = (p) => (statSync(p).size / 1048576).toFixed(1);

for (const name of FILES) {
  const path = resolve(GLB_DIR, name);
  const before = mb(path);
  const doc = await io.read(path);
  await doc.transform(
    textureCompress({
      encoder: sharp,
      targetFormat: 'webp',
      quality: QUALITY,
      resize: [MAX_SIZE, MAX_SIZE], // thu nhỏ nếu lớn hơn, giữ tỉ lệ
    }),
  );
  await io.write(path, doc);
  console.log(`✓ ${name}: ${before} MB -> ${mb(path)} MB`);
}
console.log('Xong. Texture đã sang WebP 2K, hình học giữ nguyên.');
