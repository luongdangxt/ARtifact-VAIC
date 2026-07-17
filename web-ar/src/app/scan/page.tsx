import { artisans } from '@/data/artisans';
import ARSceneClient from '@/features/ar/ARSceneClient';

// Máy quét chung (đa target): mở 1 lần, nhận diện MỌI ảnh mốc.
// Chĩa vào ảnh của nghệ nhân nào -> tự hiện model + thông tin người đó.
export default function ScanPage() {
  return <ARSceneClient artisans={artisans} />;
}
