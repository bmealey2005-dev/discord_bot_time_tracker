"""Per-guild configuration registry.

Each Discord server the bot supports gets one `GuildConfig` entry in
`GUILD_CONFIGS`, keyed by guild id. Servers not present in the registry are
politely rejected at runtime (commands, buttons, presence events, and loops
all guard through `get_guild_config`).
"""

from __future__ import annotations

from dataclasses import dataclass, field

DEFAULT_USER_TIMEZONE = "UTC"

# Role-name semantics shared by every guild; each guild maps these names to
# its own role ids via `GuildConfig.role_id_by_name`.
DEFAULT_COMMAND_ACCESS_BY_NAME: dict[str, frozenset[str]] = {
    "start": frozenset({"owner", "admin", "ui-artists", "ugc-creators"}),
    "stop": frozenset({"owner", "admin", "ui-artists", "ugc-creators"}),
    "status": frozenset({"owner", "admin", "ui-artists", "ugc-creators"}),
    "help": frozenset({"owner", "admin", "ui-artists", "ugc-creators"}),
    "weekly-earnings": frozenset({"owner", "admin", "ui-artists", "ugc-creators"}),
    "add-time": frozenset({"owner", "admin", "ui-artists", "ugc-creators"}),
    "subtract-time": frozenset({"owner", "admin", "ui-artists", "ugc-creators"}),
    "set-time": frozenset({"owner", "admin", "ui-artists", "ugc-creators"}),
    "leaderboard": frozenset({"owner", "admin", "ui-artists", "ugc-creators"}),
    "hourly-data": frozenset({"owner", "admin", "ui-artists", "ugc-creators"}),
    "report": frozenset({"owner"}),
    "payment-data": frozenset({"owner"}),
    "restoreday": frozenset({"owner"}),
    "testweeklyannouncement": frozenset({"owner"}),
    "setreportchannel": frozenset({"owner"}),
    "setclockedinrole": frozenset({"owner"}),
    "setnicknamehours": frozenset({"owner"}),
    "postpanel": frozenset({"owner"}),
}

REQUIRED_CHANNEL_KEYS: frozenset[str] = frozenset({"general", "time-logging", "announcements"})


@dataclass(frozen=True)
class GuildConfig:
    guild_id: int
    role_id_by_name: dict[str, int]
    channel_id_by_name: dict[str, int]
    user_timezone_by_id: dict[int, str]
    payment_brackets_by_user: dict[int, tuple[tuple[int, int], ...]]
    default_payment_brackets: tuple[tuple[int, int], ...]
    clocked_in_role_id: int | None = None
    command_access_by_name: dict[str, frozenset[str]] = field(
        default_factory=lambda: DEFAULT_COMMAND_ACCESS_BY_NAME
    )
    announcement_week_start: int = 0  # 0=Monday .. 6=Sunday
    announcement_grace_seconds: int = 15 * 60
    weekly_announcements_enabled: bool = True


# ---------------------------------------------------------------------------
# Server A (original server)
# ---------------------------------------------------------------------------

_SERVER_A_GUILD_ID = 1468690275676455107

_SERVER_A_USER_ID_BY_USERNAME: dict[str, int] = {
    "alex": 1014149760204156938,
    "yandere": 434418013916233755,
    "wharkk": 629991962522681365,
    "wizoo": 660195981404536832,
    "maus": 656182155311054858,
    "BabooCN": 753035328377454612,
    "calum": 347762453192376324,
    "me": 761895875361505281,
}

_SERVER_A_DEFAULT_PAYMENT_BRACKETS: tuple[tuple[int, int], ...] = (
    (0, 3000),
    (10, 3300),
    (20, 3600),
    (30, 4000),
    (40, 4500),
    (50, 5000),
)

SERVER_A_CONFIG = GuildConfig(
    guild_id=_SERVER_A_GUILD_ID,
    role_id_by_name={
        "owner": 1468691610899321029,
        "admin": 1470609632132202526,
        "ui-artists": 1479224753792221234,
        "ugc-creators": 1487967901494280202,
    },
    channel_id_by_name={
        "general": 1468690277563764812,
        "time-logging": 1475250429926572112,
        "announcements": 1469817014448029807,
    },
    # IANA tz names (Region/City) so week/day boundaries follow DST.
    user_timezone_by_id={
        _SERVER_A_USER_ID_BY_USERNAME["me"]: "America/Chicago",
        _SERVER_A_USER_ID_BY_USERNAME["alex"]: "Europe/London",
        _SERVER_A_USER_ID_BY_USERNAME["wharkk"]: "Europe/Paris",  # France
        _SERVER_A_USER_ID_BY_USERNAME["yandere"]: "Europe/Warsaw",  # Poland
        _SERVER_A_USER_ID_BY_USERNAME["wizoo"]: "Africa/Cairo",  # Egypt
        _SERVER_A_USER_ID_BY_USERNAME["maus"]: "Asia/Manila",  # Philippines
        _SERVER_A_USER_ID_BY_USERNAME["calum"]: "Europe/London",
        _SERVER_A_USER_ID_BY_USERNAME["BabooCN"]: "America/Los_Angeles",
    },
    payment_brackets_by_user={
        _SERVER_A_USER_ID_BY_USERNAME["alex"]: _SERVER_A_DEFAULT_PAYMENT_BRACKETS,
        _SERVER_A_USER_ID_BY_USERNAME["wharkk"]: _SERVER_A_DEFAULT_PAYMENT_BRACKETS,
        _SERVER_A_USER_ID_BY_USERNAME["yandere"]: _SERVER_A_DEFAULT_PAYMENT_BRACKETS,
        _SERVER_A_USER_ID_BY_USERNAME["wizoo"]: (
            (0, 3000),
        ),
        _SERVER_A_USER_ID_BY_USERNAME["maus"]: (
            (0, 3500),
            (10, 3750),
            (20, 4000),
            (30, 4500),
            (40, 5000),
            (50, 6000),
        ),
        _SERVER_A_USER_ID_BY_USERNAME["BabooCN"]: (
            (0, 1500),
        ),
        _SERVER_A_USER_ID_BY_USERNAME["calum"]: (
            (0, 3000),
        ),
        _SERVER_A_USER_ID_BY_USERNAME["me"]: (
            (0, 0),
        ),
    },
    default_payment_brackets=_SERVER_A_DEFAULT_PAYMENT_BRACKETS,
    clocked_in_role_id=1475219245775196434,
)


# ---------------------------------------------------------------------------
# Server B (second team)
# ---------------------------------------------------------------------------

_SERVER_B_GUILD_ID = 1514839205627428864

_SERVER_B_USER_ID_BY_USERNAME: dict[str, int] = {
    "aiden": 646166056594833443,
    "aric": 575499831720542261,
    "bilolbek": 483005370676281364,
    "Abheek": 745063586422063214,
    "me": 761895875361505281,
}

# Server B has no ui-artists / ugc-creators roles, so restrict the shared
# command map to the role names that exist there (owner-only commands stay
# owner-only; employee commands become owner+admin).
_SERVER_B_ROLE_NAMES = frozenset({"owner", "admin"})
_SERVER_B_COMMAND_ACCESS: dict[str, frozenset[str]] = {
    cmd: allowed & _SERVER_B_ROLE_NAMES
    for cmd, allowed in DEFAULT_COMMAND_ACCESS_BY_NAME.items()
}

# Flat $20/hr for everyone on Server B (no marginal tiers).
_SERVER_B_FLAT_PAYMENT_BRACKETS: tuple[tuple[int, int], ...] = (
    (0, 2000),
)

SERVER_B_CONFIG = GuildConfig(
    guild_id=_SERVER_B_GUILD_ID,
    role_id_by_name={
        "owner": 1514870932559233115,
        "admin": 1514870738157310033,
    },
    channel_id_by_name={
        "general": 1514839206088933378,
        "time-logging": 1514872989236203602,
        "announcements": 1514873053069181189,
    },
    user_timezone_by_id={
        _SERVER_B_USER_ID_BY_USERNAME["me"]: "America/Chicago",
        _SERVER_B_USER_ID_BY_USERNAME["aiden"]: "America/Denver",  # New Mexico (Mountain Time)
        _SERVER_B_USER_ID_BY_USERNAME["aric"]: "America/Chicago",
        _SERVER_B_USER_ID_BY_USERNAME["bilolbek"]: "America/Chicago",
        _SERVER_B_USER_ID_BY_USERNAME["Abheek"]: "America/Santiago",  # Chile
    },
    payment_brackets_by_user={
        _SERVER_B_USER_ID_BY_USERNAME["aiden"]: _SERVER_B_FLAT_PAYMENT_BRACKETS,
        _SERVER_B_USER_ID_BY_USERNAME["aric"]: _SERVER_B_FLAT_PAYMENT_BRACKETS,
        _SERVER_B_USER_ID_BY_USERNAME["bilolbek"]: _SERVER_B_FLAT_PAYMENT_BRACKETS,
        _SERVER_B_USER_ID_BY_USERNAME["Abheek"]: _SERVER_B_FLAT_PAYMENT_BRACKETS,
        _SERVER_B_USER_ID_BY_USERNAME["me"]: (
            (0, 0),
        ),
    },
    default_payment_brackets=_SERVER_B_FLAT_PAYMENT_BRACKETS,
    clocked_in_role_id=1514873278458626118,
    command_access_by_name=_SERVER_B_COMMAND_ACCESS,
    weekly_announcements_enabled=False,
)


GUILD_CONFIGS: dict[int, GuildConfig] = {
    SERVER_A_CONFIG.guild_id: SERVER_A_CONFIG,
    SERVER_B_CONFIG.guild_id: SERVER_B_CONFIG,
}


def get_guild_config(guild_id: int) -> GuildConfig | None:
    return GUILD_CONFIGS.get(int(guild_id))


def _validate_configs() -> None:
    for cfg in GUILD_CONFIGS.values():
        prefix = f"GuildConfig({cfg.guild_id})"
        missing_channels = REQUIRED_CHANNEL_KEYS - set(cfg.channel_id_by_name)
        assert not missing_channels, f"{prefix}: missing channel keys {missing_channels}"
        assert cfg.default_payment_brackets, f"{prefix}: default_payment_brackets must be non-empty"
        role_names = set(cfg.role_id_by_name)
        for cmd, allowed in cfg.command_access_by_name.items():
            assert allowed, f"{prefix}: {cmd}: allowed role names must be non-empty"
            unknown = allowed - role_names
            assert not unknown, f"{prefix}: {cmd}: unknown role names {unknown}"


_validate_configs()
