import requests
from backend.services.plugin_manager import PluginInterface

class TelegramPlugin(PluginInterface):
    @property
    def name(self) -> str:
        return "telegram_notifications"

    @property
    def version(self) -> str:
        return "1.0.0"

    @property
    def description(self) -> str:
        return "Отправка уведомлений в Telegram при изменениях в AD."

    def run(self, event_type: str, data: dict, context: dict = None):
        # В реальности эти настройки брались бы из БД или конфига плагина
        BOT_TOKEN = "123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11"
        CHAT_ID = "-100123456789"
        
        message = ""
        if event_type == "post_create":
            message = f"🆕 **User Created**\nDN: `{data.get('dn')}`\nName: {data.get('givenName')} {data.get('sn')}"
        elif event_type == "post_modify":
            message = f"✏️ **User Modified**\nDN: `{data.get('dn')}`\nChanges: {data}"
        elif event_type == "post_delete":
            message = f"🗑️ **User Deleted**\nDN: `{data.get('dn')}`"
            
        if message:
            print(f"[TelegramPlugin] Sending message to {CHAT_ID}: {message}")
            # try:
            #     url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
            #     requests.post(url, json={"chat_id": CHAT_ID, "text": message, "parse_mode": "Markdown"})
            # except Exception as e:
            #     print(f"[TelegramPlugin] Error sending: {e}")
