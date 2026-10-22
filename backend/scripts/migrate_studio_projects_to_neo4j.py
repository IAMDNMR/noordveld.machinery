"""Explicit additive migration of local project revisions. Source SQLite remains untouched."""
import argparse
from hashlib import sha256
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.schemas.application_definition import ApplicationDefinition


def snapshot(path):
    with sqlite3.connect(f'file:{Path(path).resolve().as_posix()}?mode=ro', uri=True) as db:
        db.row_factory = sqlite3.Row
        db.execute('BEGIN')
        projects = [dict(r) for r in db.execute('SELECT * FROM projects ORDER BY id')]
        revisions = []
        for row in db.execute('SELECT * FROM project_revisions ORDER BY project_id,revision'):
            row = dict(row)
            definition = ApplicationDefinition.model_validate_json(row['definition_json'])
            if definition.id != row['project_id'] or definition.revision != row['revision']:
                raise ValueError('Project revision metadata mismatch')
            revisions.append({'id':f"{row['project_id']}/{row['revision']}", 'project_id':row['project_id'],
                              'payload':{'definition':definition.model_dump(mode='json'), 'revision':row['revision'],
                                         'actor':row['actor'],'operation':row['operation'],'at':row['created_at']}})
    for project in projects:
        actual = [r['payload']['revision'] for r in revisions if r['project_id'] == project['id']]
        if actual != list(range(1, project['current_revision']+1)):
            raise ValueError('Project revision history is incomplete')
    if any(r['project_id'] not in {p['id'] for p in projects} for r in revisions):
        raise ValueError('Revision belongs to an unknown project')
    return {'projects':projects,'revisions':revisions}


def migrate(documents, data):
    def commit(tx):
        for project in data['projects']:
            head = documents.get(tx,'project',project['id'])
            expected = {'id':project['id'],'owner':project['owner'],'revision':project['current_revision']}
            if head is not None and head != expected:
                raise ValueError('Target project head differs; migration refused')
        for revision in data['revisions']:
            existing = documents.get(tx,'revision',revision['id'])
            if existing is not None and existing != revision['payload']:
                raise ValueError('Target revision differs; immutable history cannot be overwritten')
            if existing is None:
                documents.put(tx,'revision',revision['id'],revision['payload'],immutable=True)
        for project in data['projects']:
            documents.put(tx,'project',project['id'],{'id':project['id'],'owner':project['owner'],'revision':project['current_revision']})
        for revision in data['revisions']:
            tx.run('MATCH (p:DSDocument {key:$p}),(r:DSDocument {key:$r}) MERGE (p)-[:DS_HAS_REVISION]->(r)',
                   p=f"{documents.namespace}/project/{revision['project_id']}",r=f"{documents.namespace}/revision/{revision['id']}").consume()
        tx.run('MATCH (w:DSWorkspace {namespace:$ns}) SET w.project_migration_complete=true,w.project_count=$count', ns=documents.namespace,count=len(data['projects'])).consume()
    documents.write(commit)
    for project in data['projects']:
        from app.design_studio.neo4j_store import Neo4jProjectStore
        store = Neo4jProjectStore(documents)
        actual = store.history(project['owner'],project['id'])
        expected = [r['payload']['definition'] for r in data['revisions'] if r['project_id'] == project['id']]
        if [d.model_dump(mode='json') for d in actual] != expected:
            raise ValueError('Migration read-back mismatch')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--source',required=True)
    parser.add_argument('--namespace',required=True)
    parser.add_argument('--apply',action='store_true')
    args = parser.parse_args()
    data = snapshot(args.source)
    canonical = json.dumps(data,sort_keys=True,separators=(',',':'))
    summary = {'projects':len(data['projects']),'revisions':len(data['revisions']),'sha256':sha256(canonical.encode()).hexdigest(),'applied':False}
    if not args.apply:
        print(json.dumps(summary)); return
    # Caller must pause old application writers before switching its primary store.
    backup = Path(tempfile.mkdtemp(prefix='studio-project-migration-backup-'))/'projects.json'
    backup.write_text(canonical,encoding='utf-8')
    from app.core.config import get_settings
    from app.graph.client import GraphClient
    from app.design_studio.neo4j_store import Neo4jDocuments
    graph = GraphClient(get_settings())
    try:
        docs = Neo4jDocuments(graph.driver,graph._settings.neo4j_database,args.namespace)
        with graph.driver.session(database=graph._settings.neo4j_database) as session:
            session.run('CREATE CONSTRAINT ds_workspace_namespace IF NOT EXISTS FOR (w:DSWorkspace) REQUIRE w.namespace IS UNIQUE').consume()
            session.run('CREATE CONSTRAINT ds_document_key IF NOT EXISTS FOR (d:DSDocument) REQUIRE d.key IS UNIQUE').consume()
            session.run("MERGE (w:DSWorkspace {namespace:$ns}) ON CREATE SET w.schema='studio-neo4j-v1',w.lock=0",ns=args.namespace).consume()
        migrate(docs,data)
        print(json.dumps({**summary,'applied':True,'backup':str(backup)}))
    finally:
        graph.close()


if __name__ == '__main__':
    main()
