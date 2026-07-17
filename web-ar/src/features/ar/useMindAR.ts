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
  try { m.renderer?.forceContextLoss?.(); } catch { /* noop */ }
  try { m.renderer?.dispose(); } catch { /* noop */ }
}

// Khởi tạo MindAR + three, load model, gắn anchor, chạy render loop.
// Dọn dẹp (stop camera + dispose) khi rời trang / active=false để tránh treo camera & memory leak.
export function useMindAR({ target, active }: Options) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [status, setStatus] = useState<ARStatus>('idle');
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  // giữ instance để listener pagehide/visibilitychange có thể teardown ngay
  const mindarRef = useRef<MindARRuntime | null>(null);

  // Safari iOS: back-button đưa trang vào bfcache (đóng băng, vẫn giữ camera).
  // Nếu trang được KHÔI PHỤC từ bfcache -> reload để mọi thứ khởi tạo sạch lại.
  useEffect(() => {
    const onPageShow = (e: PageTransitionEvent) => {
      if (e.persisted) window.location.reload();
    };
    window.addEventListener('pageshow', onPageShow);
    return () => window.removeEventListener('pageshow', onPageShow);
  }, []);

  useEffect(() => {
    if (!active) return;
    const container = containerRef.current;
    if (!container) return;

    let cancelled = false;

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

        const model = normalizeModel(raw, target.scale, target.offset);

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
      window.removeEventListener('pagehide', releaseOnHide);
      teardownMindAR(mindarRef.current);
      mindarRef.current = null;
    };
  }, [active, target]);

  return { containerRef, status, errorMsg };
}
