from account_service import update_settings
from dashboard_service import (
    admin_links,
    dashboard,
    effective_node_ids_for_user,
    list_users,
    public_session,
    user_links,
    user_metrics,
    user_summary,
    visible_nodes_for_user,
)
from node_exit_service import apply_node_exit_info
import email_settings
import public_settings


def get_public_settings():
    return public_settings.read()


def update_public_settings(data):
    return public_settings.update(data)


def get_email_settings():
    return email_settings.public_view()


def update_email_settings(data):
    return email_settings.update(data)


__all__ = [
    "admin_links",
    "apply_node_exit_info",
    "dashboard",
    "effective_node_ids_for_user",
    "list_users",
    "public_session",
    "get_public_settings",
    "get_email_settings",
    "update_public_settings",
    "update_email_settings",
    "update_settings",
    "user_links",
    "user_metrics",
    "user_summary",
    "visible_nodes_for_user",
]
