from src.modules.air_threats.domain import ThreatConfidence, ThreatKind

THREAT_EMOJI: dict[ThreatKind, str] = {
    ThreatKind.UAV: "🛸",
    ThreatKind.FPV: "🛩",
    ThreatKind.MISSILE: "🚀",
    ThreatKind.BALLISTIC: "☄️",
    ThreatKind.KAB: "💣",
    ThreatKind.AIRCRAFT: "✈️",
    ThreatKind.UNKNOWN: "❔",
}

CONFIDENCE_LABELS: dict[ThreatConfidence, str] = {
    ThreatConfidence.LOW: "слабке",
    ThreatConfidence.MEDIUM: "середнє",
    ThreatConfidence.HIGH: "надійне",
}

INBOUND_NOTE = "курсом сюди"
GONE_NOTE = "зникла з мапи"
