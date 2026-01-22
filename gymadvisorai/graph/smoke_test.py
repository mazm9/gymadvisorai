from gymadvisorai.graph.neo4j_client import Neo4jClient

def main():
    c = Neo4jClient()
    try:
        print(c.run("RETURN 1 AS ok"))
    finally:
        c.close()

if __name__ == "__main__":
    main()