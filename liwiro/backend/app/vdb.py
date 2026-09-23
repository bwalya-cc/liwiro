# Copyright (c) 2026 Bwalya Cameron Chishimba
# SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Commercial

import json
from typing import Tuple, Union

from app.vdb_transport import (
    VDBTransportConnectionError,
    VDBTransportProtocolError,
    VDBTransportRequestError,
    build_configured_vdb_transport,
    _validate_flat_vdb_payload,
)
from utils.auth_helpers import username_variants


def _versa_name(value):
    text = str(value)
    return text if text and all(ch.isalnum() or ch in '._-' for ch in text) else json.dumps(text)


def _versa_value(value):
    if isinstance(value, dict):
        return "{ " + ", ".join(f"{key}: {_versa_value(item)}" for key, item in value.items()) + " }"
    if isinstance(value, list):
        return "[ " + ", ".join(_versa_value(item) for item in value) + " ]"
    return json.dumps(value, ensure_ascii=True) if isinstance(value, str) else ("null" if value is None else str(value).lower() if isinstance(value, bool) else str(value))


def _versa_predicate(query):
    clauses = []
    for field, condition in (query or {}).items():
        if isinstance(condition, dict):
            operators = {'$eq': '==', '$ne': '!=', '$gt': '>', '$lt': '<', '$gte': '>=', '$lte': '<=', '$in': 'in', '$nin': '!in'}
            for operator, operand in condition.items():
                if operator not in operators:
                    raise ValueError(f"Unsupported query operator: {operator}")
                clauses.append(f"{field} {operators[operator]} {_versa_value(operand)}")
        else:
            clauses.append(f"{field} == {_versa_value(condition)}")
    return " where " + " && ".join(clauses) if clauses else ""


def _pipeline_command(collection, pipeline):
    text = f"read collection {_versa_name(collection)}"
    aggregate_body = None
    group_fields = None
    aggregate_where = ""
    for stage in pipeline or []:
        if not isinstance(stage, dict):
            raise ValueError("Aggregation stages must be objects")
        if "$match" in stage:
            aggregate_where = _versa_predicate(stage["$match"])
            text += aggregate_where
        elif "$project" in stage: text += " select [" + ", ".join(k for k, v in stage["$project"].items() if v) + "]"
        elif "$sort" in stage: text += " order by " + ", ".join(f"{k} {'asc' if int(v) >= 0 else 'desc'}" for k, v in stage["$sort"].items())
        elif "$skip" in stage: text += f" offset {int(stage['$skip'])}"
        elif "$limit" in stage: text += f" limit {int(stage['$limit'])}"
        elif "$group" in stage:
            group = stage["$group"]; identifier = group.get("_id")
            group_fields = [str(identifier)[1:]] if isinstance(identifier, str) and identifier.startswith("$") else []
            aggregate_body = []
            for alias, spec in group.items():
                if alias == "_id" or not isinstance(spec, dict): continue
                if "$sum" in spec and spec["$sum"] == 1: aggregate_body.append(f"{alias}: count();")
                elif "$sum" in spec and isinstance(spec["$sum"], str): aggregate_body.append(f"{alias}: sum({str(spec['$sum']).lstrip('$')});")
                elif "$avg" in spec: aggregate_body.append(f"{alias}: avg({str(spec['$avg']).lstrip('$')});")

        else: raise ValueError(f"Unsupported pipeline stage: {next(iter(stage), '')}")
    if aggregate_body is not None:
        return f"aggregate collection {_versa_name(collection)}{aggregate_where}" + (f" by {group_fields[0]}" if group_fields else "") + " { " + " ".join(aggregate_body) + " };"
    return text + ";"

class VDBClient:
    def __init__(self, app, transport=None):
        self.app = app
        self.transport_mode = app.config.get('VDB_TRANSPORT')
        self.base_url = app.config.get('VDB_SERVER_URL')
        self.socket_path = app.config.get('VDB_UNIX_SOCKET_PATH')
        self.named_pipe_path = app.config.get('VDB_NAMED_PIPE_PATH')
        self.session_id = None
        self.username = app.config.get('VDB_USERNAME')
        self.password = app.config.get('VDB_PASSWORD')
        self.domain = app.config.get('LIWIRO_DOMAIN')
        self.db = app.config.get('LIWIRO_DB')
        self.workspace_error = ""
        self.transport = transport or build_configured_vdb_transport(app)
        
        # Authenticate on initialization
        if not self.authenticate():
            self.app.logger.critical("VDB Client initialization failed: Authentication failed")
            raise ConnectionError("Authentication failed")

    def ensure_workspace(self, domain_name: str, db_name: str = "main") -> bool:
        """Ensure domain + database exist and switch context to them."""
        self.workspace_error = ""
        try:
            # VDB versions may return either a flat list of names or rows such as
            # ``[{"name": "example"}]`` for read-domains/read-databases.  Keep
            # workspace setup idempotent across both response shapes and avoid
            # re-creating an existing workspace just because its case differs.
            def _names(value):
                if isinstance(value, dict):
                    for key in ("data", "domains", "databases", "results", "items"):
                        nested = value.get(key)
                        if nested is not None:
                            names = _names(nested)
                            if names:
                                return names
                if not isinstance(value, (list, tuple)):
                    return set()
                names = set()
                for item in value:
                    if isinstance(item, dict):
                        named = item.get("name") or item.get("domain") or item.get("database")
                        item = named if named is not None else item
                        if isinstance(item, dict):
                            names.update(_names(item))
                            continue
                    text = str(item or "").strip()
                    if text:
                        names.add(text.casefold())
                return names

            domain_name = str(domain_name or "").strip()
            db_name = str(db_name or "main").strip() or "main"
            if not domain_name:
                self.workspace_error = "Cannot prepare VDB workspace without a domain name"
                self.app.logger.error(self.workspace_error)
                return False
            ok, domains = self.list_domains()
            if not ok:
                # ``read domains`` normally does not depend on the active
                # database.  Older VDB servers, however, load the session's
                # current database first.  A generated service can therefore
                # be left with (for example) ``authcoreservice/config`` after
                # ``config`` was removed, making even domain discovery fail.
                # An atomic domain+database declaration repairs that stale
                # context without needing a working database in the affected
                # domain.  Do this only for the explicit missing-database
                # failure; connection/auth/protocol failures must still fail
                # fast instead of being misreported as workspace repairs.
                failure_text = str(domains or "").casefold()
                missing_current_database = "database does not exist in domain" in failure_text
                if not missing_current_database:
                    self.workspace_error = f"Unable to list VDB domains: {domains}"
                    return False

                # The failed command leaves this session pinned to the
                # deleted database, so a repair command issued on the same
                # session fails before VDB can evaluate it.  A newly
                # authenticated session starts from the account's valid
                # default context and can repair/select the requested
                # workspace.  Retry discovery first: it is enough when the
                # corrupt context was session-local.
                if not self.authenticate():
                    self.workspace_error = (
                        f"Unable to refresh VDB session while recovering stale workspace "
                        f"{domain_name}/{db_name}"
                    )
                    return False
                ok, domains = self.list_domains()
                if ok:
                    # Continue through normal domain/database validation
                    # below using the clean session.
                    pass
                else:
                    failure_text = str(domains or "").casefold()
                    if "database does not exist in domain" not in failure_text:
                        self.workspace_error = f"Unable to list VDB domains after refreshing session: {domains}"
                        return False
                    ok, result = self.define_domain(domain_name, db_name)
                    if not ok:
                        self.workspace_error = (
                            f"Unable to repair stale VDB workspace {domain_name}/{db_name}: {result}"
                        )
                        return False
                    ok, domains = self.list_domains()
                    if not ok:
                        self.workspace_error = (
                            f"Unable to list VDB domains after repairing stale workspace "
                            f"{domain_name}/{db_name}: {domains}"
                        )
                        return False
            if domain_name.casefold() not in _names(domains):
                # Create the requested database atomically with the domain so
                # a newly generated service never lands in a half-created
                # workspace whose default database is missing or stale.
                ok, result = self.define_domain(domain_name, db_name)
                if not ok:
                    self.workspace_error = f"Unable to define domain {domain_name}/{db_name}: {result}"
                    return False
            if not self.use_domain(domain_name):
                # Partial domain creation can leave the directory present but unusable
                # (for example a stale default_db in sys/config.bson). Re-run
                # define with the requested database so VDB repairs the domain
                # metadata and creates the target database atomically.
                ok, result = self.define_domain(domain_name, db_name)
                if not ok or not self.use_domain(domain_name):
                    self.workspace_error = f"Unable to activate VDB domain {domain_name}/{db_name}: {result}"
                    return False
            ok, dbs = self.list_databases()
            if not ok:
                # A domain switch can retain a stale database from the prior
                # session. In that state ``read databases`` fails before the
                # requested workspace can be selected. Creating the target
                # database is safe and idempotent, and also repairs this
                # context without requiring manual pre-generation setup.
                ok, result = self.define_database(db_name)
                if not ok:
                    self.workspace_error = f"Unable to define VDB database {domain_name}/{db_name}: {result}"
                    return False
            elif db_name.casefold() not in _names(dbs):
                ok, result = self.define_database(db_name)
                if not ok:
                    self.workspace_error = f"Unable to define VDB database {domain_name}/{db_name}: {result}"
                    return False
            if not self.use_database(db_name):
                ok, result = self.define_database(db_name)
                if not ok or not self.use_database(db_name):
                    self.workspace_error = f"Unable to activate VDB database {domain_name}/{db_name}: {result}"
                    return False
            self.app.logger.info(f"VDB workspace ready: {domain_name}/{db_name}")
            return True
        except Exception as e:
            self.workspace_error = f"Failed to ensure workspace {domain_name}/{db_name}: {str(e)}"
            self.app.logger.error(self.workspace_error)
            return False

    def authenticate(self) -> bool:
        """Authenticate with the VDB server and establish session"""
        try:
            last_error = None
            for candidate in self._username_variants(self.username) or [self.username]:
                try:
                    data = self.transport.auth(candidate, self.password, timeout=30)
                    self.session_id = data.get('sessionId')
                    if not self.session_id:
                        raise ValueError("No session ID in authentication response")
                    self.username = candidate
                    self.app.logger.debug(f"Authenticated VDB client as {self.username}")
                    return True
                except (VDBTransportRequestError, VDBTransportConnectionError, VDBTransportProtocolError) as e:
                    last_error = e
                    continue
                except Exception as e:
                    last_error = e
                    continue
            if isinstance(last_error, VDBTransportRequestError):
                self.app.logger.error(f"Authentication failed: {str(last_error)}")
            elif isinstance(last_error, VDBTransportConnectionError):
                self.app.logger.error(f"Authentication failed: {str(last_error)}")
            elif isinstance(last_error, VDBTransportProtocolError):
                self.app.logger.error("Authentication failed: Invalid response format")
            elif last_error is not None:
                self.app.logger.error(f"Unexpected authentication error: {str(last_error)}")
            else:
                self.app.logger.error("Authentication failed: Invalid credentials")
            return False
        except VDBTransportConnectionError as e:
            self.app.logger.error(f"Authentication failed: {str(e)}")
            return False
        except VDBTransportProtocolError:
            self.app.logger.error("Authentication failed: Invalid response format")
            return False
        except Exception as e:
            self.app.logger.error(f"Unexpected authentication error: {str(e)}")
            return False

    def execute_vql_query(self, query: dict | list) -> Tuple[bool, Union[dict, list]]:
        try:
            if isinstance(query, str):
                from app.vdb_commands import validate_command
                query = validate_command(query)
            else:
                query = _validate_flat_vdb_payload(query)
            if not self.session_id:
                if not self.authenticate():
                    return False, {'error': 'Authentication failed'}

            try:
                res_json = self.transport.vql(self.session_id, query, timeout=30)
            except VDBTransportRequestError as exc:
                if exc.status_code != 401:
                    message = self._transport_error_message(exc)
                    self.app.logger.error(message)
                    return False, {'error': message}
                self.app.logger.warning("Session expired. Re-authenticating...")
                if not self.authenticate():
                    return False, {'error': 'Re-authentication failed'}
                res_json = self.transport.vql(self.session_id, query, timeout=30)

            status = str(res_json.get('status', '')).lower()

            if status not in {'success', 'warning'}:
                error_msg = res_json.get('message', 'Unknown error')
                # If domain/database/script already exists, treat as non-critical to support idempotent flows.
                if "already exists" in str(error_msg).lower():
                    self.app.logger.warning(f"Non-fatal VQL warning: {error_msg}")
                    return True, res_json.get('data', {})
                self.app.logger.error(f"Query failed: {error_msg}")
                return False, {'error': error_msg}

            self.app.logger.debug(f"VQL query executed: {query}")
            if 'data' in res_json:
                return True, res_json.get('data')
            if 'responses' in res_json:
                return True, res_json.get('responses')
            if 'message' in res_json:
                return True, {'message': res_json.get('message')}
            return True, {}
        except VDBTransportRequestError as e:
            msg = self._transport_error_message(e)
            self.app.logger.error(msg)
            return False, {'error': msg}
        except VDBTransportConnectionError as e:
            msg = f"VDB communication failed: {str(e)}"
            self.app.logger.error(msg)
            return False, {'error': msg}
        except VDBTransportProtocolError:
            self.app.logger.error("Invalid JSON response")
            return False, {'error': 'Invalid server response'}
        except ValueError as e:
            self.app.logger.warning("Rejected invalid VDB command: %s", e)
            return False, {'error': str(e)}
        except Exception as e:
            self.app.logger.error(f"Unexpected error: {str(e)}")
            return False, {'error': 'Unexpected error occurred'}

    # Canonical Versa/VDB spelling; the old method remains as a migration alias.
    def execute_vdb_command(self, command: str) -> Tuple[bool, Union[dict, list]]:
        return self.execute_vql_query(command)

    def refresh_session(self) -> bool:
        """Refresh the current session"""
        try:
            return self.authenticate()
        except Exception as e:
            self.app.logger.error(f"Session refresh failed: {str(e)}")
            return False

    # region Core Operations
    def create_collection(self, collection_name: str, schema: dict) -> Tuple[bool, dict]:
        """Create a new collection with schema validation"""
        try:
            listed, existing = self.list_collections()
            if listed and isinstance(existing, list) and collection_name in existing:
                self.app.logger.debug(f"Collection already exists: {collection_name}")
                return True, {"message": "Collection already exists"}

            fields = []
            for field, definition in (schema or {}).items():
                if isinstance(definition, dict):
                    item = f"{field}: {definition.get('type', 'string')}"
                    if 'default' in definition: item += f" = {_versa_value(definition['default'])}"
                    if definition.get('required'): item += " @required"
                    if definition.get('unique'): item += " @unique"
                    fields.append(item)
                else:
                    fields.append(f"{field}: {definition}")
            query = f"create collection {_versa_name(collection_name)}" + (f" = {{ {', '.join(fields)} }}" if fields else "") + ";"
            success, result = self.execute_vql_query(query)
            if success:
                self.app.logger.info(f"Collection created: {collection_name}")
                return True, result
            return False, result
        except Exception as e:
            self.app.logger.error(f"Collection creation error: {str(e)}")
            return False, {'error': str(e)}

    def drop_collection(self, collection_name: str) -> Tuple[bool, dict]:
        """Drop an existing collection"""
        try:
            query = f"drop collection {_versa_name(collection_name)};"
            success, result = self.execute_vql_query(query)
            if success:
                self.app.logger.info(f"Collection dropped: {collection_name}")
            return success, result
        except Exception as e:
            self.app.logger.error(f"Collection drop failed: {str(e)}")
            return False, {'error': str(e)}

    def create_document(self, collection_name: str, document: dict) -> Tuple[bool, dict]:
        """Insert a document into a collection"""
        try:
            query = f"create in {_versa_name(collection_name)} = {_versa_value(document)};"
            success, result = self.execute_vql_query(query)
            if success:
                self.app.logger.info(f"Document inserted into {collection_name}")
            return success, result
        except Exception as e:
            self.app.logger.error(f"Document insertion failed: {str(e)}")
            return False, {'error': str(e)}

    def read_documents(self, collection_name: str, query: dict = None) -> Tuple[bool, Union[list, dict]]:
        """Read documents from a collection"""
        try:
            vql_query = f"read collection {_versa_name(collection_name)}{_versa_predicate(query)};"
            success, result = self.execute_vql_query(vql_query)
            return success, result
        except Exception as e:
            self.app.logger.error(f"Document read failed: {str(e)}")
            return False, {'error': str(e)}

    def update_document(self, collection_name: str, query: dict, updates: dict) -> Tuple[bool, dict]:
        """Update documents in a collection"""
        try:
            assignments = " ".join(f"{field} = {_versa_value(value)};" for field, value in (updates or {}).items())
            vql_query = f"update collection {_versa_name(collection_name)}{_versa_predicate(query)} {{ {assignments} }};"
            success, result = self.execute_vql_query(vql_query)
            if success:
                self.app.logger.info(f"Documents updated in {collection_name}")
            return success, result
        except Exception as e:
            self.app.logger.error(f"Document update failed: {str(e)}")
            return False, {'error': str(e)}

    def delete_document(self, collection_name: str, query: dict) -> Tuple[bool, dict]:
        """Delete documents from a collection"""
        try:
            vql_query = f"delete from {_versa_name(collection_name)}{_versa_predicate(query)};"
            success, result = self.execute_vql_query(vql_query)
            if success:
                self.app.logger.info(f"Documents deleted from {collection_name}")
            return success, result
        except Exception as e:
            self.app.logger.error(f"Document deletion failed: {str(e)}")
            return False, {'error': str(e)}
    # endregion

    # region Domain Management
    def define_domain(self, domain_name: str, db_name: str | None = None) -> Tuple[bool, dict]:
        """Define a new domain"""
        try:
            # The structured define operation is important for repairing an
            # existing domain whose default_db points at a deleted database.
            # The legacy ``create domain`` command treats that case as an
            # already-existing domain and cannot repair its metadata.
            if db_name:
                query = {"action": "define", "domain": domain_name, "db": db_name}
            else:
                query = f"create domain {_versa_name(domain_name)};"
            success, result = self.execute_vql_query(query)
            if success:
                self.app.logger.info(f"Defined new domain: {domain_name}")
            return success, result
        except Exception as e:
            self.app.logger.error(f"Domain definition failed: {str(e)}")
            return False, {'error': str(e)}

    def use_domain(self, domain_name: str) -> bool:
        """Switch to a specific domain"""
        try:
            query = f"use domain {_versa_name(domain_name)};"
            success, _ = self.execute_vql_query(query)
            if success:
                self.domain = domain_name
                self.app.logger.debug(f"Using VDB domain: {domain_name}")
            return success
        except Exception as e:
            self.app.logger.error(f"Domain switch failed: {str(e)}")
            return False

    def list_domains(self) -> Tuple[bool, list]:
        """List all available domains"""
        try:
            query = "read domains;"
            success, result = self.execute_vql_query(query)
            return success, result
        except Exception as e:
            self.app.logger.error(f"Domain listing failed: {str(e)}")
            return False, []

    def drop_domain(self, domain_name: str) -> Tuple[bool, dict]:
        """Drop a domain"""
        try:
            query = f"drop domain {_versa_name(domain_name)};"
            success, result = self.execute_vql_query(query)
            if success:
                self.app.logger.info(f"Dropped domain: {domain_name}")
            return success, result
        except Exception as e:
            self.app.logger.error(f"Domain drop failed: {str(e)}")
            return False, {'error': str(e)}
    # endregion

    # region Database Management
    def define_database(self, db_name: str) -> Tuple[bool, dict]:
        """Define a new database in current domain"""
        try:
            query = f"create database {_versa_name(db_name)};"
            success, result = self.execute_vql_query(query)
            if success:
                self.app.logger.info(f"Defined new database: {db_name}")
            return success, result
        except Exception as e:
            self.app.logger.error(f"Database definition failed: {str(e)}")
            return False, {'error': str(e)}

    def drop_database(self, db_name: str) -> Tuple[bool, dict]:
        """Drop a database in current domain"""
        try:
            query = f"drop database {_versa_name(db_name)};"
            success, result = self.execute_vql_query(query)
            if success:
                self.app.logger.info(f"Dropped database: {db_name}")
            return success, result
        except Exception as e:
            self.app.logger.error(f"Database drop failed: {str(e)}")
            return False, {'error': str(e)}

    def use_database(self, db_name: str) -> bool:
        """Switch to a specific database in current domain"""
        try:
            query = f"use database {_versa_name(db_name)};"
            success, _ = self.execute_vql_query(query)
            if success:
                self.db = db_name
                self.app.logger.debug(f"Using VDB database: {db_name}")
            return success
        except Exception as e:
            self.app.logger.error(f"Database switch failed: {str(e)}")
            return False

    def list_databases(self) -> Tuple[bool, list]:
        """List all available databases"""
        try:
            query = "read databases;"
            success, result = self.execute_vql_query(query)
            return success, result
        except Exception as e:
            self.app.logger.error(f"Database listing failed: {str(e)}")
            return False, []
    # endregion

    # region Advanced Operations
    def execute_script(self, script_name: str, params: dict = None) -> Tuple[bool, dict]:
        """Execute a stored script"""
        try:
            query = f"run script {_versa_name(script_name)} with {_versa_value(params or {})};"
            success, result = self.execute_vql_query(query)
            if success:
                self.app.logger.info(f"Script executed: {script_name}")
            return success, result
        except Exception as e:
            self.app.logger.error(f"Script execution failed: {str(e)}")
            return False, {'error': str(e)}

    def create_script(self, script_name: str, service: str, code: str) -> Tuple[bool, dict]:
        try:
            query = f"create script {_versa_name(script_name)} for {_versa_name(service)} = {{ {code} }};"
            success, result = self.execute_vql_query(query)
            if success:
                self.app.logger.info(f"Script created: {script_name}")
            return success, result
        except Exception as e:
            self.app.logger.error(f"Script creation failed: {str(e)}")
            return False, {'error': str(e)}

    def create_index(self, collection: str, field: str, unique: bool = False, sparse: bool = False) -> Tuple[bool, dict]:
        """Create an index on a collection"""
        try:
            annotations = (" @unique" if unique else "") + (" @sparse" if sparse else "")
            query = f"create index {_versa_name(collection)}.{field}{annotations};"
            success, result = self.execute_vql_query(query)
            if success:
                self.app.logger.info(f"Index created on {collection} for field {field}")
            return success, result
        except Exception as e:
            self.app.logger.error(f"Index creation failed: {str(e)}")
            return False, {'error': str(e)}

    def aggregate(self, collection: str, pipeline: list) -> Tuple[bool, list]:
        """Perform aggregation on a collection"""
        try:
            query = _pipeline_command(collection, pipeline)
            success, result = self.execute_vql_query(query)
            if success:
                self.app.logger.info(f"Aggregation executed on {collection}")
            return success, result
        except Exception as e:
            self.app.logger.error(f"Aggregation failed: {str(e)}")
            return False, []
    # endregion

    # region Utility Methods
    def whoami(self) -> dict:
        """Get current user information"""
        try:
            query = "whoami;"
            success, result = self.execute_vql_query(query)
            if success:
                self.app.logger.info("Retrieved current user info")
            return result
        except Exception as e:
            self.app.logger.error(f"Whoami query failed: {str(e)}")
            return {'error': str(e)}

    def get_context(self) -> dict:
        """Get current database context"""
        try:
            query = "context;"
            success, result = self.execute_vql_query(query)
            return result
        except Exception as e:
            self.app.logger.error(f"Context query failed: {str(e)}")
            return {'error': str(e)}

    def list_collections(self) -> Tuple[bool, list]:
        """List all collections in current database"""
        try:
            query = "read collections;"
            success, result = self.execute_vql_query(query)
            return success, result
        except Exception as e:
            self.app.logger.error(f"Collection listing failed: {str(e)}")
            return False, []

    def with_domain(self, domain_name: str, method: callable, *args, **kwargs) -> tuple:
        """Context manager for domain operations"""
        try:
            if not self.use_domain(domain_name):
                self.app.logger.error(f"Failed to switch to domain: {domain_name}")
                return False, {'error': f"Failed to switch to domain: {domain_name}"}
            return method(*args, **kwargs)
        except Exception as e:
            self.app.logger.error(f"Domain operation failed: {str(e)}")
            return False, {'error': str(e)}

    def async_authorize(self, required: str = "DATA_ACCESS", domain: str = None, db: str = None) -> bool:
        """RBAC check against current authenticated context."""
        domain_name = (domain or self.domain or "").lower()
        required_op = str(required or "DATA_ACCESS").upper()

        def _check_once():
            info = self.whoami()
            if not isinstance(info, dict) or info.get("error"):
                return None

            role = str(info.get("role", "")).strip().upper().replace("-", "_")
            try:
                role_level = int(info.get("role_level", 0))
            except Exception:
                role_level = 0

            owned_raw = info.get("owned_domains", info.get("ownedDomains", [])) or []
            owned = [str(d).lower() for d in owned_raw]

            if role == "SUPER_ADMIN" or role_level >= 100:
                return True
            if role == "ADMIN" and required_op in {"READ", "DATA_ACCESS", "WRITE"}:
                return True
            if domain_name and domain_name in owned:
                return True
            if role_level >= 70:
                return required_op in {"READ", "DATA_ACCESS", "WRITE"}
            if role_level >= 40:
                return required_op in {"READ", "DATA_ACCESS"}
            return False

        verdict = _check_once()
        if verdict is not None:
            return verdict

        # Retry once after session refresh to reduce false negatives.
        if self.refresh_session():
            verdict = _check_once()
            if verdict is not None:
                return verdict
        return False
        
    # endregion
    @staticmethod
    def _username_variants(username: str):
        return username_variants(username)

    @staticmethod
    def _transport_error_message(exc: VDBTransportRequestError) -> str:
        detail = ""
        if getattr(exc, "raw_body", None):
            detail = exc.raw_body
        elif getattr(exc, "payload", None) is not None:
            try:
                detail = json.dumps(exc.payload)
            except Exception:
                detail = str(exc.payload)
        msg = f"VDB communication failed: {str(exc)}"
        if detail:
            msg = f"{msg} | server: {detail}"
        return msg
