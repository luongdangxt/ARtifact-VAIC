import * as THREE from 'three';
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js';
import { DRACOLoader } from 'three/examples/jsm/loaders/DRACOLoader.js';

// Load + cache model .glb. Nếu load lỗi (thiếu file, sai format) -> trả placeholder
// để Phase 0 vẫn chạy được mà không cần asset thật.

const cache = new Map<string, Promise<THREE.Group>>();

let loader: GLTFLoader | null = null;

function getLoader(): GLTFLoader {
  if (loader) return loader;
  loader = new GLTFLoader();
  // Hỗ trợ .glb nén Draco. File decoder lấy từ CDN Google (chỉ tải khi model có Draco).
  const draco = new DRACOLoader();
  draco.setDecoderPath('https://www.gstatic.com/draco/versioned/decoders/1.5.6/');
  loader.setDRACOLoader(draco);
  return loader;
}

function placeholder(): THREE.Group {
  const group = new THREE.Group();
  const geo = new THREE.BoxGeometry(1, 1, 1);
  const mat = new THREE.MeshStandardMaterial({ color: 0xff5533, roughness: 0.4 });
  group.add(new THREE.Mesh(geo, mat));
  return group;
}

export function loadModel(url: string): Promise<THREE.Group> {
  const cached = cache.get(url);
  if (cached) return cached;

  const promise = new Promise<THREE.Group>((resolve) => {
    getLoader().load(
      url,
      (gltf) => resolve(gltf.scene),
      undefined,
      (err) => {
        console.warn(`[modelLoader] load lỗi ${url}, dùng placeholder:`, err);
        resolve(placeholder());
      },
    );
  });

  cache.set(url, promise);
  return promise;
}

// Chuẩn hoá kích thước model về ~`scale` đơn vị và căn TÂM về gốc anchor.
// Cấu trúc lồng nhau QUAN TRỌNG: model được dịch -center ở scale gốc (căn tâm),
// rồi group `scaler` mới scale toàn bộ. Nếu scale thẳng lên `model` sau khi
// .position.sub(center) thì phần dịch tâm KHÔNG được scale theo (three.js áp
// scale trước, position sau) -> model lệch khỏi tâm. Lồng group để scale bọc
// luôn cả phép dịch tâm.
export function normalizeModel(
  model: THREE.Group,
  scale: number,
  offset: [number, number, number],
): THREE.Group {
  const box = new THREE.Box3().setFromObject(model);
  const size = new THREE.Vector3();
  const center = new THREE.Vector3();
  box.getSize(size);
  box.getCenter(center);

  const maxDim = Math.max(size.x, size.y, size.z) || 1;
  const unit = scale / maxDim;

  model.position.sub(center); // căn tâm hình học về gốc (ở scale gốc)

  const scaler = new THREE.Group();
  scaler.add(model);
  scaler.scale.setScalar(unit); // scale bọc cả phép dịch tâm -> tâm vẫn ở gốc

  const wrapper = new THREE.Group();
  wrapper.add(scaler);
  wrapper.position.set(offset[0], offset[1], offset[2]);
  return wrapper;
}
