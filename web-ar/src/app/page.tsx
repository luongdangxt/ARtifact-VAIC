import { artisans } from '@/data/artisans';
import WelcomeClient from '@/components/WelcomeClient';

// Điểm vào duy nhất: màn chào mừng. Nút "Quét AR" -> /scan (máy quét chung đa target).
// Không còn danh sách chọn nghệ nhân — nghệ nhân được nhận diện TỰ ĐỘNG khi quét ảnh mốc.
export default function Home() {
  return <WelcomeClient sampleMarkerUrl={artisans[0]?.ar.markerUrl} />;
}
