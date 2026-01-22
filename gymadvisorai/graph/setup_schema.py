from gymadvisorai.graph.neo4j_client import Neo4jClient
from gymadvisorai.graph.schema import SCHEMA


def main():
    c = Neo4jClient()
    try:
        for q in SCHEMA:
            c.run(q)
        print("schema ok")
    finally:
        c.close()


if __name__ == "__main__":
    main()
