const axios = require("axios")
const fs = require("fs")
const path = require("path")
const { DATA_DIR, GAS_URL, SHARED_DATA_DIR } = require("./config")

const DATASETS = [
  {
    key: "items",
    file: process.env.ITEMS_JSON || path.join(DATA_DIR, "items.json"),
    localFile: path.join(DATA_DIR, "items.json"),
    sharedFile: path.join(SHARED_DATA_DIR, "items.json"),
    lineBreakFields: [],
  },
  {
    key: "spells",
    file: process.env.SPELLS_JSON || path.join(DATA_DIR, "spells.json"),
    localFile: path.join(DATA_DIR, "spells.json"),
    sharedFile: path.join(SHARED_DATA_DIR, "spells.json"),
    // get_data.js ではこれらを改行単位の配列に変換しているため、シート用に戻す。
    lineBreakFields: ["description_ja", "description_en"],
  },
  {
    key: "skills",
    file: process.env.SKILLS_JSON || path.join(DATA_DIR, "skills.json"),
    localFile: path.join(DATA_DIR, "skills.json"),
    sharedFile: path.join(SHARED_DATA_DIR, "skills.json"),
    lineBreakFields: ["description_ja", "description_en"],
  },
]

function copyFromSharedFolder() {
  DATASETS.forEach(({ localFile, sharedFile }) => {
    if (!fs.existsSync(sharedFile)) {
      throw new Error(`共有フォルダにファイルがありません: ${sharedFile}`)
    }
    fs.mkdirSync(path.dirname(localFile), { recursive: true })
    fs.copyFileSync(sharedFile, localFile)
    console.log(`${path.basename(sharedFile)} を共有フォルダからコピーしました`)
  })
}

function loadDataset({ file, key, lineBreakFields }) {
  const records = JSON.parse(fs.readFileSync(file, "utf8"))
  if (!Array.isArray(records)) {
    throw new Error(`${file} は ${key} の配列 JSON である必要があります`)
  }

  return records.map((record) => {
    const output = { ...record }
    lineBreakFields.forEach((field) => {
      if (Array.isArray(output[field])) output[field] = output[field].join("\n")
    })
    return output
  })
}

async function main() {
  copyFromSharedFolder()

  const payload = { token: process.env.GAS_SYNC_TOKEN || "" }
  DATASETS.forEach((dataset) => {
    payload[dataset.key] = loadDataset(dataset)
  })

  const { data } = await axios.post(
    GAS_URL,
    payload,
    { headers: { "Content-Type": "application/json" } },
  )

  if (!data || data.ok !== true) {
    throw new Error(`GAS への反映に失敗しました: ${JSON.stringify(data)}`)
  }
  Object.entries(data.updated).forEach(([key, result]) => {
    console.log(`${key}: ${result.sheet} シートへ ${result.updatedRows} 行を反映しました。`)
  })
}

main().catch((error) => {
  console.error(error.response?.data || error.message)
  process.exitCode = 1
})
