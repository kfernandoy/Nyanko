import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { execSync } from "node:child_process";
import sharp from "sharp";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const desktopRoot = path.resolve(__dirname, "..");
const svgPath = path.join(desktopRoot, "src-tauri", "app-icon.svg");
const iconsDir = path.join(desktopRoot, "src-tauri", "icons");

fs.mkdirSync(iconsDir, { recursive: true });

const svgBuffer = fs.readFileSync(svgPath);
const iconPng = path.join(iconsDir, "icon.png");

await sharp(svgBuffer).resize(1024, 1024, { fit: "fill" }).png().toFile(iconPng);

execSync("npm run tauri --workspace @nyanko/desktop -- icon src-tauri/icons/icon.png", {
  cwd: desktopRoot,
  stdio: "inherit",
});

console.log(`Icons generated in ${iconsDir}`);
