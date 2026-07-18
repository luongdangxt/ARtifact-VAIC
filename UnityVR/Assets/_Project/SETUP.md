# ARtifact VAIC — Hướng dẫn dựng scene AR (Giai đoạn 1)

Code (asmdef + script) đã tạo sẵn trong `Assets/_Project/Scripts/`. Các bước dưới đây làm
**trong Unity Editor** để dựng scene, assets và cấu hình build — những thứ không nên tạo bằng
tay ngoài Editor.

Kiến trúc module (7 assembly, phụ thuộc một chiều):
`Core` ← `Heritage`, `Avatar`, `Conversation`, `UI` ← `AR` / `App` (App = composition root).

---

## 0. Sau khi mở project
Unity sẽ tự tải các package AR đã thêm vào `Packages/manifest.json`:
`com.unity.xr.arfoundation`, `com.unity.xr.arcore`, `com.unity.xr.simulation`.

- Mở **Window → Package Manager**, nếu có bản mới hơn 6.0.5 tương thích Unity 6.3 thì cập nhật.
- Kiểm tra **Console** không còn lỗi biên dịch → 7 asmdef đã resolve.

## 1. XR Plug-in Management
**Edit → Project Settings → XR Plug-in Management**
- Cài (nếu được hỏi), rồi ở tab **Android** tick **ARCore** (Google ARCore XR Plugin).
- Tab **PC/Standalone** hoặc mục XR Simulation: bật **XR Simulation** để test trong Editor.

## 2. Player Settings (Android / ARCore)
**Project Settings → Player → Android**
- **Minimum API Level**: 24 trở lên.
- **Scripting Backend**: IL2CPP; **Target Architectures**: chỉ **ARM64**.
- **Graphics APIs**: bỏ Auto, để **OpenGLES3** (và/hoặc Vulkan).
- **Project Settings → XR Plug-in Management → ARCore**: đặt ARCore **Required**.
- Cấp quyền **Camera** (AR Foundation tự thêm khi build; kiểm tra lại manifest sau build đầu).

## 3. Tạo XRReferenceImageLibrary (thư viện marker)
1. Trong `Assets/_Project/Data/`, chuột phải → **Create → XR → Reference Image Library**.
   Đặt tên `ArtisanImageLibrary`.
2. **Add Image** cho từng ảnh nghệ nhân / mã QR sẽ dán ngoài thực tế.
3. **Quan trọng**: đặt **Name** của mỗi image TRÙNG với `Reference Image Name` khai trong asset
   `HeritageArtisan` tương ứng (vd `ca-tru-marker`).
4. Tick **Keep Texture at Runtime** nếu cần; nhập **Physical Size** (mét) đúng kích thước in thật
   để tracking chuẩn.

## 4. Tạo dữ liệu nghệ nhân (ScriptableObject)
1. Chuột phải trong `Assets/_Project/Data/` → **Create → ARtifact → Heritage Artisan**.
   - `Id`: kebab-case, vd `ca-tru`.
   - `Display Name`: vd `Nghệ nhân Ca trù`.
   - `Reference Image Name`: TRÙNG tên image ở bước 3, vd `ca-tru-marker`.
   - `Prefab`: gán prefab model (bước 5).
   - `Description`: mô tả di sản (dùng cho AI sau này).
2. Chuột phải → **Create → ARtifact → Artisan Catalog** (đặt `ArtisanCatalog`).
   Kéo tất cả asset `HeritageArtisan` vào danh sách `Artisans`.

## 5. Prefab model nghệ nhân (placeholder tới khi có model thật)
1. Tạo GameObject tạm (vd Capsule) trong scene, thêm component **ArtisanView**
   (script `ARtifact.Avatar`). Nếu có Animator idle thì gán vào `Animator`.
2. Kéo vào `Assets/_Project/Prefabs/` để thành prefab `Artisan_Placeholder`, xoá khỏi scene.
3. Gán prefab này vào field `Prefab` của asset `HeritageArtisan`.
   → Khi có model humanoid thật, chỉ cần thay prefab, không sửa code.

## 6. Dựng scene `ARtifact.unity`
Tạo scene mới trong `Assets/_Project/Scenes/ARtifact.unity`. Xoá `Main Camera` mặc định.

Dùng menu **GameObject → XR** để tạo đúng rig AR:
- **XR → AR Session** → object `AR Session`.
- **XR → XR Origin (AR)** → tạo `XR Origin` + `Camera Offset` + `Main Camera`
  (đã có `ARCameraManager`, `ARCameraBackground`, `TrackedPoseDriver`).

Trên **XR Origin**, thêm component **AR Tracked Image Manager**:
- `Serialized Library` = `ArtisanImageLibrary` (bước 3).
- `Max Number Of Moving Images` = số marker đồng thời cần theo dõi.
- **Tracked Image Prefab**: để TRỐNG (spawner của ta tự tạo model, không dùng prefab mặc định).

Hierarchy mục tiêu (đặt tên rõ ràng theo nhóm):
```
ARtifact (scene)
├── [AR] AR Session              (ARSession + ARSessionController)
├── [AR] XR Origin               (ARTrackedImageManager)
│   └── Camera Offset
│       └── Main Camera          (ARCameraManager, ARCameraBackground, TrackedPoseDriver)
├── [App] Bootstrap              (AppBootstrap)
├── [Managers] Services          (ImageTrackingService + ArtisanSpawner)
├── [UI] Canvas                  (rỗng — giai đoạn sau)
└── [Runtime] Spawned Artisans   (node cha cho model spawn ra)
```

## 7. Gắn & nối component (wiring)
- `[AR] AR Session`: thêm **ARSessionController**, field `Session` = ARSession trên chính nó.
- `[Managers] Services`: thêm **ArtisanSpawner** và **ImageTrackingService**.
  - ArtisanSpawner → `Spawn Root` = `[Runtime] Spawned Artisans`.
  - ImageTrackingService → `Tracked Image Manager` = component trên XR Origin;
    `Spawner` = ArtisanSpawner vừa thêm.
- `[App] Bootstrap`: thêm **AppBootstrap**, gán:
  - `Catalog` = `ArtisanCatalog`.
  - `Session Controller` = ARSessionController.
  - `Image Tracking Service` = ImageTrackingService.
  - `AR Camera` = Main Camera (hoặc để trống → tự lấy Camera.main; nhớ tag Main Camera là
    `MainCamera`).
- **File → Build Settings**: thêm `ARtifact.unity`, đưa lên đầu Scenes In Build.

---

## Kiểm chứng (Verification)
1. **Compile**: Console không lỗi; mở từng `.asmdef` xem đồ thị references đúng, không vòng lặp.
2. **Editor Play (XR Simulation)**: bật XR Simulation, chọn môi trường mô phỏng có ảnh marker
   (Window → XR → AR Foundation → XR Environment). Nhấn Play, di chuyển camera tới ảnh →
   model placeholder xuất hiện, bám marker, ẩn khi mất tracking. Xem log `ArtisanAppearedEvent`.
3. **Build Android**: build APK, chạy trên máy có ARCore, quét ảnh/QR in thật → model hiện đúng vị trí.
4. **Chỗ cắm AI**: `AppBootstrap.Conversation` đã khởi tạo (OfflineLLMClient). Giai đoạn sau
   thay bằng `BackendLLMClient : ILLMClient` gọi API — không đụng module khác.
