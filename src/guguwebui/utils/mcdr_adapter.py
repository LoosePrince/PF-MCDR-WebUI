import logging
from typing import Any, Dict, List, Optional


class MCDRAdapter:
    @staticmethod
    def get_mcdr_server(server_interface):
        """
        Safely get the internal MCDR server object.
        """
        return getattr(server_interface, "_mcdr_server", None)

    @staticmethod
    def get_plugin_object(server_interface):
        """
        Safely get the internal plugin object.
        """
        return getattr(server_interface, "_PluginServerInterface__plugin", None)

    @staticmethod
    def get_command_manager(server_interface):
        """
        Safely get the MCDR command manager.
        """
        mcdr_server = MCDRAdapter.get_mcdr_server(server_interface)
        if mcdr_server:
            return getattr(mcdr_server, "command_manager", None)
        return None

    @staticmethod
    def get_root_nodes(server_interface) -> Dict[str, Any]:
        """
        Safely get the root nodes of the command tree.
        """
        command_manager = MCDRAdapter.get_command_manager(server_interface)
        if command_manager:
            return getattr(command_manager, "root_nodes", {})
        return {}

    @staticmethod
    def get_mcdr_logger(server_interface) -> Optional[logging.Logger]:
        """
        Safely get the MCDR internal logger.
        """
        mcdr_server = MCDRAdapter.get_mcdr_server(server_interface)
        if mcdr_server:
            return getattr(mcdr_server, "logger", None)
        return None

    @staticmethod
    def list_plugin_directory(server_interface, folder_path: str) -> List[str]:
        """
        Safely list directory contents within the plugin package.
        """
        plugin = MCDRAdapter.get_plugin_object(server_interface)
        if plugin and hasattr(plugin, "list_directory"):
            try:
                return plugin.list_directory(folder_path)
            except Exception:
                pass
        return []
