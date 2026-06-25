import { cp, mkdir, readFile, rm, writeFile } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
for (const target of ["chromium", "firefox"]) {
  const destination = resolve(root, "dist", target);
  await rm(destination, { recursive: true, force: true });
  await mkdir(destination, { recursive: true });
  await cp(resolve(root, "src"), destination, { recursive: true });
  const manifest = await readFile(resolve(root, `manifest.${target}.json`), "utf8");
  await writeFile(resolve(destination, "manifest.json"), manifest);
}
