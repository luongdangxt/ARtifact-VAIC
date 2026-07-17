// mind-ar không kèm type. Khai báo tối thiểu cho MindARThree ta dùng.
declare module 'mind-ar/dist/mindar-image-three.prod.js' {
  import type { Scene, PerspectiveCamera, WebGLRenderer, Group, Object3D } from 'three';

  export interface MindARAnchor {
    group: Group;
    onTargetFound?: () => void;
    onTargetLost?: () => void;
    targetIndex: number;
  }

  export interface MindARThreeOptions {
    container: HTMLElement;
    imageTargetSrc: string;
    maxTrack?: number;
    uiScanning?: boolean | string;
    uiLoading?: boolean | string;
    uiError?: boolean | string;
    filterMinCF?: number;
    filterBeta?: number;
    warmupTolerance?: number;
    missTolerance?: number;
  }

  export class MindARThree {
    constructor(options: MindARThreeOptions);
    renderer: WebGLRenderer;
    scene: Scene;
    camera: PerspectiveCamera;
    addAnchor(targetIndex: number): MindARAnchor;
    addCSSAnchor(targetIndex: number): MindARAnchor;
    start(): Promise<void>;
    stop(): void;
    add(object: Object3D): void;
  }
}
