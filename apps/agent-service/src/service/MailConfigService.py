"""Business logic for SMTP mail configurations and user-specific credentials."""

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
from core.db.repositories.user_mail_credential_repo import UserMailCredentialRepository
from core.security.encryption import decrypt_secret, encrypt_secret


class MailConfigService:
    """Manage SMTP configurations and safe secret handling."""

    _instance: MailConfigService | None = None

    def __init__(
        self,
        repo: MailConfigRepository | None = None,
        user_cred_repo: UserMailCredentialRepository | None = None,
    ):
        self.repo = repo or MailConfigRepository()
        self.user_cred_repo = user_cred_repo or UserMailCredentialRepository()

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

    async def list_configs(
        self,
        _user_id: str,
        search: str | None = None,
        page: int | None = None,
        page_size: int | None = None,
    ) -> list[dict[str, Any]]:
        rows = await self.repo.list_active(search=search, page=page, page_size=page_size)
        return [self._masked(row) for row in rows]

    async def list_configs_paginated(
        self,
        _user_id: str,
        search: str | None = None,
        page: int = 1,
        page_size: int = 10,
    ) -> tuple[list[dict[str, Any]], int]:
        page = max(1, page)
        page_size = max(1, min(page_size, 100))
        rows = await self.repo.list_active(search=search, page=page, page_size=page_size)
        total = await self.repo.count_active(search=search)
        return [self._masked(row) for row in rows], total

    async def list_available_configs(self, _user_id: str) -> list[dict[str, Any]]:
        rows = await self.repo.list_active()
        return [
            {
                "id": row["id"],
                "name": row["name"],
                "host": row["host"],
                "port": row["port"],
                "security": row["security"],
            }
            for row in rows
        ]

    async def get_config(self, _user_id: str, config_id: str) -> dict[str, Any] | None:
        row = await self.repo.get_by_id(config_id)
        return self._masked(row) if row else None

    async def get_decrypted_config(self, _user_id: str, config_id: str) -> dict[str, Any]:
        row = await self.repo.get_by_id(config_id)
        if not row:
            raise ValueError(t("mailConfig.notFound"))
        config = self._masked(row)
        if row.get("password_encrypted"):
            config["password"] = decrypt_secret(row["password_encrypted"])
        else:
            config["password"] = None
        return config

    async def get_decrypted_active_config(self, config_id: str) -> dict[str, Any]:
        row = await self.repo.get_active_by_id(config_id)
        if not row:
            raise ValueError(t("mailConfig.selectionUnavailable"))
        config = self._masked(row)
        config["password"] = (
            decrypt_secret(row["password_encrypted"]) if row.get("password_encrypted") else None
        )
        return config

    async def create_config(self, user_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        values = dict(payload)
        password = values.pop("password", None)
        password_encrypted = encrypt_secret(password) if password else None
        row = await self.repo.create(
            user_id=user_id,
            password_encrypted=password_encrypted,
            **values,
        )
        return self._masked(row)

    async def update_config(
        self,
        _user_id: str,
        config_id: str,
        payload: dict[str, Any],
    ) -> dict[str, Any] | None:
        values = {key: value for key, value in payload.items() if value is not None}
        if "password" in values:
            pw = values.pop("password")
            values["password_encrypted"] = encrypt_secret(str(pw)) if pw else None
        row = await self.repo.update(config_id, **values)
        return self._masked(row) if row else None

    async def delete_config(self, _user_id: str, config_id: str) -> bool:
        if await self.repo.has_active_bindings(config_id):
            raise ValueError(t("mailConfig.attachedToAgent"))
        return await self.repo.deactivate(config_id)

    # -------------------------------------------------------------------------
    # User-specific mail credentials management
    # -------------------------------------------------------------------------

    async def get_user_credentials(self, user_id: str) -> dict[str, Any] | None:
        row = await self.user_cred_repo.get_by_user_id(user_id)
        return self._masked(row) if row else None

    async def get_decrypted_user_credentials(self, user_id: str) -> dict[str, Any] | None:
        row = await self.user_cred_repo.get_by_user_id(user_id)
        if not row:
            return None
        creds = self._masked(row)
        if row.get("password_encrypted"):
            creds["password"] = decrypt_secret(row["password_encrypted"])
        else:
            creds["password"] = ""
        return creds

    async def upsert_user_credentials(
        self,
        user_id: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        username = str(payload.get("username") or "").strip()
        mail_config_id = str(payload.get("mail_config_id") or "").strip()
        from_email = str(payload.get("from_email") or "").strip() or username
        from_name = str(payload.get("from_name") or "").strip() or None
        password = payload.get("password")

        if not await self.repo.get_active_by_id(mail_config_id):
            raise ValueError(t("mailConfig.selectionUnavailable"))

        existing = await self.user_cred_repo.get_by_user_id(user_id)
        password_encrypted = ""
        if password:
            password_encrypted = encrypt_secret(str(password))
        elif existing:
            password_encrypted = existing.get("password_encrypted") or ""
        else:
            raise ValueError("Password is required")

        row = await self.user_cred_repo.upsert(
            user_id=user_id,
            mail_config_id=mail_config_id,
            username=username,
            password_encrypted=password_encrypted,
            from_email=from_email,
            from_name=from_name,
        )
        return self._masked(row)

    async def delete_user_credentials(self, user_id: str) -> bool:
        return await self.user_cred_repo.deactivate(user_id)

    async def get_effective_user_smtp_config(
        self,
        user_id: str,
        mail_config_id: str,
        owner_user_id: str | None = None,
    ) -> dict[str, Any]:
        """Combine SMTP server host/port/TLS with the calling user's personal credentials."""
        user_creds = await self.get_decrypted_user_credentials(user_id)
        if user_creds and user_creds.get("username") and user_creds.get("password"):
            base_config = await self.get_decrypted_active_config(user_creds["mail_config_id"])
            base_config["username"] = user_creds["username"]
            base_config["password"] = user_creds["password"]
            base_config["from_email"] = user_creds.get("from_email") or user_creds["username"]
            if user_creds.get("from_name"):
                base_config["from_name"] = user_creds["from_name"]
            return base_config

        lookup_user_id = owner_user_id or user_id
        base_config = await self.get_decrypted_config(lookup_user_id, mail_config_id)
        if base_config.get("username") and base_config.get("password"):
            return base_config

        raise ValueError(
            "Please configure your email credentials in Settings > General to send emails."
        )

    async def test_user_credentials(
        self,
        user_id: str,
        mail_config_id: str,
        to_email: str | None = None,
    ) -> dict[str, Any]:
        user_creds = await self.get_decrypted_user_credentials(user_id)
        if not user_creds or not user_creds.get("username") or not user_creds.get("password"):
            raise ValueError(
                "Please configure your email username and password in Settings > General before testing."
            )

        base_config = await self.get_decrypted_active_config(mail_config_id)
        base_config["username"] = user_creds["username"]
        base_config["password"] = user_creds["password"]
        base_config["from_email"] = user_creds.get("from_email") or user_creds["username"]
        base_config["from_name"] = user_creds.get("from_name") or "Agentic AI User"

        target_email = to_email or base_config["from_email"]
        result = self._send_email_message(
            base_config,
            target_email,
            t("mailConfig.personalVerificationSubject"),
            t("mailConfig.personalVerificationBody"),
        )
        parsed = json.loads(result)
        success = bool(parsed.get("success"))
        if success:
            await self.user_cred_repo.mark_tested(user_id)
        error_detail = parsed.get("error")
        error_category = parsed.get("error_category", "smtp")
        message = (
            t("mailConfig.personalVerificationSent")
            if success
            else t(
                "mailConfig.personalVerificationFailed",
                detail=error_detail or error_category,
            )
        )
        return {"success": success, "message": message, "result": result}

    async def send_test_email(self, user_id: str, config_id: str, to_email: str) -> dict[str, Any]:
        config = await self.get_decrypted_config(user_id, config_id)
        result = self._send_email_message(
            config,
            to_email,
            t("mailConfig.adminTestSubject"),
            t("mailConfig.adminTestBody"),
        )
        parsed = json.loads(result)
        success = bool(parsed.get("success"))
        error_detail = parsed.get("error")
        error_category = parsed.get("error_category", "smtp")
        if success:
            await self.repo.mark_tested(config_id, status="success")
        else:
            await self.repo.mark_tested(
                config_id,
                status="failed",
                error=str(error_detail or error_category),
            )
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
        config = await self.get_effective_user_smtp_config(user_id, config_id)
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
            mime_type = str(attachment.get("mime_type") or "application/octet-stream").split(";")[0]
            maintype, _, subtype = mime_type.partition("/")
            if not maintype or not subtype:
                maintype, subtype = "application", "octet-stream"
            try:
                payload = base64.b64decode(content_base64)
            except Exception:
                continue
            message.add_attachment(
                payload,
                maintype=maintype,
                subtype=subtype,
                filename=filename or "attachment.bin",
            )

    @staticmethod
    def _build_email_message(
        config: dict[str, Any],
        to: list[str] | str,
        subject: str,
        body: str,
        cc: list[str] | None = None,
        bcc: list[str] | None = None,
        is_html: bool = False,
        reply_to: str | None = None,
        attachments: list[dict[str, Any]] | None = None,
    ) -> EmailMessage:
        message = EmailMessage()
        from_name = str(config.get("from_name") or "").strip()
        from_email = str(config.get("from_email") or config.get("username") or "")
        message["From"] = formataddr((from_name, from_email)) if from_name else from_email
        message["To"] = ", ".join(to) if isinstance(to, list) else to
        message["Subject"] = subject
        message["Message-ID"] = make_msgid()
        if cc:
            message["Cc"] = ", ".join(cc)
        if reply_to:
            message["Reply-To"] = reply_to

        if is_html:
            message.set_content("This email contains HTML content.")
            message.add_alternative(body, subtype="html")
        else:
            message.set_content(body)

        MailConfigService._attach_files(message, attachments)
        return message

    @staticmethod
    def _send_email_message(
        config: dict[str, Any],
        to_email: str,
        subject: str,
        body: str,
    ) -> str:
        message = MailConfigService._build_email_message(
            config=config,
            to=to_email,
            subject=subject,
            body=body,
        )
        return MailConfigService._dispatch_smtp(config, [to_email], message)

    @staticmethod
    def _send_email_payload(config: dict[str, Any], payload: dict[str, Any]) -> str:
        to = MailConfigService._as_list(payload.get("to"))
        cc = MailConfigService._as_list(payload.get("cc"))
        bcc = MailConfigService._as_list(payload.get("bcc"))
        subject = str(payload.get("subject") or "").strip()
        body = str(payload.get("body") or "")
        is_html = bool(payload.get("is_html", False))
        reply_to = str(payload.get("reply_to") or "").strip() or None
        attachments = (
            payload.get("attachments") if isinstance(payload.get("attachments"), list) else None
        )

        if not to:
            return json.dumps({"success": False, "error": "At least one recipient is required"})
        if not subject:
            return json.dumps({"success": False, "error": "Subject is required"})
        if not body:
            return json.dumps({"success": False, "error": "Body is required"})

        all_recipients = list(dict.fromkeys(to + cc + bcc))
        message = MailConfigService._build_email_message(
            config=config,
            to=to,
            subject=subject,
            body=body,
            cc=cc,
            bcc=bcc,
            is_html=is_html,
            reply_to=reply_to,
            attachments=attachments,
        )
        return MailConfigService._dispatch_smtp(config, all_recipients, message)

    @staticmethod
    def _dispatch_smtp(
        config: dict[str, Any],
        recipients: list[str],
        message: EmailMessage,
    ) -> str:
        context = ssl.create_default_context()
        security = str(config.get("security") or "starttls").lower()
        host = str(config.get("host") or "").strip()
        port = int(config.get("port") or 587)
        username = str(config.get("username") or "").strip()
        password = str(config.get("password") or "")

        if not host:
            return json.dumps(
                {
                    "success": False,
                    "error_category": "smtp_config",
                    "error": "SMTP host is not configured.",
                }
            )

        try:
            if security == "ssl":
                with smtplib.SMTP_SSL(
                    host,
                    port,
                    timeout=15,
                    context=context,
                ) as smtp:
                    if username and password:
                        smtp.login(username, password)
                    smtp.send_message(message)
            else:
                with smtplib.SMTP(host, port, timeout=15) as smtp:
                    if security == "starttls":
                        smtp.starttls(context=context)
                    if username and password:
                        smtp.login(username, password)
                    smtp.send_message(message)
        except smtplib.SMTPAuthenticationError as exc:
            detail = (
                exc.smtp_error.decode(errors="ignore")
                if isinstance(exc.smtp_error, bytes)
                else str(exc.smtp_error)
            )
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
                "recipient_count": len(recipients),
            }
        )


def get_mail_config_service() -> MailConfigService:
    return MailConfigService.get_instance()
