'use client';

import { useEffect, useMemo, useRef, useState } from 'react';
import type { MindARThree } from 'mind-ar/dist/mindar-image-three.prod.js';
import type { Artisan } from '@/lib/types';
import { loadModel, cloneModel, normalizeModel } from './modelLoader';

export type ARStatus =
  | 'idle'
  | 'loading'      // đang tải model + khởi tạo MindAR
  | 'starting'     // đang xin quyền + mở camera
  | 'scanning'     // camera chạy, chưa thấy mốc
  | 'tracking'     // đang thấy mốc, model hiển thị
  | 'denied'       // bị từ chối quyền camera
  | 'error';

interface Options {
  /** Danh sách nghệ nhân — mỗi người 1 targetIndex trong file .mind gộp */
  artisans: Artisan[];
  /** Đường dẫn file .mind GỘP dùng chung cho mọi target */
  targetSrc: string;
  /** bật/tắt AR (vd chỉ start sau khi user bấm nút — cần user gesture cho iOS) */
  active: boolean;
}

// Kiểu runtime nội bộ của MindARThree — bundle prod không export field .video/.controller
// nhưng chúng tồn tại lúc chạy; khai báo tối thiểu để teardown an toàn (không dùng any lung tung).
type MindARRuntime = MindARThree & {
  video?: HTMLVideoElement & { srcObject?: MediaStream | null };
  controller?: { stopProcessVideo?: () => void };
  renderer: MindARThree['renderer'] & { forceContextLoss?: () => void };
  resize?: () => void; // tính lại kích thước video + fov theo container
};

// Giải phóng TRIỆT ĐỂ: camera track + <video> + WebGL context (three + TF.js).
// Phải chạy được cả khi React cleanup KHÔNG chạy (reload / bfcache trên iOS Safari),
// nên viết null-safe và không phụ thuộc mindar.stop() (stop() ném lỗi nếu srcObject đã null).
function teardownMindAR(m: MindARRuntime | null) {
  if (!m) return;
  try { m.renderer?.setAnimationLoop(null); } catch { /* noop */ }
  try { m.controller?.stopProcessVideo?.(); } catch { /* noop */ }
  try {
    const v = m.video;
    const stream = v?.srcObject;
    if (stream && typeof stream.getTracks === 'function') {
      stream.getTracks().forEach((t) => t.stop()); // trả camera lại cho iOS
    }
    if (v) {
      try { v.pause(); } catch { /* noop */ }
      v.srcObject = null;
      v.remove();
    }
  } catch { /* noop */ }
  // forceContextLoss giải phóng GPU context ngay (dispose() thôi không đủ trên iOS)
  const canvas = m.renderer?.domElement;
  try { m.renderer?.forceContextLoss?.(); } catch { /* noop */ }
  try { m.renderer?.dispose(); } catch { /* noop */ }
  // gỡ <canvas> khỏi container, nếu không mỗi lần restart để lại canvas mồ côi
  try { canvas?.remove(); } catch { /* noop */ }
}

// Khởi tạo MindAR + three, gắn anchor, chạy render loop. Model tải THEO TARGET.
// ĐA TARGET: 1 file .mind gộp, mỗi nghệ nhân 1 anchor theo targetIndex. Chĩa vào
// ảnh nào thì anchor đó onTargetFound -> đặt activeIndex = nghệ nhân tương ứng.
// Dọn dẹp (stop camera + dispose) khi rời trang / active=false để tránh treo camera & memory leak.
export function useMindAR({ artisans, targetSrc, active }: Options) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [status, setStatus] = useState<ARStatus>('idle');
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  // targetIndex của nghệ nhân đang được camera thấy (null = chưa thấy ai)
  const [activeIndex, setActiveIndex] = useState<number | null>(null);
  // slug của những nghệ nhân đã tải xong model. Model tải LƯỜI (lúc thấy ảnh mốc)
  // nên phải biết ai đã sẵn sàng để HUD báo "đang tải" đúng người.
  const [loadedSlugs, setLoadedSlugs] = useState<string[]>([]);

  // giữ instance để listener pagehide có thể teardown ngay
  const mindarRef = useRef<MindARRuntime | null>(null);

  // Nghệ nhân đang hiển thị — suy từ activeIndex để HUD dùng đúng dữ liệu.
  const activeArtisan = useMemo(
    () => (activeIndex == null ? null : artisans.find((a) => a.targetIndex === activeIndex) ?? null),
    [activeIndex, artisans],
  );

  useEffect(() => {
    if (!active) return;
    const container = containerRef.current;
    if (!container) return;

    let cancelled = false;
    let orientCleanup: (() => void) | null = null;

    // CHỈ giải phóng khi rời trang THẬT (reload / back / đóng tab): pagehide fire tin cậy
    // trên cả iOS & Android và KHÔNG fire khi hộp thoại xin quyền camera bật lên.
    // (Trước đây dùng visibilitychange -> nó fire lúc xin quyền -> teardown giữa chừng ->
    //  gỡ mất thẻ <video> -> camera đen. Bỏ hẳn.)
    const releaseOnHide = () => {
      teardownMindAR(mindarRef.current);
    };
    window.addEventListener('pagehide', releaseOnHide);

    (async () => {
      try {
        setStatus('loading');
        setErrorMsg(null);

        // import động: mind-ar chỉ chạy client, tránh SSR đụng window/document.
        // KHÔNG preload model ở đây: mỗi nhân vật ~3MB, tải sẵn cả bộ là bắt du khách
        // chờ ~15MB trước khi camera bật, trong khi một lượt quét thường chỉ gặp 1-2
        // ảnh mốc. Model tải khi anchor tương ứng thấy ảnh mốc (xem ensureModel).
        const [{ MindARThree }, THREE] = await Promise.all([
          import('mind-ar/dist/mindar-image-three.prod.js'),
          import('three'),
        ]);
        if (cancelled) return;

        const mindar = new MindARThree({
          container,
          imageTargetSrc: targetSrc, // file .mind GỘP chứa mọi ảnh mốc
          uiScanning: false, // tự làm HUD hint
          uiLoading: false,
        }) as MindARRuntime;
        mindarRef.current = mindar;

        const { renderer, scene, camera } = mindar;

        // MindAR đặt cứng pixelRatio = devicePixelRatio (iPhone = 3) và bật MSAA. Màn
        // 375×812 hoá ra 1125×2436 = 2,7 triệu điểm ảnh MỖI KHUNG, 60 khung/giây, chạy
        // song song với vòng nhận diện ảnh của TF.js -> máy nóng ran sau vài phút. Hạ
        // trần xuống 2 là bớt ~55% việc cho GPU. KHÔNG ảnh hưởng độ nét hình camera:
        // <video> là thẻ riêng do trình duyệt vẽ ở độ phân giải gốc, pixelRatio này chỉ
        // áp cho lớp 3D. resize() của MindAR chỉ gọi setSize (không đụng setPixelRatio)
        // nên trần này giữ nguyên qua mọi lần xoay/đổi kích thước sau đó.
        renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));

        // ánh sáng để model glb hiển thị đúng
        const hemi = new THREE.HemisphereLight(0xffffff, 0x444444, 1.2);
        const dir = new THREE.DirectionalLight(0xffffff, 1.0);
        dir.position.set(0.5, 1, 1);
        scene.add(hemi, dir);

        // AnimationMixer cho model có rig (vd Mixamo). Ghép mixer với ĐÚNG anchor của
        // nó: render loop chỉ cập nhật nhân vật đang hiện, chứ tính lại xương cho cả 3
        // nghệ nhân trong khi 2 người kia vô hình thì phí (mỗi rig 33-41 xương, ~100
        // kênh animation, chạy 60 lần/giây).
        const rigs: { group: THREE.Object3D; mixer: THREE.AnimationMixer | null }[] = [];
        const clock = new THREE.Clock();

        // Mỗi nghệ nhân 1 anchor tại targetIndex của mình; chĩa ảnh nào -> hiện người đó.
        // Anchor tạo NGAY (chỉ là Group rỗng, không tốn gì) để MindAR có chỗ ghi ma trận
        // tư thế; model được nhét vào group này sau, lúc nào tải xong cũng được.
        artisans.forEach((artisan) => {
          const anchor = mindar.addAnchor(artisan.targetIndex);
          // MindAR bật/tắt group.visible theo kết quả nhận diện -> dùng luôn nó làm cờ
          // "nhân vật này có đang trên màn hình không" cho render loop.
          const rig: (typeof rigs)[number] = { group: anchor.group, mixer: null };
          rigs.push(rig);

          // Tải model của RIÊNG nghệ nhân này, chỉ 1 lần dù thấy/mất mốc bao nhiêu lần.
          // `requested` chặn tải chồng; loadModel còn cache theo URL nên lần khởi tạo
          // lại (retry) lấy luôn từ bộ nhớ, không tải mạng nữa.
          let requested = false;
          const ensureModel = () => {
            if (requested) return;
            requested = true;
            loadModel(artisan.ar.modelUrl).then((raw) => {
              // huỷ giữa chừng (rời trang / tắt AR): bỏ, đừng gắn vào scene đã dispose
              if (cancelled) return;

              // clone: raw là instance cache dùng chung; normalizeModel MUTATE nó, nên
              // phải normalize trên BẢN SAO, nếu không lần khởi tạo lại (retry/restart)
              // sẽ normalize lần 2 lên object đã biến đổi -> model biến mất dù vẫn track.
              const clone = cloneModel(raw);

              // Phát animation nếu model có clip. Mixer bind vào bản CLONE (chứa skeleton).
              // PHẢI tạo mixer + pose frame 0 TRƯỚC normalizeModel: animation Mixamo có thể
              // dời tâm nhân vật ra xa gốc (offset baked trong clip), nên normalize phải đo
              // theo POSE THẬT của frame đầu — nếu đo bind-pose thì tâm lệch, sau khi phóng
              // to nhân vật văng khỏi khung -> không thấy gì.
              const clips = raw.userData.clips as THREE.AnimationClip[] | undefined;
              if (clips && clips.length) {
                const idx = artisan.ar.animationIndex ?? 0;
                const clip = clips[idx] ?? clips[0];
                const mixer = new THREE.AnimationMixer(clone);
                mixer.clipAction(clip).play(); // loop mặc định = vô hạn
                mixer.update(0); // đặt skeleton về frame 0 để normalizeModel đo đúng pose
                rig.mixer = mixer;
              }

              const model = normalizeModel(clone, artisan.ar.scale, artisan.ar.offset, {
                rotationDeg: artisan.ar.rotationDeg,
                groundAlign: artisan.ar.groundAlign,
              });
              anchor.group.add(model);
              setLoadedSlugs((s) => (s.includes(artisan.slug) ? s : [...s, artisan.slug]));
            });
          };

          anchor.onTargetFound = () => {
            if (cancelled) return;
            ensureModel(); // lần đầu thấy người này -> mới tải model của người này
            setActiveIndex(artisan.targetIndex);
            setStatus('tracking');
          };
          anchor.onTargetLost = () => {
            if (cancelled) return;
            // chỉ về 'scanning' nếu đúng người đang hiển thị bị mất (maxTrack=1 nên
            // thường chỉ 1 anchor active, nhưng vẫn kiểm tra cho chắc)
            setActiveIndex((cur) => (cur === artisan.targetIndex ? null : cur));
            setStatus((s) => (s === 'tracking' ? 'scanning' : s));
          };
        });

        setStatus('starting');
        await mindar.start(); // mở camera (cần HTTPS / user gesture trên iOS)
        if (cancelled) return;

        setStatus('scanning');
        // Render loop "chỉ vẽ khi có gì để vẽ". Phần lớn thời gian một phiên là đang
        // QUÉT (chưa thấy ảnh mốc): cảnh 3D rỗng tuếch mà vẫn xoá + vẽ lại toàn màn
        // 60 lần/giây thì tốn GPU vô ích — hình camera nằm ở thẻ <video> phía dưới,
        // không phụ thuộc canvas này. `drewLastFrame` để khi vừa mất target thì còn
        // vẽ THÊM một khung rỗng nhằm xoá nhân vật cũ, rồi mới nghỉ hẳn.
        let drewLastFrame = false;
        renderer.setAnimationLoop(() => {
          const delta = clock.getDelta();
          let anyVisible = false;
          for (const r of rigs) {
            if (!r.group.visible) continue;
            anyVisible = true;
            r.mixer?.update(delta);
          }
          if (!anyVisible && !drewLastFrame) return;
          drewLastFrame = anyVisible;
          renderer.render(scene, camera);
        });

        // Giữ fov/model khớp mỗi khi container ĐỔI KÍCH THƯỚC. Video coverage đã do
        // CSS object-cover lo (xem ARScene), còn resize() ở đây chỉ để camera fov +
        // canvas 3D bám theo viewport thật -> model neo đúng khi màn nở/thu.
        // Dùng ResizeObserver + visualViewport thay vì setTimeout cứng: trên iOS
        // Safari container nở ra MUỘN (thanh địa chỉ thu lại) -> phải resize đúng
        // lúc đó, không đoán mốc thời gian được.
        // resize() của MindAR gọi renderer.setSize -> CẤP PHÁT LẠI framebuffer WebGL,
        // rất đắt. Mà trên iOS Safari visualViewport bắn 'scroll'/'resize' liên tục mỗi
        // khi thanh địa chỉ nhúc nhích hay trang nảy rubber-band -> cấp phát lại hàng
        // chục lần/giây cho vui. Vì vậy: gộp về 1 lần/khung hình VÀ bỏ qua nếu kích
        // thước container không đổi thật. `force` cho 2 lần gọi lúc khởi tạo, khi đó
        // <video> chưa có metadata nên resize() thoát sớm và phải chạy lại.
        let lastW = 0;
        let lastH = 0;
        let resizePending = false;
        const forceResize = (force = false) => {
          if (cancelled || resizePending) return;
          resizePending = true;
          requestAnimationFrame(() => {
            resizePending = false;
            if (cancelled) return;
            const w = container.clientWidth;
            const h = container.clientHeight;
            if (!force && w === lastW && h === lastH) return;
            lastW = w;
            lastH = h;
            try { mindar.resize?.(); } catch { /* noop */ }
          });
        };
        forceResize(true);
        setTimeout(() => forceResize(true), 300);

        const ro = new ResizeObserver(() => forceResize());
        ro.observe(container);

        const vv = window.visualViewport;
        const onVV = () => forceResize();
        vv?.addEventListener('resize', onVV);
        vv?.addEventListener('scroll', onVV);

        const onOrient = () => setTimeout(() => forceResize(true), 300);
        window.addEventListener('orientationchange', onOrient);

        orientCleanup = () => {
          ro.disconnect();
          vv?.removeEventListener('resize', onVV);
          vv?.removeEventListener('scroll', onVV);
          window.removeEventListener('orientationchange', onOrient);
        };
      } catch (err) {
        if (cancelled) return;
        console.error('[useMindAR] lỗi khởi tạo AR:', err);
        const name = (err as { name?: string })?.name;
        if (name === 'NotAllowedError' || name === 'SecurityError') {
          setStatus('denied');
        } else {
          setStatus('error');
          setErrorMsg((err as Error)?.message ?? 'Lỗi không xác định');
        }
      }
    })();

    return () => {
      cancelled = true;
      orientCleanup?.();
      window.removeEventListener('pagehide', releaseOnHide);
      teardownMindAR(mindarRef.current);
      mindarRef.current = null;
      setActiveIndex(null);
      // scene cũ đã dispose -> mọi model phải gắn lại vào anchor mới ở lần khởi tạo sau
      setLoadedSlugs([]);
    };
  }, [active, targetSrc, artisans]);

  return {
    containerRef,
    status,
    errorMsg,
    activeArtisan,
    // Đã thấy ảnh mốc nhưng model của người đó còn đang tải -> HUD báo cho du khách
    // biết là đang chờ chứ không phải quét hụt.
    modelLoading: activeArtisan != null && !loadedSlugs.includes(activeArtisan.slug),
  };
}
