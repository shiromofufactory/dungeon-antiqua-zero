const axios = require("axios")
const fs = require("fs")
const path = require("path")
const { DATA_DIR, DATASETS: DATASET_CONFIG, GAS_URL, SHARED_DATA_DIR } = require("./config")

const DATASETS = DATASET_CONFIG.map(({ key, lineBreakFields }) => {
  const filename = `${key}.json`
  return {
    key,
    file: process.env[`${key.toUpperCase()}_JSON`] || path.join(DATA_DIR, filename),
    localFile: path.join(DATA_DIR, filename),
    sharedFile: path.join(SHARED_DATA_DIR, filename),
    lineBreakFields,
  }
})

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
