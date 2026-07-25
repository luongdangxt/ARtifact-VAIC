import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Dev server CHẶN mọi request /_next/* từ origin lạ (mặc định chỉ cho localhost).
  // Test AR trên điện thoại thì phải vào bằng IP LAN -> WebSocket HMR bị 403 -> client
  // dev của Next không hydrate -> trang render ra nhưng MỌI nút đều chết (bấm "Quét AR
  // ngay" không có phản hồi). Cho phép loopback + dải LAN để test trên thiết bị thật.
  allowedDevOrigins: ['127.0.0.1', '192.168.*.*', '10.*.*.*', '172.16.*.*'],
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
