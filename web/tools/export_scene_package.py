#!/usr/bin/env python3
"""Export a Gaussian PLY file into a unified scene package.

Supported input:
- ascii PLY
- binary_little_endian PLY
- multiple vertex elements: `vertex`, `vertex_0`, `vertex_1`, ...

Output structure:
scene_dir/
├── scene_manifest.json
└── primitives/
    ├── base.bin
    ├── appearance_sh.bin
    └── appearance_sg.bin
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import struct
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Sequence


PLY_TYPE_MAP = {
    "char": ("b", 1),
    "uchar": ("B", 1),
    "int8": ("b", 1),
    "uint8": ("B", 1),
    "short": ("h", 2),
    "ushort": ("H", 2),
    "int16": ("h", 2),
    "uint16": ("H", 2),
    "int": ("i", 4),
    "uint": ("I", 4),
    "int32": ("i", 4),
    "uint32": ("I", 4),
    "float": ("f", 4),
    "float32": ("f", 4),
    "double": ("d", 8),
    "float64": ("d", 8),
}


@dataclass
class PlyProperty:
    type_name: str
    name: str


@dataclass
class PlyElement:
    name: str
    count: int
    properties: List[PlyProperty]


@dataclass
class ParsedPly:
    format_name: str
    elements: List[PlyElement]
    records: Dict[str, List[Dict[str, float]]]


def parse_header(file_obj) -> tuple[str, List[PlyElement], bytes]:
  header_lines = []
  while True:
    line = file_obj.readline()
    if not line:
      raise ValueError("Unexpected EOF while reading PLY header")
    header_lines.append(line)
    if line.strip() == b"end_header":
      break

  decoded = [line.decode("utf-8").strip() for line in header_lines]
  if not decoded or decoded[0] != "ply":
    raise ValueError("Input is not a PLY file")

  format_name = None
  elements: List[PlyElement] = []
  current: PlyElement | None = None

  for line in decoded[1:]:
    if line.startswith("format "):
      format_name = line.split()[1]
    elif line.startswith("element "):
      _, name, count = line.split()
      current = PlyElement(name=name, count=int(count), properties=[])
      elements.append(current)
    elif line.startswith("property ") and current is not None:
      parts = line.split()
      if parts[1] == "list":
        raise ValueError("List properties are not supported in this exporter")
      current.properties.append(PlyProperty(type_name=parts[1], name=parts[2]))

  if format_name not in {"ascii", "binary_little_endian"}:
    raise ValueError(f"Unsupported PLY format: {format_name}")

  return format_name, elements, b"".join(header_lines)


def parse_ascii_records(file_obj, element: PlyElement) -> List[Dict[str, float]]:
  records = []
  for _ in range(element.count):
    line = file_obj.readline().decode("utf-8").strip()
    if not line:
      raise ValueError(f"Unexpected blank line while reading element {element.name}")
    values = line.split()
    if len(values) != len(element.properties):
      raise ValueError(f"Property count mismatch for element {element.name}")
    row = {}
    for prop, value in zip(element.properties, values):
      row[prop.name] = float(value)
    records.append(row)
  return records


def parse_binary_records(file_obj, element: PlyElement) -> List[Dict[str, float]]:
  fmt = "<" + "".join(PLY_TYPE_MAP[prop.type_name][0] for prop in element.properties)
  stride = sum(PLY_TYPE_MAP[prop.type_name][1] for prop in element.properties)
  records = []
  for _ in range(element.count):
    chunk = file_obj.read(stride)
    if len(chunk) != stride:
      raise ValueError(f"Unexpected EOF while reading binary element {element.name}")
    values = struct.unpack(fmt, chunk)
    row = {}
    for prop, value in zip(element.properties, values):
      row[prop.name] = float(value)
    records.append(row)
  return records


def load_ply(path: str) -> ParsedPly:
  with open(path, "rb") as file_obj:
    format_name, elements, _ = parse_header(file_obj)
    records: Dict[str, List[Dict[str, float]]] = {}
    for element in elements:
      if format_name == "ascii":
        records[element.name] = parse_ascii_records(file_obj, element)
      else:
        records[element.name] = parse_binary_records(file_obj, element)
  return ParsedPly(format_name=format_name, elements=elements, records=records)


def vertex_elements(parsed: ParsedPly) -> Sequence[PlyElement]:
  return [element for element in parsed.elements if re.fullmatch(r"vertex(_\d+)?", element.name)]


def pack_float32(values: Sequence[float]) -> bytes:
  return struct.pack("<" + "f" * len(values), *values)


def pack_uint32(values: Sequence[int]) -> bytes:
  return struct.pack("<" + "I" * len(values), *values)


def pack_uint16(values: Sequence[int]) -> bytes:
  return struct.pack("<" + "H" * len(values), *values)


def extract_rgb_base(row: Dict[str, float]) -> List[float]:
  if "rgb_base_0" in row:
    return [row.get("rgb_base_0", 0.0), row.get("rgb_base_1", 0.0), row.get("rgb_base_2", 0.0)]
  if "f_dc_0" in row:
    return [row.get("f_dc_0", 0.0), row.get("f_dc_1", 0.0), row.get("f_dc_2", 0.0)]
  return [row.get("red", 0.0), row.get("green", 0.0), row.get("blue", 0.0)]


def build_scene_package(
  input_path: str,
  output_dir: str,
  scene_id: str,
  title: str,
  representation: str,
  algorithm_family: str,
  extra_metadata: dict | None = None,
) -> dict:
  parsed = load_ply(input_path)
  elements = vertex_elements(parsed)
  if not elements:
    raise ValueError("No supported vertex elements found in PLY file")

  scene_dir = Path(output_dir)
  primitives_dir = scene_dir / "primitives"
  source_dir = scene_dir / "source"
  primitives_dir.mkdir(parents=True, exist_ok=True)
  source_dir.mkdir(parents=True, exist_ok=True)

  base_path = primitives_dir / "base.bin"
  sh_path = primitives_dir / "appearance_sh.bin"
  sg_path = primitives_dir / "appearance_sg.bin"
  source_copy_path = source_dir / Path(input_path).name
  shutil.copyfile(input_path, source_copy_path)

  base_bytes = bytearray()
  sh_bytes = bytearray()
  sg_bytes = bytearray()
  primitive_count = 0
  appearance_layout = {}

  for element in elements:
    for row in parsed.records[element.name]:
      primitive_count += 1
      position = [row.get("x", 0.0), row.get("y", 0.0), row.get("z", 0.0)]
      scale = [row.get("scale_0", 0.0), row.get("scale_1", 0.0), row.get("scale_2", 0.0)]
      rotation = [row.get("rot_0", 1.0), row.get("rot_1", 0.0), row.get("rot_2", 0.0), row.get("rot_3", 0.0)]
      opacity = row.get("opacity", 1.0)
      flags = 0

      if representation in {"sg", "compressed-sg"}:
        inferred_axis_count = 0
        if element.name.startswith("vertex_"):
          inferred_axis_count = int(element.name.split("_")[-1])
        axis_count = int(row.get("sg_axis_count", inferred_axis_count) or 0)
        appearance_offset = len(sg_bytes)
        base_bytes.extend(pack_float32(position + scale + rotation + [opacity]))
        base_bytes.extend(pack_uint32([appearance_offset]))
        base_bytes.extend(pack_uint16([axis_count, flags]))

        sg_bytes.extend(pack_float32(extract_rgb_base(row)))
        sg_bytes.extend(pack_uint16([axis_count, 0]))
        for axis_idx in range(axis_count):
          sg_bytes.extend(
            pack_float32(
              [
                row.get(f"sg_dir_{axis_idx}_0", 0.0),
                row.get(f"sg_dir_{axis_idx}_1", 0.0),
                row.get(f"sg_dir_{axis_idx}_2", 0.0),
                row.get(f"sg_sharp_{axis_idx}", 0.0),
                row.get(f"sg_rgb_{axis_idx}_0", 0.0),
                row.get(f"sg_rgb_{axis_idx}_1", 0.0),
                row.get(f"sg_rgb_{axis_idx}_2", 0.0),
              ]
            )
          )
        appearance_layout = {
          "appearance_sg.bin": {
            "base_rgb": "float32[3]",
            "axis_count": "uint16",
            "axes": "float32[7] * axis_count",
          }
        }
      else:
        appearance_offset = len(sh_bytes)
        sh_coefficients = [row.get("f_dc_0", 0.0), row.get("f_dc_1", 0.0), row.get("f_dc_2", 0.0)]
        rest_keys = sorted(
          [key for key in row.keys() if key.startswith("f_rest_")],
          key=lambda item: int(item.split("_")[-1]),
        )
        sh_coefficients.extend([row[key] for key in rest_keys])

        base_bytes.extend(pack_float32(position + scale + rotation + [opacity]))
        base_bytes.extend(pack_uint32([appearance_offset]))
        base_bytes.extend(pack_uint16([len(sh_coefficients), flags]))
        sh_bytes.extend(pack_uint32([len(sh_coefficients)]))
        sh_bytes.extend(pack_float32(sh_coefficients if sh_coefficients else extract_rgb_base(row)))
        appearance_layout = {
          "appearance_sh.bin": {
            "coefficient_count": "uint32",
            "coefficients": "float32[n]",
          }
        }

  base_path.write_bytes(base_bytes)
  if sh_bytes:
    sh_path.write_bytes(sh_bytes)
  if sg_bytes:
    sg_path.write_bytes(sg_bytes)

  manifest = {
    "version": "0.2.0",
    "sceneId": scene_id,
    "title": title,
    "renderer": representation,
    "representation": representation,
    "source": {
      "url": f"./source/{source_copy_path.name}",
      "format": "ply",
      "originalInput": os.path.abspath(input_path),
    },
    "payloads": {
      "base": "./primitives/base.bin",
      "appearance": "./primitives/appearance_sg.bin" if sg_bytes else "./primitives/appearance_sh.bin",
    },
    "algorithm": {
      "family": algorithm_family,
      "name": algorithm_family,
    },
    "metadata": {
      "primitiveCount": primitive_count,
      "appearanceLayout": appearance_layout,
      "plyFormat": parsed.format_name,
      "supportedByViewer": representation in {"sh", "sg"},
      "viewerSource": f"./source/{source_copy_path.name}",
      **(extra_metadata or {}),
    },
  }

  manifest_path = scene_dir / "scene_manifest.json"
  manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
  return {
    "scene_dir": str(scene_dir.resolve()),
    "manifest_path": str(manifest_path.resolve()),
    "primitive_count": primitive_count,
    "representation": representation,
  }


def main() -> None:
  parser = argparse.ArgumentParser(description="Export a PLY file to a unified scene package.")
  parser.add_argument("--input", required=True, help="Input PLY path")
  parser.add_argument("--output-dir", required=True, help="Output scene package directory")
  parser.add_argument("--scene-id", required=True)
  parser.add_argument("--title", default="Gaussian Scene")
  parser.add_argument("--representation", choices=["sh", "sg", "compressed-sh", "compressed-sg"], required=True)
  parser.add_argument("--algorithm-family", default="unknown")
  args = parser.parse_args()

  result = build_scene_package(
    input_path=args.input,
    output_dir=args.output_dir,
    scene_id=args.scene_id,
    title=args.title,
    representation=args.representation,
    algorithm_family=args.algorithm_family,
  )
  print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
  main()
