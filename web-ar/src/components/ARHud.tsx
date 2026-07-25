'use client';

import type { ARStatus } from '@/features/ar/useMindAR';

interface Props {
  status: ARStatus;
  /** Tên nghệ nhân đang được camera thấy; rỗng khi chưa track được ai */
  artisanName?: string;
  aiEnabled: boolean;
  onAskAI?: () => void;
}

// Overlay: nút back, hint "chĩa vào ảnh", nút hỏi AI (Giai đoạn 2).
export default function ARHud({
  status,
  artisanName,
  aiEnabled,
  onAskAI,
}: Props) {
  const scanning = status === 'scanning';
  const tracking = status === 'tracking';

  return (
    <div className="pointer-events-none absolute inset-0 z-10 flex flex-col justify-between p-4">
      {/* Top bar. KHÔNG có nút "Trở về": máy quét AR nằm ngay trên trang chào (`/`) nên
          link về "/" chỉ nạp lại đúng trang đang đứng — bấm xong chẳng đi đâu cả. */}
      <div className="flex items-center justify-center">
        <span className="rounded-full bg-black/50 px-4 py-2 text-sm text-white backdrop-blur">
          {artisanName ?? 'Đang tìm ảnh mốc…'}
        </span>
      </div>

      {/* Hướng dẫn quét khi chưa track được. Chữ nằm TRÊN khung ngắm và cả cụm được đẩy
          lên: nửa dưới màn hình là chỗ của phụ đề + gợi ý câu hỏi, để nguyên giữa màn
          thì dòng chữ này lọt thỏm xuống dưới ô phụ đề, trông rất lộn xộn. */}
      {scanning && (
        <div className="-translate-y-8 flex flex-col items-center gap-3">
          <p className="rounded-full bg-black/50 px-4 py-2 text-sm text-white backdrop-blur">
            Chĩa camera vào ảnh mốc
          </p>
          <div className="h-40 w-40 rounded-2xl border-2 border-dashed border-white/70 animate-pulse" />
        </div>
      )}

      {/* Bottom: nút hỏi AI (GĐ2) */}
      <div className="flex flex-col items-center gap-3">
        {aiEnabled && tracking && (
          <button
            onClick={onAskAI}
            className="pointer-events-auto rounded-full bg-white px-6 py-3 text-sm font-medium text-black shadow-lg"
          >
            💬 Hỏi nghệ nhân
          </button>
        )}
      </div>
    </div>
  );
}
