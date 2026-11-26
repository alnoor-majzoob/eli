"""Artifact normalisation (plan §8.7): VTT transcripts, email de-quoting, sections."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass

from eil.modules.integration.models import SourceArtifact


@dataclass(frozen=True)
class SpeakerTurn:
    speaker: str
    text: str


@dataclass(frozen=True)
class DocumentSection:
    title: str
    content: str


def parse_vtt(vtt_text: str) -> list[SpeakerTurn]:
    """Parse WebVTT: skip timing lines; attach ``Speaker:`` prefixes to turns."""
    turns: list[SpeakerTurn] = []
    speaker = "unknown"
    for raw_line in vtt_text.splitlines():
        line = raw_line.strip()
        if not line or "-->" in line:
            continue
        match = re.match(r"^([^:]{1,40}):\s*(.*)$", line)
        if match:
            speaker = match.group(1).strip()
            text = match.group(2).strip()
        else:
            text = line
        if text:
            turns.append(SpeakerTurn(speaker=speaker, text=text))
    return turns


def dequote_email(text: str) -> str:
    """Strip quoted reply lines and reply trailers from email threads."""
    cleaned: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if re.match(r"^[>|]\s*", stripped):
            continue
        if re.match(r"^On\b.*wrote:$", stripped, re.IGNORECASE):
            break
        if stripped.startswith("--"):
            break
        cleaned.append(line)
    return "\n".join(cleaned).strip()


def section_document(text: str) -> list[DocumentSection]:
    """Split a document into (title, content) sections by heading lines."""
    sections: list[DocumentSection] = []
    current = DocumentSection(title="", content="")
    for line in text.splitlines():
        if re.match(r"^#{1,6}\s+\S", line):
            if current.title or current.content.strip():
                sections.append(current)
            current = DocumentSection(title=line.lstrip("#").strip(), content="")
        else:
            current = DocumentSection(title=current.title, content=current.content + "\n" + line)
    if current.title or current.content.strip():
        sections.append(current)
    return [section for section in sections if section.content.strip()]


async def artifact_text(artifact: SourceArtifact) -> str:
    """Best-effort plain-text body of a source artifact (VTT-normalised)."""
    payload = artifact.payload or {}
    body = (
        payload.get("body")
        or payload.get("text")
        or payload.get("subject")
        or payload.get("title")
        or ""
    )
    text = str(body)
    if payload.get("type") == "vtt" or payload.get("vtt"):
        turns = parse_vtt(text)
        return "\n".join(f"[{turn.speaker}] {turn.text}" for turn in turns)
    if artifact.title and not payload.get("body") and not payload.get("text"):
        return artifact.title
    if not text and artifact.title:
        return artifact.title
    if not text and not artifact.title:
        return json.dumps(payload, default=str)[:5000]
    return text
