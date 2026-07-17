# Kế hoạch chuyển ARtifact VAIC sang Web AR (MindAR)

> Mục tiêu: bỏ app Unity phải-cài, chuyển sang **web app AR** — quét là chạy, không cài gì.
> Chức năng giữ nguyên: quét **ảnh mốc (QR + hoa văn nền)** → hiện **model 3D nghệ nhân** neo lên ảnh.
> GĐ2 (AI trả lời qua backend) giữ nguyên định hướng, chỉ đổi client từ Unity sang web.

---

## 0. Quyết định công nghệ (đã chốt)

| Hạng mục | Chọn | Lý do |
|---|---|---|
| Tracking | **MindAR** (image target) | Miễn phí, OSS, computer-vision → **chạy cả iOS Safari** (WebXR thì không) |
| Render 3D | **three.js** | MindAR tích hợp sẵn `mindar-image-three` |
| Framework | **Next.js (App Router) + TypeScript** | Routing mỗi nghệ nhân 1 URL + có sẵn API routes cho GĐ2 + deploy HTTPS dễ |
| UI | **Tailwind CSS** | Nhanh, nhẹ |
| Model 3D | **.glb** (glTF nhị phân, nén Draco) | Chuẩn web, nhẹ |
| Hosting | **Vercel** (hoặc Netlify) | HTTPS sẵn — BẮT BUỘC để mở camera trên mobile |

**Marker = một tấm card duy nhất:** QR ở giữa (chứa URL `…/ar/<slug>`) + viền/hoa văn phong phú xung quanh để MindAR bám. Model 3D đặt NỔI PHÍA TRÊN card để không che QR.

Ràng buộc phải nhớ:
- **Camera chỉ chạy trên HTTPS** (hoặc `localhost`). Dev mobile thật → dùng `next dev --experimental-https` hoặc ngrok.
- **iOS Safari**: `<video playsinline>` bắt buộc; xin quyền camera cần user gesture. MindAR xử lý phần lớn.
- **Next.js SSR**: MindAR + three chỉ chạy client → phải `dynamic(() => …, { ssr: false })`, mọi file AR để `'use client'`.
- **QR trắng trơn track kém** → luôn bọc QR trong hoa văn nhiều chi tiết; kiểm tra feature points bằng công cụ compile của MindAR.

---

## 1. Cài thư viện từ đầu

```bash
# tạo project (repo/thư mục MỚI, tách khỏi Unity)
npx create-next-app@latest web-ar --typescript --tailwind --app --src-dir --eslint
cd web-ar

# core AR
npm install three mind-ar

# tiện ích (tùy chọn, cho mở rộng)
npm install zustand            # state client nhẹ (chọn nghệ nhân, trạng thái AR)
npm install @types/three -D
```

> ⚠️ **Kiểm tra version tương thích**: `mind-ar` ghim một range `three` nhất định. Chạy `npm info mind-ar peerDependencies` và ghim `three` cho khớp, tránh lỗi runtime (`GLTFLoader`/`camera` lệch API). Nếu lỗi, hạ/nâng `three` theo peer của `mind-ar`.

Import chính (kiểm tra lại theo version thực tế):
```ts
import { MindARThree } from 'mind-ar/dist/mindar-image-three.prod.js';
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js';
```

---

## 2. Compile ảnh mốc → file `.mind`

1. Vào công cụ web: MindAR Image Target Compiler (`hiukim.github.io/mind-ar-js-doc/tools/compile`).
2. Kéo ảnh card (QR + hoa văn) vào → xem **feature points** (càng nhiều, phân bố đều càng tốt).
3. Export ra `targets.mind`.
4. **Chiến lược file** (khuyên dùng): **mỗi nghệ nhân 1 file `.mind` riêng** (`nghe-nhan-01.mind`) đặt trong `public/targets/`. Trang `[slug]` chỉ load target của nghệ nhân đó → nhẹ, độc lập, dễ mở rộng. (Có thể gộp nhiều ảnh vào 1 `.mind` đa-target nếu sau này cần quét nhiều mốc cùng lúc.)

---

## 3. Cấu trúc code (chừa sẵn chỗ cho API & mở rộng)

```
web-ar/
├─ public/
│  ├─ targets/            # file .mind đã compile
│  │  └─ nghe-nhan-01.mind
│  ├─ models/             # model 3D
│  │  └─ nghe-nhan-01.glb
│  └─ markers/            # file in ảnh QR+hoa văn (png/pdf) để đem đi in
├─ src/
│  ├─ app/
│  │  ├─ layout.tsx
│  │  ├─ page.tsx                 # landing / danh sách nghệ nhân
│  │  ├─ ar/
│  │  │  └─ [slug]/page.tsx       # trang AR từng nghệ nhân (import ARScene ssr:false)
│  │  └─ api/
│  │     ├─ artisans/route.ts     # GET danh sách/chi tiết (giờ trả mock, sau nối DB)
│  │     └─ ai/route.ts           # ⬅️ CHỪA CHỖ GĐ2: nhận câu hỏi → gọi LLM backend
│  ├─ features/
│  │  └─ ar/
│  │     ├─ ARScene.tsx           # 'use client' — core: MindAR + three + render loop
│  │     ├─ useMindAR.ts          # hook khởi tạo/dọn dẹp (start/stop, xử lý unmount)
│  │     ├─ modelLoader.ts        # load + cache .glb qua GLTFLoader
│  │     └─ arConfig.ts           # map slug → { targetUrl, modelUrl, scale, offset }
│  ├─ components/
│  │  ├─ Loading.tsx
│  │  ├─ CameraPermission.tsx     # xin quyền + hướng dẫn khi bị từ chối
│  │  ├─ UnsupportedBrowser.tsx   # fallback trình duyệt không hỗ trợ
│  │  └─ ARHud.tsx                # overlay: hint "chĩa vào ảnh", nút hỏi AI (GĐ2)
│  ├─ lib/
│  │  ├─ api-client.ts            # fetch wrapper → /api/* (đổi sang backend thật = sửa 1 chỗ)
│  │  └─ types.ts                 # Artisan, ARTarget, ChatMessage…
│  └─ data/
│     └─ artisans.ts              # dữ liệu seed tạm trước khi có DB
├─ .env.local                     # API_BASE_URL, NEXT_PUBLIC_SITE_URL…
├─ next.config.js
└─ README.md
```

**Nguyên tắc phân lớp** (để thay API dễ): UI/feature → `lib/api-client` → (giờ) route `/api/*` trả mock từ `data/` → (sau) backend/DB/AI thật. Đổi nguồn dữ liệu **chỉ sửa `api-client` + route**, không đụng component AR.

**Kiểu dữ liệu gợi ý (`lib/types.ts`):**
```ts
export interface Artisan {
  slug: string;          // 'nghe-nhan-01' — dùng trong URL & QR
  name: string;
  craft: string;         // nghề/di sản
  bio: string;
  ar: ARTarget;
  aiEnabled: boolean;    // bật hỏi-đáp AI (GĐ2)
}
export interface ARTarget {
  targetUrl: string;     // '/targets/nghe-nhan-01.mind'
  modelUrl: string;      // '/models/nghe-nhan-01.glb'
  scale: number;
  offset: [number, number, number];  // đẩy model nổi lên trên QR
}
```

---

## 4. Lộ trình thực thi theo phase

**Phase 0 — Spike/kiểm chứng (quan trọng nhất, làm trước khi cam kết)**
- Dựng 1 trang tối giản: 1 ảnh mẫu + 1 `.glb` mẫu, MindAR track → model xoay nhẹ.
- Deploy Vercel, cầm điện thoại (cả Android + iPhone) thử tracking THẬT.
- ✅ Tiêu chí: model bám ổn định, không giật/mất khi nghiêng camera → mới đi tiếp.

**Phase 1 — Một nghệ nhân end-to-end**
- `ARScene.tsx` + `useMindAR` + `modelLoader` hoàn chỉnh, có Loading + xin quyền camera.
- Model neo đúng, đặt offset nổi trên QR.
- QR trỏ tới `…/ar/nghe-nhan-01`.

**Phase 2 — Nhiều nghệ nhân + routing + marker thật**
- Route `ar/[slug]`, `arConfig` map slug → target/model.
- Thiết kế bộ card **QR + hoa văn** cho từng nghệ nhân, compile `.mind`, để `public/markers/` bản in.
- Trang landing `page.tsx` liệt kê nghệ nhân.

**Phase 3 — Lớp dữ liệu + API mock**
- `data/artisans.ts` seed, `/api/artisans` trả về, `api-client` fetch.
- Component đọc qua `api-client` (không hardcode).

**Phase 4 — Hoàn thiện UX**
- Xử lý mất tracking (hint "chĩa lại vào ảnh"), lỗi quyền camera, fallback trình duyệt cũ/không hỗ trợ.
- Tối ưu model: nén Draco, giữ `.glb` < 5MB; lazy-load target.

**Phase 5 — Nối GĐ2 (AI)**
- `/api/ai/route.ts` từ stub → gọi backend LLM thật (biến môi trường `API_BASE_URL`).
- `ARHud` thêm nút hỏi/khung chat; hiển thị câu trả lời cạnh model.
- **Không đụng** tầng AR — chỉ thêm ở HUD + api-client.

**Tương lai (chừa sẵn):**
- CMS/DB cho nội dung nghệ nhân (thay `data/artisans.ts`).
- Analytics (đếm lượt quét mỗi mốc).
- i18n (Việt/Anh).
- Voice input/output cho hỏi-đáp.
- Nhiều mốc/1 khung hình (gộp `.mind` đa-target).

---

## 5. Checklist "gotcha" dán lên tường

- [ ] Mọi file AR: `'use client'` + import qua `dynamic(..., { ssr:false })`.
- [ ] Ghim version `three` khớp peer của `mind-ar`.
- [ ] `<video playsinline>` cho iOS; start camera sau user gesture.
- [ ] Test trên **HTTPS thật** + **iPhone Safari** sớm (đừng chỉ test Chrome desktop).
- [ ] `useMindAR` phải **stop + dispose** khi rời trang (tránh camera treo, memory leak).
- [ ] QR nằm trong hoa văn nhiều chi tiết; kiểm feature points khi compile.
- [ ] Model offset đủ để **không che QR**.
- [ ] `.glb` nén Draco, kiểm tổng dung lượng tải trang.

---

## 6. Việc đầu tiên khi mở section mới

1. Xác nhận đã có **model `.glb`** nghệ nhân chưa (nếu chưa → dùng model mẫu để chạy Phase 0).
2. Chạy mục **1. Cài thư viện** ở trên.
3. Làm **Phase 0** trước — kiểm chứng tracking trên điện thoại thật rồi mới xây tiếp.

> Kiến trúc Unity cũ vẫn giữ trong repo làm tham chiếu (7 asmdef, ILLMClient/backend GĐ2 — logic domain có thể port ý tưởng sang web).
