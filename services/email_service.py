# services/email_service.py — envoi des mails transactionnels (vérification de compte)
import html
import logging
import smtplib
from email.message import EmailMessage
from typing import Protocol

from core.config import settings

journal = logging.getLogger(__name__)


class Envoyeur(Protocol):
    """Canal d'envoi d'email — l'implémentation SMTP se branche ici.

    `corps_html` optionnel : si fourni, l'email est envoyé en multipart
    (texte + HTML), les clients affichant la version HTML.
    """

    def envoyer(self, destinataire: str, sujet: str, corps_texte: str,
                corps_html: str | None = None) -> None: ...


class EnvoyeurJournal:
    """Implémentation par défaut tant que le SMTP n'est pas configuré : log seulement."""

    def envoyer(self, destinataire: str, sujet: str, corps_texte: str,
                corps_html: str | None = None) -> None:
        journal.info("Email vers %s — %s\n%s", destinataire, sujet, corps_texte)


class EnvoyeurSMTP:
    """Envoi réel via un serveur SMTP (STARTTLS)."""

    def envoyer(self, destinataire: str, sujet: str, corps_texte: str,
                corps_html: str | None = None) -> None:
        message = EmailMessage()
        message["From"] = settings.SMTP_EXPEDITEUR
        message["To"] = destinataire
        message["Subject"] = sujet
        message.set_content(corps_texte)  # version texte (repli)
        if corps_html:
            message.add_alternative(corps_html, subtype="html")

        with smtplib.SMTP(settings.SMTP_HOTE, settings.SMTP_PORT) as serveur:
            if settings.SMTP_TLS:
                serveur.starttls()
            if settings.SMTP_UTILISATEUR:
                serveur.login(settings.SMTP_UTILISATEUR, settings.SMTP_MOT_DE_PASSE)
            serveur.send_message(message)


def envoyeur_par_defaut() -> Envoyeur:
    """SMTP si un hôte est configuré, sinon journalisation (dev/tests)."""
    return EnvoyeurSMTP() if settings.SMTP_HOTE else EnvoyeurJournal()


def construire_lien_verification(jeton: str) -> str:
    return f"{settings.URL_BASE_API}/auth/verifier-email?jeton={jeton}"


def _corps_html_verification(pseudo: str, lien: str) -> str:
    """Email HTML (tableaux + styles inline pour la compatibilité clients mail)."""
    pseudo_echappe = html.escape(pseudo)
    return f"""\
<!doctype html>
<html lang="fr">
<body style="margin:0;padding:0;background:#0F172A;">
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0"
         style="background:#0F172A;padding:32px 12px;font-family:Arial,Helvetica,sans-serif;">
    <tr><td align="center">
      <table role="presentation" width="480" cellpadding="0" cellspacing="0"
             style="max-width:480px;width:100%;background:#1E293B;border-radius:16px;padding:32px;">
        <tr><td align="center" style="font-size:26px;font-weight:bold;color:#F1F5F9;padding-bottom:8px;">
          Sync<span style="color:#8B5CF6;">Watch</span>
        </td></tr>
        <tr><td align="center" style="font-size:19px;font-weight:bold;color:#F1F5F9;padding:16px 0 8px;">
          Confirme ton adresse mail
        </td></tr>
        <tr><td align="center" style="font-size:14px;line-height:21px;color:#94A3B8;padding-bottom:26px;">
          Bonjour {pseudo_echappe}, bienvenue sur SyncWatch !<br>
          Active ton compte en cliquant sur le bouton ci-dessous.
        </td></tr>
        <tr><td align="center" style="padding-bottom:26px;">
          <a href="{lien}"
             style="display:inline-block;background:#8B5CF6;color:#ffffff;text-decoration:none;
                    font-size:15px;font-weight:bold;padding:14px 30px;border-radius:12px;">
            Vérifier mon compte
          </a>
        </td></tr>
        <tr><td align="center" style="font-size:12px;line-height:18px;color:#64748B;">
          Ce lien expire dans {settings.DUREE_JETON_VERIF_HEURES} heures.<br>
          Si le bouton ne fonctionne pas, copie ce lien dans ton navigateur :<br>
          <a href="{lien}" style="color:#22D3EE;word-break:break-all;">{lien}</a>
        </td></tr>
      </table>
      <table role="presentation" width="480" cellpadding="0" cellspacing="0" style="max-width:480px;width:100%;">
        <tr><td align="center" style="font-size:11px;color:#475569;padding-top:16px;
                 font-family:Arial,Helvetica,sans-serif;">
          Tu n'es pas à l'origine de cette inscription ? Ignore ce message.
        </td></tr>
      </table>
    </td></tr>
  </table>
</body>
</html>"""


def envoyer_mail_verification(
    envoyeur: Envoyeur, destinataire: str, pseudo: str, jeton: str
) -> None:
    """Compose et envoie le mail de confirmation (bouton HTML + lien texte de repli).
    Ne propage pas les erreurs d'envoi (typiquement lancé en tâche de fond :
    un SMTP indisponible ne doit pas remonter)."""
    lien = construire_lien_verification(jeton)
    sujet = "Confirmez votre adresse mail SyncWatch"
    corps_texte = (
        f"Bonjour {pseudo},\n\n"
        "Bienvenue sur SyncWatch ! Confirmez votre adresse mail en ouvrant ce lien :\n\n"
        f"{lien}\n\n"
        f"Ce lien expire dans {settings.DUREE_JETON_VERIF_HEURES} heures.\n"
        "Si vous n'êtes pas à l'origine de cette inscription, ignorez ce message."
    )
    corps_html = _corps_html_verification(pseudo, lien)
    try:
        envoyeur.envoyer(destinataire, sujet, corps_texte, corps_html)
    except Exception:  # noqa: BLE001 — on journalise et on n'interrompt pas le flux
        journal.exception("Échec de l'envoi du mail de vérification à %s", destinataire)
