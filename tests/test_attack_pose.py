from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from app.attack_pose import (
    AttackPoseDataError,
    attack_sequence,
    load_attack_poses,
    parse_attack_poses,
)


def document() -> dict[str, object]:
    return {
        "format_version": 1,
        "poses": [
            {
                "id": "SPEAR-1_2",
                "weapon_img": "SPEAR-1",
                "branch": "2",
                "character_pose": 2,
                "weapons": [
                    {
                        "image": 10,
                        "position": [-27, 6],
                        "layer": "back",
                        "flip_x": False,
                        "flip_y": False,
                    },
                    {
                        "image": 11,
                        "position": [-11, 6],
                        "layer": "front",
                        "flip_x": True,
                        "flip_y": False,
                    },
                ],
            },
            {
                "id": "SPEAR-1_1",
                "weapon_img": "SPEAR-1",
                "branch": "1",
                "character_pose": 0,
                "weapons": [
                    {
                        "image": 10,
                        "position": [-12, 7],
                        "layer": "back",
                        "flip_x": False,
                        "flip_y": False,
                    }
                ],
            },
        ],
    }


class AttackPoseTest(unittest.TestCase):
    def test_loads_two_weapon_composite_and_orders_basic_branches(self) -> None:
        poses = parse_attack_poses(document())

        spear = poses["SPEAR-1_2"]
        self.assertEqual(spear.character_pose, 2)
        self.assertEqual(len(spear.weapons), 2)
        self.assertEqual(spear.weapons[0].position_x, -27)
        self.assertTrue(spear.weapons[1].flip_x)
        self.assertEqual(
            tuple(pose.branch for pose in attack_sequence(poses, "SPEAR-1")),
            ("1", "2"),
        )

    def test_selects_dual_wield_branches_without_reusing_primary_poses(self) -> None:
        source = document()
        source["poses"].extend(
            [
                {
                    **source["poses"][0],
                    "id": "SPEAR-1_4",
                    "branch": "4",
                },
                {
                    **source["poses"][1],
                    "id": "SPEAR-1_3",
                    "branch": "3",
                },
            ]
        )
        poses = parse_attack_poses(source)

        self.assertEqual(
            tuple(
                pose.branch
                for pose in attack_sequence(
                    poses,
                    "SPEAR-1",
                    branches=("3", "4"),
                )
            ),
            ("3", "4"),
        )
        self.assertEqual(
            attack_sequence(poses, "UNKNOWN", branches=("3", "4")),
            (),
        )

        primary_only = parse_attack_poses(document())
        self.assertEqual(
            attack_sequence(primary_only, "SPEAR-1", branches=("3", "4")),
            (),
        )

    def test_loads_json_from_runtime_path(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "attack_poses.json"
            path.write_text(json.dumps(document()), encoding="utf-8")

            poses = load_attack_poses(path)

        self.assertEqual(tuple(poses), ("SPEAR-1_2", "SPEAR-1_1"))

    def test_rejects_mismatched_id_and_invalid_weapon_count(self) -> None:
        invalid = document()
        invalid["poses"][0]["id"] = "SPEAR-1_wrong"
        with self.assertRaisesRegex(AttackPoseDataError, "id"):
            parse_attack_poses(invalid)

        invalid = document()
        invalid["poses"][0]["weapons"] = []
        with self.assertRaisesRegex(AttackPoseDataError, "weapons"):
            parse_attack_poses(invalid)


if __name__ == "__main__":
    unittest.main()
