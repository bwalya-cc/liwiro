# Copyright (c) 2026 Bwalya Cameron Chishimba
# SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Commercial

import os  # Add this at the top with other imports
import threading
from datetime import datetime
from flask import current_app, Flask
import threading
from datetime import datetime
from config import Config
from waitress import serve
from functools import lru_cache
from multiprocessing import Process, Queue
import time
import psutil
import socket
import re
from pathlib import Path

DEFAULT_SERVICE_ENV = {
    "EMAIL_SMTP_HOST": "smtp.gmail.com",
    "EMAIL_SMTP_PORT": "587",
    "EMAIL_SMTP_STARTTLS": "true",
    "EMAIL_SMTP_SSL": "false",
    "EMAIL_SMTP_AUTH": "true",
    "EMAIL_SMTP_USERNAME": "replace-with-smtp-username@example.com",
    "EMAIL_SMTP_PASSWORD": "replace-with-smtp-password",
    "EMAIL_FROM": "replace-with-from@example.com",
    "EMAIL_TO": "replace-with-to@example.com",
    "PASSWORD_RESET_URL": "http://127.0.0.1:5001/api/auth/reset-password",
}


def _safe_env_dir_name(value: str) -> str:
    text = re.sub(r"[^A-Za-z0-9._-]+", "-", str(value or "").strip())
    return text.strip("-") or "service"


def _materialize_service_env_file(api_name: str, runtime_env: dict) -> str:
    project_root = Path(__file__).resolve().parents[2]
    configured_root = str(os.getenv("LIWIRO_GENERATED_SERVICE_RUNTIME_DIR") or "").strip()
    runtime_root = Path(configured_root).expanduser().resolve() if configured_root else project_root / "data" / "generated-service-runtime"
    target_dir = runtime_root / _safe_env_dir_name(api_name)
    target_dir.mkdir(parents=True, exist_ok=True)
    env_path = target_dir / ".env"
    lines = []
    for key in sorted((runtime_env or {}).keys()):
        if not re.fullmatch(r"[A-Z_][A-Z0-9_]*", str(key or "")):
            continue
        value = str((runtime_env or {}).get(key) or "")
        escaped = value.replace("\\", "\\\\").replace("\n", "\\n").replace('"', '\\"')
        lines.append(f'{key}="{escaped}"')
    env_path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
    return str(env_path)


def _run_service(lapis_config, port, runtime_env=None, error_queue=None):
    """Create and run the API service in a child process using Uvicorn"""
    
    try:
        import os
        from dotenv import load_dotenv
        from pathlib import Path
        import threading
        from datetime import datetime

        # Inject parent runtime config so child service authenticates with the
        # same VDB credentials used by the backend.
        runtime_env = runtime_env or {}
        for key, value in runtime_env.items():
            if value is None:
                continue
            os.environ[str(key)] = str(value)

        service_env_path = str(runtime_env.get("LIWIRO_SERVICE_ENV_PATH") or "").strip()
        if service_env_path:
            load_dotenv(service_env_path, override=True)
        
        # Load environment variables with absolute path
        current_dir = Path(__file__).resolve().parent
        env_path = current_dir.parent.parent / ".env"  # Adjust path as needed
        load_dotenv(env_path)

        # Import modules after loading environment variables
        from generators.api_generator import generate_api_service
        import uvicorn
        
        api_app = generate_api_service(lapis_config)
        uvicorn.run(
            api_app,
            host='127.0.0.1',
            port=port,
            log_level="info",
            interface="wsgi",
            reload=False,
            timeout_graceful_shutdown=5
        )
        
    except Exception as e:
        if error_queue is not None:
            try:
                error_queue.put(str(e))
            except Exception:
                pass
        print(f"Critical failure in child process: {str(e)}")
        raise


class ProcessManager:
    def __init__(self, app):
        # from app.vdb import VDBClient
        import os
        from dotenv import load_dotenv
        from pathlib import Path
        import threading
        from datetime import datetime
        
        self.processes = {}
        self.port_pool = set(range(5001, 5051))
        self.used_ports = set()
        self.lock = threading.RLock()
        self.vdb_client = app.vdb_client     
    
    def process_exists(self, process_id):
        with self.lock:
            return process_id in self.processes  
        
    def _is_port_available(self, port):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("0.0.0.0", port))
                return True
            except OSError:
                return False 

    def _wait_for_port(self, host, port, timeout=10.0):
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                with socket.create_connection((host, int(port)), timeout=0.5):
                    return True
            except Exception:
                time.sleep(0.2)
        return False
        
    def _verify_service_running(self, process_id):
        try:
            return psutil.Process(process_id).is_running()
        except psutil.NoSuchProcess:
            return False
    
    def start_api_service(self, lapis_config, api_name, port=None):
        with self.lock:
            port = port or self._get_available_port()
            
            # Check if port is actually available
            if not self._is_port_available(port):
                current_app.logger.warning(f"Port {port} is occupied. Finding new port...")
                port = self._get_available_port()
            
            runtime_env = {
                "VDB_TRANSPORT": current_app.config.get("VDB_TRANSPORT"),
                "VDB_SERVER_URL": current_app.config.get("VDB_SERVER_URL"),
                "VDB_UNIX_SOCKET_PATH": current_app.config.get("VDB_UNIX_SOCKET_PATH"),
                "VDB_NAMED_PIPE_PATH": current_app.config.get("VDB_NAMED_PIPE_PATH"),
                "VDB_USERNAME": current_app.config.get("VDB_USERNAME"),
                "VDB_PASSWORD": current_app.config.get("VDB_PASSWORD"),
                "LIWIRO_DOMAIN": current_app.config.get("LIWIRO_DOMAIN"),
                "LIWIRO_DB": current_app.config.get("LIWIRO_DB"),
                "LIWIRO_DOCS_PASSWORD_HASH": current_app.config.get("LIWIRO_DOCS_PASSWORD_HASH"),
                "PORT": str(port),
            }
            metadata = lapis_config.setdefault("metadata", {})
            service_env = metadata.get("env")
            if not isinstance(service_env, dict):
                service_env = {}
                metadata["env"] = service_env
            for key, default_value in DEFAULT_SERVICE_ENV.items():
                configured = service_env.get(key)
                if configured not in (None, ""):
                    runtime_env[key] = str(configured)
                else:
                    runtime_env[key] = str(os.getenv(key, default_value))
            runtime_env["PASSWORD_RESET_URL"] = str(runtime_env.get("PASSWORD_RESET_URL") or "").replace(
                "127.0.0.1:5001",
                f"127.0.0.1:{port}",
            )

            # Persist the effective runtime env (especially PORT) onto the
            # service config so service.env.* reflects the actual running process.
            for key in DEFAULT_SERVICE_ENV:
                if key in runtime_env:
                    service_env[key] = runtime_env[key]
            service_env["PORT"] = str(port)
            runtime_env["LIWIRO_SERVICE_ENV_PATH"] = _materialize_service_env_file(api_name, service_env)
            startup_errors = Queue()

            # Start the process
            process = Process(target=_run_service, args=(lapis_config, port, runtime_env, startup_errors))
            if os.name == 'nt':
                process.daemon = True
                
            process.start()

            # Ensure process actually booted and bound the port before claiming success.
            if not self._wait_for_port("127.0.0.1", port, timeout=20.0):
                startup_detail = ""
                try:
                    if not startup_errors.empty():
                        startup_detail = str(startup_errors.get_nowait())
                except Exception:
                    startup_detail = ""
                if process.is_alive():
                    process.terminate()
                    process.join(timeout=5)
                if startup_detail:
                    raise RuntimeError(f"Service process failed to start on port {port}: {startup_detail}")
                raise RuntimeError(f"Service process failed to start on port {port}")

            self.processes[process.pid] = {
                "process": process,
                "port": port,
                "api_name": api_name,
                "lapis_config": lapis_config
            }
            self.used_ports.add(port)

            # Update existing service or create new if not found
            update_success, _ = self.vdb_client.update_document(
                "services",
                {"apiName": api_name},
                {
                    "apiName": api_name,
                    "processId": str(process.pid),
                    "status": "RUNNING",
                    "port": port,
                    "lapis_config": lapis_config,
                    "updatedAt": datetime.now().isoformat()
                }
            )
            if not update_success:
                # Create new document if update failed (no existing service)
                self.vdb_client.create_document("services", {
                    "apiName": api_name,
                    "processId": str(process.pid),
                    "status": "RUNNING",
                    "port": port,
                    "lapis_config": lapis_config,
                    "createdAt": datetime.now().isoformat()
                })
            
            return process.pid, port

    def stop_api_service(self, process_id):
        with self.lock:
            proc_info = self.processes.get(process_id)
            port = proc_info["port"] if proc_info else None
            managed_process = proc_info.get("process") if isinstance(proc_info, dict) else None
            try:
                # Terminate process tree
                parent = psutil.Process(process_id)
                children = parent.children(recursive=True)
                for child in children:
                    try:
                        child.terminate()
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        continue

                _, still_alive = psutil.wait_procs(children, timeout=5)
                for child in still_alive:
                    try:
                        child.kill()
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        continue

                parent.terminate()
                try:
                    parent.wait(10)  # Increased wait time
                except psutil.TimeoutExpired:
                    if parent.is_running():
                        parent.kill()
                        try:
                            parent.wait(5)
                        except (psutil.TimeoutExpired, psutil.NoSuchProcess):
                            pass
                if parent.is_running():
                    parent.kill()
                    try:
                        parent.wait(5)
                    except (psutil.TimeoutExpired, psutil.NoSuchProcess):
                        pass
                
            except (KeyError, psutil.NoSuchProcess):
                if process_id not in self.processes:
                    return False
            finally:
                if managed_process is not None:
                    try:
                        managed_process.join(timeout=1)
                    except Exception:
                        pass
                    try:
                        managed_process.close()
                    except Exception:
                        pass
                # Always release local runtime bookkeeping even if process shutdown was slow.
                if port is not None:
                    self.used_ports.discard(port)
                self.processes.pop(process_id, None)

            return True

    def restart_service(self, process_id, lapis_config, api_name):
        with self.lock:
            try:
                process_id_int = int(process_id)
                old_port = self.processes[process_id_int]["port"]
                
                # Stop old service
                if not self.stop_api_service(process_id_int):
                    current_app.logger.warning(f"Old process {process_id_int} failed to run, creating new process . . .")
                
                # Start new service with same port
                new_pid, port = self.start_api_service(lapis_config, api_name, port=old_port)
                
                # Verify service started successfully
                if not self._verify_service_running(new_pid):
                    raise RuntimeError("New service failed to start")
                
                return new_pid, port
                
            except KeyError:
                current_app.logger.error(f"Process {process_id} not found. Starting fresh instance")
                return self.start_api_service(lapis_config, api_name)
            
            except Exception as e:
                current_app.logger.error(f"Restart failed: {str(e)}")
                # Fallback to new port
                return self.start_api_service(lapis_config, api_name)
            
    def _get_available_port(self):
        for port in sorted(self.port_pool):
            if port not in self.used_ports:
                return port
        raise ValueError("No available ports")
    
    @lru_cache(maxsize=128)
    def get_service_port(self, process_id):
        try:
            return self.processes[int(process_id)]["port"]
        except (KeyError, ValueError):
            return None
        
    def cleanup_all_processes(self):
        with self.lock:
            for pid in list(self.processes.keys()):
                self.stop_api_service(pid)
            self.used_ports.clear()
