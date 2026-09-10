"""Unit tests for Hikvision ISAPI search."""

from datetime import datetime, timezone

import pytest

from app.hikvision.models import HikvisionNoRecording, HikvisionXmlError
from app.hikvision.search import PAGE_SIZE, build_search_xml, parse_search_response, select_start_segment


UTC = timezone.utc


def test_build_search_xml_uses_required_minimal_schema() -> None:
    xml = build_search_xml(
        101,
        datetime(2026, 9, 9, 9, 20, tzinfo=UTC),
        datetime(2026, 9, 9, 9, 40, tzinfo=UTC),
        search_id="test-search",
    ).decode()
    assert '<CMSearchDescription version="2.0"' in xml
    assert '<searchID>test-search</searchID>' in xml
    assert '<trackID>101</trackID>' in xml
    assert '<maxResults>40</maxResults>' in xml
    assert '<searchResultPosition>0</searchResultPosition>' in xml


def test_parse_search_response_is_namespace_independent() -> None:
    payload = b'''<?xml version="1.0"?><CMSearchResult xmlns="urn:test">
      <numOfMatches>1</numOfMatches><matchList><searchMatchItem>
        <trackID>101</trackID><timeSpan><startTime>2026-09-09T09:20:00Z</startTime><endTime>2026-09-09T09:30:00Z</endTime></timeSpan>
        <mediaSegmentDescriptor><playbackURI>rtsp://nvr/Streaming/tracks/101/?starttime=a&amp;endtime=b&amp;name=x</playbackURI><codecType>H.264</codecType></mediaSegmentDescriptor>
      </searchMatchItem></matchList></CMSearchResult>'''
    segments, total = parse_search_response(payload)
    assert total == 1
    assert len(segments) == 1
    assert segments[0].track_id == 101
    assert segments[0].codec_type == "H.264"
    assert segments[0].playback_uri.endswith("name=x")


def test_parse_skips_incomplete_match_items() -> None:
    payload = b'''<CMSearchResult><numOfMatches>2</numOfMatches><matchList>
      <searchMatchItem><trackID>101</trackID><timeSpan><startTime>2026-09-09T09:20:00Z</startTime><endTime>2026-09-09T09:30:00Z</endTime></timeSpan><mediaSegmentDescriptor><playbackURI>x</playbackURI><codecType>H.264</codecType></mediaSegmentDescriptor></searchMatchItem>
      <searchMatchItem><trackID>101</trackID></searchMatchItem>
    </matchList></CMSearchResult>'''
    segments, total = parse_search_response(payload)
    assert total == 2
    assert len(segments) == 1


def test_invalid_xml_is_rejected() -> None:
    with pytest.raises(HikvisionXmlError):
        parse_search_response(b"<broken>")


def test_select_start_segment_uses_intersection_and_start_containment() -> None:
    payload = b'''<CMSearchResult><numOfMatches>2</numOfMatches><matchList>
      <searchMatchItem><trackID>101</trackID><timeSpan><startTime>2026-09-09T09:00:00Z</startTime><endTime>2026-09-09T09:20:00Z</endTime></timeSpan><mediaSegmentDescriptor><playbackURI>a</playbackURI><codecType>H.264</codecType></mediaSegmentDescriptor></searchMatchItem>
      <searchMatchItem><trackID>101</trackID><timeSpan><startTime>2026-09-09T09:20:00Z</startTime><endTime>2026-09-09T09:40:00Z</endTime></timeSpan><mediaSegmentDescriptor><playbackURI>b</playbackURI><codecType>H.264</codecType></mediaSegmentDescriptor></searchMatchItem>
    </matchList></CMSearchResult>'''
    segments, _ = parse_search_response(payload)
    selected = select_start_segment(segments, datetime(2026, 9, 9, 9, 25, tzinfo=UTC), datetime(2026, 9, 9, 9, 35, tzinfo=UTC))
    assert selected.playback_uri == "b"


def test_select_start_segment_reports_no_recording() -> None:
    payload = b'''<CMSearchResult><numOfMatches>1</numOfMatches><matchList>
      <searchMatchItem><trackID>101</trackID><timeSpan><startTime>2026-09-09T09:30:00Z</startTime><endTime>2026-09-09T09:40:00Z</endTime></timeSpan><mediaSegmentDescriptor><playbackURI>x</playbackURI><codecType>H.264</codecType></mediaSegmentDescriptor></searchMatchItem>
    </matchList></CMSearchResult>'''
    segments, _ = parse_search_response(payload)
    with pytest.raises(HikvisionNoRecording):
        select_start_segment(segments, datetime(2026, 9, 9, 9, 20, tzinfo=UTC), datetime(2026, 9, 9, 9, 25, tzinfo=UTC))


def test_page_size_does_not_exceed_spec_limit() -> None:
    assert PAGE_SIZE <= 40
