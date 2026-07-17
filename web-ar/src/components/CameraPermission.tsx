// Hiển thị khi quyền camera bị từ chối, kèm hướng dẫn bật lại.
export default function CameraPermission({ onRetry }: { onRetry: () => void }) {
  return (
    <div className="absolute inset-0 z-30 flex flex-col items-center justify-center gap-4 bg-black/90 p-6 text-center text-white">
      <div className="text-4xl">📷</div>
      <h2 className="text-lg font-semibold">Cần quyền truy cập camera</h2>
      <p className="max-w-xs text-sm text-white/70">
        Ứng dụng cần camera để quét ảnh mốc. Hãy bật quyền camera cho trang này
        trong cài đặt trình duyệt, rồi thử lại.
      </p>
      <ul className="max-w-xs list-disc space-y-1 text-left text-xs text-white/60">
        <li>iOS Safari: aA (thanh địa chỉ) → Cài đặt trang → Camera → Cho phép.</li>
        <li>Android Chrome: biểu tượng khoá → Quyền → Camera → Cho phép.</li>
      </ul>
      <button
        onClick={onRetry}
        className="mt-2 rounded-full bg-white px-6 py-2 text-sm font-medium text-black"
      >
        Thử lại
      </button>
    </div>
  );
}
