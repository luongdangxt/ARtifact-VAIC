// WebXR immersive-AR chỉ có trên Android Chrome (engine Blink). iOS Safari — và MỌI
// trình duyệt iOS vì đều bị ép dùng WebKit — KHÔNG hỗ trợ. Nên tính năng "ghim model
// vào sàn + đi quanh trong web" chỉ bật được ở Android; iOS dùng Quick Look native.
export async function isWebXRARSupported(): Promise<boolean> {
  if (typeof navigator === 'undefined') return false;
  const xr = navigator.xr;
  if (!xr?.isSessionSupported) return false;
  try {
    return await xr.isSessionSupported('immersive-ar');
  } catch {
    return false;
  }
}
