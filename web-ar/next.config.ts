import type { NextConfig } from "next";

const nextConfig: NextConfig = {
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
