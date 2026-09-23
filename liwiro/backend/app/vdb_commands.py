"""Readable command serialization for SDK callers; command parsing belongs to VDB."""
import json
import re


def validate_command(command):
    if not isinstance(command, str) or not command.strip() or command.lstrip().startswith(('{', '[')):
        raise ValueError('VDB_LEGACY_JSON_COMMAND: use a readable VDB command in Versa syntax, for example: read collection users;')
    text = command.strip()
    if 'where {' in text or 'projection {' in text or ' set {' in text or ' inc {' in text:
        raise ValueError('VDB_LEGACY_JSON_QUERY: use Versa expressions and update blocks')
    if not re.match(r'^(?:read|find|count|create|insert|update|delete|drop|use|status|suspend|resume|grant|revoke|transfer|run|begin|commit|rollback|abort|transaction|aggregate|export|help|context|whoami|echo|clear|cls|license|licence|exit|quit)\b', text, re.I):
        raise ValueError('Unknown VDB command; use a readable VDB command in native Versa syntax such as: read collection users;')
    if re.match(r'^(?:status|suspend|resume|drop|use)\s+domain\s*$', text, re.I):
        raise ValueError('Incomplete readable VDB command; specify a domain name, for example: status domain engineering;')
    return text


def command_text(payload):
    if isinstance(payload, str):
        return validate_command(payload)
    if isinstance(payload, list):
        return ';\n'.join(command_text(item) for item in payload)
    if 'commands' in payload:
        return ';\n'.join(command_text(item) for item in payload['commands'])
    fields = dict(payload)
    action = str(fields.pop('action')).lower()
    quote = lambda value: json.dumps(value, ensure_ascii=True, separators=(',', ':')) if not _simple_name(value) else str(value)
    def obj(value):
        if isinstance(value, dict): return '{ ' + ', '.join(f'{k}: {obj(v)}' for k, v in value.items()) + ' }'
        if isinstance(value, list): return '[ ' + ', '.join(obj(v) for v in value) + ' ]'
        return json.dumps(value, ensure_ascii=True, separators=(',', ':')) if isinstance(value, str) else quote(value)
    def predicate(value):
        if not value: return ''
        parts = []
        for key, condition in value.items():
            if isinstance(condition, dict):
                for operator, operand in condition.items():
                    op = {'$eq': '==', '$ne': '!=', '$gt': '>', '$lt': '<', '$gte': '>=', '$lte': '<=', '$in': 'in', '$nin': '!in'}.get(operator)
                    if not op: raise ValueError(f'Unsupported legacy query operator: {operator}')
                    parts.append(f'{key} {op} {obj(operand)}')
            else: parts.append(f'{key} == {obj(condition)}')
        return ' where ' + ' && '.join(parts)
    if action == 'tumi':
        operation = fields.pop('operation')
        if operation == 'list':
            resource = fields.pop('resource', 'permissions' if 'permissions' in fields else 'users')
            head = 'read ' + resource
            if resource == 'permissions' and 'permissions' in fields and 'username' not in fields:
                fields['username'] = fields.pop('permissions')
        elif operation in ('create', 'update') and isinstance(fields.get('role'), dict):
            role = dict(fields.pop('role'))
            role_name = role.pop('name')
            # Role definitions are native Versa objects, not positional parameter bags.
            return f"{operation} role {quote(role_name)} = {obj(role)};"
        elif operation in ('read', 'delete') and 'role' in fields and 'username' not in fields:
            head = operation + ' role ' + quote(fields.pop('role'))
        elif operation in ('create', 'delete', 'update'):
            head = operation + ' user'
        else:
            head = operation
    elif action == 'list':
        resource = fields.pop('resource') if 'resource' in fields else fields.pop('type', 'collections')
        head = 'read ' + resource
    elif action == 'define':
        resource = fields.pop('resource', 'domain' if 'domain' in fields else 'db')
        name = fields.pop('name') if 'name' in fields else fields.pop(resource, '')
        # VDB supports an atomic domain+database declaration.  Keeping this
        # in the command serializer is important: workspace repair uses the
        # same flat action boundary as every other service-management caller.
        if resource == 'domain' and fields.get('db'):
            database = fields.pop('db')
            head = 'create domain ' + quote(name) + ' = { database: ' + obj(database) + ' }'
        else:
            head = 'create ' + resource + ' ' + quote(name)
    elif action == 'use':
        resource = 'domain' if 'domain' in fields else 'db'
        head = 'use ' + resource + ' ' + quote(fields.pop(resource))
    elif action in ('find', 'read'):
        collection = fields.pop('collection'); head = 'read collection ' + quote(collection) + predicate(fields.pop('where', {}))
        if fields.get('projection'):
            projection = fields.pop('projection'); head += ' select [' + ', '.join(k for k, v in projection.items() if v) + ']'
        if fields.get('sort'):
            sort = fields.pop('sort'); head += ' order by ' + ', '.join(f'{k} {"asc" if int(v) >= 0 else "desc"}' for k, v in sort.items())
        if fields.get('offset') is not None: head += ' offset ' + str(fields.pop('offset'))
        if fields.get('limit') is not None: head += ' limit ' + str(fields.pop('limit'))
    elif action in ('insert', 'create'):
        document = fields.pop('document', None)
        if document is None: document = fields.pop('data', {})
        head = 'create in ' + quote(fields.pop('collection')) + ' = ' + obj(document)
    elif action == 'update':
        head = 'update collection ' + quote(fields.pop('collection')) + predicate(fields.pop('where', {})) + ' { '
        updates = fields.pop('set', {})
        for key, value in updates.items(): head += f'{key} = {obj(value)}; '
        for key, value in fields.pop('inc', {}).items(): head += f'{key} += {obj(value)}; '
        for key in fields.pop('unset', {}).keys(): head += f'unset {key}; '
        head += '}'
    elif action == 'delete':
        head = 'delete from ' + quote(fields.pop('collection')) + predicate(fields.pop('where', {}))
    elif action in ('create_collection', 'drop_collection'):
        collection = fields.pop('collection')
        if action == 'create_collection':
            schema = fields.pop('schema', None)
            if schema:
                declarations = []
                for key, definition in schema.items():
                    if isinstance(definition, dict):
                        field_type = definition.get('type', 'string')
                        suffix = ''
                        if 'default' in definition: suffix += ' = ' + obj(definition['default'])
                        if definition.get('required'): suffix += ' @required'
                        if definition.get('unique'): suffix += ' @unique'
                        declarations.append(f'{key}: {field_type}{suffix}')
                    else: declarations.append(f'{key}: {definition}')
                head = 'create collection ' + quote(collection) + ' = { ' + ', '.join(declarations) + ' }'
            else: head = 'create collection ' + quote(collection)
        else: head = 'drop collection ' + quote(collection)
    elif action.startswith('script_'):
        operation = action[7:]
        head = 'read scripts' if operation == 'list' else ('run' if operation == 'execute' else operation) + ' script'
    elif action.startswith('transaction_'):
        head = action[12:] + ' transaction'
    elif action.startswith('domain_'):
        name = fields.pop('domain') if 'domain' in fields else fields.pop('name', '')
        head = action[7:] + ' domain ' + quote(name)
    elif action in ('drop_domain', 'drop_db'):
        resource = action[5:]
        name = fields.pop(resource) if resource in fields else fields.pop('name', '')
        head = 'drop ' + resource + ' ' + quote(name)
    elif action.startswith('model_'):
        head = ('read' if action == 'model_get' else 'delete') + ' model'
    elif action in ('create_index', 'drop_index', 'list_indexes', 'rebuild_indexes'):
        head = action.replace('_', ' ')
    else:
        head = action
    return ' '.join([head, *(str(key) + ' ' + obj(value) for key, value in fields.items() if value is not None)])


def _simple_name(value):
    # Keep values with punctuation quoted.  In particular, usernames and
    # email addresses commonly contain dots; leaving them bare makes older
    # VDB command parsers interpret the dot as syntax and fail with
    # INVALID_CHARACTER while executing generated LAPIS services.
    return isinstance(value, str) and bool(value) and all(ch.isalnum() or ch == '_' for ch in value) and value.lower() not in {'true', 'false', 'null'}


_OPTIONS = set('where data set schema limit skip sort projection fields domain db database name username password email role permissions scope collection model field unique code service params pipeline resource operation value domains package out_dir topic section page page_size pageSize args options documents index update filter inc unset document sparse relinquish zip payload type'.split())
_ACTIONS = set('define use list find read insert create update delete drop aggregate create_collection drop_collection drop_domain drop_db create_index drop_index list_indexes rebuild_indexes model_get model_delete script_create script_read script_execute script_delete script_list transaction_begin transaction_commit transaction_abort domain_status domain_suspend domain_resume tumi help context whoami echo export'.split())


def _tokens(source):
    result, token = [], ''
    quote, escaped, depth = '', False, 0
    for char in source:
        if quote:
            token += char
            if escaped: escaped = False
            elif char == '\\': escaped = True
            elif char == quote: quote = ''
            continue
        if char in '\"\'': quote = char; token += char; continue
        if char in '{[': depth += 1
        if char in '}]': depth -= 1
        if depth < 0: raise ValueError('Unbalanced data literal')
        if depth == 0 and (char.isspace() or char in ';,='):
            if token: result.append(token); token = ''
            if char in ';\n': result.append(';')
            elif char in ',=': result.append(char)
        else: token += char
    if quote or depth: raise ValueError('Unclosed quote or data literal')
    if token: result.append(token)
    return result


def parse_command(source):
    """Validate command syntax locally; execution and permissions remain in VDB."""
    if not isinstance(source, str) or not source.strip() or source.lstrip().startswith(('{', '[')):
        raise ValueError('Use a readable VDB command, for example: read users or read collection orders')
    native = _parse_native_read(source)
    if native is not None:
        return native
    tokens = _tokens(source)
    position = 0
    def peek(): return tokens[position] if position < len(tokens) else ''
    def take():
        nonlocal position
        if not peek() or peek() == ';': raise ValueError('Incomplete VDB command. Type help for examples.')
        token = tokens[position]; position += 1; return token
    def accept(token):
        nonlocal position
        if peek().lower() == token: position += 1; return True
        return False
    def value(token):
        if token.startswith("'") and token.endswith("'"): return token[1:-1].replace("\\'", "'")
        try: return json.loads(token)
        except ValueError:
            if token.startswith(('"', '{', '[')): raise ValueError('Invalid data literal') from None
            return token
    def positional(command, key):
        if peek() and peek() != ';' and peek() not in _OPTIONS: command[key] = value(take())
    commands = []
    while peek():
        if accept(';'): continue
        verb = take().lower(); target = peek().lower(); command = {}; action = verb
        if verb in ('whoami', 'context'): pass
        elif verb == 'help': positional(command, 'topic')
        elif verb == 'echo':
            if peek() and peek() not in (';', 'value'): command['value'] = value(take())
        elif verb == 'transaction': action = 'transaction_' + take().lower()
        elif verb in ('begin', 'commit', 'abort'): accept('transaction'); action = 'transaction_' + verb
        elif verb in ('read', 'list') and target in ('users', 'roles', 'permissions', 'owned_domains'):
            take(); action = 'tumi'; command.update(operation='list', resource=target)
        elif verb in ('read', 'list') and target in ('domains', 'domains_and_owners', 'dbs', 'databases', 'collections', 'models', 'scripts'):
            take(); action = 'list'; command['resource'] = 'dbs' if target == 'databases' else target
        elif target in ('user', 'role', 'permission'):
            take(); action = 'tumi'; command['operation'] = verb; positional(command, 'role' if target == 'role' else 'username')
        elif verb in ('grant', 'revoke', 'transfer'):
            action = 'tumi'; command['operation'] = verb; positional(command, 'username')
        elif target == 'script':
            take(); action = 'script_' + ('execute' if verb == 'run' else verb); positional(command, 'name')
        elif target == 'model':
            take(); action = 'model_' + ('get' if verb == 'read' else verb); positional(command, 'model')
        elif target in ('index', 'indexes'):
            take(); action = 'list_indexes' if verb in ('read', 'list') else verb + '_' + target; positional(command, 'collection')
        elif target in ('domain', 'db', 'database'):
            take(); resource = 'db' if target == 'database' else target
            if verb == 'use': command[resource] = value(take())
            elif verb in ('create', 'define'): action = 'define'; command.update(resource=resource, name=value(take()))
            elif verb in ('drop', 'delete'): action = 'drop_' + resource; command[resource] = value(take())
            else: action = 'domain_' + ('status' if verb == 'read' else verb); command['domain'] = value(take())
        elif target == 'collection':
            take(); command['collection'] = value(take()); action = {'create': 'create_collection', 'drop': 'drop_collection', 'read': 'find'}.get(verb, verb)
        elif verb in ('read', 'find', 'insert', 'create', 'update', 'delete', 'aggregate', 'drop'):
            command['collection'] = value(take()); action = {'read': 'find', 'create': 'insert'}.get(verb, verb)
        command['action'] = action
        if action not in _ACTIONS: raise ValueError('Unknown VDB command. Type help for examples.')
        while peek() and peek() != ';':
            key = take()
            if key not in _OPTIONS: raise ValueError(f"Unknown option '{key}'. Type help for examples.")
            if key == 'database': key = 'db'
            accept('=')
            if key in ('where', 'data', 'set') and not peek().startswith(('{', '[')):
                fields = {}
                while True:
                    field = take()
                    if not accept('='): raise ValueError(f"Expected '=' after {field}")
                    fields[field] = value(take())
                    if not (accept(',') or accept('and')): break
                command[key] = fields
            else: command[key] = value(take())
        if action == 'insert' and 'data' in command: command['document'] = command.pop('data')
        if action == 'update' and 'data' in command: command['set'] = command.pop('data')
        required = []
        if action in ('find', 'read', 'insert', 'update', 'delete', 'drop', 'aggregate', 'create_collection', 'drop_collection', 'create_index', 'drop_index', 'list_indexes', 'rebuild_indexes'): required.append('collection')
        if action in ('create_index', 'drop_index'): required.append('field')
        if action in ('insert', 'create'): required.append('document')
        if action.startswith('model_'): required.append('model')
        if action in ('script_create', 'script_read', 'script_execute', 'script_delete'): required.append('name')
        for key in required:
            if key not in command: raise ValueError(f'Missing {key}. Type help for examples.')
        if action == 'update' and not any(isinstance(command.get(key), dict) for key in ('set', 'inc', 'unset')):
            raise ValueError('Update requires set, inc or unset fields')
        commands.append(command)
    if not commands: raise ValueError('Enter a VDB command')
    return commands[0] if len(commands) == 1 else {'commands': commands}


def _parse_native_read(source):
    """Parse the native read/count surface into the SDK compatibility shape.

    The service generator still merges request parameters using a flat mapping;
    this adapter keeps that boundary typed while the stored LAPIS command stays
    native Versa text.
    """
    text = str(source or '').strip().rstrip(';').strip()
    match = re.match(r'^(read|find|count)\s+(?:collection\s+)?([A-Za-z_][A-Za-z0-9_.-]*)(.*)$', text, re.I | re.S)
    if not match:
        return None
    verb, collection, tail = match.groups()
    result = {'collection': collection, 'action': 'count' if verb.lower() == 'count' else 'find'}
    where_match = re.search(r'\bwhere\s+(.+?)(?=\s+(?:select|order\s+by|offset|limit)\b|$)', tail, re.I | re.S)
    if where_match:
        conditions = {}
        for clause in re.split(r'\s+&&\s+', where_match.group(1).strip()):
            cond = re.match(r'^([A-Za-z_][A-Za-z0-9_.]*)\s*(==|=|!=|>=|<=|>|<|in|!in)\s*(.+)$', clause.strip(), re.I | re.S)
            if not cond:
                raise ValueError('Native VDB where expression must use field comparisons')
            field, operator, raw_value = cond.groups()
            try:
                value = json.loads(raw_value.strip())
            except json.JSONDecodeError:
                value = raw_value.strip()
            op = {'==': '$eq', '=': '$eq', '!=': '$ne', '>': '$gt', '<': '$lt', '>=': '$gte', '<=': '$lte', 'in': '$in', '!in': '$nin'}[operator.lower()]
            if operator == '=' and isinstance(value, dict) and len(value) == 1 and next(iter(value)).startswith('$'):
                conditions[field] = value
                continue
            conditions[field] = value if operator == '==' else {op: value}
        result['where'] = conditions
    limit_match = re.search(r'\blimit\s+(\d+)', tail, re.I)
    offset_match = re.search(r'\boffset\s+(\d+)', tail, re.I)
    if limit_match: result['limit'] = int(limit_match.group(1))
    if offset_match: result['offset'] = int(offset_match.group(1))
    page_match = re.search(r'\bpage\s+(\d+)', tail, re.I)
    if page_match: result['page'] = int(page_match.group(1))
    select_match = re.search(r'\bselect\s*\[([^]]*)\]', tail, re.I | re.S)
    if select_match: result['projection'] = {field.strip(): True for field in select_match.group(1).split(',') if field.strip()}
    order_match = re.search(r'\border\s+by\s+(.+?)(?=\s+(?:offset|limit)\b|$)', tail, re.I | re.S)
    if order_match:
        result['sort'] = {part.strip().split()[0]: (-1 if len(part.strip().split()) > 1 and part.strip().split()[1].lower() == 'desc' else 1) for part in order_match.group(1).split(',')}
    return result
