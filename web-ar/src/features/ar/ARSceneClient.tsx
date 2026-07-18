'use client';

import dynamic from 'next/dynamic';
import type { Artisan } from '@/lib/types';

// Client wrapper: chỉ ở đây mới được dùng dynamic(ssr:false).
// Giữ ARScene (MindAR + three) hoàn toàn client-side, không SSR.
const ARScene = dynamic(() => import('./ARScene'), {
  ssr: false,
  loading: () => (
    <div className="flex h-dvh w-full items-center justify-center bg-black text-white">
      Đang tải AR…
    </div>
  ),
});

export default function ARSceneClient({ artisans }: { artisans: Artisan[] }) {
  return <ARScene artisans={artisans} />;
}
