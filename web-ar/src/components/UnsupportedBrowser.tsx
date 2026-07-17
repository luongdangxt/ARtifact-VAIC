// Fallback khi trình duyệt không hỗ trợ getUserMedia (WebRTC) hoặc không HTTPS.
export default function UnsupportedBrowser({ reason }: { reason?: string }) {
  return (
    <div className="absolute inset-0 z-30 flex flex-col items-center justify-center gap-4 bg-black/90 p-6 text-center text-white">
      <div className="text-4xl">🚫</div>
      <h2 className="text-lg font-semibold">Trình duyệt chưa hỗ trợ AR</h2>
      <p className="max-w-xs text-sm text-white/70">
        {reason ??
          'Thiết bị/trình duyệt này không mở được camera. Hãy dùng Safari (iOS) hoặc Chrome (Android) mới nhất, và mở qua HTTPS.'}
      </p>
    </div>
  );
}
