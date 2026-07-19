'use client';

import { useEffect, useRef, useState } from 'react';
import type { Artisan } from '@/lib/types';
import { TARGETS_MIND } from '@/data/artisans';
import { useMindAR } from './useMindAR';
import Loading from '@/components/Loading';
import CameraPermission from '@/components/CameraPermission';
import UnsupportedBrowser from '@/components/UnsupportedBrowser';
import ARHud from '@/components/ARHud';
import ChatPanel from '@/components/ChatPanel';

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
  // Tự bắt đầu quét ngay khi vào — user-gesture đã lấy ở nút "Quét AR ngay" của màn
  // chào (cùng trang), nên không cần nút bấm thứ 2 ở đây.
  const [started, setStarted] = useState(true);
  const [retryKey, setRetryKey] = useState(0);
  // Phiên trò chuyện AI (Giai đoạn 2). GHIM nghệ nhân lúc bắt đầu để hội thoại + ghi âm
  // TỒN TẠI XUYÊN SUỐT, không tắt khi camera lia khỏi model (activeArtisan tạm null).
  const [session, setSession] = useState<Artisan | null>(null);
  // slug vừa bị user đóng (✕) để KHÔNG tự mở lại ngay khi vẫn đang thấy nghệ nhân đó.
  const dismissedRef = useRef<string | null>(null);

  const { containerRef, status, errorMsg, activeArtisan } = useMindAR({
    artisans,
    targetSrc: TARGETS_MIND,
    // active phụ thuộc started (user gesture) + retryKey để thử lại sau khi bị từ chối
    active: started,
  });

  // Voice-first: vừa THẤY nghệ nhân có bật AI là tự mở phiên trò chuyện (xin mic + sẵn sàng
  // bấm-giữ để nói). Không tự mở lại nghệ nhân user vừa đóng; khi mất tracking hẳn thì cho
  // phép mở lại lần sau. Phiên đã mở thì giữ nguyên (không phụ thuộc activeArtisan nữa).
  useEffect(() => {
    if (activeArtisan?.slug) {
      if (
        activeArtisan.aiEnabled &&
        !session &&
        dismissedRef.current !== activeArtisan.slug
      ) {
        setSession(activeArtisan);
      }
    } else {
      dismissedRef.current = null;
    }
  }, [activeArtisan, session]);

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
          // Nút "Hỏi nghệ nhân" chỉ để MỞ LẠI khi user đã đóng phiên (bình thường tự mở).
          aiEnabled={(activeArtisan?.aiEnabled ?? false) && !session}
          onAskAI={() => activeArtisan && setSession(activeArtisan)}
        />
      )}

      {/* Phiên trò chuyện AI: đã mở là GIỮ MOUNT xuyên suốt (kể cả khi mất tracking), chỉ
          đóng khi user bấm ✕. `tracking` chỉ để panel hiện gợi ý, không điều khiển mount. */}
      {session && (
        <ChatPanel
          key={session.slug}
          artisan={session}
          tracking={activeArtisan?.slug === session.slug && status === 'tracking'}
          onClose={() => {
            dismissedRef.current = session.slug;
            setSession(null);
          }}
        />
      )}
    </div>
  );
}
