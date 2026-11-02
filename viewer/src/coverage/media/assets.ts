// What the scenes draw from, loaded once by main.ts before window.FAL_MEDIA is set: the outlines, the 30 m
// against 1 m comparison (contrast.json and its hillshades from ./contrast/) and the fonts.
import { loadShapes } from "../data";
import { prepareWorld, type World } from "../draw/world";
import type { Contrast } from "../types";

export interface Assets {
  world: World;
  contrast: Contrast;
  images: Map<string, HTMLImageElement>;   // "<place>-fine", "<place>-coarse"
  year: number;                            // fills "{year}" of the credits
}

export const CONTRAST_DIR = "contrast/";

let assets: Assets | null = null;

export function got(): Assets {
  if (!assets) throw new Error("the media page's data are not loaded yet");
  return assets;
}

function image(url: string): Promise<HTMLImageElement> {
  const im = new Image();
  im.src = url;
  return im.decode().then(() => im);
}

const FONT_FACES = ["500", "600", "700"].map(weight => `${weight} 40px "Barlow Condensed"`);

export async function load(): Promise<Assets> {
  const [shapes, contrast] = await Promise.all([
    loadShapes(),
    fetch(`${CONTRAST_DIR}contrast.json`).then(answer => {
      if (!answer.ok) throw new Error(`contrast.json: HTTP ${answer.status}`);
      return answer.json() as Promise<Contrast>;
    }),
  ]);
  const images = new Map<string, HTMLImageElement>();
  await Promise.all(Object.entries(contrast.places).flatMap(([place, d]) => (["fine", "coarse"] as const).map(async side => {
    images.set(`${place}-${side}`, await image(CONTRAST_DIR + d[side].image));
  })));
  // both subsets (latin and latin-ext, the Polish letters) of every weight, before the first frame
  await Promise.all(FONT_FACES.map(face => document.fonts.load(face, "AZaz09ŻżĄąŁł")));
  assets = {world: prepareWorld(shapes), contrast, images, year: new Date().getFullYear()};
  return assets;
}
