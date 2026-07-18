// Sinh ẢNH MỐC TẠM (temporary markers) nhiều feature để MindAR bám tốt.
// Dùng khi CHƯA có ảnh mốc chính thức. Mỗi ảnh là 1 pattern hình học ngẫu-nhiên-tất-định
// (seed cố định) + nhãn chữ để phân biệt. Khi có ảnh thật: bỏ file này, thay PNG trong
// public/markers rồi chạy lại compile-targets.mjs.
//
//   node scripts/gen-temp-markers.mjs
//
import { createCanvas } from '@napi-rs/canvas';
import { writeFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, resolve } from 'node:path';

const __dirname = dirname(fileURLToPath(import.meta.url));
const OUT = resolve(__dirname, '../public/markers');

// PRNG tất định (mulberry32) để marker luôn giống nhau giữa các lần chạy.
function rng(seed) {
  let a = seed >>> 0;
  return () => {
    a |= 0; a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

const PALETTE = ['#e63946', '#f1a208', '#2a9d8f', '#264653', '#8338ec', '#3a86ff', '#fb5607'];

// Vẽ nhiều hình khối tương phản -> nhiều góc/cạnh cho MindAR (feature detection thích điều này).
function drawMarker({ size, seed, label, bg }) {
  const c = createCanvas(size, size);
  const ctx = c.getContext('2d');
  const rand = rng(seed);

  ctx.fillStyle = bg;
  ctx.fillRect(0, 0, size, size);

  const N = 90;
  for (let i = 0; i < N; i++) {
    ctx.save();
    ctx.translate(rand() * size, rand() * size);
    ctx.rotate(rand() * Math.PI * 2);
    ctx.fillStyle = PALETTE[Math.floor(rand() * PALETTE.length)];
    ctx.globalAlpha = 0.55 + rand() * 0.45;
    const s = size * (0.04 + rand() * 0.12);
    const kind = Math.floor(rand() * 3);
    if (kind === 0) {
      ctx.fillRect(-s / 2, -s / 2, s, s);
    } else if (kind === 1) {
      ctx.beginPath();
      ctx.arc(0, 0, s / 2, 0, Math.PI * 2);
      ctx.fill();
    } else {
      ctx.beginPath();
      ctx.moveTo(-s / 2, s / 2);
      ctx.lineTo(s / 2, s / 2);
      ctx.lineTo(0, -s / 2);
      ctx.closePath();
      ctx.fill();
    }
    ctx.restore();
  }

  // Khung + nhãn để người in/quét phân biệt được 2 mốc.
  ctx.globalAlpha = 1;
  ctx.lineWidth = size * 0.02;
  ctx.strokeStyle = '#111';
  ctx.strokeRect(ctx.lineWidth / 2, ctx.lineWidth / 2, size - ctx.lineWidth, size - ctx.lineWidth);

  const bar = size * 0.16;
  ctx.fillStyle = 'rgba(17,17,17,0.85)';
  ctx.fillRect(0, size - bar, size, bar);
  ctx.fillStyle = '#fff';
  ctx.font = `bold ${Math.floor(bar * 0.42)}px Sans`;
  ctx.textAlign = 'center';
  ctx.textBaseline = 'middle';
  ctx.fillText(label, size / 2, size - bar / 2);

  return c;
}

const markers = [
  { file: 'quan-ho-nu.png', seed: 20260718, label: 'QUAN HO — NU (TAM)', bg: '#fff4e6' },
  { file: 'dong-ho-nam.png', seed: 99887766, label: 'DONG HO — NAM (TAM)', bg: '#e6f4ff' },
];

for (const m of markers) {
  const canvas = drawMarker({ size: 900, seed: m.seed, label: m.label, bg: m.bg });
  writeFileSync(resolve(OUT, m.file), canvas.toBuffer('image/png'));
  console.log('✓ marker:', m.file);
}
console.log('Xong. Tiếp: node scripts/compile-targets.mjs');
