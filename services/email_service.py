# services/email_service.py — envoi des mails transactionnels (vérification de compte)
import html
import logging
import smtplib
from email.message import EmailMessage
from email.utils import parseaddr
from typing import Protocol

import httpx

from core.config import settings
from core.gabarits import contenus_emails, rendre, substituer

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
        journal.warning("Aucun backend mail configuré — mail NON envoyé (mode journal) vers %s.\n%s",
                        destinataire, corps_texte)


class EnvoyeurSMTP:
    """Envoi réel via un serveur SMTP (STARTTLS)."""

    def envoyer(self, destinataire: str, sujet: str, corps_texte: str,
                corps_html: str | None = None) -> None:
        message = EmailMessage()
        message["From"] = settings.MAIL_EXPEDITEUR
        message["To"] = destinataire
        message["Subject"] = sujet
        message.set_content(corps_texte)  # version texte (repli)
        if corps_html:
            message.add_alternative(corps_html, subtype="html")

        # timeout : sans lui, un port SMTP filtré fait « hanguer » la tâche de fond
        # indéfiniment (aucune erreur, aucun mail). Le timeout la transforme en erreur nette.
        with smtplib.SMTP(settings.SMTP_HOTE, settings.SMTP_PORT, timeout=15) as serveur:
            if settings.SMTP_TLS:
                serveur.starttls()
            if settings.SMTP_UTILISATEUR:
                serveur.login(settings.SMTP_UTILISATEUR, settings.SMTP_MOT_DE_PASSE)
            serveur.send_message(message)


class EnvoyeurBrevoAPI:
    """Envoi via l'API HTTP de Brevo (HTTPS, port 443).

    À préférer sur les hébergeurs PaaS (Render, Heroku…) qui filtrent les ports SMTP.
    """

    URL = "https://api.brevo.com/v3/smtp/email"

    def envoyer(self, destinataire: str, sujet: str, corps_texte: str,
                corps_html: str | None = None) -> None:
        nom, adresse = parseaddr(settings.MAIL_EXPEDITEUR)
        expediteur: dict[str, str] = {"email": adresse}
        if nom:
            expediteur["name"] = nom

        charge: dict = {
            "sender": expediteur,
            "to": [{"email": destinataire}],
            "subject": sujet,
            "textContent": corps_texte,
        }
        if corps_html:
            charge["htmlContent"] = corps_html

        with httpx.Client(timeout=15) as client:
            reponse = client.post(
                self.URL, json=charge,
                headers={"api-key": settings.BREVO_API_KEY, "accept": "application/json"})
            reponse.raise_for_status()  # lève sur 4xx/5xx (clé invalide, expéditeur non validé…)


def envoyeur_par_defaut() -> Envoyeur:
    """API Brevo si une clé est configurée (recommandé en prod), sinon SMTP, sinon journal."""
    if settings.BREVO_API_KEY:
        return EnvoyeurBrevoAPI()
    if settings.SMTP_HOTE:
        return EnvoyeurSMTP()
    return EnvoyeurJournal()


def construire_lien_verification(jeton: str) -> str:
    return f"{settings.URL_BASE_API}/auth/verifier-email?jeton={jeton}"


def construire_lien_reset(jeton: str) -> str:
    return f"{settings.URL_BASE_API}/auth/reinitialiser-mot-de-passe?jeton={jeton}"


def _corps_html_bouton(pseudo: str, titre: str, intro: str, texte_bouton: str,
                       lien: str, note_expiration: str, pied: str) -> str:
    """Email HTML générique à bouton (gabarit templates/email_bouton.html)."""
    return rendre("email_bouton.html", pseudo=html.escape(pseudo), titre=titre,
                  intro=intro, texte_bouton=texte_bouton, lien=lien,
                  note_expiration=note_expiration, pied=pied)


def _envoyer_mail(envoyeur: Envoyeur, cle: str, destinataire: str,
                  pseudo: str, lien: str, duree: int) -> None:
    """Compose et envoie un mail transactionnel dont la copie vit dans templates/emails.toml.
    Ne propage pas les erreurs (tâche de fond : un backend mail KO ne doit pas remonter)."""
    contenu = contenus_emails()[cle]
    ctx = {"pseudo": pseudo, "lien": lien, "duree": str(duree)}
    # contexte échappé pour tout ce qui finit dans du HTML : un pseudo contenant
    # « <img onerror=…> » ne doit pas s'injecter dans le mail (le texte brut, lui,
    # n'a pas besoin d'échappement).
    ctx_html = {cle_ctx: html.escape(valeur) for cle_ctx, valeur in ctx.items()}
    corps_texte = substituer(contenu["texte"], **ctx)
    corps_html = _corps_html_bouton(
        pseudo, contenu["titre"], substituer(contenu["intro"], **ctx_html),
        contenu["bouton"], lien,
        substituer(contenu["note"], **ctx_html), substituer(contenu["pied"], **ctx_html))
    try:
        envoyeur.envoyer(destinataire, contenu["sujet"], corps_texte, corps_html)
    except Exception:  # noqa: BLE001 — on journalise (niveau ERROR, visible) sans interrompre le flux
        journal.exception("Échec de l'envoi du mail (%s) à %s", cle, destinataire)


def envoyer_mail_verification(
    envoyeur: Envoyeur, destinataire: str, pseudo: str, jeton: str
) -> None:
    """Mail de confirmation d'adresse (copie : section [verification] de emails.toml)."""
    _envoyer_mail(envoyeur, "verification", destinataire, pseudo,
                  construire_lien_verification(jeton), settings.DUREE_JETON_VERIF_HEURES)


def envoyer_mail_reset(
    envoyeur: Envoyeur, destinataire: str, pseudo: str, jeton: str
) -> None:
    """Mail de réinitialisation de mot de passe (copie : section [reset] de emails.toml)."""
    _envoyer_mail(envoyeur, "reset", destinataire, pseudo,
                  construire_lien_reset(jeton), settings.DUREE_JETON_RESET_MINUTES)


def envoyer_mail_compte_existant(
    envoyeur: Envoyeur, destinataire: str, pseudo: str, jeton: str
) -> None:
    """Inscription tentée sur une adresse déjà enregistrée : l'API reste muette
    (anti-énumération), c'est ce mail qui prévient le vrai propriétaire."""
    _envoyer_mail(envoyeur, "compte_existant", destinataire, pseudo,
                  construire_lien_reset(jeton), settings.DUREE_JETON_RESET_MINUTES)


def envoyer_alerte_signalement(
    envoyeur: Envoyeur, id_signalement: int, signaleur: str, motif: str,
    id_avis: int | None, id_vise: int | None, precision: str | None,
) -> None:
    """Prévient l'éditeur qu'un contenu est signalé.

    Texte brut et sans lien : ce mail ne s'adresse pas à un utilisateur mais à
    l'exploitant, qui tranchera depuis la base. La directive 1.2 de l'App Store
    demande une réponse « en temps voulu » — encore faut-il être au courant.
    """
    cible = f"avis #{id_avis}" if id_avis is not None else f"utilisateur #{id_vise}"
    corps = (
        f"Signalement #{id_signalement}\n"
        f"Cible   : {cible}\n"
        f"Motif   : {motif}\n"
        f"Signalé par : {signaleur}\n"
        f"Précision : {precision or '—'}\n"
    )
    try:
        envoyeur.envoyer(settings.MAIL_EXPEDITEUR,
                         f"[SyncWatch] Signalement {motif} — {cible}",
                         corps, f"<pre>{html.escape(corps)}</pre>")
    except Exception:  # noqa: BLE001 — journalisé, jamais propagé
        journal.exception("Échec de l'alerte de signalement #%s", id_signalement)
