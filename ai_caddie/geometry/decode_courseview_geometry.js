#!/usr/bin/env node
"use strict";

const fs = require("fs");
const path = require("path");

function usage() {
  console.error(`Usage:
  node decode_courseview_geometry.js --geometry-dir <extracted-hole-dir> [options]

Options:
  --out <path>        Write decoded mesh JSON. Default: output/prodgeometry/<gid>_h<hole>_meshes.json
  --stats <path>      Write compact mesh stats JSON. Default: output/prodgeometry/<gid>_h<hole>_stats.json
  --precision <n>     Decimal places for decoded positions. Default: 3
  --no-mesh-json      Only write stats; do not write full decoded mesh JSON.
`);
}

function parseArgs(argv) {
  const args = {
    precision: 3,
    writeMeshJson: true,
  };
  for (let i = 2; i < argv.length; i += 1) {
    const a = argv[i];
    if (a === "--geometry-dir") args.geometryDir = argv[++i];
    else if (a === "--out") args.out = argv[++i];
    else if (a === "--stats") args.stats = argv[++i];
    else if (a === "--precision") args.precision = Number(argv[++i]);
    else if (a === "--no-mesh-json") args.writeMeshJson = false;
    else if (a === "-h" || a === "--help") {
      usage();
      process.exit(0);
    } else {
      throw new Error(`unknown argument: ${a}`);
    }
  }
  if (!args.geometryDir) throw new Error("--geometry-dir is required");
  if (!Number.isFinite(args.precision) || args.precision < 0) {
    throw new Error("--precision must be a non-negative number");
  }
  return args;
}

function requireDraco() {
  try {
    return require("draco3d");
  } catch (err) {
    throw new Error("draco3d is not installed. Run `npm install` in this project first.");
  }
}

function readJson(file) {
  return JSON.parse(fs.readFileSync(file, "utf8"));
}

function rounder(precision) {
  const scale = 10 ** precision;
  return (value) => Math.round(value * scale) / scale;
}

function attributeTypeName(decoderModule, value) {
  const names = new Map([
    [decoderModule.POSITION, "POSITION"],
    [decoderModule.NORMAL, "NORMAL"],
    [decoderModule.COLOR, "COLOR"],
    [decoderModule.TEX_COORD, "TEX_COORD"],
    [decoderModule.GENERIC, "GENERIC"],
  ]);
  return names.get(value) || `UNKNOWN_${value}`;
}

function dataTypeName(decoderModule, value) {
  const names = new Map([
    [decoderModule.DT_INVALID, "INVALID"],
    [decoderModule.DT_INT8, "INT8"],
    [decoderModule.DT_UINT8, "UINT8"],
    [decoderModule.DT_INT16, "INT16"],
    [decoderModule.DT_UINT16, "UINT16"],
    [decoderModule.DT_INT32, "INT32"],
    [decoderModule.DT_UINT32, "UINT32"],
    [decoderModule.DT_INT64, "INT64"],
    [decoderModule.DT_UINT64, "UINT64"],
    [decoderModule.DT_FLOAT32, "FLOAT32"],
    [decoderModule.DT_FLOAT64, "FLOAT64"],
    [decoderModule.DT_BOOL, "BOOL"],
  ]);
  return names.get(value) || `UNKNOWN_${value}`;
}

function attributeSchema(decoderModule, decoder, mesh, precision) {
  const toFixed = rounder(precision);
  const rows = [];
  for (let index = 0; index < mesh.num_attributes(); index += 1) {
    const attribute = decoder.GetAttribute(mesh, index);
    const components = attribute.num_components();
    const values = new decoderModule.DracoFloat32Array();
    try {
      decoder.GetAttributeFloatForAllPoints(mesh, attribute, values);
      const minimum = Array(components).fill(Infinity);
      const maximum = Array(components).fill(-Infinity);
      for (let offset = 0; offset < values.size(); offset += components) {
        for (let component = 0; component < components; component += 1) {
          const value = values.GetValue(offset + component);
          if (value < minimum[component]) minimum[component] = value;
          if (value > maximum[component]) maximum[component] = value;
        }
      }

      const metadata = decoder.GetAttributeMetadata(mesh, index);
      const metadataEntries = [];
      if (metadata && metadata.ptr) {
        const querier = new decoderModule.MetadataQuerier();
        try {
          for (let entry = 0; entry < querier.NumEntries(metadata); entry += 1) {
            metadataEntries.push(querier.GetEntryName(metadata, entry));
          }
        } finally {
          decoderModule.destroy(querier);
        }
      }

      rows.push({
        index,
        uniqueId: attribute.unique_id(),
        semantic: attributeTypeName(decoderModule, attribute.attribute_type()),
        dataType: dataTypeName(decoderModule, attribute.data_type()),
        components,
        normalized: Boolean(attribute.normalized()),
        valueCount: attribute.size(),
        byteOffset: attribute.byte_offset(),
        byteStride: attribute.byte_stride(),
        minimum: minimum.map((value) => Number.isFinite(value) ? toFixed(value) : null),
        maximum: maximum.map((value) => Number.isFinite(value) ? toFixed(value) : null),
        metadataEntries,
      });
    } finally {
      decoderModule.destroy(values);
    }
  }
  return rows;
}

function boundsForPositions(positions) {
  const min = [Infinity, Infinity, Infinity];
  const max = [-Infinity, -Infinity, -Infinity];
  for (const p of positions) {
    for (let i = 0; i < 3; i += 1) {
      if (p[i] < min[i]) min[i] = p[i];
      if (p[i] > max[i]) max[i] = p[i];
    }
  }
  return { min, max };
}

function hole2dBounds(positions) {
  const min = [Infinity, Infinity];
  const max = [-Infinity, -Infinity];
  for (const [x, _y, z] of positions) {
    const east = -x;
    const north = z;
    if (east < min[0]) min[0] = east;
    if (north < min[1]) min[1] = north;
    if (east > max[0]) max[0] = east;
    if (north > max[1]) max[1] = north;
  }
  return { min, max };
}

function decodeMesh(decoderModule, file, precision) {
  const toFixed = rounder(precision);
  const data = fs.readFileSync(file);
  const decoder = new decoderModule.Decoder();
  const buffer = new decoderModule.DecoderBuffer();
  buffer.Init(new Int8Array(data), data.length);
  try {
    const geometryType = decoder.GetEncodedGeometryType(buffer);
    if (geometryType !== decoderModule.TRIANGULAR_MESH) {
      throw new Error(`${path.basename(file)} is not a triangular mesh`);
    }

    const mesh = new decoderModule.Mesh();
    const status = decoder.DecodeBufferToMesh(buffer, mesh);
    try {
      if (!status.ok()) {
        throw new Error(`${path.basename(file)} decode failed: ${status.error_msg()}`);
      }
      const positionAttributeId = decoder.GetAttributeId(mesh, decoderModule.POSITION);
      if (positionAttributeId < 0) {
        throw new Error(`${path.basename(file)} has no POSITION attribute`);
      }
      const attr = decoder.GetAttribute(mesh, positionAttributeId);
      const positionValues = new decoderModule.DracoFloat32Array();
      const faceValues = new decoderModule.DracoInt32Array();
      try {
        decoder.GetAttributeFloatForAllPoints(mesh, attr, positionValues);
        const dims = attr.num_components();
        if (dims < 3) throw new Error(`${path.basename(file)} POSITION has ${dims} components`);

        const positions = [];
        for (let i = 0; i < positionValues.size(); i += dims) {
          positions.push([
            toFixed(positionValues.GetValue(i)),
            toFixed(positionValues.GetValue(i + 1)),
            toFixed(positionValues.GetValue(i + 2)),
          ]);
        }

        const faces = [];
        for (let i = 0; i < mesh.num_faces(); i += 1) {
          decoder.GetFaceFromMesh(mesh, i, faceValues);
          faces.push([
            faceValues.GetValue(0),
            faceValues.GetValue(1),
            faceValues.GetValue(2),
          ]);
        }

        const stats = {
          file: path.basename(file),
          bytes: data.length,
          type: "mesh",
          points: mesh.num_points(),
          faces: mesh.num_faces(),
          attributes: mesh.num_attributes(),
          attributeSchema: attributeSchema(decoderModule, decoder, mesh, precision),
          positionComponents: dims,
          positionBounds: boundsForPositions(positions),
          hole2dBounds: hole2dBounds(positions),
        };
        return { name: path.basename(file), positions, faces, stats };
      } finally {
        decoderModule.destroy(positionValues);
        decoderModule.destroy(faceValues);
      }
    } finally {
      decoderModule.destroy(mesh);
    }
  } finally {
    decoderModule.destroy(buffer);
    decoderModule.destroy(decoder);
  }
}

function defaultOutputPaths(hole, geometryDir) {
  const globalId = hole.GlobalId || "unknown";
  const holeNumber = String(hole.HoleNumber || path.basename(geometryDir)).padStart(2, "0");
  const stem = `gid${globalId}_h${holeNumber}`;
  return {
    out: path.join("output", "prodgeometry", `${stem}_meshes.json`),
    stats: path.join("output", "prodgeometry", `${stem}_stats.json`),
  };
}

async function main() {
  const args = parseArgs(process.argv);
  const geometryDir = path.resolve(args.geometryDir);
  const holePath = path.join(geometryDir, "hole.json");
  const foliagePath = path.join(geometryDir, "foliage.json");
  if (!fs.existsSync(holePath)) throw new Error(`missing ${holePath}`);

  const hole = readJson(holePath);
  const foliage = fs.existsSync(foliagePath) ? readJson(foliagePath) : null;
  const defaults = defaultOutputPaths(hole, geometryDir);
  const outPath = args.out || defaults.out;
  const statsPath = args.stats || defaults.stats;

  const draco3d = requireDraco();
  const decoderModule = await draco3d.createDecoderModule({});
  const meshes = [];
  for (const file of fs.readdirSync(geometryDir).filter((n) => n.endsWith(".drc")).sort()) {
    meshes.push(decodeMesh(decoderModule, path.join(geometryDir, file), args.precision));
  }

  const stats = {
    sourceDir: geometryDir,
    globalId: hole.GlobalId,
    holeNumber: hole.HoleNumber,
    refLat: hole.RefLat,
    refLon: hole.RefLon,
    meshCount: meshes.length,
    meshes: meshes.map((m) => m.stats),
    foliageCounts: foliage ? {
      foliage: Array.isArray(foliage.foliage) ? foliage.foliage.length : 0,
      trees: Array.isArray(foliage.trees) ? foliage.trees.length : 0,
      rocks: Array.isArray(foliage.rocks) ? foliage.rocks.length : 0,
    } : null,
  };

  const decoded = {
    sourceDir: geometryDir,
    hole,
    foliage,
    precision: args.precision,
    meshes,
  };

  fs.mkdirSync(path.dirname(statsPath), { recursive: true });
  fs.writeFileSync(statsPath, `${JSON.stringify(stats, null, 2)}\n`);
  if (args.writeMeshJson) {
    fs.mkdirSync(path.dirname(outPath), { recursive: true });
    fs.writeFileSync(outPath, `${JSON.stringify(decoded)}\n`);
  }

  console.log(JSON.stringify({
    meshCount: stats.meshCount,
    stats: statsPath,
    meshJson: args.writeMeshJson ? outPath : null,
  }, null, 2));
}

main().catch((err) => {
  console.error(err.message || err);
  process.exit(1);
});
