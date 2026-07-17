import * as THREE from 'three';
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js';
import { DRACOLoader } from 'three/examples/jsm/loaders/DRACOLoader.js';

// Phiên WebXR immersive-AR (Android Chrome): quét mặt sàn bằng hit-test -> chạm để
// ĐẶT model cỡ thật xuống sàn, model được GHIM vào không gian (world-locked) nên người
// dùng đi ra/vào/vòng quanh soi thoải mái. Vẫn ở TRONG trang web -> AI/animation chạy được.
// Khác hẳn MindAR (dán vào thẻ) và Quick Look (viewer hệ thống, không AI).

export interface WebXRHandlers {
  /** phiên đã mở xong (nên tắt MindAR để nhường camera) */
  onSessionStart: () => void;
  /** đang quét sàn, chờ người dùng chạm để đặt */
  onSearching: () => void;
  /** đã đặt model xuống sàn */
  onPlaced: () => void;
  /** phiên kết thúc (thoát AR) */
  onEnd: () => void;
  onError: (msg: string) => void;
}

export interface WebXRController {
  end: () => void;
  /** cho phép đặt lại vị trí model */
  replace: () => void;
}

// Tải GLB kèm animation (khác loadModel ở modelLoader: cái đó bỏ animations).
function loadGLTFWithAnim(url: string): Promise<{
  scene: THREE.Group;
  animations: THREE.AnimationClip[];
}> {
  const loader = new GLTFLoader();
  const draco = new DRACOLoader();
  draco.setDecoderPath('https://www.gstatic.com/draco/versioned/decoders/1.5.6/');
  loader.setDRACOLoader(draco);
  return new Promise((resolve, reject) => {
    loader.load(
      url,
      (gltf) => resolve({ scene: gltf.scene, animations: gltf.animations }),
      undefined,
      (err) => reject(err),
    );
  });
}

export async function startWebXRSession(
  modelUrl: string,
  overlayRoot: HTMLElement,
  handlers: WebXRHandlers,
): Promise<WebXRController | null> {
  const xr = navigator.xr;
  if (!xr) {
    handlers.onError('Thiết bị không hỗ trợ WebXR.');
    return null;
  }

  // requestSession PHẢI gọi trong cùng user-gesture -> gọi ngay, không await gì trước nó.
  let session: XRSession;
  try {
    session = await xr.requestSession('immersive-ar', {
      requiredFeatures: ['hit-test'],
      optionalFeatures: ['dom-overlay', 'local-floor'],
      domOverlay: { root: overlayRoot },
    });
  } catch (err) {
    handlers.onError(`Không vào được AR: ${(err as Error)?.message ?? ''}`);
    return null;
  }

  handlers.onSessionStart();

  const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
  renderer.setPixelRatio(window.devicePixelRatio);
  renderer.setSize(window.innerWidth, window.innerHeight);
  renderer.xr.enabled = true;
  renderer.xr.setReferenceSpaceType('local');
  await renderer.xr.setSession(session);

  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(); // WebXR tự ghi đè ma trận camera

  scene.add(new THREE.HemisphereLight(0xffffff, 0x444444, 1.2));
  const dirLight = new THREE.DirectionalLight(0xffffff, 1.0);
  dirLight.position.set(0.5, 1, 0.5);
  scene.add(dirLight);

  // Vòng ngắm (reticle) hiện trên sàn dò được
  const reticle = new THREE.Mesh(
    new THREE.RingGeometry(0.07, 0.09, 32).rotateX(-Math.PI / 2),
    new THREE.MeshBasicMaterial({ color: 0x00ffcc }),
  );
  reticle.matrixAutoUpdate = false;
  reticle.visible = false;
  scene.add(reticle);

  // Bọc model, hạ chân về y=0 -> đặt reticle là chân chạm đúng sàn.
  // (KHÔNG scale — dùng GLB cỡ mét thật để ra đúng cỡ người thật.)
  const modelWrap = new THREE.Group();
  modelWrap.visible = false;
  scene.add(modelWrap);
  let mixer: THREE.AnimationMixer | null = null;

  loadGLTFWithAnim(modelUrl)
    .then(({ scene: gltfScene, animations }) => {
      const box = new THREE.Box3().setFromObject(gltfScene);
      gltfScene.position.y -= box.min.y; // chân xuống đáy wrap
      modelWrap.add(gltfScene);
      if (animations.length > 0) {
        mixer = new THREE.AnimationMixer(gltfScene);
        mixer.clipAction(animations[0]).play();
      }
    })
    .catch((err) => {
      console.warn('[webxr] load model lỗi:', err);
    });

  let placed = false;
  const viewerSpace = await session.requestReferenceSpace('viewer');
  const localSpace = renderer.xr.getReferenceSpace();
  const hitTestSource = await session.requestHitTestSource?.({ space: viewerSpace });

  handlers.onSearching();

  // Chạm màn hình -> đặt model tại vị trí reticle, xoay mặt về phía người dùng.
  const onSelect = () => {
    if (placed || !reticle.visible) return;
    modelWrap.position.setFromMatrixPosition(reticle.matrix);
    const camPos = new THREE.Vector3().setFromMatrixPosition(camera.matrixWorld);
    modelWrap.rotation.y = Math.atan2(
      camPos.x - modelWrap.position.x,
      camPos.z - modelWrap.position.z,
    );
    modelWrap.visible = true;
    placed = true;
    reticle.visible = false;
    handlers.onPlaced();
  };
  session.addEventListener('select', onSelect);

  const clock = new THREE.Clock();
  renderer.setAnimationLoop((_time, frame?: XRFrame) => {
    if (frame && hitTestSource && localSpace && !placed) {
      const results = frame.getHitTestResults(hitTestSource);
      if (results.length > 0) {
        const pose = results[0].getPose(localSpace);
        if (pose) {
          reticle.visible = true;
          reticle.matrix.fromArray(pose.transform.matrix);
        }
      } else {
        reticle.visible = false;
      }
    }
    if (mixer) mixer.update(clock.getDelta());
    renderer.render(scene, camera);
  });

  const onEnd = () => {
    session.removeEventListener('select', onSelect);
    session.removeEventListener('end', onEnd);
    try {
      hitTestSource?.cancel();
    } catch {
      /* noop */
    }
    renderer.setAnimationLoop(null);
    try {
      renderer.dispose();
    } catch {
      /* noop */
    }
    handlers.onEnd();
  };
  session.addEventListener('end', onEnd);

  return {
    end: () => {
      try {
        session.end();
      } catch {
        /* noop */
      }
    },
    replace: () => {
      placed = false;
      modelWrap.visible = false;
    },
  };
}
