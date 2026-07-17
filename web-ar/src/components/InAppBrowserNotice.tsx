'use client';

import { useState } from 'react';
import { isAndroid, openInAndroidChrome } from '@/lib/browser';

// Hiển thị khi phát hiện trình duyệt in-app (WebView trong Zalo/Facebook/Messenger...).
// Các WebView này không mở/không render được camera cho AR (iOS: nền đen; Android:
// bị chặn hẳn nên không detect). Hướng dẫn người dùng mở bằng trình duyệt thật.
export default function InAppBrowserNotice({ onProceed }: { onProceed: () => void }) {
  const [copied, setCopied] = useState(false);
  const [android] = useState<boolean>(isAndroid);

  const copyLink = async () => {
    try {
      await navigator.clipboard.writeText(window.location.href);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // clipboard có thể bị chặn trong WebView -> người dùng tự copy từ menu app
    }
  };

  return (
    <div className="absolute inset-0 z-40 flex flex-col items-center justify-center gap-5 bg-black p-6 text-center text-white">
      <div className="text-5xl">🌐</div>
      <h2 className="text-xl font-semibold">Hãy mở bằng trình duyệt</h2>
      <p className="max-w-xs text-sm text-white/70">
        Bạn đang mở trong trình duyệt thu nhỏ của ứng dụng (Zalo/Facebook…). Trình
        duyệt này <span className="text-white">không chạy được camera AR</span>. Hãy
        mở bằng Safari (iPhone) hoặc Chrome (Android).
      </p>

      {android ? (
        // Android: ép mở Chrome bằng intent:// (thoát WebView được)
        <>
          <button
            onClick={openInAndroidChrome}
            className="rounded-full bg-white px-8 py-3 text-base font-semibold text-black"
          >
            Mở bằng Chrome
          </button>
          <p className="max-w-xs text-xs text-white/50">
            Nếu nút không chạy: bấm{' '}
            <span className="text-white/80">••• → “Mở trong trình duyệt”</span>.
          </p>
        </>
      ) : (
        // iOS: không ép mở Safari được -> hướng dẫn thao tác tay
        <div className="max-w-xs rounded-xl bg-white/10 p-4 text-left text-sm leading-relaxed">
          <p className="mb-1 font-medium text-white">Cách mở trên iPhone:</p>
          <p className="text-white/80">
            Bấm nút <span className="font-semibold text-white">•••</span> (góc trên
            bên phải) → chọn{' '}
            <span className="font-semibold text-white">“Mở bằng Safari”</span>.
          </p>
        </div>
      )}

      <button
        onClick={copyLink}
        className="rounded-full bg-white/10 px-6 py-2.5 text-sm font-medium text-white"
      >
        {copied ? 'Đã sao chép link ✓' : 'Hoặc sao chép link'}
      </button>

      <button
        onClick={onProceed}
        className="text-xs text-white/50 underline"
      >
        Vẫn thử ở đây (có thể không hiện camera)
      </button>
    </div>
  );
}
