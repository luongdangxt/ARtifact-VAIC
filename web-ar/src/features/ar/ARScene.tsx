'use client';

import { useState } from 'react';
import type { Artisan } from '@/lib/types';
import { useMindAR } from './useMindAR';
import Loading from '@/components/Loading';
import CameraPermission from '@/components/CameraPermission';
import UnsupportedBrowser from '@/components/UnsupportedBrowser';
import InAppBrowserNotice from '@/components/InAppBrowserNotice';
import ARHud from '@/components/ARHud';
import { detectInAppBrowser } from '@/lib/browser';

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

// Core AR: kiểm tra hỗ trợ -> chờ user gesture (iOS) -> chạy MindAR + render loop.
export default function ARScene({ artisan }: { artisan: Artisan }) {
  const [supported] = useState<boolean>(detectSupport);
  const [inApp] = useState<boolean>(detectInAppBrowser);
  // cho phép người dùng bỏ qua cảnh báo in-app và vẫn thử (một số WebView Android chạy được)
  const [forceProceed, setForceProceed] = useState(false);
  const [started, setStarted] = useState(false);
  const [retryKey, setRetryKey] = useState(0);

  const { containerRef, status, errorMsg } = useMindAR({
    target: artisan.ar,
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

      {/* Màn hình bắt đầu — cần user gesture để mở camera trên iOS Safari */}
      {!started && supported && (!inApp || forceProceed) && (
        <div className="absolute inset-0 z-30 flex flex-col items-center justify-center gap-6 bg-black p-6 text-center text-white">
          <h1 className="text-2xl font-semibold">{artisan.name}</h1>
          <p className="max-w-xs text-sm text-white/70">{artisan.craft}</p>
          <button
            onClick={() => setStarted(true)}
            className="rounded-full bg-white px-8 py-3 font-medium text-black"
          >
            Bắt đầu quét AR
          </button>
          <p className="max-w-xs text-xs text-white/50">
            Cho phép quyền camera khi được hỏi, rồi chĩa vào ảnh mốc.
          </p>
          {artisan.ar.markerUrl && (
            <a
              href={artisan.ar.markerUrl}
              target="_blank"
              rel="noreferrer"
              className="text-xs text-blue-300 underline"
            >
              Chưa có ảnh mốc? Mở ảnh mốc để in/hiện lên màn khác ↗
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
          artisanName={artisan.name}
          aiEnabled={artisan.aiEnabled}
          onAskAI={() => {
            // Giai đoạn 2: mở khung chat -> askAI(). Hiện để trống chỗ.
            alert('Tính năng hỏi-đáp AI sẽ có ở Giai đoạn 2.');
          }}
        />
      )}
    </div>
  );
}
