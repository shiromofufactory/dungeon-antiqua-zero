"""Validated attack-pose definitions shared by battle presentations."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import re
from types import MappingProxyType
from typing import Mapping


ATTACK_POSE_FORMAT_VERSION = 1
WEAPON_IMG_PATTERN = re.compile(r"[A-Z0-9]+(?:-[A-Z0-9]+)*\Z")
BRANCH_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]*\Z")
MIN_POSITION = -128
MAX_POSITION = 128


class AttackPoseDataError(ValueError):
    """Raised when compiled attack-pose data cannot be interpreted safely."""


def _integer(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


@dataclass(frozen=True)
class AttackWeaponSprite:
    """One image-bank weapon positioned relative to its character sprite."""

    image: int
    position_x: int
    position_y: int
    layer: str
    flip_x: bool
    flip_y: bool

    @classmethod
    def from_record(cls, record: object, *, pose_id: str) -> AttackWeaponSprite:
        if not isinstance(record, Mapping):
            raise AttackPoseDataError(f"attack weapon must be an object: {pose_id}")
        image = record.get("image")
        if not _integer(image) or not 0 <= image <= 15:
            raise AttackPoseDataError(
                f"attack weapon.image must be from 0 to 15: {pose_id}"
            )
        position = record.get("position")
        if not (
            isinstance(position, list)
            and len(position) == 2
            and all(
                _integer(value) and MIN_POSITION <= value <= MAX_POSITION
                for value in position
            )
        ):
            raise AttackPoseDataError(
                f"attack weapon.position must contain two integers: {pose_id}"
            )
        layer = record.get("layer")
        if layer not in ("front", "back"):
            raise AttackPoseDataError(
                f"attack weapon.layer must be front or back: {pose_id}"
            )
        flip_x = record.get("flip_x")
        flip_y = record.get("flip_y")
        if not isinstance(flip_x, bool) or not isinstance(flip_y, bool):
            raise AttackPoseDataError(
                f"attack weapon flips must be booleans: {pose_id}"
            )
        return cls(image, position[0], position[1], layer, flip_x, flip_y)

    def to_record(self) -> dict[str, object]:
        return {
            "image": self.image,
            "position": [self.position_x, self.position_y],
            "layer": self.layer,
            "flip_x": self.flip_x,
            "flip_y": self.flip_y,
        }


@dataclass(frozen=True)
class AttackPoseDefinition:
    """One authored character-and-weapon composite."""

    pose_id: str
    weapon_img: str
    branch: str
    character_pose: int
    weapons: tuple[AttackWeaponSprite, ...]

    @classmethod
    def from_record(cls, record: object) -> AttackPoseDefinition:
        if not isinstance(record, Mapping):
            raise AttackPoseDataError("attack pose must be an object")
        pose_id = record.get("id")
        weapon_img = record.get("weapon_img")
        branch = record.get("branch")
        if (
            not isinstance(weapon_img, str)
            or WEAPON_IMG_PATTERN.fullmatch(weapon_img) is None
        ):
            raise AttackPoseDataError("attack pose.weapon_img is invalid")
        if (
            not isinstance(branch, str)
            or BRANCH_PATTERN.fullmatch(branch) is None
        ):
            raise AttackPoseDataError("attack pose.branch is invalid")
        expected_id = f"{weapon_img}_{branch}"
        if pose_id != expected_id:
            raise AttackPoseDataError(
                f"attack pose.id must equal weapon_img + branch: {pose_id}"
            )
        character_pose = record.get("character_pose")
        if not _integer(character_pose) or not 0 <= character_pose <= 8:
            raise AttackPoseDataError(
                f"attack pose.character_pose must be from 0 to 8: {pose_id}"
            )
        weapon_records = record.get("weapons")
        if not isinstance(weapon_records, list) or not 1 <= len(weapon_records) <= 2:
            raise AttackPoseDataError(
                f"attack pose.weapons must contain one or two entries: {pose_id}"
            )
        return cls(
            pose_id,
            weapon_img,
            branch,
            character_pose,
            tuple(
                AttackWeaponSprite.from_record(weapon, pose_id=pose_id)
                for weapon in weapon_records
            ),
        )

    def to_record(self) -> dict[str, object]:
        return {
            "id": self.pose_id,
            "weapon_img": self.weapon_img,
            "branch": self.branch,
            "character_pose": self.character_pose,
            "weapons": [weapon.to_record() for weapon in self.weapons],
        }


def parse_attack_poses(document: object) -> Mapping[str, AttackPoseDefinition]:
    """Validate one attack-pose document and index it by stable pose ID."""

    if not isinstance(document, Mapping):
        raise AttackPoseDataError("attack pose document must be an object")
    if document.get("format_version") != ATTACK_POSE_FORMAT_VERSION:
        raise AttackPoseDataError("unsupported attack pose format_version")
    records = document.get("poses")
    if not isinstance(records, list) or not records:
        raise AttackPoseDataError("attack pose document must contain poses")
    poses: dict[str, AttackPoseDefinition] = {}
    for record in records:
        pose = AttackPoseDefinition.from_record(record)
        if pose.pose_id in poses:
            raise AttackPoseDataError(f"attack pose ID is duplicated: {pose.pose_id}")
        poses[pose.pose_id] = pose
    return MappingProxyType(poses)


def load_attack_poses(path: Path) -> Mapping[str, AttackPoseDefinition]:
    """Load a compiled attack-pose document from disk."""

    if not isinstance(path, Path):
        raise TypeError("path must be a Path")
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise AttackPoseDataError(f"attack pose data is missing: {path}") from error
    except json.JSONDecodeError as error:
        raise AttackPoseDataError(f"attack pose JSON is invalid: {path}") from error
    return parse_attack_poses(document)


def attack_sequence(
    poses: Mapping[str, AttackPoseDefinition],
    weapon_img: str,
) -> tuple[AttackPoseDefinition, ...]:
    """Return the authored basic attack sequence for one weapon image key."""

    ordered = tuple(
        pose for pose in poses.values() if pose.weapon_img == weapon_img
    )
    if not ordered:
        return ()
    by_branch = {pose.branch: pose for pose in ordered}
    primary = tuple(
        pose for branch in ("1", "2") if (pose := by_branch.get(branch)) is not None
    )
    return primary or ordered[:2]


__all__ = [
    "ATTACK_POSE_FORMAT_VERSION",
    "AttackPoseDataError",
    "AttackPoseDefinition",
    "AttackWeaponSprite",
    "attack_sequence",
    "load_attack_poses",
    "parse_attack_poses",
]
