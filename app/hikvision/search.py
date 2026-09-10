"""ISAPI archive search and namespace-independent XML parsing."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4
from xml.etree import ElementTree as ET

import requests

from app.config import RecorderConfig
from app.hikvision.models import (
    HikvisionAuthError,
    HikvisionHttpError,
    HikvisionNoRecording,
    HikvisionXmlError,
    SearchSegment,
)


ISAPI_SEARCH_PATH = "/ISAPI/ContentMgmt/search"
PAGE_SIZE = 40


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _children(element: ET.Element, name: str) -> list[ET.Element]:
    return [child for child in list(element) if _local_name(child.tag) == name]


def _first(element: ET.Element, name: str) -> ET.Element | None:
    for child in element.iter():
        if _local_name(child.tag) == name:
            return child
    return None


def _text(element: ET.Element, name: str) -> str | None:
    child = _first(element, name)
    return child.text.strip() if child is not None and child.text else None


def _parse_time(value: str, field: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise HikvisionXmlError(f"invalid {field}") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise HikvisionXmlError(f"{field} must be timezone-aware")
    return parsed.astimezone(timezone.utc)


def build_search_xml(track_id: int, start: datetime, end: datetime, *, position: int = 0, search_id: str | None = None) -> bytes:
    if track_id <= 0 or position < 0:
        raise ValueError("track_id must be > 0 and position must be >= 0")
    if start.tzinfo is None or end.tzinfo is None:
        raise ValueError("search interval must be timezone-aware")
    root = ET.Element("CMSearchDescription", {"version": "2.0", "xmlns": "http://www.hikvision.com/ver20/XMLSchema"})
    ET.SubElement(root, "searchID").text = search_id or uuid4().hex
    ET.SubElement(root, "trackID").text = str(track_id)
    span = ET.SubElement(root, "timeSpan")
    ET.SubElement(span, "startTime").text = start.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    ET.SubElement(span, "endTime").text = end.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    ET.SubElement(root, "maxResults").text = str(PAGE_SIZE)
    ET.SubElement(root, "searchResultPosition").text = str(position)
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def parse_search_response(payload: bytes) -> tuple[list[SearchSegment], int]:
    try:
        root = ET.fromstring(payload)
    except ET.ParseError as exc:
        raise HikvisionXmlError("invalid search response XML") from exc

    matches = [element for element in root.iter() if _local_name(element.tag) == "searchMatchItem"]
    segments: list[SearchSegment] = []
    for match in matches:
        track = _text(match, "trackID")
        start = _text(match, "startTime")
        end = _text(match, "endTime")
        uri = _text(match, "playbackURI")
        codec = _text(match, "codecType")
        if not all((track, start, end, uri, codec)):
            continue
        try:
            track_id = int(track)
            if track_id <= 0:
                continue
            parsed_start = _parse_time(start, "startTime")
            parsed_end = _parse_time(end, "endTime")
        except (ValueError, HikvisionXmlError):
            continue
        if parsed_end <= parsed_start:
            continue
        segments.append(SearchSegment(track_id, parsed_start, parsed_end, uri, codec))

    total_text = _text(root, "numOfMatches")
    try:
        total = int(total_text) if total_text is not None else len(segments)
    except ValueError as exc:
        raise HikvisionXmlError("invalid numOfMatches") from exc
    if total < 0:
        raise HikvisionXmlError("invalid numOfMatches")
    return segments, total


def select_start_segment(segments: list[SearchSegment], requested_start: datetime, requested_end: datetime) -> SearchSegment:
    if requested_start.tzinfo is None or requested_end.tzinfo is None:
        raise ValueError("requested interval must be timezone-aware")
    candidates = [s for s in segments if s.end > requested_start and s.start < requested_end]
    for segment in candidates:
        if segment.start <= requested_start < segment.end:
            return segment
    raise HikvisionNoRecording("no archive segment contains requested start time")


class HikvisionSearchClient:
    """Synchronous ISAPI client intended for execution outside the HTTP handler."""

    def __init__(self, recorder: RecorderConfig, password: str, *, session: requests.Session | None = None, timeout: float = 10.0) -> None:
        self.recorder = recorder
        self._auth = (recorder.username, password)
        self._session = session or requests.Session()
        self._timeout = timeout

    def search(self, track_id: int, start: datetime, end: datetime) -> list[SearchSegment]:
        position = 0
        results: list[SearchSegment] = []
        while True:
            response = self._session.post(
                f"{self.recorder.url}{ISAPI_SEARCH_PATH}",
                data=build_search_xml(track_id, start, end, position=position),
                headers={"Content-Type": "application/xml"},
                auth=self._auth,
                timeout=self._timeout,
            )
            if response.status_code in (401, 403):
                raise HikvisionAuthError(f"ISAPI authentication failed: HTTP {response.status_code}")
            if response.status_code != 200:
                raise HikvisionHttpError(f"ISAPI search failed: HTTP {response.status_code}")
            page, total = parse_search_response(response.content)
            results.extend(page)
            returned = len(page)
            if returned == 0 or returned < PAGE_SIZE or position + returned >= total:
                break
            next_position = position + returned
            if next_position <= position:
                raise HikvisionXmlError("invalid pagination progress")
            position = next_position
        return results
