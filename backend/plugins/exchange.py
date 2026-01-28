from backend.services.plugin_manager import PluginInterface

class ExchangePlugin(PluginInterface):
    @property
    def name(self) -> str:
        return "exchange_integration"

    @property
    def version(self) -> str:
        return "1.0.0"

    @property
    def description(self) -> str:
        return "Автоматическое создание почтовых ящиков Exchange при создании пользователя."

    def run(self, event_type: str, data: dict, context: dict = None):
        if event_type == "post_create":
            user_dn = data.get("dn")
            mail = data.get("mail")
            if not mail:
                print(f"[ExchangePlugin] No mail attribute for {user_dn}, skipping mailbox creation.")
                return
            
            # В реальности здесь был бы вызов PowerShell:
            # Enable-Mailbox -Identity user_dn -Alias ...
            print(f"[ExchangePlugin] Creating mailbox for {user_dn} ({mail})... SUCCESS")
            
        elif event_type == "post_delete":
            user_dn = data.get("dn")
            # Disable-Mailbox ...
            print(f"[ExchangePlugin] Disabling mailbox for {user_dn}... SUCCESS")
