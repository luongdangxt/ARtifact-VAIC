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

// Khởi tạo MindAR + three, load model, gắn anchor, chạy render loop.
// ĐA TARGET: 1 file .mind gộp, mỗi nghệ nhân 1 anchor theo targetIndex. Chĩa vào
// ảnh nào thì anchor đó onTargetFound -> đặt activeIndex = nghệ nhân tương ứng.
// Dọn dẹp (stop camera + dispose) khi rời trang / active=false để tránh treo camera & memory leak.
export function useMindAR({ artisans, targetSrc, active }: Options) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [status, setStatus] = useState<ARStatus>('idle');
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  // targetIndex của nghệ nhân đang được camera thấy (null = chưa thấy ai)
  const [activeIndex, setActiveIndex] = useState<number | null>(null);

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
        // Preload model của TẤT CẢ nghệ nhân song song (theo thứ tự artisans[]).
        const [{ MindARThree }, THREE, ...rawModels] = await Promise.all([
          import('mind-ar/dist/mindar-image-three.prod.js'),
          import('three'),
          ...artisans.map((a) => loadModel(a.ar.modelUrl)),
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

        // ánh sáng để model glb hiển thị đúng
        const hemi = new THREE.HemisphereLight(0xffffff, 0x444444, 1.2);
        const dir = new THREE.DirectionalLight(0xffffff, 1.0);
        dir.position.set(0.5, 1, 1);
        scene.add(hemi, dir);

        // AnimationMixer cho model có rig (vd Mixamo). Cập nhật mỗi frame trong render
        // loop bằng delta của clock. Model tĩnh (không clip) không tạo mixer.
        const mixers: THREE.AnimationMixer[] = [];
        const clock = new THREE.Clock();

        // Mỗi nghệ nhân 1 anchor tại targetIndex của mình; chĩa ảnh nào -> hiện người đó.
        artisans.forEach((artisan, i) => {
          // clone: rawModels[i] là instance cache dùng chung; normalizeModel MUTATE nó,
          // nên phải normalize trên BẢN SAO, nếu không lần khởi tạo lại (retry/restart)
          // sẽ normalize lần 2 lên object đã biến đổi -> model biến mất dù vẫn track.
          const clone = cloneModel(rawModels[i]);

          // Phát animation nếu model có clip. Mixer bind vào bản CLONE (chứa skeleton).
          // PHẢI tạo mixer + pose frame 0 TRƯỚC normalizeModel: animation Mixamo có thể
          // dời tâm nhân vật ra xa gốc (offset baked trong clip), nên normalize phải đo
          // theo POSE THẬT của frame đầu — nếu đo bind-pose thì tâm lệch, sau khi phóng
          // to nhân vật văng khỏi khung -> không thấy gì.
          const clips = rawModels[i].userData.clips as THREE.AnimationClip[] | undefined;
          if (clips && clips.length) {
            const idx = artisan.ar.animationIndex ?? 0;
            const clip = clips[idx] ?? clips[0];
            const mixer = new THREE.AnimationMixer(clone);
            mixer.clipAction(clip).play(); // loop mặc định = vô hạn
            mixer.update(0); // đặt skeleton về frame 0 để normalizeModel đo đúng pose
            mixers.push(mixer);
          }

          const model = normalizeModel(clone, artisan.ar.scale, artisan.ar.offset, {
            rotationDeg: artisan.ar.rotationDeg,
            groundAlign: artisan.ar.groundAlign,
          });

          const anchor = mindar.addAnchor(artisan.targetIndex);
          anchor.group.add(model);
          anchor.onTargetFound = () => {
            if (cancelled) return;
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
        renderer.setAnimationLoop(() => {
          const delta = clock.getDelta();
          for (const mx of mixers) mx.update(delta);
          renderer.render(scene, camera);
        });

        // Giữ fov/model khớp mỗi khi container ĐỔI KÍCH THƯỚC. Video coverage đã do
        // CSS object-cover lo (xem ARScene), còn resize() ở đây chỉ để camera fov +
        // canvas 3D bám theo viewport thật -> model neo đúng khi màn nở/thu.
        // Dùng ResizeObserver + visualViewport thay vì setTimeout cứng: trên iOS
        // Safari container nở ra MUỘN (thanh địa chỉ thu lại) -> phải resize đúng
        // lúc đó, không đoán mốc thời gian được.
        const forceResize = () => {
          if (cancelled) return;
          try { mindar.resize?.(); } catch { /* noop */ }
        };
        requestAnimationFrame(forceResize);
        setTimeout(forceResize, 300);

        const ro = new ResizeObserver(() => forceResize());
        ro.observe(container);

        const vv = window.visualViewport;
        const onVV = () => forceResize();
        vv?.addEventListener('resize', onVV);
        vv?.addEventListener('scroll', onVV);

        const onOrient = () => setTimeout(forceResize, 300);
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
    };
  }, [active, targetSrc, artisans]);

  return { containerRef, status, errorMsg, activeArtisan };
}
