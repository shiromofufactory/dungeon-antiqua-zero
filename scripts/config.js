const path = require("path")

const DATA_DIR = path.join(__dirname, "../packages/data")
const SHARED_DATA_DIR =
  process.env.SHARED_DATA_DIR || "/Users/shiromofufactory/Documents/pyxel/DATranslate/da0"

// doGet / doPost をデプロイした同一の GAS ウェブアプリ URL。
const GAS_URL =
  process.env.GAS_URL ||
  "https://script.google.com/macros/s/AKfycbwLPb_Ry07KPHVu_q9Csc4t8bNrLH04paMU0Rpa5xNkiMfWb0ivL4M7vf3-tvMmzGxD/exec"

const DATASETS = [
  { key: "items", lineBreakFields: [] },
  { key: "spells", lineBreakFields: ["description_ja", "description_en"] },
  { key: "skills", lineBreakFields: ["description_ja", "description_en"] },
  { key: "characters", lineBreakFields: ["skills", "equips"] },
  { key: "shops", lineBreakFields: ["items"] },
  { key: "monsters", lineBreakFields: ["monsters"] },
]

module.exports = { DATA_DIR, DATASETS, GAS_URL, SHARED_DATA_DIR }
