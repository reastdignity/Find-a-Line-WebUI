// The page of the coverage animations and images (tools/coverage_media.py): a placeholder until wave 1
// (agent B) builds it. It sets window.FAL_MEDIA once its data are loaded.
import { loadShapes } from "../data";

declare global { interface Window { FAL_MEDIA?: unknown } }

loadShapes().then(shapes => { window.FAL_MEDIA = {ready: true, shapes: shapes.features.length}; });
