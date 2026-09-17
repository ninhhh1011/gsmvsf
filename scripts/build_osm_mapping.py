#!/usr/bin/env python3
"""
Build OSM ↔ Dataset V1 node and segment mappings.
"""
import gzip
import osmium
import json
from collections import defaultdict

def main():
    print("=" * 70)
    print("BUILDING OSM <-> DATASET V1 MAPPING")
    print("=" * 70)

    # Load Dataset V1 internal nodes
    print("\n1. Loading Dataset V1 internal nodes...")
    dataset_nodes = {}
    with gzip.open("dataset_v1/map/processed/road_nodes.csv.gz", "rt", encoding="utf-8", errors="replace") as f:
        f.readline()  # header
        for line in f:
            parts = line.strip().split(",")
            if len(parts) >= 3:
                node_id = parts[0]
                lat = float(parts[1])
                lon = float(parts[2])
                dataset_nodes[node_id] = {"lat": lat, "lon": lon}
    print(f"   Dataset V1 nodes: {len(dataset_nodes)}")

    # Load OSM nodes from PBF
    print("\n2. Loading OSM nodes from PBF...")
    class OSMHandler(osmium.SimpleHandler):
        def __init__(self):
            super().__init__()
            self.nodes = {}
            self.ways = {}

        def node(self, n):
            self.nodes[n.id] = {"lon": n.location.lon, "lat": n.location.lat}

        def way(self, w):
            self.ways[w.id] = {"nodes": [n.ref for n in w.nodes]}

    handler = OSMHandler()
    handler.apply_file("dataset_v1/map/raw/hanoi-patched.osm.pbf")

    osm_nodes = handler.nodes
    osm_ways = handler.ways
    print(f"   OSM nodes: {len(osm_nodes)}")
    print(f"   OSM ways: {len(osm_ways)}")

    # Build coordinate-based mapping (precision 7)
    print("\n3. Building coordinate-based node mapping...")
    precision = 7
    coord_to_internal = defaultdict(list)

    for node_id, coords in dataset_nodes.items():
        key = (round(coords["lat"], precision), round(coords["lon"], precision))
        coord_to_internal[key].append(node_id)

    # Create mappings
    internal_to_osm = {}  # internal_id -> osm_id
    osm_to_internal = {}   # osm_id -> internal_id
    ambiguous_nodes = []

    for osm_id, coords in osm_nodes.items():
        key = (round(coords["lat"], precision), round(coords["lon"], precision))
        if key in coord_to_internal:
            internal_ids = coord_to_internal[key]
            if len(internal_ids) == 1:
                internal_id = internal_ids[0]
                internal_to_osm[internal_id] = osm_id
                osm_to_internal[osm_id] = internal_id
            else:
                ambiguous_nodes.append((osm_id, internal_ids))

    print(f"   Mapped nodes: {len(internal_to_osm)}")
    print(f"   Ambiguous mappings: {len(ambiguous_nodes)}")

    # Load road segments to build segment mapping
    print("\n4. Loading Dataset V1 road segments...")
    segments = {}
    with gzip.open("dataset_v1/map/processed/road_segments.csv.gz", "rt", encoding="utf-8", errors="replace") as f:
        f.readline()  # header
        for line in f:
            parts = line.strip().split(",", 7)
            if len(parts) >= 7:
                segment_id = parts[0]
                from_node = parts[1]
                to_node = parts[2]
                direction = parts[3]
                base_id = parts[4] if parts[4] else None
                osm_way_id = int(parts[5]) if parts[5] else None
                segments[segment_id] = {
                    "from_node": from_node,
                    "to_node": to_node,
                    "direction": direction,
                    "base_segment_id": base_id,
                    "osm_way_id": osm_way_id,
                }
    print(f"   Dataset V1 segments: {len(segments)}")

    # Build segment OSM mapping
    print("\n5. Building segment OSM mapping...")

    # Group segments by (osm_way_id, from_node, to_node)
    way_node_pairs = defaultdict(list)  # (osm_way_id, from_node, to_node) -> [segment_ids]

    for seg_id, seg in segments.items():
        if seg["osm_way_id"] and seg["from_node"] and seg["to_node"]:
            key = (seg["osm_way_id"], seg["from_node"], seg["to_node"])
            way_node_pairs[key].append(seg_id)

    # Create segment mapping with OSM node IDs
    segment_osm_mapping = {}  # segment_id -> {osm_from, osm_to, osm_way_id, is_forward}

    for seg_id, seg in segments.items():
        if seg["osm_way_id"] and seg["from_node"] and seg["to_node"]:
            osm_way_id = seg["osm_way_id"]

            # Get OSM node IDs
            osm_from = internal_to_osm.get(seg["from_node"])
            osm_to = internal_to_osm.get(seg["to_node"])

            if osm_from and osm_to:
                # Validate against OSM way structure
                osm_way = osm_ways.get(osm_way_id)
                if osm_way:
                    nodes = osm_way["nodes"]
                    if osm_from in nodes and osm_to in nodes:
                        from_idx = nodes.index(osm_from)
                        to_idx = nodes.index(osm_to)

                        # Check if nodes are adjacent in the way
                        is_forward = (to_idx == from_idx + 1)
                        is_adjacent = (abs(to_idx - from_idx) == 1)

                        segment_osm_mapping[seg_id] = {
                            "osm_from": osm_from,
                            "osm_to": osm_to,
                            "osm_way_id": osm_way_id,
                            "is_forward": is_forward,
                            "is_adjacent": is_adjacent,
                        }

    print(f"   Segments with OSM mapping: {len(segment_osm_mapping)}")

    # Build reverse segment mapping (segment by OSM node pair)
    print("\n6. Building OSM node pair → segment mapping...")

    osm_pair_to_segment = defaultdict(list)  # (osm_way_id, osm_from, osm_to) -> [segment_ids]

    for seg_id, mapping in segment_osm_mapping.items():
        key = (mapping["osm_way_id"], mapping["osm_from"], mapping["osm_to"])
        osm_pair_to_segment[key].append(seg_id)

    # Check for ambiguous pairs
    ambiguous_pairs = {k: v for k, v in osm_pair_to_segment.items() if len(v) > 1}
    print(f"   Ambiguous OSM node pairs: {len(ambiguous_pairs)}")

    # Save mappings
    print("\n7. Saving mappings...")

    # Node mapping
    node_mapping = {
        "internal_to_osm": internal_to_osm,
        "osm_to_internal": osm_to_internal,
        "precision": precision,
        "stats": {
            "total_internal_nodes": len(dataset_nodes),
            "mapped_internal_nodes": len(internal_to_osm),
            "total_osm_nodes": len(osm_nodes),
            "mapped_osm_nodes": len(osm_to_internal),
            "ambiguous_mappings": len(ambiguous_nodes),
        }
    }

    with open("runtime/map_mapping/node_mapping.json", "w") as f:
        json.dump(node_mapping, f)
    print(f"   Saved node_mapping.json ({len(internal_to_osm)} entries)")

    # Segment mapping
    segment_mapping = {
        "segment_osm": segment_osm_mapping,
        "osm_pair_to_segment": {str(k): v for k, v in osm_pair_to_segment.items()},
        "stats": {
            "total_segments": len(segments),
            "segments_with_osm_mapping": len(segment_osm_mapping),
            "ambiguous_pairs": len(ambiguous_pairs),
        }
    }

    with open("runtime/map_mapping/segment_mapping.json", "w") as f:
        json.dump(segment_mapping, f)
    print(f"   Saved segment_mapping.json ({len(segment_osm_mapping)} entries)")

    # OSM ways (just IDs for reference)
    with open("runtime/map_mapping/osm_way_nodes.json", "w") as f:
        osm_way_nodes = {str(k): v["nodes"] for k, v in osm_ways.items()}
        json.dump(osm_way_nodes, f)
    print(f"   Saved osm_way_nodes.json ({len(osm_ways)} ways)")

    print("\n" + "=" * 70)
    print("MAPPING BUILD COMPLETE")
    print("=" * 70)
    print(f"\nNode mapping coverage: {len(internal_to_osm)}/{len(dataset_nodes)} ({len(internal_to_osm)/len(dataset_nodes)*100:.1f}%)")
    print(f"Segment mapping coverage: {len(segment_osm_mapping)}/{len(segments)} ({len(segment_osm_mapping)/len(segments)*100:.1f}%)")

if __name__ == "__main__":
    main()
