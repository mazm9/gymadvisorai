from neo4j import GraphDatabase
from gymadvisorai.config import settings


class Neo4jClient:
    def __init__(self):
        self.driver = GraphDatabase.driver(
            settings.neo4j_uri,
            auth=(settings.neo4j_user, settings.neo4j_password),
        )

    def close(self):
        self.driver.close()

    def run(self, query: str, **params):
        with self.driver.session(database=settings.neo4j_db) as session:
            result = session.run(query, **params)
            return [record.data() for record in result]
