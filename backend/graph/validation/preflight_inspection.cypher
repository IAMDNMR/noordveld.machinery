// READ-ONLY. Run against AuraDB BEFORE any import. If anything exists, STOP and report; do not delete or overwrite.
CALL db.info() YIELD name, id RETURN name AS database, id;
MATCH (n) RETURN count(n) AS existing_nodes;
MATCH ()-[r]->() RETURN count(r) AS existing_relationships;
CALL db.labels() YIELD label RETURN collect(label) AS existing_labels;
CALL db.relationshipTypes() YIELD relationshipType RETURN collect(relationshipType) AS existing_relationship_types;
SHOW CONSTRAINTS YIELD name, type, labelsOrTypes, properties RETURN name, type, labelsOrTypes, properties;
SHOW INDEXES YIELD name, type, labelsOrTypes, properties RETURN name, type, labelsOrTypes, properties;
