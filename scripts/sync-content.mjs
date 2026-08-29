import { execFileSync } from "node:child_process";
import { randomUUID } from "node:crypto";
import {
  access,
  copyFile,
  mkdir,
  readFile,
  readdir,
  rename,
  rm,
} from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const DATA_FILES = [
  "characters.json",
  "items.json",
  "monsters.json",
  "shops.json",
  "skills.json",
  "spells.json",
  "texts.json",
];

const projectRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const contentRoot = path.resolve(
  process.env.DA0_CONTENT_DIR ?? path.join(projectRoot, "content"),
);
const sourceDir = path.join(contentRoot, "data");
const targetDir = path.join(projectRoot, "app", "data");
const checkOnly = process.argv.includes("--check");

async function exists(target) {
  try {
    await access(target);
    return true;
  } catch {
    return false;
  }
}

async function validateSource() {
  const validator = path.join(contentRoot, "scripts", "validate.mjs");

  if (!await exists(validator)) {
    throw new Error(
      `共有コンテンツが初期化されていません: ${contentRoot}\n` +
        "npm run content:init を実行してください。",
    );
  }

  execFileSync(process.execPath, [validator], {
    cwd: contentRoot,
    stdio: "inherit",
  });

  for (const file of DATA_FILES) {
    const value = JSON.parse(await readFile(path.join(sourceDir, file), "utf8"));
    if (!Array.isArray(value)) {
      throw new Error(`${file} のルートは配列である必要があります。`);
    }
  }
}

async function checkSync() {
  const problems = [];

  for (const file of DATA_FILES) {
    const source = await readFile(path.join(sourceDir, file));
    const targetPath = path.join(targetDir, file);
    if (!await exists(targetPath)) {
      problems.push(`${file}: app/data にありません`);
      continue;
    }

    const target = await readFile(targetPath);
    if (!source.equals(target)) {
      problems.push(`${file}: 共有コンテンツと内容が異なります`);
    }
  }

  if (await exists(targetDir)) {
    const unexpected = (await readdir(targetDir))
      .filter((file) => file.endsWith(".json") && !DATA_FILES.includes(file));
    for (const file of unexpected) {
      problems.push(`${file}: app/data に未定義のJSONがあります`);
    }
  }

  if (problems.length > 0) {
    throw new Error(`同期チェックに失敗しました:\n- ${problems.join("\n- ")}`);
  }

  console.log("app/data は共有コンテンツと一致しています。");
}

async function sync() {
  const appDir = path.join(projectRoot, "app");
  const token = randomUUID();
  const stagingDir = path.join(appDir, `.data-staging-${token}`);
  const backupDir = path.join(appDir, `.data-backup-${token}`);
  let backedUp = false;

  await mkdir(stagingDir, { recursive: false });

  try {
    await Promise.all(
      DATA_FILES.map((file) => copyFile(
        path.join(sourceDir, file),
        path.join(stagingDir, file),
      )),
    );

    if (await exists(targetDir)) {
      await rename(targetDir, backupDir);
      backedUp = true;
    }

    await rename(stagingDir, targetDir);
    if (backedUp) {
      await rm(backupDir, { recursive: true, force: true });
    }
  } catch (error) {
    await rm(stagingDir, { recursive: true, force: true });
    if (backedUp && !await exists(targetDir)) {
      await rename(backupDir, targetDir);
    }
    throw error;
  }

  let revision = "unknown";
  try {
    revision = execFileSync("git", ["rev-parse", "--short", "HEAD"], {
      cwd: contentRoot,
      encoding: "utf8",
    }).trim();
  } catch {
    // DA0_CONTENT_DIR may point to an unpacked copy during local testing.
  }

  console.log(`app/data を共有コンテンツ ${revision} から同期しました。`);
}

try {
  await validateSource();
  if (checkOnly) {
    await checkSync();
  } else {
    await sync();
  }
} catch (error) {
  console.error(error.message);
  process.exitCode = 1;
}
