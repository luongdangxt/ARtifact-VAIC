// Nhận diện trình duyệt in-app (WebView nhúng trong app: Facebook, Messenger, Zalo,
// Instagram, TikTok, Line, WeChat...). Trên iOS các WebView này thường KHÔNG render
// được thẻ <video> camera (nền đen) dù getUserMedia + tracking vẫn chạy bình thường
// -> phải mở bằng Safari/Chrome thật. Không có cách ép WebView vẽ video một cách tin
// cậy, nên ta phát hiện rồi hướng dẫn người dùng mở ở trình duyệt đầy đủ.
export function detectInAppBrowser(): boolean {
  if (typeof navigator === 'undefined') return false;
  const ua = navigator.userAgent || '';
  const rules = [
    'FBAN', 'FBAV', 'FB_IAB', 'FBIOS', 'Messenger', // Facebook / Messenger
    'Instagram',
    'Zalo',
    'Line/',
    'Twitter',
    'MicroMessenger', // WeChat
    'TikTok', 'BytedanceWebview', 'musical_ly',
    'Snapchat',
    'Pinterest',
  ];
  return rules.some((r) => ua.includes(r));
}

export function isAndroid(): boolean {
  if (typeof navigator === 'undefined') return false;
  return /Android/i.test(navigator.userAgent || '');
}

export function isIOS(): boolean {
  if (typeof navigator === 'undefined') return false;
  const ua = navigator.userAgent || '';
  // iPadOS 13+ báo UA giống macOS -> kiểm tra thêm cảm ứng
  return /iPhone|iPad|iPod/i.test(ua) ||
    (/Macintosh/i.test(ua) && typeof document !== 'undefined' && 'ontouchend' in document);
}

// Thoát WebView in-app trên Android bằng intent:// -> mở link hiện tại trong Chrome thật.
// Nếu không có Chrome, browser_fallback_url mở lại bằng trình duyệt mặc định.
// (iOS không có cơ chế tương đương — phải hướng dẫn người dùng tự mở bằng Safari.)
export function openInAndroidChrome(): void {
  if (typeof window === 'undefined') return;
  const href = window.location.href;
  const hostAndPath = href.replace(/^https?:\/\//, '');
  const fallback = encodeURIComponent(href);
  window.location.href =
    `intent://${hostAndPath}#Intent;scheme=https;package=com.android.chrome;` +
    `S.browser_fallback_url=${fallback};end`;
}
