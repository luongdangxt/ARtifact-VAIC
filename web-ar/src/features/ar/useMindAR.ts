'use client';

import { useEffect, useRef, useState } from 'react';
import type { MindARThree } from 'mind-ar/dist/mindar-image-three.prod.js';
import type { ARTarget } from '@/lib/types';
import { loadModel, normalizeModel } from './modelLoader';

export type ARStatus =
  | 'idle'
  | 'loading'      // đang tải model + khởi tạo MindAR
  | 'starting'     // đang xin quyền + mở camera
  | 'scanning'     // camera chạy, chưa thấy mốc
  | 'tracking'     // đang thấy mốc, model hiển thị
  | 'denied'       // bị từ chối quyền camera
  | 'error';

interface Options {
  target: ARTarget;
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
  // gỡ <canvas> khỏi container, nếu không mỗi lần restart (thoát WebXR) để lại canvas mồ côi
  try { canvas?.remove(); } catch { /* noop */ }
}

// Khởi tạo MindAR + three, load model, gắn anchor, chạy render loop.
// Dọn dẹp (stop camera + dispose) khi rời trang / active=false để tránh treo camera & memory leak.
export function useMindAR({ target, active }: Options) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [status, setStatus] = useState<ARStatus>('idle');
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  // giữ instance để listener pagehide có thể teardown ngay
  const mindarRef = useRef<MindARRuntime | null>(null);

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
    const releaseOnHide = () => teardownMindAR(mindarRef.current);
    window.addEventListener('pagehide', releaseOnHide);

    (async () => {
      try {
        setStatus('loading');
        setErrorMsg(null);

        // import động: mind-ar chỉ chạy client, tránh SSR đụng window/document
        const [{ MindARThree }, THREE, raw] = await Promise.all([
          import('mind-ar/dist/mindar-image-three.prod.js'),
          import('three'),
          loadModel(target.modelUrl),
        ]);
        if (cancelled) return;

        const model = normalizeModel(raw, target.scale, target.offset, {
          rotationDeg: target.rotationDeg,
          groundAlign: target.groundAlign,
        });

        const mindar = new MindARThree({
          container,
          imageTargetSrc: target.targetUrl,
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

        const anchor = mindar.addAnchor(0);
        anchor.group.add(model);
        anchor.onTargetFound = () => !cancelled && setStatus('tracking');
        anchor.onTargetLost = () => !cancelled && setStatus('scanning');

        setStatus('starting');
        await mindar.start(); // mở camera (cần HTTPS / user gesture trên iOS)
        if (cancelled) return;

        setStatus('scanning');
        renderer.setAnimationLoop(() => renderer.render(scene, camera));

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
    };
  }, [active, target]);

  return { containerRef, status, errorMsg };
}
