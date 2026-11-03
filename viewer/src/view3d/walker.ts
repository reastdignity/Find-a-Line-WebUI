// The walker: a mannequin of 1.7 m made of three.js primitives, its feet at the group's origin, facing +Z
// (scene.ts turns it along the line with webbing.ts walkerPose's yaw). Arms out for balance.

import {
  CapsuleGeometry, Group, Mesh, MeshLambertMaterial, SphereGeometry, type BufferGeometry,
} from "three";
import { WALKER_HEIGHT } from "./webbing";

export interface Walker {
  group: Group;
  dispose(): void;
}

export function createWalker(color: string): Walker {
  const group = new Group(), material = new MeshLambertMaterial({color});
  const geometries: BufferGeometry[] = [];
  const part = (geometry: BufferGeometry, x: number, y: number, z: number, roll = 0) => {
    geometries.push(geometry);
    const mesh = new Mesh(geometry, material);
    mesh.position.set(x, y, z);
    mesh.rotation.z = roll;
    group.add(mesh);
    return mesh;
  };
  const scale = WALKER_HEIGHT / 1.7;
  // Legs (0 to 0.85 m), the torso (0.85 to 1.45 m), the head (to 1.7 m), arms spread sideways
  const leg = () => new CapsuleGeometry(0.06 * scale, 0.73 * scale, 4, 8);
  part(leg(), -0.09 * scale, 0.425 * scale, 0, 0.06);
  part(leg(), 0.09 * scale, 0.425 * scale, 0, -0.06);
  part(new CapsuleGeometry(0.15 * scale, 0.32 * scale, 4, 10), 0, 1.16 * scale, 0);
  part(new SphereGeometry(0.11 * scale, 14, 10), 0, 1.59 * scale, 0);
  const arm = () => new CapsuleGeometry(0.045 * scale, 0.55 * scale, 4, 8);
  part(arm(), -0.42 * scale, 1.30 * scale, 0, Math.PI / 2 - 0.35);
  part(arm(), 0.42 * scale, 1.30 * scale, 0, -(Math.PI / 2 - 0.35));
  return {
    group,
    dispose() { for (const g of geometries) g.dispose(); material.dispose(); },
  };
}
