'use client';

import { useState, useSyncExternalStore } from 'react';
import InAppBrowserNotice from './InAppBrowserNotice';
import ARSceneClient from '@/features/ar/ARSceneClient';
import { artisans } from '@/data/artisans';
import { detectInAppBrowser } from '@/lib/browser';
import { unlockSharedAudio } from '@/lib/audioUnlock';

// Đọc trạng thái in-app CHỈ ở client (server luôn trả false) mà không lệch hydrate
// và không setState-trong-effect: dùng useSyncExternalStore với snapshot server=false.
const noopSubscribe = () => () => {};
function useInAppBrowser(): boolean {
  return useSyncExternalStore(noopSubscribe, () => detectInAppBrowser(), () => false);
}

// Điểm vào duy nhất (1 QR/1 link chung): màn chào giới thiệu sứ mệnh + 1 nút.
// Bấm "Quét AR ngay" -> VÀO THẲNG máy quét (không có màn/nút thứ 2). Chính cú bấm
// này là user-gesture để mở camera trên iOS Safari, nên gộp cùng 1 trang thay vì
// điều hướng sang route khác (điều hướng sẽ mất gesture -> iOS chặn camera).
// Cảnh báo trình duyệt in-app (Zalo/FB…) hiện ngay lúc vào link.
export default function WelcomeClient() {
  const inApp = useInAppBrowser();
  const [forceProceed, setForceProceed] = useState(false);
  const [entered, setEntered] = useState(false);

  // Đã bấm nút -> render máy quét, camera tự mở ngay (started=true trong ARScene).
  if (entered) {
    return <ARSceneClient artisans={artisans} />;
  }

  const sampleMarkerUrl = artisans[0]?.ar.markerUrl;

  return (
    <main className="relative flex min-h-dvh flex-col items-center justify-center gap-8 overflow-hidden bg-[#1d0a11] px-6 py-16 text-center text-white">
      {/* Nền: gradient sơn mài đỏ-vàng + hoạ tiết vòng tròn đồng tâm gợi mặt trống đồng.
          Thuần CSS (không ảnh) nên không tốn thêm request; luôn tối bất kể theme hệ thống. */}
      <div aria-hidden className="pointer-events-none absolute inset-0">
        <div className="absolute inset-0 bg-[linear-gradient(165deg,#4c1113_0%,#2c0b17_48%,#150a20_100%)]" />
        {/* quầng vàng ấm phía sau tiêu đề + quầng đỏ son góc dưới */}
        <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_50%_18%,rgba(251,191,36,0.22),transparent_58%)]" />
        <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_88%_105%,rgba(225,29,72,0.28),transparent_55%)]" />
        {/* vòng tròn đồng tâm: góc trên phải + góc dưới trái */}
        <div className="absolute -right-28 -top-28 h-96 w-96 rounded-full border border-amber-200/15" />
        <div className="absolute -right-14 -top-14 h-64 w-64 rounded-full border border-amber-200/10" />
        <div className="absolute -right-2 -top-2 h-40 w-40 rounded-full border border-amber-200/[0.07]" />
        <div className="absolute -bottom-36 -left-36 h-[30rem] w-[30rem] rounded-full border border-amber-200/15" />
        <div className="absolute -bottom-24 -left-24 h-96 w-96 rounded-full border border-amber-200/10" />
        <div className="absolute -bottom-10 -left-10 h-64 w-64 rounded-full border border-amber-200/[0.07]" />
      </div>

      <div className="relative flex flex-col items-center gap-4">
        <span className="text-6xl drop-shadow-[0_0_24px_rgba(251,191,36,0.45)]">🪷</span>
        <h1 className="text-3xl font-bold tracking-tight text-amber-50 sm:text-4xl">
          ARtifact VAIC
        </h1>
        <p className="max-w-md text-base leading-relaxed text-amber-100/75">
          Gìn giữ và lan tỏa những nghệ nhân di sản Việt Nam bằng AR ngay trên trình
          duyệt — chĩa camera vào ảnh mốc để gặp nghệ nhân sống động, không cần cài app.
        </p>
      </div>

      <button
        onClick={() => {
          // Cú chạm này còn dùng để MỞ KHOÁ loa (iOS): lời chào của nghệ nhân về sau
          // tự phát trên AudioContext đã unlock ở đây, không cần cú chạm thứ hai.
          unlockSharedAudio();
          setEntered(true);
        }}
        className="relative rounded-full bg-gradient-to-r from-amber-300 via-amber-400 to-amber-500 px-10 py-4 text-lg font-semibold text-[#3a0d0d] shadow-lg shadow-amber-900/50 transition active:scale-95"
      >
        Quét AR ngay
      </button>

      <p className="relative max-w-xs text-xs text-amber-100/50">
        Cho phép quyền camera khi được hỏi, rồi chĩa vào ảnh mốc của di sản.
        {sampleMarkerUrl && (
          <>
            {' '}
            <a
              href={sampleMarkerUrl}
              target="_blank"
              rel="noreferrer"
              className="text-amber-300 underline"
            >
              Xem ảnh mốc mẫu ↗
            </a>
          </>
        )}
      </p>

      {/* Cảnh báo in-app hiện đè lên màn chào ngay khi vào link (Zalo/FB WebView) */}
      {inApp && !forceProceed && (
        <InAppBrowserNotice onProceed={() => setForceProceed(true)} />
      )}
    </main>
  );
}
