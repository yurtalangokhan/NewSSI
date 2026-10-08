"""Business logic for SMTP mail configurations and user-specific credentials."""

from __future__ import annotations

import asyncio
import base64
import binascii
from email.message import EmailMessage
from email.utils import formataddr, make_msgid
import json
import smtplib
import ssl
from typing import TYPE_CHECKING, Any, NoReturn

from error_contract import (
    BadRequestError,
    ConfigurationError,
    ConflictError,
    DependencyAuthenticationError,
    DependencyConnectionError,
    DependencyResponseError,
    DependencyTimeoutError,
    DependencyUnavailableError,
    NotFoundError,
    PayloadTooLargeError,
)
from localization import t

from core.security.encryption import SecretScope, decrypt_secret, encrypt_secret
from infrastructure.db.persistence_gateway import (
    mail_config_repository,
    user_mail_credential_repository,
)
from schemas.mail_configs import (
    AvailableMailConfigResponse,
    MailConfigEntity,
    MailConfigResponse,
)

if TYPE_CHECKING:
    # Type only: the repository itself comes from the gateway at
    # runtime, so the class is never reachable here.
    from infrastructure.db.repositories import (
        MailConfigRepository,
        UserMailCredentialRepository,
    )


#: Attachment ceilings. These used to be enforced in tools-service, which
#: no longer receives the payload now that the send happens here.
MAX_ATTACHMENT_BYTES = 10 * 1024 * 1024
MAX_TOTAL_ATTACHMENT_BYTES = 25 * 1024 * 1024


class MailConfigService:
    """Manage SMTP configurations and safe secret handling."""

    _instance: MailConfigService | None = None

    def __init__(
        self,
        repo: MailConfigRepository | None = None,
        user_cred_repo: UserMailCredentialRepository | None = None,
        service: Any | None = None,
    ):
        self._service = service
        self.repo = repo or getattr(service, "repo", None) or mail_config_repository()
        self.user_cred_repo = (
            user_cred_repo or getattr(service, "user_cred_repo", None) or user_mail_credential_repository()
        )

    @classmethod
    def get_instance(cls) -> MailConfigService:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @staticmethod
    def _masked(row: dict[str, Any] | MailConfigEntity) -> dict[str, Any]:
        result = {key: value for key, value in dict(row).items() if key not in {"password", "password_encrypted"}}
        result["password_configured"] = bool(row.get("password_encrypted"))
        return result

    async def list_configs(
        self,
        _user_id: str,
        search: str | None = None,
        page: int | None = None,
        page_size: int | None = None,
    ) -> list[MailConfigResponse] | dict[str, Any]:
        if self._service is not None:
            p = page or 1
            ps = page_size or 10
            items, total = await self._service.list_configs_paginated(_user_id, search=search, page=p, page_size=ps)
            total_pages = max(1, (total + ps - 1) // ps) if total > 0 else 1
            return {
                "items": items,
                "total_items": total,
                "page": p,
                "page_size": ps,
                "total_pages": total_pages,
            }
        if page is None and page_size is None:
            rows = await self.repo.list_active(search=search, page=page, page_size=page_size)
            return [self._masked(row) for row in rows]

        p = page or 1
        ps = page_size or 10
        rows = await self.repo.list_active(search=search, page=p, page_size=ps)
        total = await self.repo.count_active(search=search) if hasattr(self.repo, "count_active") else len(rows)
        return {
            "items": [self._masked(row) for row in rows],
            "total_items": total,
            "page": p,
            "page_size": ps,
            "total_pages": max(1, (total + ps - 1) // ps) if total > 0 else 1,
        }

    async def list_configs_paginated(
        self,
        _user_id: str,
        search: str | None = None,
        page: int = 1,
        page_size: int = 10,
    ) -> tuple[list[MailConfigResponse], int]:
        page = max(1, page)
        page_size = max(1, min(page_size, 100))
        rows = await self.repo.list_active(search=search, page=page, page_size=page_size)
        total = await self.repo.count_active(search=search) if hasattr(self.repo, "count_active") else len(rows)
        return [self._masked(row) for row in rows], total

    async def list_available_configs(self, _user_id: str) -> list[AvailableMailConfigResponse]:
        rows = await self.repo.list_active()
        return [
            AvailableMailConfigResponse(
                id=row["id"],
                name=row["name"],
                host=row["host"],
                port=row["port"],
                security=row["security"],
            )
            for row in rows
        ]

    async def get_config(self, _user_id: str, config_id: str) -> dict[str, Any] | None:
        if self._service is not None:
            cfg = await self._service.get_config(_user_id, config_id)
            if not cfg:
                raise NotFoundError(code="mail.config_not_found", message_key="errors.mail.config_not_found")
            return cfg
        row = await self.repo.get_by_id(config_id)
        if not row:
            raise NotFoundError(code="mail.config_not_found", message_key="errors.mail.config_not_found")
        return self._masked(row)

    async def get_decrypted_config(self, user_id: str, config_id: str) -> dict[str, Any]:
        """Return one mail configuration with its password decrypted.

        Scoped to ``user_id``: listing configurations is deliberately
        platform-wide but always masked, whereas this hands back live SMTP
        credentials, so an id alone must not be enough. For a shared agent the
        caller passes the persona owner, whose configuration it legitimately is.
        """
        row = await self.repo.get_by_id(config_id, user_ids=[user_id] if user_id else None)
        if not row:
            raise NotFoundError(code="mail.config_not_found", message_key="errors.mail.config_not_found")
        config = self._masked(row)
        if row.get("password_encrypted"):
            config["password"] = decrypt_secret(SecretScope.MAIL_CONFIG, row["password_encrypted"])
        else:
            config["password"] = None
        return config

    async def get_decrypted_active_config(self, config_id: str) -> dict[str, Any]:
        row = await self.repo.get_active_by_id(config_id)
        if not row:
            raise NotFoundError(code="mail.config_unavailable", message_key="errors.mail.config_unavailable")
        config = self._masked(row)
        config["password"] = (
            decrypt_secret(SecretScope.MAIL_CONFIG, row["password_encrypted"])
            if row.get("password_encrypted")
            else None
        )
        return config

    async def create_config(self, user_id: str, payload: dict[str, Any]) -> MailConfigResponse:
        values = dict(payload)
        password = values.pop("password", None)
        password_encrypted = encrypt_secret(SecretScope.MAIL_CONFIG, password) if password else None
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
    ) -> MailConfigResponse | None:
        values = {key: value for key, value in payload.items() if value is not None}
        if "password" in values:
            pw = values.pop("password")
            values["password_encrypted"] = encrypt_secret(SecretScope.MAIL_CONFIG, str(pw)) if pw else None
        row = await self.repo.update(config_id, **values)
        if not row:
            raise NotFoundError(code="mail.config_not_found", message_key="errors.mail.config_not_found")
        return self._masked(row)

    async def test_config(
        self,
        user_id: str,
        config_id: str,
        to_email: str,
    ) -> dict[str, Any]:
        if self._service is not None:
            try:
                return await self._service.send_test_email(user_id, config_id, to_email)
            except ValueError as exc:
                raise NotFoundError(code="mail.config_not_found", message_key="errors.mail.config_not_found") from exc
        return await self.send_test_email(user_id, config_id, to_email)

    async def delete_config(self, _user_id: str, config_id: str) -> dict[str, bool]:
        if self._service is not None:
            try:
                deleted = await self._service.delete_config(_user_id, config_id)
            except ValueError as exc:
                raise BadRequestError() from exc
            if not deleted:
                raise NotFoundError(code="mail.config_not_found", message_key="errors.mail.config_not_found")
            return {"success": True}
        if await self.repo.has_active_bindings(config_id):
            raise ConflictError(code="mail.config_in_use", message_key="errors.mail.config_in_use")
        # DELETE is idempotent. A retry after a completed soft delete should
        # still produce a valid success response so clients can refresh state.
        await self.repo.deactivate(config_id)
        return {"success": True}

    # -------------------------------------------------------------------------
    # User-specific mail credentials management
    # -------------------------------------------------------------------------

    async def get_user_credentials(self, user_id: str) -> dict[str, Any] | None:
        row = await self.user_cred_repo.get_by_user_id(user_id)
        if not row:
            return None
        return self._masked(row)

    async def get_decrypted_user_credentials(self, user_id: str) -> dict[str, Any] | None:
        row = await self.user_cred_repo.get_by_user_id(user_id)
        if not row:
            return None
        creds = self._masked(row)
        if row.get("password_encrypted"):
            creds["password"] = decrypt_secret(SecretScope.MAIL_CONFIG, row["password_encrypted"])
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
            raise NotFoundError(code="mail.config_unavailable", message_key="errors.mail.config_unavailable")

        existing = await self.user_cred_repo.get_by_user_id(user_id)
        password_encrypted = ""
        if password:
            password_encrypted = encrypt_secret(SecretScope.MAIL_CONFIG, str(password))
        elif existing:
            password_encrypted = existing.get("password_encrypted") or ""
        else:
            raise BadRequestError(code="mail.password_required", message_key="errors.mail.password_required")

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

        raise ConfigurationError(code="mail.credentials_required", message_key="errors.mail.credentials_required")

    @staticmethod
    def _raise_delivery_error(result: dict[str, Any]) -> NoReturn:
        """Translate SMTP failure categories without exposing relay diagnostics."""
        category = result.get("error_category")
        error_types = {
            "validation": (BadRequestError, "invalid_payload"),
            "smtp_config": (ConfigurationError, "smtp_not_configured"),
            "authentication": (DependencyAuthenticationError, "authentication_failed"),
            "timeout": (DependencyTimeoutError, "timeout"),
            "connection": (DependencyConnectionError, "connection_failed"),
            "recipient": (BadRequestError, "recipients_rejected"),
            "smtp": (DependencyResponseError, "message_rejected"),
        }
        error_type, key = error_types.get(category, (DependencyUnavailableError, "delivery_failed"))
        raise error_type(code=f"mail.{key}", message_key=f"errors.mail.{key}")

    async def test_user_credentials(
        self,
        user_id: str,
        mail_config_id: str,
        to_email: str | None = None,
    ) -> dict[str, Any]:
        user_creds = await self.get_decrypted_user_credentials(user_id)
        if not user_creds or not user_creds.get("username") or not user_creds.get("password"):
            raise ConfigurationError(code="mail.credentials_required", message_key="errors.mail.credentials_required")

        base_config = await self.get_decrypted_active_config(mail_config_id)
        base_config["username"] = user_creds["username"]
        base_config["password"] = user_creds["password"]
        base_config["from_email"] = user_creds.get("from_email") or user_creds["username"]
        base_config["from_name"] = user_creds.get("from_name") or "Agentic AI User"

        target_email = to_email or base_config["from_email"]
        # smtplib is synchronous: connecting, TLS and delivery all block,
        # and a slow or unreachable relay stalled every other request.
        result = await asyncio.to_thread(
            self._send_email_message,
            base_config,
            target_email,
            t("mailConfig.personalVerificationSubject"),
            t("mailConfig.personalVerificationBody"),
        )
        parsed = json.loads(result)
        success = bool(parsed.get("success"))
        if success:
            await self.user_cred_repo.mark_tested(user_id)
        if not success:
            self._raise_delivery_error(parsed)
        message = t("mailConfig.personalVerificationSent")
        return {"success": success, "message": message, "result": result}

    async def send_test_email(self, user_id: str, config_id: str, to_email: str) -> dict[str, Any]:
        config = await self.get_decrypted_config(user_id, config_id)
        # smtplib is synchronous: connecting, TLS and delivery all block,
        # and a slow or unreachable relay stalled every other request.
        result = await asyncio.to_thread(
            self._send_email_message,
            config,
            to_email,
            t("mailConfig.adminTestSubject"),
            t("mailConfig.adminTestBody"),
        )
        parsed = json.loads(result)
        success = bool(parsed.get("success"))
        if success:
            await self.repo.mark_tested(config_id, status="success")
        else:
            await self.repo.mark_tested(
                config_id,
                status="failed",
                error=str(parsed.get("error") or parsed.get("error_category", "smtp")),
            )
            self._raise_delivery_error(parsed)
        message = t("mailConfig.testEmailSent")
        return {"success": success, "message": message, "result": result}

    async def send_email(
        self,
        user_id: str,
        config_id: str,
        payload: dict[str, Any],
        owner_user_id: str | None = None,
    ) -> dict[str, Any]:
        config = await self.get_effective_user_smtp_config(user_id, config_id, owner_user_id)
        result = await asyncio.to_thread(self._send_email_payload, config, payload)
        parsed = json.loads(result)
        success = bool(parsed.get("success"))
        if not success:
            self._raise_delivery_error(parsed)
        message = t("mailConfig.emailSent")
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
        """Attach each payload, refusing anything past the size ceilings.

        Raises PayloadTooLargeError for oversized payloads: a dropped attachment used to
        be invisible, so the user was told the mail had been sent while the
        file they asked for was missing from it.
        """
        total = 0
        for attachment in attachments or []:
            filename = str(attachment.get("filename") or "").strip()
            content_base64 = str(attachment.get("content_base64") or "").strip()
            mime_type = str(attachment.get("mime_type") or "application/octet-stream").split(";")[0]
            maintype, _, subtype = mime_type.partition("/")
            if not maintype or not subtype:
                maintype, subtype = "application", "octet-stream"

            # Check the encoded length first: base64 is ~4/3 of the payload,
            # so an oversized attachment is refused without ever being
            # materialised in memory.
            if len(content_base64) * 3 // 4 > MAX_ATTACHMENT_BYTES:
                raise PayloadTooLargeError(
                    code="mail.attachment_too_large", message_key="errors.mail.attachment_too_large"
                )
            try:
                payload = base64.b64decode(content_base64, validate=True)
            except ValueError as exc:  # binascii.Error is a ValueError
                raise BadRequestError(code="mail.invalid_payload", message_key="errors.mail.invalid_payload") from exc
            total += len(payload)
            if len(payload) > MAX_ATTACHMENT_BYTES:
                raise PayloadTooLargeError(
                    code="mail.attachment_too_large", message_key="errors.mail.attachment_too_large"
                )
            if total > MAX_TOTAL_ATTACHMENT_BYTES:
                raise PayloadTooLargeError(
                    code="mail.attachments_too_large", message_key="errors.mail.attachments_too_large"
                )

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
        attachments = payload.get("attachments") if isinstance(payload.get("attachments"), list) else None

        if not to:
            return json.dumps(
                {"success": False, "error_category": "validation", "error": "At least one recipient is required"}
            )
        if not subject:
            return json.dumps({"success": False, "error_category": "validation", "error": "Subject is required"})
        if not body:
            return json.dumps({"success": False, "error_category": "validation", "error": "Body is required"})

        all_recipients = list(dict.fromkeys(to + cc + bcc))
        try:
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
        except (ValueError, TypeError, binascii.Error) as exc:
            return json.dumps(
                {
                    "success": False,
                    "error_category": "validation",
                    "error": str(exc),
                }
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
        except smtplib.SMTPAuthenticationError:
            return json.dumps(
                {
                    "success": False,
                    "error_category": "authentication",
                    "error": t("mailConfig.smtpAuthFailedDetail"),
                }
            )
        except TimeoutError:
            return json.dumps(
                {
                    "success": False,
                    "error_category": "timeout",
                    "error": t("mailConfig.smtpConnectionFailed"),
                }
            )
        except (smtplib.SMTPConnectError, smtplib.SMTPServerDisconnected):
            return json.dumps(
                {
                    "success": False,
                    "error_category": "connection",
                    "error": t("mailConfig.smtpConnectionFailed"),
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
        except smtplib.SMTPException:
            return json.dumps(
                {
                    "success": False,
                    "error_category": "smtp",
                    "error": t("mailConfig.messageRejected"),
                }
            )
        except OSError:
            return json.dumps(
                {
                    "success": False,
                    "error_category": "connection",
                    "error": t("mailConfig.smtpConnectionFailed"),
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


# -------------------------------------------------------------------------
