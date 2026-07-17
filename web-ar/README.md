# ARtifact VAIC — Web AR (MindAR + Next.js)

Web app AR: quét **ảnh mốc (QR + hoa văn)** → hiện **model 3D nghệ nhân** neo lên ảnh.
Không cần cài app, chạy cả **iOS Safari** lẫn Android Chrome (MindAR dùng computer-vision, không cần WebXR).

> Kế hoạch tổng thể: `../WEB-AR-MIGRATION-PLAN.md`. Kiến trúc Unity cũ giữ trong repo cha làm tham chiếu (GĐ2 AI).

## Công nghệ
- **Next.js 16** (App Router, TypeScript, Turbopack) + **Tailwind CSS 4**
- **MindAR** (`mind-ar` image-tracking) + **three.js** (`three@0.160`)
- Hosting: Vercel/Netlify (HTTPS bắt buộc để mở camera)

## Chạy dev
```bash
npm install                 # (đã cài) — nếu cần: npm install --ignore-scripts
npm run dev                 # http://localhost:3000  (camera OK trên localhost)
```

Test trên **điện thoại thật** cần HTTPS:
```bash
npm run dev:https           # next dev --experimental-https, mở qua IP máy tính
# hoặc dùng ngrok trỏ tới :3000
```

## Build / chạy production
```bash
npm run build
npm run start
```

## Cấu trúc
```
public/
  targets/   # .mind đã compile (sample-card.mind)
  models/    # model 3D .glb (sample.glb — Duck mẫu Phase 0)
  markers/   # ảnh QR+hoa văn để in (sample-card.png)
src/
  app/
    page.tsx              # landing: danh sách nghệ nhân
    ar/[slug]/page.tsx    # trang AR mỗi nghệ nhân (server) -> ARSceneClient (ssr:false)
    api/artisans/route.ts # GET list/detail (mock)
    api/ai/route.ts       # POST — STUB GĐ2 (nối LLM sau)
  features/ar/
    ARScene.tsx           # core UI: hỗ trợ trình duyệt, start-gesture, HUD
    ARSceneClient.tsx     # wrapper dynamic(ssr:false) — chỉ đây được tắt SSR
    useMindAR.ts          # lifecycle MindAR: start/stop/dispose, trạng thái tracking
    modelLoader.ts        # load + cache .glb (Draco), fallback placeholder
    arConfig.ts           # slug -> ARTarget
  components/             # Loading, CameraPermission, UnsupportedBrowser, ARHud
  lib/                    # types.ts, api-client.ts (đổi backend chỉ sửa ở đây)
  data/artisans.ts        # dữ liệu seed (nguồn duy nhất, cũng dùng cho /api)
  types/mind-ar.d.ts      # khai báo type cho mind-ar
```

## Nguyên tắc phân lớp
UI → `lib/api-client` → route `/api/*` → (giờ) `data/artisans` → (sau) DB/AI thật.
Đổi nguồn dữ liệu chỉ sửa `api-client` + route + `data`, **không đụng** tầng AR.
(Server Component đọc thẳng `data/artisans`; Client Component/GĐ2 dùng `api-client` qua HTTP.)

## Thêm một nghệ nhân
1. Thiết kế card **QR (trỏ `…/ar/<slug>`) + hoa văn nhiều chi tiết**; để bản in vào `public/markers/`.
2. Compile ảnh card → `.mind` bằng [MindAR Compiler](https://hiukim.github.io/mind-ar-js-doc/tools/compile), lưu `public/targets/<slug>.mind`.
3. Bỏ model `public/models/<slug>.glb` (nén Draco, < 5MB).
4. Thêm entry vào `src/data/artisans.ts` (slug, target/model URL, `scale`, `offset` đủ để model **không che QR**).

## Ghi chú kỹ thuật (gotcha)
- Mọi thứ AR chỉ chạy client: `ARSceneClient` dùng `dynamic(ssr:false)`; `useMindAR` **import động** mind-ar/three trong effect.
- `useMindAR` **stop + dispose** khi unmount → tránh treo camera / memory leak.
- `next.config.ts` stub `fs`/`path` về `empty-module.js` cho browser (mind-ar/tfjs có nhánh Node).
- `three` ghim `0.160.x` khớp peer `mind-ar` — không nâng tuỳ tiện.
- iOS: cần **user gesture** để mở camera (nút "Bắt đầu quét AR") + `viewport-fit=cover`.
- Dep native `canvas` của mind-ar (chỉ dùng phía Node) không build với Node mới → cài `--ignore-scripts`, không ảnh hưởng browser.

## Lộ trình
- **Phase 0** ✅ scaffold + asset mẫu chạy được — cần cầm điện thoại thật kiểm chứng tracking.
- **Phase 1–4**: card + model thật từng nghệ nhân, routing, data layer, hoàn thiện UX.
- **Phase 5**: nối GĐ2 — `api/ai` gọi LLM thật, `ARHud` thêm khung chat. Không đụng tầng AR.
