'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import InAppBrowserNotice from './InAppBrowserNotice';
import { detectInAppBrowser } from '@/lib/browser';

// Màn hình chào mừng — điểm vào duy nhất của web (1 QR/1 link chung).
// Giới thiệu ngắn sứ mệnh dự án + 1 nút mở thẳng máy quét AR (/scan).
// Cảnh báo trình duyệt in-app (Zalo/Facebook…) hiện NGAY lúc vừa vào link,
// vì các WebView đó không chạy được camera AR.
export default function WelcomeClient({ sampleMarkerUrl }: { sampleMarkerUrl?: string }) {
  // Phát hiện in-app SAU khi mount (navigator chỉ có ở client) để server & client
  // render khớp lúc hydrate; notice vẫn bật gần như ngay lập tức.
  const [inApp, setInApp] = useState(false);
  const [forceProceed, setForceProceed] = useState(false);

  useEffect(() => {
    setInApp(detectInAppBrowser());
  }, []);

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

      <Link
        href="/scan"
        className="rounded-full bg-black px-10 py-4 text-lg font-semibold text-white shadow-lg transition active:scale-95 dark:bg-white dark:text-black"
      >
        Quét AR ngay
      </Link>

      <p className="max-w-xs text-xs text-black/50 dark:text-white/50">
        Mở trên điện thoại và cho phép quyền camera để trải nghiệm.
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
