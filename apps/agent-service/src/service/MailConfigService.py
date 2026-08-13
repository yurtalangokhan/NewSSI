"""Business logic for SMTP mail configurations."""

from __future__ import annotations

import base64
import json
import smtplib
import ssl
from email.message import EmailMessage
from email.utils import formataddr, make_msgid
from typing import Any

from i18n import t

from core.db.repositories.mail_config_repo import MailConfigRepository
from core.security.encryption import decrypt_secret, encrypt_secret


class MailConfigService:
    """Manage SMTP configurations and safe secret handling."""

    _instance: MailConfigService | None = None

    def __init__(self, repo: MailConfigRepository | None = None):
        self.repo = repo or MailConfigRepository()

    @classmethod
    def get_instance(cls) -> MailConfigService:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @staticmethod
    def _masked(row: dict[str, Any]) -> dict[str, Any]:
        result = {
            key: value
            for key, value in row.items()
            if key not in {"password", "password_encrypted"}
        }
        result["password_configured"] = bool(row.get("password_encrypted"))
        return result

    async def list_configs(self, user_id: str) -> list[dict[str, Any]]:
        rows = await self.repo.list_by_user(user_id)
        return [self._masked(row) for row in rows]

    async def get_config(self, user_id: str, config_id: str) -> dict[str, Any] | None:
        row = await self.repo.get_by_id(user_id, config_id)
        return self._masked(row) if row else None

    async def get_decrypted_config(self, user_id: str, config_id: str) -> dict[str, Any]:
        row = await self.repo.get_by_id(user_id, config_id)
        if not row:
            raise ValueError(t("mailConfig.notFound"))
        config = self._masked(row)
        config["password"] = decrypt_secret(row["password_encrypted"])
        return config

    async def create_config(self, user_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        values = dict(payload)
        password = values.pop("password")
        row = await self.repo.create(
            user_id=user_id,
            password_encrypted=encrypt_secret(password),
            **values,
        )
        return self._masked(row)

    async def update_config(
        self,
        user_id: str,
        config_id: str,
        payload: dict[str, Any],
    ) -> dict[str, Any] | None:
        values = {key: value for key, value in payload.items() if value is not None}
        if "password" in values:
            values["password_encrypted"] = encrypt_secret(str(values.pop("password")))
        row = await self.repo.update(user_id, config_id, **values)
        return self._masked(row) if row else None

    async def delete_config(self, user_id: str, config_id: str) -> bool:
        if await self.repo.has_active_bindings(user_id, config_id):
            raise ValueError(t("mailConfig.attachedToAgent"))
        return await self.repo.deactivate(user_id, config_id)

    async def send_test_email(self, user_id: str, config_id: str, to_email: str) -> dict[str, Any]:
        config = await self.get_decrypted_config(user_id, config_id)
        result = self._send_email_message(
            config,
            to_email,
            "Agentic AI SMTP test",
            "This test email confirms that your SMTP configuration can send mail.",
        )
        parsed = json.loads(result)
        success = bool(parsed.get("success"))
        if success:
            await self.repo.mark_tested(user_id, config_id)
        error_detail = parsed.get("error")
        error_category = parsed.get("error_category", "smtp")
        message = (
            t("mailConfig.testEmailSent")
            if success
            else t("mailConfig.testEmailFailed", detail=error_detail or error_category)
        )
        return {"success": success, "message": message, "result": result}

    async def send_email(
        self,
        user_id: str,
        config_id: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        config = await self.get_decrypted_config(user_id, config_id)
        result = self._send_email_payload(config, payload)
        parsed = json.loads(result)
        success = bool(parsed.get("success"))
        error_detail = parsed.get("error")
        error_category = parsed.get("error_category", "smtp")
        message = (
            t("mailConfig.emailSent")
            if success
            else t("mailConfig.emailFailed", detail=error_detail or error_category)
        )
        return {"success": success, "message": message, "result": result}

    @staticmethod
    def _as_list(value: list[str] | str | None) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return [str(item).strip() for item in value if str(item).strip()]

    @staticmethod
    def _attach_files(message: EmailMessage, attachments: list[dict[str, Any]] | None) -> None:
        for attachment in attachments or []:
            filename = str(attachment.get("filename") or "").strip()
            content_base64 = str(attachment.get("content_base64") or "").strip()
            mime_type = str(
                attachment.get("mime_type") or "application/octet-stream"
            ).split(";")[0]
            maintype, _, subtype = mime_type.partition("/")
            if not filename or not content_base64:
                raise ValueError(t("mailConfig.attachmentRequired"))
            if not maintype or not subtype:
                maintype, subtype = "application", "octet-stream"
            content = base64.b64decode(content_base64, validate=True)
            message.add_attachment(
                content,
                maintype=maintype,
                subtype=subtype,
                filename=filename,
            )

    @staticmethod
    def _send_email_payload(config: dict[str, Any], payload: dict[str, Any]) -> str:
        to_list = MailConfigService._as_list(payload.get("to"))
        cc_list = MailConfigService._as_list(payload.get("cc"))
        bcc_list = MailConfigService._as_list(payload.get("bcc"))
        all_recipients = [*to_list, *cc_list, *bcc_list]
        subject = str(payload.get("subject") or "").strip()
        body = str(payload.get("body") or "").strip()

        if not all_recipients or not subject or not body:
            return json.dumps(
                {
                    "success": False,
                    "error_category": "validation",
                    "error": t("mailConfig.recipientSubjectBodyRequired"),
                }
            )

        message = EmailMessage()
        from_email = str(config["from_email"])
        from_name = str(config.get("from_name") or "").strip()
        message["From"] = formataddr((from_name, from_email)) if from_name else from_email
        message["To"] = ", ".join(to_list)
        if cc_list:
            message["Cc"] = ", ".join(cc_list)
        if payload.get("reply_to"):
            message["Reply-To"] = str(payload["reply_to"])
        message["Subject"] = subject
        message["Message-ID"] = make_msgid()

        if payload.get("is_html"):
            message.set_content("This email contains HTML content.")
            message.add_alternative(body, subtype="html")
        else:
            message.set_content(body)

        try:
            MailConfigService._attach_files(message, payload.get("attachments"))
        except (ValueError, TypeError):
            return json.dumps(
                {
                    "success": False,
                    "error_category": "validation",
                    "error": t("mailConfig.attachmentInvalid"),
                }
            )

        context = ssl.create_default_context()
        security = str(config.get("security") or "starttls").lower()
        try:
            if security == "ssl":
                with smtplib.SMTP_SSL(
                    str(config["host"]),
                    int(config["port"]),
                    timeout=15,
                    context=context,
                ) as smtp:
                    smtp.login(str(config["username"]), str(config["password"]))
                    smtp.send_message(message)
            else:
                with smtplib.SMTP(str(config["host"]), int(config["port"]), timeout=15) as smtp:
                    if security == "starttls":
                        smtp.starttls(context=context)
                    smtp.login(str(config["username"]), str(config["password"]))
                    smtp.send_message(message)
        except smtplib.SMTPAuthenticationError as exc:
            detail = exc.smtp_error.decode(errors="ignore") if isinstance(exc.smtp_error, bytes) else str(exc.smtp_error)
            return json.dumps(
                {
                    "success": False,
                    "error_category": "authentication",
                    "error": t("mailConfig.smtpAuthFailedDetail", detail=detail or exc.smtp_code),
                }
            )
        except (TimeoutError, OSError, smtplib.SMTPConnectError) as exc:
            return json.dumps(
                {
                    "success": False,
                    "error_category": "connection",
                    "error": t("mailConfig.smtpConnectionFailed", error=str(exc)),
                }
            )
        except smtplib.SMTPRecipientsRefused:
            return json.dumps(
                {
                    "success": False,
                    "error_category": "recipient",
                    "error": t("mailConfig.recipientsRejected"),
                }
            )
        except smtplib.SMTPException as exc:
            return json.dumps(
                {
                    "success": False,
                    "error_category": "smtp",
                    "error": t("mailConfig.messageRejected", error=str(exc)),
                }
            )
        return json.dumps(
            {
                "success": True,
                "message_id": message["Message-ID"],
                "recipient_count": len(all_recipients),
            }
        )

    @staticmethod
    def _send_email_message(
        config: dict[str, Any],
        to_email: str,
        subject: str,
        body: str,
    ) -> str:
        message = EmailMessage()
        from_email = str(config["from_email"])
        from_name = str(config.get("from_name") or "").strip()
        message["From"] = formataddr((from_name, from_email)) if from_name else from_email
        message["To"] = to_email
        message["Subject"] = subject
        message.set_content(body)

        context = ssl.create_default_context()
        security = str(config.get("security") or "starttls").lower()
        try:
            if security == "ssl":
                with smtplib.SMTP_SSL(
                    str(config["host"]),
                    int(config["port"]),
                    timeout=15,
                    context=context,
                ) as smtp:
                    smtp.login(str(config["username"]), str(config["password"]))
                    smtp.send_message(message)
            else:
                with smtplib.SMTP(str(config["host"]), int(config["port"]), timeout=15) as smtp:
                    if security == "starttls":
                        smtp.starttls(context=context)
                    smtp.login(str(config["username"]), str(config["password"]))
                    smtp.send_message(message)
        except smtplib.SMTPAuthenticationError:
            return json.dumps(
                {
                    "success": False,
                    "error_category": "authentication",
                    "error": t("mailConfig.smtpAuthFailed"),
                }
            )
        except (TimeoutError, OSError, smtplib.SMTPConnectError) as exc:
            return json.dumps(
                {
                    "success": False,
                    "error_category": "connection",
                    "error": t("mailConfig.smtpConnectionFailed", error=str(exc)),
                }
            )
        except smtplib.SMTPRecipientsRefused:
            return json.dumps(
                {
                    "success": False,
                    "error_category": "recipient",
                    "error": t("mailConfig.testRecipientRejected"),
                }
            )
        except smtplib.SMTPException as exc:
            return json.dumps(
                {
                    "success": False,
                    "error_category": "smtp",
                    "error": t("mailConfig.testMessageRejected", error=str(exc)),
                }
            )
        return json.dumps({"success": True})


def get_mail_config_service() -> MailConfigService:
    return MailConfigService.get_instance()
