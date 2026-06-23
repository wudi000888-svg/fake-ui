import urllib.parse

import audit_log
import desktop_bundle
import desktop_catalog
import desktop_config_builder
import desktop_runtime
from api_common import ok, require_admin
from http_utils import api_error


def handle_desktop_get(path, session):
    parsed = urllib.parse.urlparse(path)
    clean = parsed.path
    if not clean.startswith("/api/desktops"):
        return None
    if (err := require_admin(session)):
        return err

    if clean == "/api/desktops":
        return ok(devices=desktop_catalog.list_devices(), network=desktop_catalog.get_network(), topology=desktop_config_builder.topology())

    if clean == "/api/desktops/server-wireguard-config":
        return ok(
            filename="fake-ui-vps-wireguard.conf",
            content=desktop_config_builder.server_wireguard_config(),
            content_type="text/plain",
        )

    prefix = "/api/desktops/"
    suffix = "/bundle"
    if clean.startswith(prefix) and clean.endswith(suffix):
        node_id = urllib.parse.unquote(clean[len(prefix):-len(suffix)].strip("/"))
        try:
            device = desktop_catalog.get_device(node_id)
        except RuntimeError as exc:
            return api_error(str(exc), 404)
        return ok(
            filename=f"{device.get('id')}-remote-desktop-agent.zip",
            content=desktop_bundle.build_bundle(device),
            content_type="application/zip",
        )

    suffix = "/wireguard-config"
    if clean.startswith(prefix) and clean.endswith(suffix):
        node_id = urllib.parse.unquote(clean[len(prefix):-len(suffix)].strip("/"))
        try:
            device = desktop_catalog.get_device(node_id)
        except RuntimeError as exc:
            return api_error(str(exc), 404)
        return ok(
            filename=f"{device.get('id')}-wireguard.conf",
            content=desktop_config_builder.wireguard_config(device),
            content_type="text/plain",
        )

    return api_error("not found", 404)


def handle_desktop_post(clean, data, session):
    if not clean.startswith("/api/desktops"):
        return None
    if (err := require_admin(session)):
        return err

    if clean == "/api/desktops/save":
        try:
            device = desktop_catalog.upsert_device(data or {})
        except RuntimeError as exc:
            return api_error(str(exc), 400)
        audit_log.write(session.get("u", "admin"), "desktop.save", device.get("id", ""), device)
        return ok(
            device=device,
            devices=desktop_catalog.list_devices(),
            topology=desktop_config_builder.topology(),
            applied=False,
        )

    if clean == "/api/desktops/network":
        try:
            network = desktop_catalog.update_network(data or {})
        except RuntimeError as exc:
            return api_error(str(exc), 400)
        audit_log.write(session.get("u", "admin"), "desktop.network", "wireguard", network)
        return ok(network=network, devices=desktop_catalog.list_devices(), topology=desktop_config_builder.topology())

    if clean == "/api/desktops/action":
        action = (data or {}).get("action", "")
        node_id = (data or {}).get("id", "")
        try:
            if action == "delete":
                device = desktop_catalog.delete_device(node_id)
            elif action in ("enable", "disable"):
                device = desktop_catalog.set_device_enabled(node_id, action == "enable")
            else:
                return api_error("unknown desktop action", 400)
        except RuntimeError as exc:
            return api_error(str(exc), 400)
        audit_log.write(session.get("u", "admin"), "desktop." + action, node_id)
        return ok(device=device, devices=desktop_catalog.list_devices(), topology=desktop_config_builder.topology())

    if clean == "/api/desktops/apply":
        try:
            result = desktop_runtime.apply_hysteria_desktop_users()
        except RuntimeError as exc:
            return api_error(str(exc), 400)
        audit_log.write(session.get("u", "admin"), "desktop.apply", "hysteria2", result)
        return ok(result=result, devices=desktop_catalog.list_devices(), topology=desktop_config_builder.topology())

    if clean == "/api/desktops/apply-wireguard":
        try:
            result = desktop_runtime.apply_server_wireguard()
        except RuntimeError as exc:
            return api_error(str(exc), 400)
        audit_log.write(session.get("u", "admin"), "desktop.apply-wireguard", "vps", result)
        return ok(result=result, devices=desktop_catalog.list_devices(), topology=desktop_config_builder.topology())

    return api_error("not found", 404)
