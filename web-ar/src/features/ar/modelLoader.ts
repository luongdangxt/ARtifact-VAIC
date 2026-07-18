import * as THREE from 'three';
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js';
import { DRACOLoader } from 'three/examples/jsm/loaders/DRACOLoader.js';
import { clone as cloneSkinned } from 'three/examples/jsm/utils/SkeletonUtils.js';

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
      (gltf) => {
        // Gắn animation clip vào userData của scene để tầng trên (useMindAR) tạo
        // AnimationMixer phát. GLTFLoader trả clip RỜI khỏi scene; nếu chỉ lấy
        // gltf.scene thì mất animation -> model đứng yên (T-pose). Clip là AnimationClip
        // stateless (bind vào node theo TÊN lúc clipAction), nên dùng chung được cho mọi
        // bản clone của model — SkeletonUtils.clone giữ nguyên tên node.
        gltf.scene.userData.clips = gltf.animations ?? [];
        resolve(gltf.scene);
      },
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

// Bản SAO mới của model từ cache. BẮT BUỘC clone trước khi normalizeModel vì
// loadModel trả về CÙNG một instance (đã cache) mỗi lần, còn normalizeModel thì
// MUTATE (dịch tâm + reparent). Nếu dùng thẳng instance cache, lần khởi tạo lại
// (vd thoát Quick Look rồi bật lại MindAR) sẽ normalize lần 2 lên object đã bị
// biến đổi -> model lệch/biến mất dù anchor vẫn track. clone của SkeletonUtils
// giữ đúng cả model có xương (nhân vật người), dùng chung geometry/material nên nhẹ.
export function cloneModel(model: THREE.Group): THREE.Group {
  return cloneSkinned(model) as THREE.Group;
}

// Chuẩn hoá kích thước model về ~`scale` đơn vị và căn TÂM về gốc anchor.
// Cấu trúc lồng nhau QUAN TRỌNG: model được dịch -center ở scale gốc (căn tâm),
// rồi group `scaler` mới scale toàn bộ. Nếu scale thẳng lên `model` sau khi
// .position.sub(center) thì phần dịch tâm KHÔNG được scale theo (three.js áp
// scale trước, position sau) -> model lệch khỏi tâm. Lồng group để scale bọc
// luôn cả phép dịch tâm.
export interface NormalizeOptions {
  /** Xoay model (độ) — vd [90,0,0] để dựng đứng người khỏi thẻ nằm ngang. */
  rotationDeg?: [number, number, number];
  /** Hạ đáy model chạm mặt phẳng thẻ (chân chạm đất) thay vì căn tâm. */
  groundAlign?: boolean;
}

// Bounding box theo POSE THẬT (đã skin), KHÔNG phải geometry thô. three.js
// Box3.setFromObject với SkinnedMesh lấy box của POSITION gốc (bỏ qua skinning) ->
// sai nặng khi model rig có scale lạ ở Armature (vd Mixamo xuất scale 0.01): box nhỏ
// gấp ~100 lần thực tế -> normalizeModel chia ra hệ số phóng khổng lồ (600×+) ->
// model to vọt + văng khỏi khung -> KHÔNG thấy gì. Ở đây quét từng đỉnh ĐÃ áp bone
// transform để lấy đúng kích thước + tâm nhìn thấy. Model không rig -> fallback
// setFromObject (rẻ hơn, không cần quét đỉnh).
function posedBoundingBox(root: THREE.Object3D): THREE.Box3 {
  root.updateMatrixWorld(true);
  const box = new THREE.Box3();
  const v = new THREE.Vector3();
  let skinned = false;
  root.traverse((o) => {
    const mesh = o as THREE.SkinnedMesh;
    if (mesh.isSkinnedMesh) {
      skinned = true;
      mesh.skeleton.update();
      const pos = mesh.geometry.attributes.position;
      for (let i = 0; i < pos.count; i++) {
        // getVertexPosition trả toạ độ đỉnh SAU skinning nhưng trong hệ MESH-LOCAL;
        // phải nhân matrixWorld mới ra toạ độ THẬT (gồm cả scale 0.01 ở Armature) ->
        // đo đúng kích thước mắt nhìn. Thiếu bước này box sai không gian -> chia lệch.
        mesh.getVertexPosition(i, v);
        v.applyMatrix4(mesh.matrixWorld);
        box.expandByPoint(v);
      }
    }
  });
  return skinned ? box : box.setFromObject(root);
}

export function normalizeModel(
  model: THREE.Group,
  scale: number,
  offset: [number, number, number],
  opts?: NormalizeOptions,
): THREE.Group {
  const box = posedBoundingBox(model);
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

  // Xoay dựng đứng (nếu có) — áp trên scaler nên quay quanh tâm đã căn.
  if (opts?.rotationDeg) {
    const d = Math.PI / 180;
    scaler.rotation.set(
      opts.rotationDeg[0] * d,
      opts.rotationDeg[1] * d,
      opts.rotationDeg[2] * d,
    );
  }

  const wrapper = new THREE.Group();
  wrapper.add(scaler);

  // Hạ đáy chạm mặt phẳng thẻ: tính lại bounding box SAU khi xoay+scale, dịch
  // scaler dọc trục pháp tuyến thẻ (Z) sao cho đáy (min.z) = 0 -> chân đứng trên thẻ.
  if (opts?.groundAlign) {
    wrapper.updateMatrixWorld(true);
    const b = posedBoundingBox(scaler);
    scaler.position.z -= b.min.z;
  }

  wrapper.position.set(offset[0], offset[1], offset[2]);
  return wrapper;
}
