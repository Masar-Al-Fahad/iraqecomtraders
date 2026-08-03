import logging
import os
import httpx
from datetime import datetime

logger = logging.getLogger(__name__)


class WhatsAppService:
    """Service for sending WhatsApp messages via WhatsApp Business Cloud API"""

    def __init__(self):
        self.phone_number_id = os.environ.get("WHATSAPP_PHONE_NUMBER_ID", "")
        self.access_token = os.environ.get("WHATSAPP_CLOUD_API_TOKEN", "")
        self.api_url = f"https://graph.facebook.com/v18.0/{self.phone_number_id}/messages"

    def _format_phone(self, phone: str) -> str:
        """Format Iraqi phone number to international format"""
        phone = phone.strip().replace(" ", "").replace("-", "")
        if phone.startswith("07"):
            phone = "964" + phone[1:]
        elif phone.startswith("+964"):
            phone = phone[1:]
        elif not phone.startswith("964"):
            phone = "964" + phone
        return phone

    async def send_message(self, phone: str, message: str) -> dict:
        """Send a WhatsApp text message"""
        if not self.phone_number_id or not self.access_token:
            logger.warning("WhatsApp credentials not configured")
            return {"success": False, "error": "WhatsApp credentials not configured"}

        formatted_phone = self._format_phone(phone)

        payload = {
            "messaging_product": "whatsapp",
            "to": formatted_phone,
            "type": "text",
            "text": {"body": message}
        }

        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json"
        }

        try:
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.post(self.api_url, json=payload, headers=headers)
                if response.status_code == 200:
                    logger.info(f"WhatsApp message sent successfully to {formatted_phone}")
                    return {"success": True, "timestamp": datetime.utcnow().isoformat()}
                else:
                    logger.error(f"WhatsApp API error: {response.status_code} - {response.text}")
                    return {"success": False, "error": f"API error: {response.status_code}"}
        except Exception as e:
            logger.error(f"WhatsApp send error: {str(e)}")
            return {"success": False, "error": str(e)}

    def get_registration_message(self, merchant_name: str, business_name: str) -> str:
        """Get the registration confirmation message"""
        return (
            f"مرحبًا {merchant_name}\n\n"
            f"تم إرسال طلب انضمامك إلى تجمع تجار التجارة الإلكترونية في العراق بنجاح.\n\n"
            f"اسم النشاط التجاري:\n{business_name}\n\n"
            f"طلبك الآن قيد المراجعة، وسيتم إشعارك عبر واتساب بعد مراجعة الطلب."
        )

    def get_approval_message(self) -> str:
        """Get the approval message"""
        return (
            "مرحبًا بك في تجمع تجار التجارة الإلكترونية في العراق 🌹\n\n"
            "تمت الموافقة على طلب انضمامك بنجاح، وأصبحت عضوًا في التجمع.\n\n"
            "يمكنك الآن الانضمام إلى كروب الواتساب الرسمي عبر الرابط التالي:\n\n"
            "https://chat.whatsapp.com/K7mtcycs8bBAnryQk3UgLc\n\n"
            "نتمنى لك التوفيق، ونسعد بانضمامك إلى أكبر تجمع لتجار التجارة الإلكترونية في العراق."
        )