# Copyright (c) 2026 Bwalya Cameron Chishimba
# SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Commercial

from app.vdb import VDBClient  # 延迟导入

class DomainManager:
    def __init__(self, app):
        self.vdb_client = VDBClient(app)
        
    def create_domain(self, domain_name):
        return self.vdb_client.define_domain(domain_name)

    def ensure_workspace(self, domain_name, db_name="main"):
        return self.vdb_client.ensure_workspace(domain_name, db_name)
    
    def use_domain(self, domain_name):
        return self.vdb_client.use_domain(domain_name)
    
    def create_collection(self, collection_name, schema):
        success, collections = self.vdb_client.list_collections()
        if success and isinstance(collections, list) and collection_name in collections:
            return True, {}  # Return tuple (success, empty result)
        return self.vdb_client.create_collection(collection_name, schema)
    
    def create_document(self, collection_name, document):
        return self.vdb_client.create_document(collection_name, document)
    
    def read_documents(self, collection_name, query=None):
        return self.vdb_client.read_documents(collection_name, query)
    
    def update_document(self, collection_name, query, updates):
        return self.vdb_client.update_document(collection_name, query, updates)
    
    def delete_document(self, collection_name, query):
        return self.vdb_client.delete_document(collection_name, query)
