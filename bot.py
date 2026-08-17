from __future__ import annotations

import asyncio
import re
from datetime import datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands, tasks

import db
from config import (
    BRAND_COLOR,
    BUYER_CITY,
    BUYER_NAME,
    BUYER_STREET,
    DISCORD_TOKEN,
    GUILD_ID,
    PDF_TEMPLATE,
    TIMEZONE,
    validate_config,
)
from pdf_generator import format_eur, generate_prefilled_pdf
from backup_manager import create_backup_bundle, create_csv_export, create_scheduled_backup, latest_backup


def brand_embed(title: str, description: str = "") -> discord.Embed:
    return discord.Embed(title=title, description=description, color=BRAND_COLOR)


def build_ankauf_panel() -> discord.Embed:
    """Erstellt das öffentliche Smexycards-Ankauf-Panel."""
    panel = brand_embed(
        "💰 SMEXYCARDS • KARTENANKAUF",
        "Du möchtest Trading Cards an **Smexycards** verkaufen?\n"
        "Erstelle mit einem Klick dein **privates Ankauf-Ticket**. Nur du und unser Ankauf-Team können den Inhalt sehen.",
    )
    panel.add_field(
        name="🃏 Einzelkarte verkaufen",
        value=(
            "Ideal für einzelne Karten. Gib Spieler/Karte, Set, Zustand bzw. Grading "
            "und deine Preisvorstellung an. Fotos kannst du direkt danach im Ticket hochladen."
        ),
        inline=False,
    )
    panel.add_field(
        name="📦 Mehrere Karten / Sammlung",
        value=(
            "Du musst **nicht jede Karte einzeln auflisten**. Eine grobe Anzahl, Kategorie und "
            "Preisvorstellung reichen. Anschließend kannst du Übersichtsfotos oder eine Excel-/PDF-Liste hochladen."
        ),
        inline=False,
    )
    panel.add_field(
        name="🤝 Wenn wir uns einigen",
        value=(
            "Das Ankauf-Team bestätigt den Deal im Ticket. Danach werden deine Verkäuferdaten erfasst "
            "und dein **Ankaufsformular automatisch vorbereitet**. Versanddaten erhältst du erst nach Freigabe."
        ),
        inline=False,
    )
    panel.add_field(
        name="✅ Ankauf möglich",
        value="Einzelkarten • Graded Cards • Sammlungen / Lots • Sealed-Produkte",
        inline=False,
    )
    panel.set_footer(text="Smexycards • Sicherer Kartenankauf • Bitte erst nach bestätigtem Deal versenden")
    if bot.user is not None:
        panel.set_thumbnail(url=bot.user.display_avatar.url)
    return panel


def parse_euro_to_cents(raw: str) -> int:
    text = raw.strip().replace("€", "").replace(" ", "")
    if not text:
        raise ValueError("Kein Preis angegeben")

    if "," in text and "." in text:
        # German format: 1.234,56
        text = text.replace(".", "").replace(",", ".")
    elif "," in text:
        text = text.replace(",", ".")

    try:
        value = Decimal(text)
    except InvalidOperation as exc:
        raise ValueError("Ungültiger Preis") from exc

    if value <= 0:
        raise ValueError("Preis muss größer als 0 sein")
    return int((value * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def ticket_kind_label(kind: str) -> str:
    return "🃏 Einzelkarte" if kind == "single" else "📦 Mehrere Karten / Sammlung"


def clean_field(value: object, max_len: int = 1024) -> str:
    text = str(value or "-").strip() or "-"
    return text[:max_len]


STATUS_LABELS = {
    "open": "🟢 Offen",
    "offer_pending": "🟡 Angebot offen",
    "deal": "🤝 Deal",
    "seller_data": "📄 Formular",
    "shipping": "📦 Versand",
    "closed": "🔒 Geschlossen",
    "declined": "❌ Abgelehnt",
}


def status_label(status: str) -> str:
    return STATUS_LABELS.get(status, f"• {status}")


def build_dashboard_embed(guild: discord.Guild) -> discord.Embed:
    stats = db.get_dashboard_stats(guild.id)
    tickets = db.list_recent_tickets(guild.id, limit=12, active_only=True)

    embed = brand_embed(
        "📊 SMEXYCARDS • ANKAUF-DASHBOARD",
        "Interne Übersicht für das Ankauf-Team. Verkäuferdaten und Exporte bitte vertraulich behandeln.",
    )
    embed.add_field(name="🎫 Aktiv", value=str(stats["active"]), inline=True)
    embed.add_field(name="💶 Angebote offen", value=str(stats["offer_pending"]), inline=True)
    embed.add_field(name="🤝 Deals / Formular", value=str(stats["deal"] + stats["seller_data"]), inline=True)
    embed.add_field(name="📦 Versand", value=str(stats["shipping"]), inline=True)
    embed.add_field(name="🔒 Abgeschlossen", value=str(stats["closed"]), inline=True)
    embed.add_field(name="❌ Abgelehnt", value=str(stats["declined"]), inline=True)
    embed.add_field(
        name="💰 Vereinbarte Ankaufssumme",
        value=format_eur(stats["agreed_price_cents"]),
        inline=False,
    )

    if tickets:
        lines: list[str] = []
        for ticket in tickets:
            channel_text = f"<#{ticket['channel_id']}>" if ticket.get("channel_id") else "ohne Kanal"
            price = (
                f" • **{format_eur(int(ticket['agreed_price_cents']))}**"
                if ticket.get("agreed_price_cents") is not None
                else ""
            )
            owner = clean_field(ticket.get("owner_name"), 40)
            lines.append(
                f"{status_label(str(ticket['status']))} • **#{ticket['id']:04d}** • {channel_text} • {owner}{price}"
            )
        embed.add_field(name="📋 Zuletzt aktive Tickets", value="\n".join(lines)[:1024], inline=False)
    else:
        embed.add_field(name="📋 Zuletzt aktive Tickets", value="Aktuell keine offenen Ankauf-Tickets.", inline=False)

    backup = latest_backup()
    if backup is not None:
        try:
            modified = datetime.fromtimestamp(backup.stat().st_mtime, tz=TIMEZONE).strftime("%d.%m.%Y %H:%M")
            backup_text = f"Letztes automatisches Backup: **{modified} Uhr**"
        except OSError:
            backup_text = "Automatisches Backup vorhanden."
    else:
        backup_text = "Noch kein automatisches Backup vorhanden."
    embed.set_footer(text=f"Smexycards • Insgesamt {stats['total']} Tickets • {backup_text}")
    return embed


async def is_staff(interaction: discord.Interaction) -> bool:
    if not interaction.guild or not isinstance(interaction.user, discord.Member):
        return False
    if interaction.user.guild_permissions.administrator or interaction.user.guild_permissions.manage_guild:
        return True
    settings = db.get_guild_settings(interaction.guild.id)
    if not settings:
        return False
    return any(role.id == settings["staff_role_id"] for role in interaction.user.roles)


async def require_staff(interaction: discord.Interaction) -> bool:
    if await is_staff(interaction):
        return True
    if not interaction.response.is_done():
        await interaction.response.send_message(
            "❌ Diese Aktion ist nur für das Ankauf-Team freigeschaltet.", ephemeral=True
        )
    else:
        await interaction.followup.send(
            "❌ Diese Aktion ist nur für das Ankauf-Team freigeschaltet.", ephemeral=True
        )
    return False


async def get_ticket_from_interaction(interaction: discord.Interaction) -> Optional[dict]:
    if not interaction.channel_id:
        return None
    return db.get_ticket_by_channel(interaction.channel_id)


async def send_log(guild: discord.Guild, title: str, description: str) -> None:
    settings = db.get_guild_settings(guild.id)
    if not settings or not settings.get("log_channel_id"):
        return
    channel = guild.get_channel(settings["log_channel_id"])
    if isinstance(channel, discord.TextChannel):
        try:
            await channel.send(embed=brand_embed(title, description))
        except discord.HTTPException:
            pass


async def get_or_create_archive_category(
    guild: discord.Guild, settings: dict
) -> discord.CategoryChannel:
    """Return an archive category with free room, creating the next archive if needed."""
    current = None
    archive_id = settings.get("archive_category_id")
    if archive_id:
        candidate = guild.get_channel(archive_id)
        if isinstance(candidate, discord.CategoryChannel):
            current = candidate
            if len(candidate.channels) < 50:
                return candidate

    # Reuse any existing numbered Smexycards archive that still has room.
    archives = [
        category
        for category in guild.categories
        if category.name.startswith("📁 ANKAUF ARCHIV")
    ]
    for category in sorted(archives, key=lambda item: item.position, reverse=True):
        if len(category.channels) < 50:
            if category.id != archive_id:
                db.save_guild_settings(
                    guild_id=guild.id,
                    staff_role_id=settings["staff_role_id"],
                    ticket_category_id=settings["ticket_category_id"],
                    archive_category_id=category.id,
                    log_channel_id=settings.get("log_channel_id"),
                    panel_channel_id=settings.get("panel_channel_id"),
                    panel_message_id=settings.get("panel_message_id"),
                )
            return category

    staff_role = guild.get_role(settings["staff_role_id"])
    me = guild.me
    if staff_role is None or me is None:
        raise RuntimeError("Ankauf-Team-Rolle oder Bot-Mitglied nicht gefunden.")

    # The original archive keeps its name; subsequent archives are numbered 2, 3, ...
    used_numbers = {1}
    pattern = re.compile(r"^📁 ANKAUF ARCHIV(?: (\d+))?$")
    for category in archives:
        match = pattern.match(category.name)
        if match:
            used_numbers.add(int(match.group(1) or "1"))
    next_number = 2
    while next_number in used_numbers:
        next_number += 1

    overwrites = {
        guild.default_role: discord.PermissionOverwrite(view_channel=False),
        staff_role: discord.PermissionOverwrite(view_channel=True, read_message_history=True),
        me: discord.PermissionOverwrite(
            view_channel=True,
            manage_channels=True,
            send_messages=True,
            read_message_history=True,
        ),
    }
    archive = await guild.create_category(
        f"📁 ANKAUF ARCHIV {next_number}",
        overwrites=overwrites,
        reason="Smexycards Ankauf-Archiv automatisch erweitert",
    )
    db.save_guild_settings(
        guild_id=guild.id,
        staff_role_id=settings["staff_role_id"],
        ticket_category_id=settings["ticket_category_id"],
        archive_category_id=archive.id,
        log_channel_id=settings.get("log_channel_id"),
        panel_channel_id=settings.get("panel_channel_id"),
        panel_message_id=settings.get("panel_message_id"),
    )
    return archive


async def create_ticket_channel(
    interaction: discord.Interaction, kind: str, details: dict[str, str]
) -> None:
    if not interaction.guild or not isinstance(interaction.user, discord.Member):
        await interaction.response.send_message("❌ Tickets funktionieren nur auf dem Server.", ephemeral=True)
        return

    settings = db.get_guild_settings(interaction.guild.id)
    if not settings:
        await interaction.response.send_message(
            "❌ Das Ankauf-System ist noch nicht eingerichtet. Ein Admin muss zuerst `/ankauf_setup` ausführen.",
            ephemeral=True,
        )
        return

    category = interaction.guild.get_channel(settings["ticket_category_id"])
    staff_role = interaction.guild.get_role(settings["staff_role_id"])
    me = interaction.guild.me
    if not isinstance(category, discord.CategoryChannel) or staff_role is None or me is None:
        await interaction.response.send_message(
            "❌ Die gespeicherte Ticket-Konfiguration ist nicht mehr gültig. Bitte `/ankauf_setup` erneut ausführen.",
            ephemeral=True,
        )
        return

    await interaction.response.defer(ephemeral=True, thinking=True)

    ticket_id = db.create_ticket_placeholder(
        guild_id=interaction.guild.id,
        owner_id=interaction.user.id,
        owner_name=str(interaction.user),
        kind=kind,
        details=details,
    )

    overwrites = {
        interaction.guild.default_role: discord.PermissionOverwrite(view_channel=False),
        interaction.user: discord.PermissionOverwrite(
            view_channel=True,
            send_messages=True,
            read_message_history=True,
            attach_files=True,
            embed_links=True,
        ),
        staff_role: discord.PermissionOverwrite(
            view_channel=True,
            send_messages=True,
            read_message_history=True,
            attach_files=True,
            embed_links=True,
            manage_messages=True,
        ),
        me: discord.PermissionOverwrite(
            view_channel=True,
            send_messages=True,
            read_message_history=True,
            attach_files=True,
            embed_links=True,
            manage_channels=True,
            manage_messages=True,
        ),
    }

    channel_name = f"ankauf-{ticket_id:04d}"
    try:
        channel = await interaction.guild.create_text_channel(
            name=channel_name,
            category=category,
            overwrites=overwrites,
            topic=f"Smexycards Ankauf #{ticket_id:04d} | Verkäufer {interaction.user.id} | {kind}",
            reason=f"Ankauf-Ticket #{ticket_id:04d} erstellt von {interaction.user}",
        )
    except Exception:
        db.delete_ticket(ticket_id)
        raise

    db.bind_ticket_channel(ticket_id, channel.id)

    embed = brand_embed(
        f"💰 Ankauf-Ticket #{ticket_id:04d}",
        f"Hallo {interaction.user.mention}! Danke für dein Angebot.\n\n"
        "**Bitte lade jetzt Fotos der Karten hoch.** Bei mehreren Karten/Sammlungen reichen Übersichtsfotos. "
        "Du kannst auch eine vorhandene **Excel-, PDF- oder Kartenliste** direkt in dieses Ticket schicken.\n\n"
        "Ein Mitarbeiter schaut sich dein Angebot an und macht dir bei Interesse ein Angebot.",
    )
    embed.add_field(name="Ankauf", value=ticket_kind_label(kind), inline=False)

    if kind == "single":
        embed.add_field(name="Spieler / Karte", value=clean_field(details.get("card")), inline=True)
        embed.add_field(name="Set / Jahr", value=clean_field(details.get("set_year")), inline=True)
        embed.add_field(name="Parallel / Nummerierung", value=clean_field(details.get("parallel")), inline=True)
        embed.add_field(name="Zustand / Grading", value=clean_field(details.get("condition")), inline=True)
        embed.add_field(name="Preisvorstellung", value=clean_field(details.get("asking_price")), inline=True)
    else:
        embed.add_field(name="Ungefähre Anzahl", value=clean_field(details.get("count")), inline=True)
        embed.add_field(name="Bereich / Kartenarten", value=clean_field(details.get("category")), inline=True)
        embed.add_field(name="Raw / Graded", value=clean_field(details.get("grading_mix")), inline=True)
        embed.add_field(name="Preisvorstellung", value=clean_field(details.get("asking_price")), inline=True)
        embed.add_field(name="Kurzbeschreibung", value=clean_field(details.get("description")), inline=False)

    await channel.send(
        content=f"{interaction.user.mention} {staff_role.mention}",
        embed=embed,
        view=TicketControlView(),
        allowed_mentions=discord.AllowedMentions(users=True, roles=True),
    )
    await interaction.followup.send(f"✅ Dein Ticket wurde erstellt: {channel.mention}", ephemeral=True)
    await send_log(
        interaction.guild,
        "🎫 Neues Ankauf-Ticket",
        f"Ticket **#{ticket_id:04d}** von {interaction.user.mention} – {ticket_kind_label(kind)}\n{channel.mention}",
    )


async def post_deal_step(channel: discord.TextChannel, ticket: dict) -> None:
    owner = channel.guild.get_member(ticket["owner_id"])
    mention = owner.mention if owner else f"<@{ticket['owner_id']}>"
    amount = format_eur(int(ticket["agreed_price_cents"]))

    embed = brand_embed(
        f"🎉 Deal für Ticket #{int(ticket['id']):04d}",
        f"**Vereinbarter Ankaufspreis: {amount}**\n"
        f"**Auszahlung:** {clean_field(ticket.get('payment_method'))}\n\n"
        "Bitte klicke auf **„Verkäuferdaten für PDF“**. Der Bot trägt deine Daten dann automatisch in das Smexycards-Ankaufsformular ein.\n\n"
        "Das Blankoformular hängt ebenfalls an dieser Nachricht, falls du es lieber manuell ausfüllen möchtest.",
    )
    if ticket.get("deal_description"):
        embed.add_field(name="Vereinbarung / Inhalt", value=clean_field(ticket["deal_description"]), inline=False)

    await channel.send(
        content=mention,
        embed=embed,
        view=DealSellerView(),
        file=discord.File(PDF_TEMPLATE, filename="Smexycards_Privates_Ankaufsformular.pdf"),
    )


class SingleCardModal(discord.ui.Modal, title="🃏 Einzelkarte verkaufen"):
    card = discord.ui.TextInput(
        label="Spieler / Karte",
        placeholder="z. B. Lionel Messi Topps Chrome Auto",
        max_length=100,
    )
    set_year = discord.ui.TextInput(
        label="Set / Jahr",
        placeholder="z. B. Topps Chrome UCC 2025/26",
        max_length=100,
    )
    parallel = discord.ui.TextInput(
        label="Parallel / Nummerierung",
        placeholder="z. B. Gold /50 – falls vorhanden",
        required=False,
        max_length=100,
    )
    condition = discord.ui.TextInput(
        label="Zustand / Grading",
        placeholder="z. B. Raw NM / PSA 10",
        max_length=100,
    )
    asking_price = discord.ui.TextInput(
        label="Deine Preisvorstellung",
        placeholder="z. B. 250 €",
        max_length=40,
    )

    async def on_submit(self, interaction: discord.Interaction) -> None:
        await create_ticket_channel(
            interaction,
            "single",
            {
                "card": self.card.value,
                "set_year": self.set_year.value,
                "parallel": self.parallel.value,
                "condition": self.condition.value,
                "asking_price": self.asking_price.value,
            },
        )


class CollectionModal(discord.ui.Modal, title="📦 Mehrere Karten / Sammlung"):
    count = discord.ui.TextInput(
        label="Ungefähre Anzahl Karten",
        placeholder="z. B. ca. 35 Karten / 2 Boxen / großes Lot",
        max_length=80,
    )
    category = discord.ui.TextInput(
        label="Bereich / Kartenarten",
        placeholder="z. B. Fußball, Basketball, gemischt",
        max_length=100,
    )
    grading_mix = discord.ui.TextInput(
        label="Raw / Graded / Gemischt",
        placeholder="z. B. überwiegend Raw, 4x PSA",
        max_length=100,
    )
    asking_price = discord.ui.TextInput(
        label="Preisvorstellung gesamt",
        placeholder="z. B. 800 €",
        required=False,
        max_length=40,
    )
    description = discord.ui.TextInput(
        label="Kurze Beschreibung",
        placeholder="Nur grob beschreiben – nicht jede Karte einzeln.",
        style=discord.TextStyle.paragraph,
        required=False,
        max_length=500,
    )

    async def on_submit(self, interaction: discord.Interaction) -> None:
        await create_ticket_channel(
            interaction,
            "collection",
            {
                "count": self.count.value,
                "category": self.category.value,
                "grading_mix": self.grading_mix.value,
                "asking_price": self.asking_price.value,
                "description": self.description.value,
            },
        )


class AnkaufPanelView(discord.ui.View):
    def __init__(self) -> None:
        super().__init__(timeout=None)

    @discord.ui.button(
        label="Einzelkarte verkaufen",
        emoji="🃏",
        style=discord.ButtonStyle.primary,
        custom_id="smexycards:panel:single",
    )
    async def single(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await interaction.response.send_modal(SingleCardModal())

    @discord.ui.button(
        label="Mehrere Karten / Sammlung",
        emoji="📦",
        style=discord.ButtonStyle.success,
        custom_id="smexycards:panel:collection",
    )
    async def collection(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await interaction.response.send_modal(CollectionModal())

    @discord.ui.button(
        label="So läuft der Ankauf",
        emoji="ℹ️",
        style=discord.ButtonStyle.secondary,
        custom_id="smexycards:panel:info",
    )
    async def info(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        info = brand_embed(
            "ℹ️ So läuft dein Ankauf ab",
            "**1. Ticket öffnen**\n"
            "Wähle Einzelkarte oder Sammlung und trage die wichtigsten Eckdaten ein.\n\n"
            "**2. Fotos / Liste hochladen**\n"
            "Lade im privaten Ticket Bilder hoch. Bei Sammlungen reichen zunächst Übersichtsfotos oder eine vorhandene Liste.\n\n"
            "**3. Angebot & Einigung**\n"
            "Unser Ankauf-Team prüft dein Angebot und kann dir direkt im Ticket einen Preis anbieten.\n\n"
            "**4. Ankaufformular**\n"
            "Bei einer Einigung werden deine Daten erfasst und das Ankaufformular für den Deal vorbereitet.\n\n"
            "**5. Versand**\n"
            "Bitte versende deine Karten **erst nach Versandfreigabe** im Ticket."
        )
        info.set_footer(text="Diese Information ist nur für dich sichtbar.")
        await interaction.response.send_message(embed=info, ephemeral=True)


class OfferModal(discord.ui.Modal, title="💶 Angebot machen"):
    price = discord.ui.TextInput(label="Angebotspreis", placeholder="z. B. 650 €", max_length=40)
    payment = discord.ui.TextInput(
        label="Auszahlung",
        placeholder="Barzahlung / PayPal / Überweisung",
        max_length=50,
    )
    note = discord.ui.TextInput(
        label="Nachricht / Begründung",
        placeholder="Optional: kurze Nachricht zum Angebot",
        required=False,
        style=discord.TextStyle.paragraph,
        max_length=500,
    )

    async def on_submit(self, interaction: discord.Interaction) -> None:
        if not await require_staff(interaction):
            return
        ticket = await get_ticket_from_interaction(interaction)
        if not ticket:
            await interaction.response.send_message("❌ Dieses Channel ist kein Ankauf-Ticket.", ephemeral=True)
            return
        try:
            cents = parse_euro_to_cents(self.price.value)
        except ValueError:
            await interaction.response.send_message("❌ Bitte einen gültigen Preis eingeben, z. B. `650` oder `650,00`.", ephemeral=True)
            return

        db.create_offer(ticket["id"], cents, self.note.value, self.payment.value.strip(), interaction.user.id)
        embed = brand_embed(
            f"💶 Angebot: {format_eur(cents)}",
            f"<@{ticket['owner_id']}> – Smexycards bietet dir für dieses Ticket **{format_eur(cents)}**.\n\n"
            f"**Auszahlung:** {clean_field(self.payment.value)}\n\n"
            "Du kannst das Angebot direkt unten annehmen oder ablehnen.",
        )
        if self.note.value.strip():
            embed.add_field(name="Nachricht", value=clean_field(self.note.value), inline=False)
        await interaction.response.send_message("✅ Angebot wurde gesendet.", ephemeral=True)
        assert isinstance(interaction.channel, discord.TextChannel)
        await interaction.channel.send(
            content=f"<@{ticket['owner_id']}>", embed=embed, view=OfferResponseView()
        )
        await send_log(
            interaction.guild,
            "💶 Angebot gesendet",
            f"Ticket **#{ticket['id']:04d}** – {format_eur(cents)} – von {interaction.user.mention}",
        )


class DealModal(discord.ui.Modal, title="✅ Deal abschließen"):
    price = discord.ui.TextInput(label="Vereinbarter Ankaufspreis", placeholder="z. B. 850 €", max_length=40)
    payment = discord.ui.TextInput(
        label="Auszahlung",
        placeholder="Barzahlung / PayPal / Überweisung",
        max_length=50,
    )
    description = discord.ui.TextInput(
        label="Was wird angekauft?",
        placeholder="z. B. Sammlung Fußballkarten, ca. 35 Karten",
        style=discord.TextStyle.paragraph,
        max_length=500,
    )

    async def on_submit(self, interaction: discord.Interaction) -> None:
        if not await require_staff(interaction):
            return
        ticket = await get_ticket_from_interaction(interaction)
        if not ticket:
            await interaction.response.send_message("❌ Dieses Channel ist kein Ankauf-Ticket.", ephemeral=True)
            return
        try:
            cents = parse_euro_to_cents(self.price.value)
        except ValueError:
            await interaction.response.send_message("❌ Bitte einen gültigen Preis eingeben.", ephemeral=True)
            return
        db.set_deal(ticket["id"], cents, self.payment.value.strip(), self.description.value.strip())
        ticket = db.get_ticket(ticket["id"])
        await interaction.response.send_message("✅ Deal gespeichert und Formular-Schritt gestartet.", ephemeral=True)
        assert ticket and isinstance(interaction.channel, discord.TextChannel)
        await post_deal_step(interaction.channel, ticket)
        await send_log(
            interaction.guild,
            "✅ Deal abgeschlossen",
            f"Ticket **#{ticket['id']:04d}** – **{format_eur(cents)}** – {interaction.channel.mention}",
        )


class SellerDataModal(discord.ui.Modal, title="📄 Verkäuferdaten für Ankaufsformular"):
    seller_name = discord.ui.TextInput(label="Vor- und Nachname", max_length=100)
    seller_street = discord.ui.TextInput(label="Straße / Hausnummer", max_length=120)
    seller_city = discord.ui.TextInput(label="PLZ / Ort", placeholder="z. B. 09117 Chemnitz", max_length=100)
    seller_contact = discord.ui.TextInput(
        label="Telefon / E-Mail (optional)", required=False, max_length=120
    )

    async def on_submit(self, interaction: discord.Interaction) -> None:
        ticket = await get_ticket_from_interaction(interaction)
        if not ticket:
            await interaction.response.send_message("❌ Dieses Channel ist kein Ankauf-Ticket.", ephemeral=True)
            return
        if interaction.user.id != ticket["owner_id"]:
            await interaction.response.send_message(
                "❌ Nur der Verkäufer dieses Tickets kann die Verkäuferdaten eintragen.", ephemeral=True
            )
            return
        if ticket.get("agreed_price_cents") is None:
            await interaction.response.send_message("❌ Es wurde noch kein Deal gespeichert.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True, thinking=True)
        db.set_seller_data(
            ticket["id"],
            self.seller_name.value.strip(),
            self.seller_street.value.strip(),
            self.seller_city.value.strip(),
            self.seller_contact.value.strip(),
        )
        ticket = db.get_ticket(ticket["id"])
        assert ticket is not None
        date_text = datetime.now(TIMEZONE).strftime("%d.%m.%Y")
        pdf_path = await asyncio.to_thread(generate_prefilled_pdf, ticket, date_text)

        assert isinstance(interaction.channel, discord.TextChannel)
        embed = brand_embed(
            "📄 Dein vorausgefülltes Ankaufsformular",
            "Bitte prüfe die Daten im PDF. Danach **unterschreiben** und die unterschriebene Datei bzw. ein Foto/Scan wieder hier im Ticket hochladen.\n\n"
            "Die Käuferdaten von Smexycards, der vereinbarte Preis, das Belegdatum und die Ticketnummer sind bereits eingetragen.",
        )
        await interaction.channel.send(
            content=f"<@{ticket['owner_id']}>",
            embed=embed,
            file=discord.File(pdf_path, filename=pdf_path.name),
        )
        await interaction.followup.send("✅ Formular erstellt und im Ticket hochgeladen.", ephemeral=True)
        await send_log(
            interaction.guild,
            "📄 Ankaufsformular erstellt",
            f"Ticket **#{ticket['id']:04d}** – Verkäuferdaten wurden eingetragen.",
        )


class TicketControlView(discord.ui.View):
    def __init__(self) -> None:
        super().__init__(timeout=None)

    @discord.ui.button(
        label="Angebot machen",
        emoji="💶",
        style=discord.ButtonStyle.primary,
        custom_id="smexycards:ticket:offer",
        row=0,
    )
    async def offer(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if not await require_staff(interaction):
            return
        await interaction.response.send_modal(OfferModal())

    @discord.ui.button(
        label="Deal abschließen",
        emoji="✅",
        style=discord.ButtonStyle.success,
        custom_id="smexycards:ticket:deal",
        row=0,
    )
    async def deal(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if not await require_staff(interaction):
            return
        await interaction.response.send_modal(DealModal())

    @discord.ui.button(
        label="Ablehnen",
        emoji="❌",
        style=discord.ButtonStyle.danger,
        custom_id="smexycards:ticket:decline",
        row=0,
    )
    async def decline(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if not await require_staff(interaction):
            return
        ticket = await get_ticket_from_interaction(interaction)
        if not ticket:
            await interaction.response.send_message("❌ Kein Ankauf-Ticket.", ephemeral=True)
            return
        db.set_ticket_status(ticket["id"], "declined")
        await interaction.response.send_message("✅ Ankauf wurde als abgelehnt markiert.", ephemeral=True)
        assert isinstance(interaction.channel, discord.TextChannel)
        await interaction.channel.send(
            f"❌ <@{ticket['owner_id']}> – vielen Dank für dein Angebot. Für dieses Ticket kommt aktuell leider kein Ankauf zustande."
        )
        await send_log(interaction.guild, "❌ Ankauf abgelehnt", f"Ticket **#{ticket['id']:04d}**")

    @discord.ui.button(
        label="Versand freigeben",
        emoji="📦",
        style=discord.ButtonStyle.secondary,
        custom_id="smexycards:ticket:shipping",
        row=1,
    )
    async def shipping(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if not await require_staff(interaction):
            return
        ticket = await get_ticket_from_interaction(interaction)
        if not ticket:
            await interaction.response.send_message("❌ Kein Ankauf-Ticket.", ephemeral=True)
            return
        if ticket.get("agreed_price_cents") is None:
            await interaction.response.send_message("❌ Erst einen Deal abschließen.", ephemeral=True)
            return
        db.set_ticket_status(ticket["id"], "shipping")
        await interaction.response.send_message("✅ Versandinformationen wurden freigegeben.", ephemeral=True)
        assert isinstance(interaction.channel, discord.TextChannel)
        embed = brand_embed(
            "📦 Versand freigegeben",
            f"<@{ticket['owner_id']}> bitte sende die vereinbarten Karten gut geschützt an:\n\n"
            f"**{BUYER_NAME}**\n{BUYER_STREET}\n{BUYER_CITY}\n\n"
            f"Bitte lege nach Möglichkeit einen Hinweis auf **Ticket #{ticket['id']:04d}** bei und teile die Sendungsnummer hier im Ticket mit, falls vorhanden.",
        )
        await interaction.channel.send(content=f"<@{ticket['owner_id']}>", embed=embed)
        await send_log(interaction.guild, "📦 Versand freigegeben", f"Ticket **#{ticket['id']:04d}**")

    @discord.ui.button(
        label="Ticket schließen",
        emoji="🔒",
        style=discord.ButtonStyle.secondary,
        custom_id="smexycards:ticket:close",
        row=1,
    )
    async def close(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if not await require_staff(interaction):
            return
        ticket = await get_ticket_from_interaction(interaction)
        if not ticket or not isinstance(interaction.channel, discord.TextChannel) or not interaction.guild:
            await interaction.response.send_message("❌ Kein Ankauf-Ticket.", ephemeral=True)
            return
        settings = db.get_guild_settings(interaction.guild.id)
        if not settings:
            await interaction.response.send_message(
                "❌ Die Ankauf-Konfiguration fehlt. Bitte `/ankauf_setup` erneut ausführen.",
                ephemeral=True,
            )
            return

        await interaction.response.send_message("🔒 Ticket wird geschlossen.", ephemeral=True)

        try:
            archive = await get_or_create_archive_category(interaction.guild, settings)

            owner = interaction.guild.get_member(ticket["owner_id"])
            if owner:
                await interaction.channel.set_permissions(
                    owner,
                    view_channel=True,
                    send_messages=False,
                    read_message_history=True,
                    attach_files=False,
                    reason=f"Ankauf-Ticket #{ticket['id']:04d} geschlossen",
                )

            await interaction.channel.edit(
                name=f"geschlossen-{ticket['id']:04d}",
                category=archive,
                reason=f"Ankauf-Ticket #{ticket['id']:04d} geschlossen",
            )
        except discord.Forbidden:
            await interaction.followup.send(
                "❌ Ich konnte das Ticket nicht archivieren. Bitte prüfe beim Bot **Kanäle verwalten**.",
                ephemeral=True,
            )
            return
        except discord.HTTPException as exc:
            await interaction.followup.send(
                f"❌ Discord hat das Archivieren abgelehnt (`{exc.code}`). Bitte schick mir die Railway-Logs, falls das erneut passiert.",
                ephemeral=True,
            )
            return
        except RuntimeError as exc:
            await interaction.followup.send(f"❌ {exc}", ephemeral=True)
            return

        db.set_ticket_status(ticket["id"], "closed")
        await interaction.channel.send(
            f"🔒 **Ticket geschlossen.** Der Verlauf bleibt zur Dokumentation sichtbar.\n📁 Archiv: **{archive.name}**"
        )
        await send_log(
            interaction.guild,
            "🔒 Ticket geschlossen",
            f"Ticket **#{ticket['id']:04d}** → **{archive.name}**",
        )


class OfferResponseView(discord.ui.View):
    def __init__(self) -> None:
        super().__init__(timeout=None)

    @discord.ui.button(
        label="Angebot annehmen",
        emoji="✅",
        style=discord.ButtonStyle.success,
        custom_id="smexycards:offer:accept",
    )
    async def accept(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        ticket = await get_ticket_from_interaction(interaction)
        if not ticket:
            await interaction.response.send_message("❌ Kein Ankauf-Ticket.", ephemeral=True)
            return
        if interaction.user.id != ticket["owner_id"]:
            await interaction.response.send_message("❌ Nur der Verkäufer kann das Angebot annehmen.", ephemeral=True)
            return
        offer = db.get_latest_pending_offer(ticket["id"])
        if not offer:
            await interaction.response.send_message("❌ Dieses Angebot ist nicht mehr aktiv.", ephemeral=True)
            return

        db.set_offer_status(offer["id"], "accepted")
        description = (offer.get("note") or "Angebot im Discord-Ticket angenommen").strip()
        db.set_deal(ticket["id"], int(offer["amount_cents"]), offer["payment_method"], description)
        ticket = db.get_ticket(ticket["id"])
        await interaction.response.send_message(
            f"✅ Du hast das Angebot über **{format_eur(int(offer['amount_cents']))}** angenommen.", ephemeral=True
        )
        assert ticket and isinstance(interaction.channel, discord.TextChannel)
        await interaction.channel.send(
            f"🎉 **Angebot angenommen!** <@{ticket['owner_id']}> und Smexycards haben sich auf **{format_eur(int(offer['amount_cents']))}** geeinigt."
        )
        await post_deal_step(interaction.channel, ticket)
        await send_log(
            interaction.guild,
            "✅ Angebot angenommen",
            f"Ticket **#{ticket['id']:04d}** – **{format_eur(int(offer['amount_cents']))}**",
        )

    @discord.ui.button(
        label="Angebot ablehnen",
        emoji="✖️",
        style=discord.ButtonStyle.danger,
        custom_id="smexycards:offer:reject",
    )
    async def reject(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        ticket = await get_ticket_from_interaction(interaction)
        if not ticket:
            await interaction.response.send_message("❌ Kein Ankauf-Ticket.", ephemeral=True)
            return
        if interaction.user.id != ticket["owner_id"]:
            await interaction.response.send_message("❌ Nur der Verkäufer kann das Angebot ablehnen.", ephemeral=True)
            return
        offer = db.get_latest_pending_offer(ticket["id"])
        if not offer:
            await interaction.response.send_message("❌ Dieses Angebot ist nicht mehr aktiv.", ephemeral=True)
            return
        db.set_offer_status(offer["id"], "rejected")
        db.set_ticket_status(ticket["id"], "open")
        await interaction.response.send_message("✖️ Angebot abgelehnt.", ephemeral=True)
        assert isinstance(interaction.channel, discord.TextChannel)
        await interaction.channel.send(f"✖️ <@{ticket['owner_id']}> hat das aktuelle Angebot abgelehnt.")


class DealSellerView(discord.ui.View):
    def __init__(self) -> None:
        super().__init__(timeout=None)

    @discord.ui.button(
        label="Verkäuferdaten für PDF",
        emoji="📄",
        style=discord.ButtonStyle.success,
        custom_id="smexycards:deal:sellerdata",
    )
    async def seller_data(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        ticket = await get_ticket_from_interaction(interaction)
        if not ticket:
            await interaction.response.send_message("❌ Kein Ankauf-Ticket.", ephemeral=True)
            return
        if interaction.user.id != ticket["owner_id"]:
            await interaction.response.send_message(
                "❌ Nur der Verkäufer dieses Tickets kann das Formular ausfüllen.", ephemeral=True
            )
            return
        await interaction.response.send_modal(SellerDataModal())


class DashboardView(discord.ui.View):
    def __init__(self) -> None:
        super().__init__(timeout=300)

    @discord.ui.button(label="Aktualisieren", emoji="🔄", style=discord.ButtonStyle.primary)
    async def refresh(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if not await require_staff(interaction):
            return
        if not interaction.guild:
            await interaction.response.send_message("❌ Nur auf einem Server verfügbar.", ephemeral=True)
            return
        await interaction.response.edit_message(embed=build_dashboard_embed(interaction.guild), view=self)

    @discord.ui.button(label="CSV Export", emoji="📊", style=discord.ButtonStyle.secondary)
    async def export(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if not await require_staff(interaction):
            return
        if not interaction.guild:
            await interaction.response.send_message("❌ Nur auf einem Server verfügbar.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True, thinking=True)
        path = await asyncio.to_thread(create_csv_export, interaction.guild.id)
        try:
            await interaction.followup.send(
                "📊 **CSV-Export erstellt.** Die ZIP enthält Tickets, Angebote und Server-Einstellungen. "
                "Sie kann Verkäufer-/Kontaktdaten enthalten – bitte vertraulich speichern.",
                file=discord.File(path, filename=path.name),
                ephemeral=True,
            )
        finally:
            try:
                path.unlink()
            except OSError:
                pass

    @discord.ui.button(label="Backup ZIP", emoji="💾", style=discord.ButtonStyle.success)
    async def backup(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if not await require_staff(interaction):
            return
        if not interaction.guild:
            await interaction.response.send_message("❌ Nur auf einem Server verfügbar.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True, thinking=True)
        path = await asyncio.to_thread(create_backup_bundle, interaction.guild.id)
        try:
            await interaction.followup.send(
                "💾 **Datenbank-Backup erstellt.** Lade die ZIP herunter und bewahre sie sicher auf. "
                "Sie enthält die Ankauf-Datenbank einschließlich Verkäuferdaten.",
                file=discord.File(path, filename=path.name),
                ephemeral=True,
            )
        finally:
            try:
                path.unlink()
            except OSError:
                pass


@tasks.loop(hours=24)
async def automatic_database_backup() -> None:
    try:
        path = await asyncio.to_thread(create_scheduled_backup, 14)
        print(f"💾 Automatisches Datenbank-Backup erstellt: {path.name}")
    except Exception as exc:
        print(f"⚠️ Automatisches Datenbank-Backup fehlgeschlagen: {exc}")


@automatic_database_backup.before_loop
async def before_automatic_database_backup() -> None:
    await bot.wait_until_ready()


class SmexycardsBot(commands.Bot):
    def __init__(self) -> None:
        intents = discord.Intents.default()
        super().__init__(command_prefix="!", intents=intents)

    async def setup_hook(self) -> None:
        db.init_db()
        self.add_view(AnkaufPanelView())
        self.add_view(TicketControlView())
        self.add_view(OfferResponseView())
        self.add_view(DealSellerView())

        if GUILD_ID:
            guild = discord.Object(id=GUILD_ID)
            self.tree.copy_global_to(guild=guild)
            await self.tree.sync(guild=guild)
        else:
            await self.tree.sync()


bot = SmexycardsBot()


@bot.event
async def on_ready() -> None:
    print(f"✅ Eingeloggt als {bot.user} (ID: {bot.user.id if bot.user else 'n/a'})")
    print("💰 Smexycards Ankauf-Bot ist bereit.")
    if not automatic_database_backup.is_running():
        automatic_database_backup.start()


@bot.tree.command(name="ankauf_setup", description="Richtet das Smexycards-Ankauf-Ticketsystem ein.")
@app_commands.describe(
    staff_rolle="Rolle, die Ankauf-Tickets bearbeiten darf",
    ticket_kategorie="Optional: vorhandene Kategorie für offene Tickets",
    log_kanal="Optional: Kanal für interne Ankauf-Logs",
)
@app_commands.default_permissions(manage_guild=True)
async def ankauf_setup(
    interaction: discord.Interaction,
    staff_rolle: discord.Role,
    ticket_kategorie: Optional[discord.CategoryChannel] = None,
    log_kanal: Optional[discord.TextChannel] = None,
) -> None:
    if not interaction.guild or not isinstance(interaction.user, discord.Member):
        await interaction.response.send_message("❌ Nur auf einem Server verfügbar.", ephemeral=True)
        return
    # Discord selbst steuert die Standardberechtigung dieses Slash-Commands
    # über @app_commands.default_permissions(manage_guild=True).
    # Keine zusätzliche lokale Permission-Prüfung, da diese bei einzelnen
    # Discord/Cache-Konstellationen fälschlich False liefern kann.
    if staff_rolle.is_default() or staff_rolle.managed:
        await interaction.response.send_message(
            "❌ Bitte wähle eine normale eigene Team-Rolle (z. B. `Ankauf-Team`) und nicht `@everyone` oder eine verwaltete Bot-/Integrationsrolle.",
            ephemeral=True,
        )
        return
    if not isinstance(interaction.channel, discord.TextChannel):
        await interaction.response.send_message("❌ Bitte in einem Textkanal ausführen.", ephemeral=True)
        return

    await interaction.response.defer(ephemeral=True, thinking=True)

    existing = db.get_guild_settings(interaction.guild.id)

    try:
        if ticket_kategorie is None and existing:
            old_ticket_category = interaction.guild.get_channel(existing["ticket_category_id"])
            if isinstance(old_ticket_category, discord.CategoryChannel):
                ticket_kategorie = old_ticket_category

        if ticket_kategorie is None:
            ticket_kategorie = await interaction.guild.create_category(
                "💰 SMEXYCARDS ANKAUF",
                reason="Smexycards Ankauf-System eingerichtet",
            )

        archive_category = None
        if existing and existing.get("archive_category_id"):
            old_archive = interaction.guild.get_channel(existing["archive_category_id"])
            if isinstance(old_archive, discord.CategoryChannel):
                archive_category = old_archive

        if archive_category is None:
            archive_overwrites = {
                interaction.guild.default_role: discord.PermissionOverwrite(view_channel=False),
                staff_rolle: discord.PermissionOverwrite(view_channel=True, read_message_history=True),
            }
            if interaction.guild.me:
                archive_overwrites[interaction.guild.me] = discord.PermissionOverwrite(
                    view_channel=True, manage_channels=True, send_messages=True, read_message_history=True
                )
            archive_category = await interaction.guild.create_category(
                "📁 ANKAUF ARCHIV",
                overwrites=archive_overwrites,
                reason="Smexycards Ankauf-Archiv erstellt",
            )
        else:
            if existing and existing.get("staff_role_id") != staff_rolle.id:
                old_staff_role = interaction.guild.get_role(existing["staff_role_id"])
                if old_staff_role is not None:
                    await archive_category.set_permissions(
                        old_staff_role, overwrite=None, reason="Alte Ankauf-Team-Rolle entfernt"
                    )
            await archive_category.set_permissions(
                staff_rolle, view_channel=True, read_message_history=True,
                reason="Smexycards Ankauf-Team aktualisiert"
            )
    except discord.Forbidden:
        await interaction.followup.send(
            "❌ Mir fehlen Berechtigungen zum Erstellen/Verwalten von Kanälen. Gib dem Bot **Kanäle verwalten** und versuche es erneut.",
            ephemeral=True,
        )
        return

    db.save_guild_settings(
        guild_id=interaction.guild.id,
        staff_role_id=staff_rolle.id,
        ticket_category_id=ticket_kategorie.id,
        archive_category_id=archive_category.id,
        log_channel_id=log_kanal.id if log_kanal else None,
    )

    panel = build_ankauf_panel()
    message = await interaction.channel.send(embed=panel, view=AnkaufPanelView())
    db.update_panel_message(interaction.guild.id, interaction.channel.id, message.id)

    await interaction.followup.send(
        f"✅ Ankauf-System eingerichtet.\n"
        f"**Team:** {staff_rolle.mention}\n"
        f"**Tickets:** {ticket_kategorie.name}\n"
        f"**Archiv:** {archive_category.name}\n"
        f"**Panel:** {message.jump_url}",
        ephemeral=True,
    )


@bot.tree.command(name="ankauf_panel", description="Postet das Ankauf-Panel erneut in diesem Kanal.")
async def ankauf_panel(interaction: discord.Interaction) -> None:
    if not interaction.guild or not isinstance(interaction.channel, discord.TextChannel):
        await interaction.response.send_message("❌ Nur in einem Server-Textkanal verfügbar.", ephemeral=True)
        return
    if not await require_staff(interaction):
        return
    settings = db.get_guild_settings(interaction.guild.id)
    if not settings:
        await interaction.response.send_message("❌ Bitte zuerst `/ankauf_setup` ausführen.", ephemeral=True)
        return

    panel = build_ankauf_panel()
    await interaction.response.send_message("✅ Panel wird gepostet.", ephemeral=True)
    message = await interaction.channel.send(embed=panel, view=AnkaufPanelView())
    db.update_panel_message(interaction.guild.id, interaction.channel.id, message.id)


@bot.tree.command(name="ankauf_panel_update", description="Aktualisiert das bestehende Ankauf-Panel auf das aktuelle Design.")
async def ankauf_panel_update(interaction: discord.Interaction) -> None:
    if not interaction.guild:
        await interaction.response.send_message("❌ Nur auf einem Server verfügbar.", ephemeral=True)
        return
    if not await require_staff(interaction):
        return

    settings = db.get_guild_settings(interaction.guild.id)
    if not settings:
        await interaction.response.send_message("❌ Bitte zuerst `/ankauf_setup` ausführen.", ephemeral=True)
        return

    panel_channel_id = settings.get("panel_channel_id")
    panel_message_id = settings.get("panel_message_id")
    if not panel_channel_id or not panel_message_id:
        await interaction.response.send_message(
            "❌ Es ist noch kein bestehendes Panel gespeichert. Nutze `/ankauf_panel` in deinem gewünschten Ankauf-Kanal.",
            ephemeral=True,
        )
        return

    channel = interaction.guild.get_channel(int(panel_channel_id))
    if not isinstance(channel, discord.TextChannel):
        await interaction.response.send_message(
            "❌ Der gespeicherte Panel-Kanal wurde nicht gefunden. Nutze `/ankauf_panel`, um ein neues Panel zu posten.",
            ephemeral=True,
        )
        return

    try:
        message = await channel.fetch_message(int(panel_message_id))
        await message.edit(embed=build_ankauf_panel(), view=AnkaufPanelView())
    except (discord.NotFound, discord.Forbidden):
        await interaction.response.send_message(
            "❌ Das alte Panel konnte nicht bearbeitet werden. Nutze `/ankauf_panel`, um ein neues Panel zu posten.",
            ephemeral=True,
        )
        return
    except discord.HTTPException as exc:
        await interaction.response.send_message(
            f"❌ Discord konnte das Panel gerade nicht aktualisieren: `{exc}`",
            ephemeral=True,
        )
        return

    await interaction.response.send_message(
        f"✅ Das Ankauf-Panel wurde aktualisiert: {message.jump_url}",
        ephemeral=True,
    )


@bot.tree.command(name="ankauf_dashboard", description="Zeigt das interne Ankauf-Dashboard für das Team.")
async def ankauf_dashboard(interaction: discord.Interaction) -> None:
    if not interaction.guild:
        await interaction.response.send_message("❌ Nur auf einem Server verfügbar.", ephemeral=True)
        return
    if not await require_staff(interaction):
        return
    await interaction.response.send_message(
        embed=build_dashboard_embed(interaction.guild),
        view=DashboardView(),
        ephemeral=True,
    )


@bot.tree.command(name="ankauf_export", description="Exportiert Ankauf-Tickets und Angebote als CSV-ZIP.")
async def ankauf_export(interaction: discord.Interaction) -> None:
    if not interaction.guild:
        await interaction.response.send_message("❌ Nur auf einem Server verfügbar.", ephemeral=True)
        return
    if not await require_staff(interaction):
        return
    await interaction.response.defer(ephemeral=True, thinking=True)
    path = await asyncio.to_thread(create_csv_export, interaction.guild.id)
    try:
        await interaction.followup.send(
            "📊 Export fertig. Die ZIP kann Verkäufer-/Kontaktdaten enthalten – bitte vertraulich behandeln.",
            file=discord.File(path, filename=path.name),
            ephemeral=True,
        )
    finally:
        try:
            path.unlink()
        except OSError:
            pass


@bot.tree.command(name="ankauf_backup", description="Erstellt ein privates Backup der Ankauf-Datenbank.")
async def ankauf_backup(interaction: discord.Interaction) -> None:
    if not interaction.guild:
        await interaction.response.send_message("❌ Nur auf einem Server verfügbar.", ephemeral=True)
        return
    if not await require_staff(interaction):
        return
    await interaction.response.defer(ephemeral=True, thinking=True)
    path = await asyncio.to_thread(create_backup_bundle, interaction.guild.id)
    try:
        await interaction.followup.send(
            "💾 Backup fertig. Die ZIP enthält die Ankauf-Datenbank einschließlich Verkäuferdaten – bitte sicher speichern.",
            file=discord.File(path, filename=path.name),
            ephemeral=True,
        )
    finally:
        try:
            path.unlink()
        except OSError:
            pass


@bot.tree.command(name="ankauf_status", description="Zeigt den aktuellen Status dieses Ankauf-Tickets.")
async def ankauf_status(interaction: discord.Interaction) -> None:
    ticket = await get_ticket_from_interaction(interaction)
    if not ticket:
        await interaction.response.send_message("❌ Dieses Channel ist kein Ankauf-Ticket.", ephemeral=True)
        return
    if interaction.user.id != ticket["owner_id"] and not await is_staff(interaction):
        await interaction.response.send_message("❌ Kein Zugriff.", ephemeral=True)
        return
    text = (
        f"**Ticket:** #{ticket['id']:04d}\n"
        f"**Typ:** {ticket_kind_label(ticket['kind'])}\n"
        f"**Status:** `{ticket['status']}`"
    )
    if ticket.get("agreed_price_cents") is not None:
        text += f"\n**Deal:** {format_eur(int(ticket['agreed_price_cents']))}"
    await interaction.response.send_message(embed=brand_embed("📋 Ankauf-Status", text), ephemeral=True)


if __name__ == "__main__":
    validate_config()
    bot.run(DISCORD_TOKEN)
