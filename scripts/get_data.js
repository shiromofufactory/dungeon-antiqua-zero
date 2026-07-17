const axios = require("axios")
const fs = require("fs")
const path = require("path")
const { DATA_DIR, GAS_URL, SHARED_DATA_DIR } = require("./config")

const save = (fname, json) => {
  const filename = fname + ".json"
  const localFile = path.join(DATA_DIR, filename)
  const sharedFile = path.join(SHARED_DATA_DIR, filename)

  fs.mkdirSync(DATA_DIR, { recursive: true })
  fs.mkdirSync(SHARED_DATA_DIR, { recursive: true })
  fs.writeFileSync(localFile, JSON.stringify(json, null, 2) + "\n")
  fs.copyFileSync(localFile, sharedFile)
  console.log(`${filename} を共有フォルダへコピーしました`)
}

const isNumeric = (value) => value !== "" && !isNaN(value)

async function main() {
  const { data: dataAll } = await axios.get(GAS_URL)
  saveData(dataAll.items, "items")
  saveData(dataAll.spells, "spells")
  saveData(dataAll.skills, "skills")
  // getMonsters(dataAll.monsters)
}

function saveData(data, fname) {
  const json = []
  data.forEach((item) => {
    const output = {}
    for (key in item) {
      let result = item[key]
      if (isNumeric(result)) {
        result = result * 1
      }
      if (key == "description_ja" || key == "description_en") {
        result = (result || "").split("\n")
      }
      output[key] = result
    }
    json.push(output)
  })
  save(fname, json)
}



main()
