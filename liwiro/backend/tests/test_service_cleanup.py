# Copyright (c) 2026 Bwalya Cameron Chishimba
# SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Commercial

import sys
import unittest
import json
from pathlib import Path
from unittest.mock import MagicMock, patch


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.main import create_app, _lapis_change_impacts


class ServiceCleanupRoutesTests(unittest.TestCase):
    def _build_app(self):
        with patch("app.main._initialize_vdb_runtime", return_value=(True, "ok")), \
             patch("app.main._reconcile_service_runtime_states", return_value=[]), \
             patch("app.main._autostart_services_if_enabled", return_value=None):
            app = create_app()

        app.testing = True
        app.config["LIWIRO_DOMAIN"] = "liwiro"
        app.config["LIWIRO_DB"] = "config"
        app.vdb_client = MagicMock()
        app.vdb_client.async_authorize.return_value = True
        app.vdb_client.use_domain.return_value = True
        app.vdb_client.use_database.return_value = True
        app.process_manager = MagicMock()
        app.process_manager.stop_api_service.return_value = True

        token = "test-token"
        app.auth_sessions[token] = {
            "username": "zulan",
            "role": "admin",
            "is_super_admin": True,
            "service_access": ["*"],
            "permissions_overrides": [],
            "liwiro_rbac": {},
            "permissions": ["VIEW_SERVICES", "MANAGE_SERVICES"],
        }
        return app, token

    def test_model_rename_reports_affected_crud_endpoint(self):
        old = {
            "models": {"user": {"name": "User", "fields": {}}},
            "endpoints": {"listUsers": {"operationType": "crud", "linkedModel": "User"}},
            "auth": {},
        }
        new = {
            "models": {"user": {"name": "Member", "fields": {}}},
            "endpoints": {"listUsers": {"operationType": "crud", "linkedModel": "User"}},
            "auth": {},
        }

        impacts = _lapis_change_impacts(old, new)

        self.assertTrue(any("listUsers" in impact and "Renaming model" in impact for impact in impacts))

    def test_route_tester_relays_to_configured_service_with_base_path(self):
        app, token = self._build_app()
        app.vdb_client.read_documents.return_value = (
            True,
            [{
                "apiName": "accounts",
                "processId": "123",
                "port": 5011,
                "lapis_config": {
                    "metadata": {"basePath": "/api/accounts"},
                    "endpoints": {
                        "createUser": {"method": "POST", "path": "/users", "operationType": "crud", "requiresAuth": True},
                    },
                },
            }],
        )
        upstream = MagicMock(status_code=409)
        upstream.text = '{"error":"duplicate"}'
        upstream.json.return_value = {"error": "duplicate"}

        with patch("app.main.requests.request", return_value=upstream) as request_mock:
            response = app.test_client().post(
                "/services/123/test-route",
                headers={"Authorization": f"Bearer {token}"},
                json={"endpointId": "createUser", "body": {"username": "taken"}, "bearerToken": "abc"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["status"], 409)
        self.assertEqual(request_mock.call_args.args[1], "http://127.0.0.1:5011/api/accounts/users")
        self.assertEqual(request_mock.call_args.kwargs["headers"]["Authorization"], "Bearer abc")

    def test_api_governance_manifest_exposes_contract_and_lifecycle_controls(self):
        app, token = self._build_app()
        response = app.test_client().get(
            "/platform/api/governance",
            headers={"Authorization": f"Bearer {token}"},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.get_json() or {}
        self.assertEqual(payload.get("sourceOfTruth"), "LAPIS")
        self.assertEqual(payload.get("contractStages"), ["author", "validate", "generate", "document", "operate", "audit"])
        self.assertEqual((payload.get("management") or {}).get("create", {}).get("path"), "/generate")
        self.assertEqual((payload.get("management") or {}).get("testRoute", {}).get("path"), "/services/{processId}/test-route")
        self.assertEqual((payload.get("controls") or {}).get("serviceReadiness"), "services[].governance")
        self.assertTrue((payload.get("security") or {}).get("seedPasswordsAreHashedAndTransient"))

    def test_list_services_summary_mode_omits_full_lapis_config_and_skips_refresh(self):
        app, token = self._build_app()
        app.vdb_client.read_documents.return_value = (
            True,
            [
                {
                    "_id": "svc-1",
                    "apiName": "accounts-api",
                    "processId": "321",
                    "port": 5011,
                    "status": "RUNNING",
                    "createdAt": "2026-03-12T10:00:00",
                    "vdb_domain": "accounts-domain",
                    "lapis_config": {
                        "metadata": {
                            "apiName": "accounts-api",
                            "basePath": "/accounts",
                            "documentation": {
                                "enabled": True,
                                "keyHash": "secret-hash",
                            },
                        },
                        "auth": {
                            "enabled": True,
                            "isAuthService": False,
                        },
                        "endpoints": {
                            "listUsers": {
                                "method": "GET",
                                "path": "/users",
                                "operationType": "QUERY",
                            }
                        },
                    },
                }
            ],
        )

        with patch("app.main._maybe_sync_service_state") as sync_state:
            client = app.test_client()
            res = client.get(
                "/services?summary=1&refresh=0",
                headers={"Authorization": f"Bearer {token}"},
            )

        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]["apiName"], "accounts-api")
        self.assertIn("governance", data[0])
        self.assertEqual(data[0]["runtimeUrl"], "http://127.0.0.1:5011/liwiro")
        self.assertEqual(data[0]["rootUrl"], "http://127.0.0.1:5011/")
        self.assertEqual(data[0]["liwiroDocsUrl"], "http://127.0.0.1:5011/liwiro/docs")
        self.assertEqual(data[0]["basePath"], "/accounts")
        self.assertTrue(data[0]["docsEnabled"])
        self.assertTrue(data[0]["docsKeyConfigured"])
        self.assertEqual(data[0]["vdbDomain"], "accounts-domain")
        self.assertNotIn("lapis_config", data[0])
        self.assertNotIn("routes", data[0])
        self.assertNotIn("authContext", data[0])
        sync_state.assert_not_called()

    def test_list_services_summary_mode_hides_management_urls_in_production_mode(self):
        app, token = self._build_app()
        app.vdb_client.read_documents.return_value = (
            True,
            [
                {
                    "_id": "svc-1",
                    "apiName": "accounts-api",
                    "processId": "321",
                    "port": 5011,
                    "status": "RUNNING",
                    "createdAt": "2026-03-12T10:00:00",
                    "lapis_config": {
                        "metadata": {
                            "apiName": "accounts-api",
                            "basePath": "/accounts",
                            "documentation": {"enabled": True, "keyHash": "secret-hash"},
                        },
                        "auth": {},
                        "endpoints": {},
                    },
                }
            ],
        )

        with patch("app.main._load_normalized_auth_data", return_value={"settings": {"productionMode": True}}):
            client = app.test_client()
            res = client.get(
                "/services?summary=1&refresh=0",
                headers={"Authorization": f"Bearer {token}"},
            )

        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertEqual(len(data), 1)
        self.assertTrue(data[0]["productionMode"])
        self.assertFalse(data[0]["managementRoutesEnabled"])
        self.assertIsNone(data[0]["runtimeUrl"])
        self.assertIsNone(data[0]["liwiroDocsUrl"])

    def test_list_services_summary_mode_includes_sanitized_media_capabilities(self):
        app, token = self._build_app()
        app.vdb_client.read_documents.return_value = (
            True,
            [
                {
                    "_id": "svc-media",
                    "apiName": "media-bridge",
                    "processId": "654",
                    "port": 5099,
                    "status": "RUNNING",
                    "createdAt": "2026-03-12T10:00:00",
                    "lapis_config": {
                        "metadata": {
                            "apiName": "media-bridge",
                            "basePath": "/api/media",
                            "documentation": {"enabled": True, "keyHash": "secret-hash"},
                            "env": {
                                "MEDIA_DEFAULT_PROVIDER": "cloudinary",
                                "MEDIA_ASSET_COLLECTION": "media_assets",
                                "CLOUDINARY_CLOUD_NAME": "replace-with-cloudinary-cloud-name",
                                "CLOUDINARY_API_KEY": "replace-with-cloudinary-api-key",
                                "CLOUDINARY_API_SECRET": "replace-with-cloudinary-api-secret",
                            },
                        },
                        "auth": {},
                        "endpoints": {
                            "upload_cloudinary": {
                                "method": "POST",
                                "path": "/upload/cloudinary",
                                "operationType": "script",
                                "versaScript": "let res = http.post(\"https://api.cloudinary.com/v1_1/demo/auto/upload\", {});",
                            }
                        },
                    },
                }
            ],
        )

        client = app.test_client()
        res = client.get(
            "/services?summary=1&refresh=0",
            headers={"Authorization": f"Bearer {token}"},
        )

        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertEqual(len(data), 1)
        self.assertNotIn("lapis_config", data[0])
        media = data[0].get("mediaCapabilities") or {}
        self.assertTrue(media.get("enabled"))
        self.assertEqual(media.get("assetCollection"), "media_assets")
        self.assertEqual(media.get("defaultProvider"), "cloudinary")
        self.assertTrue(media.get("jsonRequestOnly"))
        provider = next((item for item in (media.get("providers") or []) if item.get("id") == "cloudinary"), None)
        self.assertIsNotNone(provider)
        self.assertFalse(provider.get("ready"))
        self.assertIn("CLOUDINARY_API_SECRET", provider.get("envKeys") or [])
        self.assertEqual(((provider.get("routes") or [])[0]).get("path"), "/upload/cloudinary")
        self.assertNotIn("replace-with-cloudinary-api-secret", json.dumps(media))

    def test_list_services_filters_inaccessible_rows_before_decoration(self):
        app, token = self._build_app()
        app.auth_sessions[token] = {
            "username": "analyst",
            "role": "viewer",
            "is_super_admin": False,
            "service_access": ["accounts-api"],
            "permissions_overrides": [],
            "liwiro_rbac": {},
            "permissions": ["VIEW_SERVICES"],
        }
        app.vdb_client.read_documents.return_value = (
            True,
            [
                {
                    "_id": "svc-1",
                    "apiName": "accounts-api",
                    "processId": "321",
                    "port": 5011,
                    "status": "RUNNING",
                    "createdAt": "2026-03-12T10:00:00",
                    "lapis_config": {"metadata": {"apiName": "accounts-api"}, "auth": {}, "endpoints": {}},
                },
                {
                    "_id": "svc-2",
                    "apiName": "payments-api",
                    "processId": "654",
                    "port": 5090,
                    "status": "RUNNING",
                    "createdAt": "2026-03-12T10:00:00",
                    "lapis_config": {"metadata": {"apiName": "payments-api"}, "auth": {}, "endpoints": {}},
                },
            ],
        )

        decorated = []

        def fake_decorate(service_doc, **_kwargs):
            decorated.append(str(service_doc.get("apiName") or ""))
            return {"apiName": str(service_doc.get("apiName") or ""), "processId": str(service_doc.get("processId") or "")}

        with patch("app.main._decorate_service", side_effect=fake_decorate):
            client = app.test_client()
            res = client.get(
                "/services?summary=1&refresh=0",
                headers={"Authorization": f"Bearer {token}"},
            )

        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.get_json(), [{"apiName": "accounts-api", "processId": "321"}])
        self.assertEqual(decorated, ["accounts-api"])

    def test_auth_key_export_route_returns_manual_key_pair_for_auth_service(self):
        app, token = self._build_app()
        app.vdb_client.read_documents.return_value = (
            True,
            [
                {
                    "apiName": "authcore",
                    "processId": "321",
                    "lapis_config": {
                        "metadata": {"apiName": "authcore"},
                        "auth": {
                            "enabled": True,
                            "isAuthService": True,
                            "keyManagement": "manual",
                            "privateKey": "PRIVATE-KEY-DATA",
                            "publicKey": "PUBLIC-KEY-DATA",
                        },
                    },
                }
            ],
        )

        client = app.test_client()
        res = client.get(
            "/services/321/auth-keys",
            headers={"Authorization": f"Bearer {token}"},
        )

        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertEqual(data["service"], "authcore")
        self.assertEqual(data["materialType"], "key-pair")
        self.assertEqual(len(data["files"]), 2)
        self.assertEqual(data["files"][0]["filename"], "authcore-private-key.pem")
        self.assertEqual(data["files"][1]["filename"], "authcore-public-key.pem")

    def test_auth_key_export_route_returns_active_shared_secret_for_auto_auth_service(self):
        app, token = self._build_app()
        app.vdb_client.read_documents.return_value = (
            True,
            [
                {
                    "apiName": "authcore",
                    "processId": "321",
                    "lapis_config": {
                        "metadata": {
                            "apiName": "authcore",
                            "setupApiKey": "setup-secret",
                        },
                        "auth": {
                            "enabled": True,
                            "isAuthService": True,
                            "keyManagement": "auto",
                        },
                    },
                }
            ],
        )

        client = app.test_client()
        res = client.get(
            "/services/321/auth-keys",
            headers={"Authorization": f"Bearer {token}"},
        )

        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertEqual(data["materialType"], "shared-secret")
        self.assertIn("shared-secret", data["caution"])
        self.assertEqual(len(data["files"]), 1)
        self.assertEqual(data["files"][0]["filename"], "authcore-signing-secret.txt")
        self.assertEqual(data["files"][0]["content"], "setup-secret")

    def test_update_service_can_persist_manager_state_without_restarting(self):
        app, token = self._build_app()
        manager_state = {
            "testing": {
                "auth": {
                    "profileChoice": "kalulu.kaumba",
                    "token": "jwt-token",
                    "profile": {
                        "username": "kalulu.kaumba",
                        "email": "kalulu@example.com",
                        "password": "secret",
                        "role": "SUPER_ADMIN",
                    },
                },
                "routes": {
                    "listUsers": {
                        "queryText": "{\n  \"limit\": 5\n}",
                        "bodyText": "{}",
                        "bearerToken": "jwt-token",
                        "responseText": "HTTP 200\n[]",
                        "responseToken": "",
                    },
                },
            },
        }
        app.vdb_client.read_documents.side_effect = [
            (
                True,
                [
                    {
                        "apiName": "accounts-api",
                        "processId": "321",
                        "port": 5011,
                        "status": "RUNNING",
                        "lapis_config": {
                            "metadata": {"apiName": "accounts-api"},
                            "auth": {},
                            "models": {},
                            "endpoints": {},
                        },
                    }
                ],
            ),
            (
                True,
                [
                    {
                        "apiName": "accounts-api",
                        "processId": "321",
                        "port": 5011,
                        "status": "RUNNING",
                        "lapis_config": {
                            "metadata": {"apiName": "accounts-api"},
                            "auth": {},
                            "models": {},
                            "endpoints": {},
                        },
                        "managerState": manager_state,
                    }
                ],
            ),
        ]

        client = app.test_client()
        res = client.put(
            "/services/321",
            json={"manager_state": manager_state, "restart": False},
            headers={"Authorization": f"Bearer {token}"},
        )

        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertEqual(data["managerState"], manager_state)
        app.process_manager.restart_service.assert_not_called()
        self.assertEqual(app.vdb_client.update_document.call_count, 1)
        args = app.vdb_client.update_document.call_args.args
        self.assertEqual(args[0], "services")
        self.assertEqual(args[1], {"processId": {"$eq": "321"}})
        self.assertEqual(args[2]["apiName"], "accounts-api")
        self.assertEqual(args[2]["managerState"], manager_state)
        self.assertIn("updatedAt", args[2])

    def test_stop_service_route_stops_process_and_persists_status(self):
        app, token = self._build_app()
        app.vdb_client.read_documents.return_value = (
            True,
            [{"apiName": "accounts-api", "processId": "321", "port": 5011}],
        )
        app.vdb_client.update_document.return_value = (True, {})

        response = app.test_client().post(
            "/services/321/stop",
            headers={"Authorization": f"Bearer {token}"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("stopped", (response.get_json() or {}).get("message", "").lower())
        app.process_manager.stop_api_service.assert_called_once_with(321)
        update_args = app.vdb_client.update_document.call_args.args
        self.assertEqual(update_args[0], "services")
        self.assertEqual(update_args[2]["status"], "NOT_RUNNING")

    def test_start_service_route_restarts_process_and_updates_runtime_record(self):
        app, token = self._build_app()
        service = {
            "apiName": "accounts-api",
            "processId": "321",
            "port": 5011,
            "status": "NOT_RUNNING",
            "lapis_config": {
                "metadata": {"apiName": "accounts-api"},
                "auth": {},
                "models": {},
                "endpoints": {},
            },
        }
        app.vdb_client.read_documents.return_value = (True, [service])
        app.vdb_client.update_document.return_value = (True, {})
        app.process_manager.restart_service.return_value = (654, 5012)

        response = app.test_client().post(
            "/services/321/start",
            headers={"Authorization": f"Bearer {token}"},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.get_json() or {}
        self.assertEqual(payload.get("process_id"), 654)
        self.assertIn("restarted", payload.get("message", "").lower())
        app.process_manager.restart_service.assert_called_once_with(321, service["lapis_config"], "accounts-api")
        update_args = app.vdb_client.update_document.call_args.args
        self.assertEqual(update_args[0], "services")
        self.assertEqual(update_args[2]["status"], "RUNNING")
        self.assertEqual(update_args[2]["processId"], "654")

    def test_delete_service_with_data_removal_drops_service_domain(self):
        app, token = self._build_app()
        app.vdb_client.read_documents.return_value = (
            True,
            [
                {
                    "apiName": "articles-api",
                    "vdb_domain": "articles-domain",
                    "processId": "321",
                    "port": 5011,
                }
            ],
        )
        app.vdb_client.drop_domain.return_value = (True, {"message": "dropped"})
        app.vdb_client.list_domains.return_value = (True, ["liwiro", "default"])

        client = app.test_client()
        res = client.delete(
            "/services/321/delete?deleteData=true",
            headers={"Authorization": f"Bearer {token}"},
        )

        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data["data_cleanup"]["requested"])
        self.assertTrue(data["data_cleanup"]["droppedDomain"])
        self.assertTrue(data["data_cleanup"]["droppedDb"])
        self.assertEqual(data["data_cleanup"]["errors"], [])
        app.vdb_client.drop_domain.assert_called_once_with("articles-domain")
        app.vdb_client.drop_database.assert_not_called()
        app.vdb_client.delete_document.assert_called_once()

    def test_delete_service_fails_when_domain_is_still_visible_after_drop(self):
        app, token = self._build_app()
        app.vdb_client.read_documents.return_value = (
            True,
            [
                {
                    "apiName": "billing-api",
                    "vdb_domain": "billing-domain",
                    "processId": "654",
                    "port": 5012,
                }
            ],
        )
        app.vdb_client.drop_domain.return_value = (True, {"message": "dropped"})
        app.vdb_client.list_domains.return_value = (True, ["billing-domain"])

        client = app.test_client()
        res = client.delete(
            "/services/654/delete?deleteData=true",
            headers={"Authorization": f"Bearer {token}"},
        )

        self.assertEqual(res.status_code, 500)
        data = res.get_json()
        self.assertIn("did not complete", data["error"])
        self.assertIn(
            "Service domain 'billing-domain' still exists after deletion attempt",
            data["data_cleanup"]["errors"],
        )
        app.vdb_client.drop_domain.assert_called_once_with("billing-domain")
        app.vdb_client.delete_document.assert_not_called()

    def test_vdb_whoami_no_longer_exposes_ownership_consistency_payload(self):
        app, token = self._build_app()
        portal_token = "portal-token"
        app.vdb_portal_sessions[portal_token] = {
            "mode": "app",
            "username": "liwiro",
            "owner_username": "zulan",
            "vdb_transport": "http",
            "vdb_server_url": "http://127.0.0.1:1957",
            "issued_at": "2026-03-11T00:00:00",
        }

        with patch(
            "app.main._vdb_portal_query",
            side_effect=[
                (
                    True,
                    {
                        "data": {
                            "username": "liwiro",
                            "owned_domains": ["articles-domain", "ghost-domain"],
                        }
                    },
                ),
                (True, ["articles-domain"]),
                (True, ["articles-domain", "ghost-domain"]),
            ],
        ):
            client = app.test_client()
            res = client.get(
                "/platform/vdb/whoami",
                headers={
                    "Authorization": f"Bearer {token}",
                    "X-VDB-Portal-Token": portal_token,
                },
            )

        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertNotIn("consistency", data)
        self.assertEqual(data["data"]["owned_domains"], ["articles-domain"])
        self.assertEqual(data["data"]["ownedDomains"], ["articles-domain"])


if __name__ == "__main__":
    unittest.main()
