'use client';

import { useState, useSyncExternalStore } from 'react';
import InAppBrowserNotice from './InAppBrowserNotice';
import ARSceneClient from '@/features/ar/ARSceneClient';
import { artisans } from '@/data/artisans';
import { detectInAppBrowser } from '@/lib/browser';

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
    <main className="relative flex min-h-dvh flex-col items-center justify-center gap-8 px-6 py-16 text-center">
      <div className="flex flex-col items-center gap-4">
        <span className="text-5xl">🪷</span>
        <h1 className="text-3xl font-bold tracking-tight sm:text-4xl">ARtifact VAIC</h1>
        <p className="max-w-md text-base leading-relaxed text-black/70 dark:text-white/70">
          Gìn giữ và lan tỏa những nghệ nhân di sản Việt Nam bằng AR ngay trên trình
          duyệt — chĩa camera vào ảnh mốc để gặp nghệ nhân sống động, không cần cài app.
        </p>
      </div>

      <button
        onClick={() => setEntered(true)}
        className="rounded-full bg-black px-10 py-4 text-lg font-semibold text-white shadow-lg transition active:scale-95 dark:bg-white dark:text-black"
      >
        Quét AR ngay
      </button>

      <p className="max-w-xs text-xs text-black/50 dark:text-white/50">
        Cho phép quyền camera khi được hỏi, rồi chĩa vào ảnh mốc của di sản.
        {sampleMarkerUrl && (
          <>
            {' '}
            <a
              href={sampleMarkerUrl}
              target="_blank"
              rel="noreferrer"
              className="text-blue-600 underline dark:text-blue-400"
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
