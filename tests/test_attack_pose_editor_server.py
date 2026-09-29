from __future__ import annotations

import io
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import threading
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen
import zipfile

from PIL import Image

from app.attack_pose import load_attack_poses
from tools.attack_pose_editor.server import (
    AttackPoseApplication,
    create_server,
    initial_document,
    validate_document,
)


class AttackPoseEditorServerTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = TemporaryDirectory()
        root = Path(self.temporary.name)
        self.content_root = root / "content"
        self.app_root = root / "app"
        character_root = self.content_root / "images" / "characters"
        character_root.mkdir(parents=True)
        sheet = Image.new("P", (160, 128), 1)
        sheet.putpalette([0, 0, 0, 255, 0, 128] + [0, 0, 0] * 254)
        sheet.info["transparency"] = 1
        sheet.putpixel((0, 96), 0)
        sheet.save(character_root / "ch_battle.gif", transparency=1)

        data_root = self.content_root / "data"
        data_root.mkdir(parents=True)
        (data_root / "characters.json").write_text(json.dumps([
            {"name_en": "Fiora", "name_ja": "フィオラ", "battle_sprite": 0, "race": "FAIRY"},
            {"name_en": "Cerion", "name_ja": "セリオン", "battle_sprite": 1, "race": "FAIRY"},
            {"name_en": "Alvan", "name_ja": "アルヴァン", "battle_sprite": 2, "race": "FAIRY"},
            {"name_en": "Elika", "name_ja": "エリカ", "battle_sprite": 3, "race": "HUMAN"},
        ]), encoding="utf-8")
        (data_root / "texts.json").write_text(json.dumps([
            {"text_key": "race.FAIRY", "text_ja": "ようせい"},
            {"text_key": "race.HUMAN", "text_ja": "にんげん"},
        ]), encoding="utf-8")
        (data_root / "items.json").write_text(json.dumps([
            {"name_en": "BRONZE SWORD", "weapon_img": "SWORD-1"},
            {"name_en": "IRON SWORD", "weapon_img": "SWORD-1"},
            {"name_en": "BRONZE SPEAR", "weapon_img": "SPEAR-1"},
            {"name_en": "POTION", "weapon_img": ""},
        ]), encoding="utf-8")

        self.app_root.mkdir()
        (self.app_root / "assets.pyxpal").write_text("000000\nFF0080\nFFFFFF\n", encoding="utf-8")
        rows = [[1] * 256 for _ in range(48)]
        rows[32][0] = 2
        resource = "format_version = 1\n\n[[images]]\nwidth = 256\nheight = 256\ndata = " + json.dumps(rows)
        with zipfile.ZipFile(self.app_root / "assets.pyxres", "w") as archive:
            archive.writestr("pyxel_resource.toml", resource)

        self.application = AttackPoseApplication(
            self.content_root,
            self.app_root,
            token="test-token",
        )
        self.server = create_server(self.application, 0)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base_url = f"http://127.0.0.1:{self.server.server_address[1]}"

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        self.temporary.cleanup()

    def get_json(self, path: str) -> dict:
        with urlopen(f"{self.base_url}{path}", timeout=2) as response:
            return json.loads(response.read())

    def post_json(self, data: object) -> dict:
        request = Request(
            f"{self.base_url}/api/save",
            data=json.dumps({"data": data}).encode(),
            method="POST",
            headers={"Content-Type": "application/json", "X-Attack-Pose-Token": "test-token"},
        )
        with urlopen(request, timeout=2) as response:
            return json.loads(response.read())

    def test_loads_initial_document_and_four_character_catalog(self) -> None:
        payload = self.get_json("/api/document?token=test-token")
        self.assertTrue(payload["is_new"])
        self.assertEqual(payload["data"]["poses"][0]["id"], "SWORD-1_1")
        self.assertEqual(payload["data"]["poses"][0]["weapon_img"], "SWORD-1")
        self.assertEqual(payload["data"]["poses"][0]["branch"], "1")
        self.assertEqual(payload["weapon_img_options"], ["SWORD-1", "SPEAR-1"])
        self.assertEqual([item["key"] for item in payload["characters"]], ["Fiora", "Cerion", "Alvan", "Elika"])
        self.assertEqual(payload["characters"][3]["name"], "エリカ")
        self.assertEqual(payload["characters"][3]["battle_sprite"], 3)
        self.assertEqual([item["race"] for item in payload["characters"]], ["FAIRY", "FAIRY", "FAIRY", "HUMAN"])
        self.assertEqual(payload["races"][:2], [
            {"key": "FAIRY", "name": "ようせい"},
            {"key": "HUMAN", "name": "にんげん"},
        ])

        with self.assertRaises(HTTPError) as context:
            self.get_json("/api/document")
        self.assertEqual(context.exception.code, 403)

    def test_serves_transparent_sprite_sheets(self) -> None:
        for endpoint, expected_size in (("characters.png", (160, 128)), ("weapons.png", (256, 16))):
            with urlopen(f"{self.base_url}/api/{endpoint}?token=test-token", timeout=2) as response:
                image = Image.open(io.BytesIO(response.read()))
                self.assertEqual(image.size, expected_size)
                self.assertEqual(image.mode, "RGBA")
                if endpoint == "characters.png":
                    self.assertEqual(image.getpixel((0, 96)), (0, 0, 0, 255))
        with urlopen(f"{self.base_url}/api/weapons.png?token=test-token", timeout=2) as response:
            weapon = Image.open(io.BytesIO(response.read()))
            self.assertEqual(weapon.getpixel((0, 0)), (255, 255, 255, 255))
            self.assertEqual(weapon.getpixel((1, 0))[3], 0)

    def test_saves_multiple_valid_poses(self) -> None:
        data = initial_document()
        second = json.loads(json.dumps(data["poses"][0]))
        second["id"] = "SWORD-1_slash_finish"
        second["branch"] = "slash_finish"
        second["character_pose"] = 2
        second["race_y_offsets"] = {"FAIRY": -3, "HUMAN": 2}
        second["weapons"][0].update({
            "position": [-10, 9],
            "layer": "back",
            "flip_x": True,
            "flip_y": True,
        })
        second["weapons"].append({
            "image": 2,
            "position": [-8, 9],
            "layer": "front",
            "flip_x": False,
            "flip_y": True,
        })
        data["poses"].append(second)
        result = self.post_json(data)
        self.assertTrue(result["saved"])
        self.assertTrue(result["compiled"])
        saved = json.loads(self.application.source_path.read_text(encoding="utf-8"))
        self.assertEqual(len(saved["poses"]), 2)
        self.assertEqual([pose["id"] for pose in saved["poses"]], ["SWORD-1_1", "SWORD-1_slash_finish"])
        self.assertNotIn("character_position", saved["poses"][1])
        self.assertEqual(len(saved["poses"][1]["weapons"]), 2)
        self.assertEqual(saved["poses"][1]["weapons"][0]["position"], [-10, 9])
        self.assertTrue(saved["poses"][1]["weapons"][0]["flip_x"])
        self.assertTrue(saved["poses"][1]["weapons"][1]["flip_y"])
        self.assertEqual(saved["poses"][1]["race_y_offsets"], {"FAIRY": -3, "HUMAN": 2})
        runtime_poses = load_attack_poses(self.application.generated_path)
        self.assertEqual(runtime_poses["SWORD-1_slash_finish"].weapon_y_offset("HUMAN"), 2)
        self.assertEqual(
            [pose.to_record() for pose in runtime_poses.values()],
            saved["poses"],
        )

    def test_rejects_invalid_pose_data(self) -> None:
        data = initial_document()
        data["poses"][0]["character_pose"] = 9
        result = self.post_json(data)
        self.assertFalse(result["saved"])
        self.assertEqual(result["diagnostics"][0]["code"], "invalid_character_pose")
        self.assertFalse(self.application.source_path.exists())
        self.assertFalse(self.application.generated_path.exists())

    def test_validation_rejects_duplicate_ids_and_invalid_positions(self) -> None:
        data = initial_document()
        data["poses"].append(json.loads(json.dumps(data["poses"][0])))
        data["poses"][1]["weapons"][0]["position"] = [0, 1.5]
        codes = {item["code"] for item in validate_document(data)}
        self.assertEqual(codes, {"duplicate_id", "invalid_position"})

        empty = {"format_version": 1, "poses": []}
        self.assertEqual(validate_document(empty)[0]["code"], "empty_poses")

    def test_rejects_unknown_weapon_img_and_mismatched_generated_id(self) -> None:
        data = initial_document()
        data["poses"][0]["weapon_img"] = "UNKNOWN-1"
        data["poses"][0]["id"] = "UNKNOWN-1_1"
        result = self.post_json(data)
        self.assertFalse(result["saved"])
        self.assertEqual(result["diagnostics"][0]["code"], "unknown_weapon_img")

        data = initial_document()
        data["poses"][0]["id"] = "SWORD-1_wrong"
        self.assertEqual(validate_document(data)[0]["code"], "invalid_id")

    def test_rejects_more_than_two_weapons(self) -> None:
        data = initial_document()
        weapon = json.loads(json.dumps(data["poses"][0]["weapons"][0]))
        data["poses"][0]["weapons"].extend([weapon, weapon])
        self.assertEqual(validate_document(data)[0]["code"], "invalid_weapons")

    def test_rejects_invalid_race_y_offsets(self) -> None:
        for offsets in ({"FAIRY": 129}, {"HUMAN": 1.5}, {"FAIRY": True}, {"UNKNOWN": 1}):
            with self.subTest(offsets=offsets):
                data = initial_document()
                data["poses"][0]["race_y_offsets"] = offsets
                self.assertEqual(validate_document(data)[0]["code"], "invalid_race_y_offset")

    def test_static_ui_exposes_three_panes_and_pixel_controls(self) -> None:
        with urlopen(f"{self.base_url}/?token=test-token", timeout=2) as response:
            page = response.read().decode("utf-8")
        with urlopen(f"{self.base_url}/app.js", timeout=2) as response:
            script = response.read().decode("utf-8")
        with urlopen(f"{self.base_url}/styles.css", timeout=2) as response:
            styles = response.read().decode("utf-8")
        self.assertIn('class="panel character-panel"', page)
        self.assertIn('class="panel main-panel"', page)
        self.assertIn('class="panel weapon-panel"', page)
        self.assertIn('class="panel preset-panel"', page)
        self.assertNotIn('id="character-x"', page)
        self.assertIn('id="origin-x" type="number"', page)
        self.assertIn('id="race-offset-grid"', page)
        self.assertIn('function renderRaceOffsets()', script)
        self.assertIn('weapon.position[1] + weaponYOffset()', script)
        self.assertIn('data-target="weapon_1"', page)
        self.assertIn('id="toggle-second-weapon"', page)
        self.assertIn('id="pose-weapon-img"', page)
        self.assertIn('id="pose-branch"', page)
        self.assertIn('id="pose-id-readout"', page)
        self.assertIn('class="preset-fields"', page)
        self.assertIn("ハンドルをドラッグして並び替え", page)
        self.assertIn('data-layer="front"', page)
        self.assertIn('data-flip="flip_x"', page)
        self.assertIn('data-flip="flip_y"', page)
        self.assertIn('<span>8× zoom</span>', page)
        self.assertIn('for (let index = 0; index < 9; index += 1)', script)
        self.assertIn('for (let index = 0; index < 16; index += 1)', script)
        self.assertIn('context.scale(weapon.flip_x ? -1 : 1, weapon.flip_y ? -1 : 1)', script)
        self.assertIn("function reorderPose(fromIndex, targetIndex, placeAfter)", script)
        self.assertIn("function composePoseId(weaponImg, branch)", script)
        self.assertIn('handle.addEventListener("dragstart"', script)
        self.assertNotIn("character_position", script)
        self.assertIn("minmax(556px, 580px) minmax(500px, 1fr)", styles)
        self.assertIn("grid-template-columns: repeat(2, minmax(240px, 1fr))", styles)
        self.assertNotIn("max-height: 310px", styles)


if __name__ == "__main__":
    unittest.main()
