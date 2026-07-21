const path = require("path")

const DATA_DIR = path.join(__dirname, "../packages/data")
const SHARED_DATA_DIR =
  process.env.SHARED_DATA_DIR || "/Users/shiromofufactory/Documents/pyxel/DATranslate/da0"

// doGet / doPost をデプロイした同一の GAS ウェブアプリ URL。
const GAS_URL =
  process.env.GAS_URL ||
  "https://script.google.com/macros/s/AKfycbwvFXZvu-p2wvdQ6fGfLsyX2gaXpcz-x0AMQNAd31WDBmQD7UXJwwSfgCiz7OpdhUAq/exec"

const DATASETS = [
  { key: "items", lineBreakFields: [] },
  { key: "spells", lineBreakFields: ["description_ja", "description_en"] },
  { key: "skills", lineBreakFields: ["description_ja", "description_en"] },
  { key: "characters", lineBreakFields: ["skills"] },
]

module.exports = { DATA_DIR, DATASETS, GAS_URL, SHARED_DATA_DIR }
