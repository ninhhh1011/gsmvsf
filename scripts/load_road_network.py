"""Load canonical road segments into PostGIS without changing Dataset files."""
import csv
import gzip
import sys
from contextlib import closing
from pathlib import Path
import psycopg2

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.app.config import settings

def main():
    source = settings.dataset_path / "map/processed/road_segments.csv.gz"
    with closing(psycopg2.connect(settings.database_url_sync, connect_timeout=5)) as conn:
        with conn:
            with conn.cursor() as cur:
                cur.execute("CREATE EXTENSION IF NOT EXISTS postgis")
                cur.execute("""CREATE TABLE IF NOT EXISTS road_segments (
                    segment_id varchar(50) PRIMARY KEY, from_node_id varchar(20) NOT NULL,
                    to_node_id varchar(20) NOT NULL, travel_direction varchar(10) NOT NULL,
                    base_segment_id varchar(50), osm_way_id bigint NOT NULL,
                    length_m double precision, wkt_geometry text, geom geometry(LineString,4326))""")
                cur.execute("""CREATE TEMP TABLE import_segments (
                    segment_id text, from_node_id text, to_node_id text, travel_direction text,
                    base_segment_id text, osm_way_id text, geometry text, length_m text,
                    road_type text, road_name text, oneway text, maxspeed_kmh text, lanes text,
                    bridge text, tunnel text, access text) ON COMMIT DROP""")
                with gzip.open(source, "rt", encoding="utf-8") as handle:
                    cur.copy_expert("COPY import_segments FROM STDIN WITH (FORMAT CSV, HEADER TRUE)", handle)
                cur.execute("""INSERT INTO road_segments
                    (segment_id,from_node_id,to_node_id,travel_direction,base_segment_id,osm_way_id,length_m,wkt_geometry,geom)
                    SELECT segment_id,from_node_id,to_node_id,travel_direction,base_segment_id,
                        osm_way_id::bigint,length_m::double precision,geometry,ST_GeomFromText(geometry,4326)
                    FROM import_segments ON CONFLICT (segment_id) DO NOTHING""")
                inserted = cur.rowcount
                cur.execute("CREATE INDEX IF NOT EXISTS road_segments_geom_idx ON road_segments USING gist(geom)")
                cur.execute("CREATE INDEX IF NOT EXISTS road_segments_osm_way_idx ON road_segments(osm_way_id)")
                cur.execute("""SELECT count(*) FROM import_segments i JOIN road_segments r USING(segment_id)
                    WHERE r.osm_way_id=i.osm_way_id::bigint AND r.travel_direction=i.travel_direction
                        AND ST_Equals(r.geom,ST_GeomFromText(i.geometry,4326))""")
                verified = cur.fetchone()[0]
                cur.execute("SELECT count(*) FROM import_segments")
                assert verified == cur.fetchone()[0], "Existing database differs from canonical road data"
        print(f"Inserted {inserted}; verified {verified} canonical segments")

if __name__ == "__main__":
    main()
