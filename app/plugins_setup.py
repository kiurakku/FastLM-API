import logging

from hookify import PluginRegistry
from hookify.plugins import AuditLogPlugin, PIIMaskPlugin, PromptInjectionPlugin

from app.settings import settings

log = logging.getLogger("fastlm")


def build_plugin_registry() -> PluginRegistry:
    reg = PluginRegistry()
    names = {x.strip() for x in settings.enabled_plugins.split(",") if x.strip()}
    if "pii_mask" in names:
        reg.register(PIIMaskPlugin())
    if "prompt_injection" in names:
        reg.register(PromptInjectionPlugin())
    if "audit" in names:
        reg.register(AuditLogPlugin(sink=lambda line: log.info("audit %s", line)))
    return reg


plugin_registry = build_plugin_registry()
