import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Huy hiệu "N" của Next ở góc dưới trái CHỈ có trong dev, nhưng nó nằm đè lên vùng
  // điều khiển AR và trông y như một nút bấm của app -> tắt hẳn cho khỏi gây hiểu nhầm
  // khi test trên điện thoại. Lỗi biên dịch/runtime vẫn hiện bình thường.
  devIndicators: false,
  // Dev server CHẶN mọi request /_next/* từ origin lạ (mặc định chỉ cho localhost).
  // Test AR trên điện thoại thì phải vào bằng IP LAN -> WebSocket HMR bị 403 -> client
  // dev của Next không hydrate -> trang render ra nhưng MỌI nút đều chết (bấm "Quét AR
  // ngay" không có phản hồi). Cho phép loopback + dải LAN để test trên thiết bị thật.
  // *.trycloudflare.com: khi không cùng wifi thì mở tunnel công khai bằng
  // `cloudflared tunnel --url https://localhost:3000 --no-tls-verify`, điện thoại
  // vào qua 4G ở bất cứ đâu -> origin là domain đó chứ không phải IP LAN.
  allowedDevOrigins: [
    '127.0.0.1',
    '192.168.*.*',
    '10.*.*.*',
    '172.16.*.*',
    '*.trycloudflare.com',
  ],
  turbopack: {
    // Bundle mind-ar/tfjs cho browser có nhánh Node dùng require("fs"),
    // Turbopack không resolve được -> stub về module rỗng cho môi trường browser.
    resolveAlias: {
      fs: { browser: "./empty-module.js" },
      path: { browser: "./empty-module.js" },
    },
  },
};

export default nextConfig;
