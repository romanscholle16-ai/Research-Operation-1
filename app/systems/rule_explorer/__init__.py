"""Rule/Logic Explorer: tests structural variations to strategy logic
(add/remove confirmation, AND vs OR, alternative entries/exits, ...).
Built around explicit, named strategy variants rather than arbitrary
code generation - every experiment records exactly which rule
configuration produced it."""

from app.systems.rule_explorer.explorer import RuleExplorer, RuleExplorerRequest, RuleVariant

__all__ = ["RuleExplorer", "RuleExplorerRequest", "RuleVariant"]
