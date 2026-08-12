"""Canonical registry for the isolated August 2026 Grile V2 pilot."""
from __future__ import annotations

from dataclasses import dataclass


PILOT_V2_MONTH = "2026-08"


@dataclass(frozen=True)
class PilotV2Sheet:
    site_code: str
    sheet_id: str
    agent_one_code: str
    agent_one_name: str
    agent_two_code: str
    agent_two_name: str


PILOT_V2_SHEETS = (
    PilotV2Sheet(
        "PROMEN",
        "1jcVCLHaujv0O2qlTPXG7b1IqGGVq8572p7pJFvEAgdg",  # pragma: allowlist secret
        "PANAR",
        "Pana Remus Cristian",
        "BARBUC",
        "Barbu Cosmin",
    ),
    PilotV2Sheet(
        "MCRFBAL",
        "1MusUrpTjkFyW2JefvJVdFOdx5ypUbKr1Hs-2SViihEo",  # pragma: allowlist secret
        "LUCAG",
        "Luca Georgiana",
        "ILIEI",
        "Ilie Isabela",
    ),
    PilotV2Sheet(
        "CRFFEER",
        "1bEWiDcg9tqWPeqQdw6hna_lsIIc16ozKMCutkVIAHu0",  # pragma: allowlist secret
        "PICIORUSE",
        "Piciorus Emanuel",
        "GOJNEAG",
        "Gojnea Mirel",
    ),
    PilotV2Sheet(
        "ORAUCHAN",
        "1ZxugdHXXhvPSFyxyOh9bipq11J2N872n7isAxRXMxuM",  # pragma: allowlist secret
        "REZMIVESR",
        "Rezmives Diana",
        "TAUC",
        "Tau Cristina",
    ),
    PilotV2Sheet(
        "ORAUCH",
        "12ejRCcDRNdQqiz38S7BjTKNb-pSrJWW2UNclhFJUiCI",  # pragma: allowlist secret
        "DOGARUP",
        "Dogaru Paula",
        "BODEL",
        "Bode Liana",
    ),
    PilotV2Sheet(
        "BRCRF",
        "1FbxE-eJtO4SXfunuXS4fT_Kv5Hqf0v9634pcHNX9TYk",  # pragma: allowlist secret
        "GHEORGHITAD",
        "Gheorghita Daniela",
        "GUGEANUA",
        "Gugeanu Andreea",
    ),
    PilotV2Sheet(
        "PLAFI",
        "1mZPm0S4Cq4m_AypOJjNSqQGLkbuUin9YwRWOqkgQVwc",  # pragma: allowlist secret
        "CIOBANUGA",
        "Ciobanu Gabriela",
        "IORDACHEA",
        "Iordache Alexandra",
    ),
    PilotV2Sheet(
        "PLCRF",
        "1gdA-DtgZ4FgT1gn_v6_BFouJMjv63lSeUh6gw1nIL7Y",  # pragma: allowlist secret
        "CIOCARLANC",
        "Ciocirlan Cristina",
        "STOICAD",
        "Stoica Daniela",
    ),
    PilotV2Sheet(
        "TGVMLL",
        "1VMHsyCyQdYv0CeFxx6ZmASnEdZ4K5Ftrr4PBf-v0OBw",  # pragma: allowlist secret
        "CIOBANUB",
        "Ciobanu Bianca",
        "TUREAC",
        "Turea Adriana",
    ),
    PilotV2Sheet(
        "BRPROM",
        "1e2lEnrddOwQ-pQqNyhDiyXTwXRFdq-zcH9jKAm1M8oA",  # pragma: allowlist secret
        "PATRASCUV",
        "Patrascu Violeta",
        "POPAM",
        "Popa Mihaela",
    ),
    PilotV2Sheet(
        "FOCCRARF",
        "1Xm8NxGM9r8GaJGKNCIqBGHaIJ4Sdx09KgEDKhl9ySUM",  # pragma: allowlist secret
        "BRODICA",
        "Burlacu Rodica",
        "POPARLANE",
        "Poparlan Elena",
    ),
    PilotV2Sheet(
        "GLCRFA",
        "1tjNiOuao0BdeyJx44xHCqzGimAXJdozY0Nuut_50xpY",  # pragma: allowlist secret
        "FLUTURM",
        "Flutur Mariana",
        "IOVUL",
        "Iovu Liliana",
    ),
    PilotV2Sheet(
        "PLAFIPL",
        "1JrCGF_0CYtDhktCy6tZHpsVv6DJWF-QcbkuhuQ9ccDc",  # pragma: allowlist secret
        "GRIGOREB",
        "Grigore Bianca",
        "PIRJOLG",
        "Pirjol Georgiana",
    ),
    PilotV2Sheet(
        "PLSHOP",
        "1_4EqzuOtV2W5HmqzOufSN-69aQtIBmXaiSTYPOys0N8",  # pragma: allowlist secret
        "BARBUD",
        "Barbu David",
        "OPREAE",
        "Oprea Sorina",
    ),
    PilotV2Sheet(
        "DBMALL",
        "1sH85XX-3tEl3mAD8umwJOEatNyZUXHs5_06sUpy_A0Y",  # pragma: allowlist secret
        "BRATUA",
        "Bratu Ana",
        "RIZEAD",
        "Rizea Denisa",
    ),
    PilotV2Sheet(
        "CTVIVO",
        "1JR5HHtfwruGUcsjHBP1y_YpkXm_Zt8Q-1urN68XG2rI",  # pragma: allowlist secret
        "CHIRILAC",
        "Chirila Crina",
        "CHEVEREANUA",
        "Chevereanu Andreea",
    ),
    PilotV2Sheet(
        "CTAUCH",
        "1UEKuP9su7xJl15Rk_pvh2c0F_fuOQJ4agv8TzPkS_dw",  # pragma: allowlist secret
        "POENARUA",
        "Poenaru Ana",
        "MUNGIUG",
        "Mungiu George",
    ),
    PilotV2Sheet(
        "CCTCIT",
        "17tCxcm5kvnL-H0TiiYYLULiV5HwlXNFVNj3YVufMzt8",  # pragma: allowlist secret
        "MANUC",
        "Manu Claudia",
        "HUDESCUE",
        "Hudescu Elena",
    ),
    PilotV2Sheet(
        "CTCRFTOM",
        "13K0N70Os29zrIRPr3yAK97DXYuqpXBt99WJwSuLuctY",  # pragma: allowlist secret
        "SALIM",
        "Salim Melisa",
        "SCRIPCARUA",
        "Scripcaru Amalia",
    ),
    PilotV2Sheet(
        "CTCORA",
        "1SIU8OkHMdp0-a7SyKbsczxqWk54YVjSFoOfYeqFn4Ek",  # pragma: allowlist secret
        "BANICAC",
        "Banica Victoria",
        "CHELESE",
        "Cheles Violeta",
    ),
    PilotV2Sheet(
        "CTCITYPRK",
        "1Sq6iJMRDgqLclh5MNB4JcKjOLb5OvqgJNXguF9Mfp8I",  # pragma: allowlist secret
        "MANEANI",
        "Manea Nicoleta",
        "GISCAN",
        "Gisca Nela",
    ),
)


PILOT_V2_BY_SITE = {sheet.site_code: sheet for sheet in PILOT_V2_SHEETS}
