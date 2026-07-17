import { isIOS, isAndroid } from './browser';

// Mở model ở KÍCH THƯỚC THẬT bằng AR gốc của thiết bị (không cần thư viện):
//  - iOS  : AR Quick Look qua <a rel="ar" href=.usdz> (BẮT BUỘC có file .usdz).
//  - Android: Google Scene Viewer qua intent:// (dùng file .glb, cỡ theo mét thật trong file).
// Model được đặt đứng yên trên sàn; người dùng tự đi gần/xa để soi từng chi tiết.
// Đây là bổ sung cho MindAR (model nhỏ đứng trên thẻ) — không thay thế nó.

export type RealScaleResult =
  | 'launching' // đã kích hoạt AR gốc
  | 'no-usdz' // iOS nhưng thiếu file .usdz
  | 'unsupported'; // không phải iOS/Android

// Đường dẫn tương đối -> URL tuyệt đối https. Scene Viewer & Quick Look cần URL công khai
// (không nhận đường dẫn tương đối vì chúng mở ở app hệ thống khác, ngoài trang web).
function absoluteUrl(path: string): string {
  if (/^https?:\/\//.test(path)) return path;
  return new URL(path, window.location.href).href;
}

export function launchRealScaleAR(opts: {
  glbUrl: string;
  usdzUrl?: string;
}): RealScaleResult {
  if (typeof window === 'undefined') return 'unsupported';

  // iOS -> AR Quick Look
  if (isIOS()) {
    if (!opts.usdzUrl) return 'no-usdz';
    const a = document.createElement('a');
    a.setAttribute('rel', 'ar');
    // #allowsContentScaling=0: khoá tỉ lệ -> luôn đúng cỡ thật, không cho phóng to/thu nhỏ.
    a.setAttribute('href', `${absoluteUrl(opts.usdzUrl)}#allowsContentScaling=0`);
    // Safari CHỈ kích hoạt Quick Look nếu <a rel="ar"> có đúng 1 con là <img>.
    const img = document.createElement('img');
    img.src =
      'data:image/gif;base64,R0lGODlhAQABAAAAACH5BAEKAAEALAAAAAABAAEAAAICTAEAOw==';
    a.appendChild(img);
    a.style.display = 'none';
    document.body.appendChild(a);
    a.click();
    setTimeout(() => a.remove(), 1000);
    return 'launching';
  }

  // Android -> Google Scene Viewer (hosted trong app Google / googlequicksearchbox)
  if (isAndroid()) {
    const file = encodeURIComponent(absoluteUrl(opts.glbUrl));
    const fallback = encodeURIComponent(window.location.href);
    // mode=ar_preferred: vào thẳng AR (fallback 3D nếu máy không hỗ trợ ARCore).
    // resizable=false: khoá cỡ thật, không cho người dùng phóng to/thu nhỏ.
    window.location.href =
      `intent://arvr.google.com/scene-viewer/1.0?file=${file}` +
      `&mode=ar_preferred&resizable=false` +
      `#Intent;scheme=https;package=com.google.android.googlequicksearchbox;` +
      `action=android.intent.action.VIEW;S.browser_fallback_url=${fallback};end;`;
    return 'launching';
  }

  return 'unsupported';
}
