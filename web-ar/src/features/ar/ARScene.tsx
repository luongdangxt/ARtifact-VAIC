'use client';

import { useEffect, useRef, useState } from 'react';
import type { Artisan } from '@/lib/types';
import { TARGETS_MIND } from '@/data/artisans';
import { useMindAR } from './useMindAR';
import Loading from '@/components/Loading';
import CameraPermission from '@/components/CameraPermission';
import UnsupportedBrowser from '@/components/UnsupportedBrowser';
import InAppBrowserNotice from '@/components/InAppBrowserNotice';
import ARHud from '@/components/ARHud';
import { detectInAppBrowser } from '@/lib/browser';
import { launchRealScaleAR } from '@/lib/realScaleAR';
import { isWebXRARSupported } from '@/lib/webxr';
import { startWebXRSession, type WebXRController } from './webxrController';

type XRPhase = 'off' | 'searching' | 'placed';

// Kiểm tra getUserMedia + ngữ cảnh bảo mật (HTTPS/localhost).
// ARScene chỉ chạy client (ssr:false) nên initializer này chỉ chạy trên browser -> không lo hydration mismatch.
function detectSupport(): boolean {
  const hasMedia =
    typeof navigator !== 'undefined' && !!navigator.mediaDevices?.getUserMedia;
  const secure =
    typeof window !== 'undefined' &&
    (window.isSecureContext || window.location.hostname === 'localhost');
  return hasMedia && secure;
}

// Core AR (máy quét chung, đa target): kiểm tra hỗ trợ -> chờ user gesture (iOS)
// -> chạy MindAR với file .mind gộp -> chĩa ảnh nào thì tự hiện nghệ nhân đó.
export default function ARScene({ artisans }: { artisans: Artisan[] }) {
  const [supported] = useState<boolean>(detectSupport);
  const [inApp] = useState<boolean>(detectInAppBrowser);
  // cho phép người dùng bỏ qua cảnh báo in-app và vẫn thử (một số WebView Android chạy được)
  const [forceProceed, setForceProceed] = useState(false);
  const [started, setStarted] = useState(false);
  const [retryKey, setRetryKey] = useState(0);
  // thông báo ngắn khi mở "cỡ thật" không được (thiếu USDZ / không phải điện thoại)
  const [realScaleMsg, setRealScaleMsg] = useState<string | null>(null);

  // WebXR (Android): ghim model vào sàn thật trong web (giữ AI). iOS không hỗ trợ -> dùng native.
  const [xrSupported, setXrSupported] = useState(false);
  const [xrPhase, setXrPhase] = useState<XRPhase>('off');
  // khoảng chờ sau khi thoát WebXR để camera (ARCore) nhả xong trước khi MindAR xin lại
  const [restarting, setRestarting] = useState(false);
  const xrOverlayRef = useRef<HTMLDivElement>(null);
  const xrCtrlRef = useRef<WebXRController | null>(null);
  const restartTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    return () => {
      if (restartTimer.current) clearTimeout(restartTimer.current);
    };
  }, []);

  useEffect(() => {
    let alive = true;
    isWebXRARSupported().then((ok) => alive && setXrSupported(ok));
    return () => {
      alive = false;
    };
  }, []);

  // Kết thúc phiên WebXR nếu component bị gỡ (rời trang) khi đang trong AR.
  useEffect(() => {
    return () => xrCtrlRef.current?.end();
  }, []);

  // Chặn tap vào NÚT overlay bị tính là "select" đặt model của WebXR.
  useEffect(() => {
    const el = xrOverlayRef.current;
    if (!el || xrPhase === 'off') return;
    const block = (e: Event) => {
      if ((e.target as HTMLElement)?.closest('[data-xr-ui]')) e.preventDefault();
    };
    el.addEventListener('beforexrselect', block);
    return () => el.removeEventListener('beforexrselect', block);
  }, [xrPhase]);

  // Mở model cỡ thật. Android hỗ trợ WebXR -> ghim vào sàn NGAY TRONG web (giữ AI).
  // Còn lại (iOS...) -> AR gốc: Quick Look (iOS) / Scene Viewer (Android cũ).
  const handleViewRealScale = () => {
    // Chỉ mở "cỡ thật" khi đang thấy 1 nghệ nhân (nút chỉ hiện lúc tracking).
    if (!activeArtisan) return;
    const glbUrl = activeArtisan.ar.modelRealUrl ?? activeArtisan.ar.modelUrl;

    if (xrSupported && xrOverlayRef.current) {
      setXrPhase('searching');
      // requestSession phải nằm trong user-gesture -> gọi ngay, không await trước.
      startWebXRSession(glbUrl, xrOverlayRef.current, {
        onSessionStart: () => setStarted(false), // nhường camera từ MindAR
        onSearching: () => setXrPhase('searching'),
        onPlaced: () => setXrPhase('placed'),
        onEnd: () => {
          xrCtrlRef.current = null;
          setXrPhase('off');
          // Android nhả camera ARCore không tức thì -> chờ rồi mới bật lại MindAR,
          // nếu không getUserMedia sẽ ném NotReadableError (camera bận) -> AR chết.
          setRestarting(true);
          if (restartTimer.current) clearTimeout(restartTimer.current);
          restartTimer.current = setTimeout(() => {
            setStarted(true); // bật lại MindAR khi camera đã rảnh
            setRestarting(false);
          }, 700);
        },
        onError: (m) => {
          setXrPhase('off');
          setRealScaleMsg(m);
          setTimeout(() => setRealScaleMsg(null), 4000);
        },
      }).then((ctrl) => {
        if (ctrl) xrCtrlRef.current = ctrl;
      });
      return;
    }

    // Fallback: AR gốc của thiết bị.
    const r = launchRealScaleAR({ glbUrl, usdzUrl: activeArtisan.ar.modelUsdzUrl });
    if (r === 'no-usdz') {
      setRealScaleMsg(
        'Chưa có bản model cỡ thật cho iPhone (.usdz). Hãy thử trên Android, hoặc bổ sung file USDZ.',
      );
    } else if (r === 'unsupported') {
      setRealScaleMsg('Xem cỡ thật cần mở trên điện thoại iPhone hoặc Android.');
    }
    if (r !== 'launching') setTimeout(() => setRealScaleMsg(null), 4000);
  };

  const { containerRef, status, errorMsg, activeArtisan } = useMindAR({
    artisans,
    targetSrc: TARGETS_MIND,
    // active phụ thuộc started (user gesture) + retryKey để thử lại sau khi bị từ chối
    active: started,
  });

  if (supported === false) {
    return (
      <div className="relative h-dvh w-full bg-black">
        <UnsupportedBrowser />
      </div>
    );
  }

  return (
    <div className="fixed inset-0 overflow-hidden bg-black">
      {/* MindAR chèn <video> (z-index:-2) + <canvas> vào container này.
          - `isolate`: stacking context riêng để video z-index:-2 KHÔNG bị nền
            bg-black của div cha che mất -> nếu thiếu, camera hiện đen.
          - `[&>video]:...`: ÉP thẻ <video> luôn phủ kín container bằng object-cover,
            GHI ĐÈ (!) kích thước inline mà MindAR.resize() tự set. MindAR tính
            width/height/top/left của video theo container.clientHeight tại thời điểm
            gọi; trên iOS Safari container nở ra sau khi thanh địa chỉ thu lại ->
            video giữ chiều cao cũ (ngắn) -> chừa dải đen dưới. Ép object-cover thì
            video luôn full màn, không phụ thuộc thời điểm resize (kết quả crop
            trùng đúng với "cover" của MindAR nên model vẫn neo khớp). */}
      <div
        ref={containerRef}
        className="absolute inset-0 isolate [&>video]:!absolute [&>video]:!inset-0 [&>video]:!m-0 [&>video]:!h-full [&>video]:!w-full [&>video]:!max-w-none [&>video]:!object-cover"
      />

      {/* Trình duyệt in-app (Zalo/Facebook…) không mở được camera AR -> chặn sớm,
          hướng dẫn mở bằng Safari/Chrome. Cho phép "vẫn thử" để không khoá cứng. */}
      {!started && supported && inApp && !forceProceed && (
        <InAppBrowserNotice onProceed={() => setForceProceed(true)} />
      )}

      {/* Đang chờ camera nhả sau khi thoát WebXR rồi bật lại MindAR */}
      {restarting && <Loading label="Đang mở lại camera…" />}

      {/* Màn hình bắt đầu — cần user gesture để mở camera trên iOS Safari */}
      {!started && !restarting && supported && (!inApp || forceProceed) && (
        <div className="absolute inset-0 z-30 flex flex-col items-center justify-center gap-6 bg-black p-6 text-center text-white">
          <h1 className="text-2xl font-semibold">Quét AR di sản</h1>
          <p className="max-w-xs text-sm text-white/70">
            Chĩa camera vào ảnh mốc của di sản bất kỳ — nghệ nhân sẽ tự hiện lên.
          </p>
          <button
            onClick={() => setStarted(true)}
            className="rounded-full bg-white px-8 py-3 font-medium text-black"
          >
            Bắt đầu quét AR
          </button>
          <p className="max-w-xs text-xs text-white/50">
            Cho phép quyền camera khi được hỏi, rồi chĩa vào ảnh mốc.
          </p>
          {artisans[0]?.ar.markerUrl && (
            <a
              href={artisans[0].ar.markerUrl}
              target="_blank"
              rel="noreferrer"
              className="text-xs text-blue-300 underline"
            >
              Chưa có ảnh mốc? Mở ảnh mốc mẫu để in/hiện lên màn khác ↗
            </a>
          )}
        </div>
      )}

      {/* Loading trong lúc khởi tạo */}
      {started &&
        (status === 'loading' || status === 'starting') && (
          <Loading
            label={status === 'loading' ? 'Đang tải model 3D…' : 'Đang mở camera…'}
          />
        )}

      {/* Bị từ chối quyền */}
      {status === 'denied' && (
        <CameraPermission
          onRetry={() => {
            setStarted(false);
            setRetryKey((k) => k + 1);
            // cho React unmount rồi bật lại
            setTimeout(() => setStarted(true), 50);
          }}
        />
      )}

      {/* Lỗi khác */}
      {status === 'error' && (
        <div className="absolute inset-0 z-30 flex flex-col items-center justify-center gap-3 bg-black/90 p-6 text-center text-white">
          <div className="text-4xl">⚠️</div>
          <p className="text-sm text-white/70">Có lỗi khi khởi tạo AR.</p>
          {errorMsg && <p className="text-xs text-white/40">{errorMsg}</p>}
          <button
            onClick={() => {
              setStarted(false);
              setRetryKey((k) => k + 1);
              setTimeout(() => setStarted(true), 50);
            }}
            className="mt-2 rounded-full bg-white px-6 py-2 text-sm font-medium text-black"
          >
            Thử lại
          </button>
        </div>
      )}

      {/* HUD khi camera đã chạy */}
      {started && (status === 'scanning' || status === 'tracking') && (
        <ARHud
          key={retryKey}
          status={status}
          artisanName={activeArtisan?.name}
          aiEnabled={activeArtisan?.aiEnabled ?? false}
          canRealScale={!!activeArtisan}
          onViewRealScale={handleViewRealScale}
          onAskAI={() => {
            // Giai đoạn 2: mở khung chat -> askAI(). Hiện để trống chỗ.
            alert('Tính năng hỏi-đáp AI sẽ có ở Giai đoạn 2.');
          }}
        />
      )}

      {/* Thông báo ngắn khi mở "cỡ thật" không được */}
      {realScaleMsg && (
        <div className="absolute bottom-28 left-1/2 z-20 max-w-xs -translate-x-1/2 rounded-xl bg-black/85 px-4 py-3 text-center text-xs leading-relaxed text-white">
          {realScaleMsg}
        </div>
      )}

      {/* Overlay của WebXR (dom-overlay). LUÔN render để làm root + giữ ref; khi 'off'
          là div rỗng, pointer-events-none nên không chắn UI MindAR phía dưới. */}
      <div ref={xrOverlayRef} className="pointer-events-none absolute inset-0 z-40">
        {xrPhase !== 'off' && (
          <div className="flex h-full flex-col justify-between p-4">
            <div className="flex justify-end">
              <button
                data-xr-ui
                onClick={() => xrCtrlRef.current?.end()}
                className="pointer-events-auto rounded-full bg-black/60 px-4 py-2 text-sm text-white backdrop-blur"
              >
                ✕ Thoát AR
              </button>
            </div>

            {xrPhase === 'searching' && (
              <div className="mx-auto mb-6 max-w-xs rounded-xl bg-black/60 px-4 py-3 text-center text-sm text-white backdrop-blur">
                Di chuyển điện thoại quét mặt sàn. Thấy vòng tròn xanh thì
                <span className="font-semibold"> chạm để đặt</span> nhân vật.
              </div>
            )}

            {xrPhase === 'placed' && (
              <div className="flex flex-col items-center gap-3">
                {activeArtisan?.aiEnabled && (
                  <button
                    data-xr-ui
                    onClick={() => alert('Tính năng hỏi-đáp AI sẽ có ở Giai đoạn 2.')}
                    className="pointer-events-auto rounded-full bg-white px-6 py-3 text-sm font-medium text-black shadow-lg"
                  >
                    💬 Hỏi nghệ nhân
                  </button>
                )}
                <button
                  data-xr-ui
                  onClick={() => {
                    xrCtrlRef.current?.replace();
                    setXrPhase('searching');
                  }}
                  className="pointer-events-auto rounded-full bg-black/60 px-6 py-2.5 text-sm font-medium text-white backdrop-blur"
                >
                  ↺ Đặt lại vị trí
                </button>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
