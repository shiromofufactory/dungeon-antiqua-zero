const path = require("path")

const DATA_DIR = path.join(__dirname, "../packages/data")
const SHARED_DATA_DIR =
  process.env.SHARED_DATA_DIR || "/Users/shiromofufactory/Documents/pyxel/DATranslate/da0"

// doGet / doPost をデプロイした同一の GAS ウェブアプリ URL。
const GAS_URL =
  process.env.GAS_URL ||
  "https://script.google.com/macros/s/AKfycbwxscVRBi7IlXzHEUrlvOguyaul5zBV8uzEZ3o4wVE1h1hiVa0J536kJwuGNnmIEE4s/exec"

module.exports = { DATA_DIR, GAS_URL, SHARED_DATA_DIR }
