// Kiểu dữ liệu dùng chung toàn app.
// Tầng AR chỉ phụ thuộc vào các type này, không phụ thuộc nguồn dữ liệu (mock/DB/API).

export interface ARTarget {
  /** Đường dẫn file .mind đã compile, vd '/targets/nghe-nhan-01.mind' */
  targetUrl: string;
  /** Đường dẫn model 3D .glb, vd '/models/nghe-nhan-01.glb' */
  modelUrl: string;
  /** Hệ số phóng to model sau khi load */
  scale: number;
  /** Dịch model để nổi phía trên QR, không che mã: [x, y, z] */
  offset: [number, number, number];
  /** Ảnh mốc để in/hiện ra mà quét (png/pdf), vd '/markers/nghe-nhan-01.png' */
  markerUrl?: string;
  /**
   * GLB cho chế độ "xem cỡ thật" (Android Scene Viewer). File PHẢI được dựng theo
   * mét thật (vd người cao ~1.7m) để đặt xuống sàn đúng kích cỡ. Bỏ trống -> dùng modelUrl.
   */
  modelRealUrl?: string;
  /**
   * USDZ cho iOS AR Quick Look — BẮT BUỘC để xem cỡ thật trên iPhone
   * (convert từ GLB, cùng cỡ mét thật). Thiếu file này thì iPhone sẽ báo chưa hỗ trợ.
   */
  modelUsdzUrl?: string;
  /**
   * Xoay model (độ) trong hệ ảnh-mốc. Để DỰNG ĐỨNG người khỏi tấm thẻ đặt nằm ngang
   * trên bàn/sàn: thường [90, 0, 0]. Nếu người quay lưng/nghiêng thì chỉnh trục Y, vd [90, 180, 0].
   */
  rotationDeg?: [number, number, number];
  /**
   * true = hạ ĐÁY model chạm mặt phẳng thẻ (chân chạm "đất") thay vì căn tâm
   * (mặc định căn tâm -> nửa model chìm dưới thẻ). Dùng chung với rotationDeg để đứng thật.
   */
  groundAlign?: boolean;
}

export interface Artisan {
  /** 'nghe-nhan-01' — dùng trong URL & mã QR */
  slug: string;
  name: string;
  /** nghề / di sản */
  craft: string;
  bio: string;
  ar: ARTarget;
  /** bật hỏi-đáp AI (Giai đoạn 2) */
  aiEnabled: boolean;
}

export type ChatRole = 'user' | 'assistant';

export interface ChatMessage {
  role: ChatRole;
  content: string;
}
