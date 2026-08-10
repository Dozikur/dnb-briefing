#!/usr/bin/env python3
"""Validate the manifest, legacy archive, schema v2 briefings, and the week 31 special."""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "news" / "index.json"
SECTION_IDS = [
    "competition", "festival_industry", "dnb_scene", "cz_sk",
    "audience_sentiment", "strategic_releases", "lir_actions",
]
CATEGORIES = {
    "competition", "festival_industry", "dnb_scene", "cz_sk",
    "audience_sentiment", "strategic_release", "lir_action",
}
REGIONS = {"world", "europe", "cz_sk", "global"}
CONFIDENCE = {"confirmed", "probable", "unverified"}
SOURCE_KINDS = {"primary", "secondary", "community"}
MEDIA_TYPES = {"image", "instagram", "youtube", "spotify", "soundcloud"}
EDITORIAL_COVERAGE_START = (2026, 29)


class ValidationError(Exception):
    pass


def fail(message: str) -> None:
    raise ValidationError(message)


def load_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except FileNotFoundError:
        fail(f"Missing file: {path.relative_to(ROOT)}")
    except json.JSONDecodeError as exc:
        fail(f"Invalid JSON in {path.relative_to(ROOT)}: {exc}")


def text(value, field: str, minimum: int, maximum: int) -> str:
    if not isinstance(value, str) or not minimum <= len(value.strip()) <= maximum:
        fail(f"{field} must contain {minimum} to {maximum} characters")
    return value.strip()


def iso_date(value, field: str) -> date:
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError):
        fail(f"{field} must use YYYY-MM-DD")


def https_url(value, field: str) -> None:
    if not isinstance(value, str):
        fail(f"{field} must be a URL")
    parsed = urlparse(value)
    if parsed.scheme != "https" or not parsed.netloc:
        fail(f"{field} must be a valid HTTPS URL")


def exact_keys(value, keys: set[str], field: str) -> None:
    if not isinstance(value, dict) or set(value) != keys:
        fail(f"{field} keys must be exactly {sorted(keys)}")


def validate_source(value: dict, field: str) -> None:
    exact_keys(value, {"name", "url", "kind"}, field)
    text(value["name"], f"{field}.name", 2, 100)
    https_url(value["url"], f"{field}.url")
    if value["kind"] not in SOURCE_KINDS:
        fail(f"{field}.kind is invalid")


def validate_media(value: dict, field: str) -> None:
    exact_keys(value, {"type", "url"}, field)
    if value["type"] not in MEDIA_TYPES:
        fail(f"{field}.type is invalid")
    https_url(value["url"], f"{field}.url")


def validate_unique_text_list(value, field: str, maximum: int, max_text: int = 80) -> None:
    if not isinstance(value, list) or len(value) > maximum:
        fail(f"{field} must contain at most {maximum} values")
    cleaned = [text(item, field, 2, max_text) for item in value]
    if len(cleaned) != len(set(cleaned)):
        fail(f"{field} contains duplicates")


def validate_v2(path: Path, report: dict) -> list[str]:
    try:
        top_keys = {"schema_version", "period", "headline", "executive_summary", "sections", "sources_scanned"}
        exact_keys(report, top_keys, "report")
        if report["schema_version"] != 2:
            fail("schema_version must be 2")

        period = report["period"]
        exact_keys(period, {"year", "week", "window_start", "window_end", "generated_at"}, "period")
        if not isinstance(period["year"], int) or period["year"] < 2026:
            fail("period.year is invalid")
        if not isinstance(period["week"], int) or not 1 <= period["week"] <= 53:
            fail("period.week is invalid")
        start = iso_date(period["window_start"], "period.window_start")
        end = iso_date(period["window_end"], "period.window_end")
        if start > end:
            fail("period.window_start is after period.window_end")
        try:
            generated_at = datetime.fromisoformat(period["generated_at"].replace("Z", "+00:00"))
        except (TypeError, ValueError):
            fail("period.generated_at must be an ISO datetime")
        expected_filename = f"{period['year']}-week_{period['week']}.json"
        if path.name != expected_filename:
            fail(f"filename must be {expected_filename}")

        text(report["headline"], "headline", 8, 160)
        bullets = report["executive_summary"]
        if not isinstance(bullets, list) or not 1 <= len(bullets) <= 5:
            fail("executive_summary must contain 1 to 5 bullets")
        for index, bullet in enumerate(bullets):
            text(bullet, f"executive_summary[{index}]", 20, 360)

        sections = report["sections"]
        if not isinstance(sections, list) or len(sections) != 7:
            fail("sections must contain all seven sections")
        actual_section_ids = [section.get("id") for section in sections if isinstance(section, dict)]
        if actual_section_ids != SECTION_IDS:
            fail(f"section order must be {SECTION_IDS}")

        seen_ids: set[str] = set()
        seen_titles: set[str] = set()
        non_action_count = 0
        for section_index, section in enumerate(sections):
            section_field = f"sections[{section_index}]"
            exact_keys(section, {"id", "title", "items"}, section_field)
            text(section["title"], f"{section_field}.title", 2, 80)
            items = section["items"]
            if not isinstance(items, list) or len(items) > 6:
                fail(f"{section_field}.items must contain at most 6 items")
            if section["id"] != "lir_actions":
                non_action_count += len(items)

            for item_index, item in enumerate(items):
                field = f"{section_field}.items[{item_index}]"
                item_keys = {
                    "id", "published_at", "event_start", "event_end", "title", "summary",
                    "why_it_matters", "recommended_action", "region", "category", "competitors",
                    "confidence", "sources", "media", "tags",
                }
                exact_keys(item, item_keys, field)
                item_id = text(item["id"], f"{field}.id", 8, 100)
                if not re.fullmatch(r"[a-z0-9][a-z0-9-]+", item_id):
                    fail(f"{field}.id must be a lowercase slug")
                if item_id in seen_ids:
                    fail(f"duplicate item id: {item_id}")
                seen_ids.add(item_id)

                published = iso_date(item["published_at"], f"{field}.published_at")
                event_start = iso_date(item["event_start"], f"{field}.event_start") if item["event_start"] else None
                event_end = iso_date(item["event_end"], f"{field}.event_end") if item["event_end"] else None
                if event_end and not event_start:
                    fail(f"{field}.event_end requires event_start")
                if event_start and event_end and event_end < event_start:
                    fail(f"{field}.event_end is before event_start")
                late_event_coverage = (
                    published == end + timedelta(days=1)
                    and published <= generated_at.date()
                    and event_start is not None
                    and start <= event_start <= end
                )
                if not start <= published <= end and not late_event_coverage:
                    fail(f"{field}.published_at is outside the reporting window")

                title = text(item["title"], f"{field}.title", 8, 180)
                normalized = re.sub(r"\W+", " ", title.casefold()).strip()
                if normalized in seen_titles:
                    fail(f"duplicate title: {title}")
                seen_titles.add(normalized)

                paragraphs = item["summary"]
                if not isinstance(paragraphs, list) or not 1 <= len(paragraphs) <= 4:
                    fail(f"{field}.summary must contain 1 to 4 paragraphs")
                for paragraph_index, paragraph in enumerate(paragraphs):
                    text(paragraph, f"{field}.summary[{paragraph_index}]", 20, 520)
                text(item["why_it_matters"], f"{field}.why_it_matters", 20, 520)
                text(item["recommended_action"], f"{field}.recommended_action", 10, 300)
                if item["region"] not in REGIONS:
                    fail(f"{field}.region is invalid")
                if item["category"] not in CATEGORIES:
                    fail(f"{field}.category is invalid")
                if item["confidence"] not in CONFIDENCE:
                    fail(f"{field}.confidence is invalid")
                validate_unique_text_list(item["competitors"], f"{field}.competitors", 10)
                validate_unique_text_list(item["tags"], f"{field}.tags", 8, 40)

                sources = item["sources"]
                if not isinstance(sources, list) or not 1 <= len(sources) <= 5:
                    fail(f"{field}.sources must contain 1 to 5 sources")
                for source_index, source in enumerate(sources):
                    validate_source(source, f"{field}.sources[{source_index}]")
                if item["confidence"] == "confirmed":
                    has_primary = any(source["kind"] == "primary" for source in sources)
                    hosts = {urlparse(source["url"]).netloc for source in sources}
                    if not has_primary and len(hosts) < 2:
                        fail(f"{field}: confirmed claims need a primary source or two independent sources")

                media = item["media"]
                if not isinstance(media, list) or len(media) > 3:
                    fail(f"{field}.media must contain at most 3 entries")
                for media_index, media_item in enumerate(media):
                    validate_media(media_item, f"{field}.media[{media_index}]")

        if non_action_count > 14:
            fail("the report may contain at most 14 non-action items")
        validate_unique_text_list(report["sources_scanned"], "sources_scanned", 100, 120)
        if not report["sources_scanned"]:
            fail("sources_scanned must not be empty")

        if (period["year"], period["week"]) >= EDITORIAL_COVERAGE_START:
            section_map = {section["id"]: section["items"] for section in sections}
            if len(section_map["dnb_scene"]) < 2:
                fail("dnb_scene must contain at least 2 items")

            scan_labels = [label.casefold() for label in report["sources_scanned"]]
            if not any("reddit" in label and "r/dnb" in label and "top/week" in label for label in scan_labels):
                fail("sources_scanned must record the Reddit r/DnB hot + top/week sweep")

        return []
    except ValidationError as exc:
        return [f"{path.relative_to(ROOT)}: {exc}"]


def validate_special(path: Path, report: dict) -> list[str]:
    try:
        if path.name != "2026-week_31-special.json":
            fail("post_event_monitoring is only supported for 2026-week_31-special.json")
        exact_keys(
            report,
            {
                "schema_version", "type", "headline", "period", "methodology", "stats",
                "instagram", "media", "community", "management_summary",
            },
            "special report",
        )
        if report["schema_version"] != 1 or report["type"] != "post_event_monitoring":
            fail("special report must use schema_version 1 and type post_event_monitoring")
        text(report["headline"], "headline", 8, 180)
        text(report["methodology"], "methodology", 20, 1000)

        period = report["period"]
        exact_keys(period, {"window_start", "window_end", "updated_at", "metrics_checked_at"}, "period")
        start = iso_date(period["window_start"], "period.window_start")
        end = iso_date(period["window_end"], "period.window_end")
        if start > end:
            fail("period.window_start is after period.window_end")
        for field in ("updated_at", "metrics_checked_at"):
            try:
                datetime.fromisoformat(period[field].replace("Z", "+00:00"))
            except (AttributeError, TypeError, ValueError):
                fail(f"period.{field} must be an ISO datetime")

        stats = report["stats"]
        stat_keys = {
            "lineup_units", "units_with_posts", "units_without_posts",
            "instagram_posts", "posts_with_visible_metrics",
        }
        exact_keys(stats, stat_keys, "stats")
        if any(not isinstance(stats[key], int) or stats[key] < 0 for key in stat_keys):
            fail("all stats values must be non-negative integers")
        if stats["units_with_posts"] + stats["units_without_posts"] != stats["lineup_units"]:
            fail("units_with_posts and units_without_posts must add up to lineup_units")

        instagram = report["instagram"]
        exact_keys(instagram, {"note", "top_posts", "posts", "without_post"}, "instagram")
        text(instagram["note"], "instagram.note", 10, 1000)
        for list_name in ("top_posts", "posts", "without_post"):
            if not isinstance(instagram[list_name], list):
                fail(f"instagram.{list_name} must be an array")
        if len(instagram["top_posts"]) > 10:
            fail("instagram.top_posts may contain at most 10 entries")
        if len(instagram["posts"]) != stats["instagram_posts"]:
            fail("instagram.posts count must match stats.instagram_posts")
        for list_name in ("top_posts", "posts"):
            for index, post in enumerate(instagram[list_name]):
                field = f"instagram.{list_name}[{index}]"
                if not isinstance(post, dict):
                    fail(f"{field} must be an object")
                for required in ("billing", "url", "published_at", "caption", "sentiment"):
                    if required not in post:
                        fail(f"{field} is missing {required}")
                text(post["billing"], f"{field}.billing", 1, 160)
                https_url(post["url"], f"{field}.url")
                if post["published_at"] is not None:
                    iso_date(post["published_at"], f"{field}.published_at")

        media = report["media"]
        exact_keys(media, {"note", "featured", "others"}, "media")
        text(media["note"], "media.note", 10, 1000)
        for list_name in ("featured", "others"):
            if not isinstance(media[list_name], list):
                fail(f"media.{list_name} must be an array")
            for index, item in enumerate(media[list_name]):
                field = f"media.{list_name}[{index}]"
                if not isinstance(item, dict) or "title" not in item or "url" not in item:
                    fail(f"{field} must contain title and url")
                text(item["title"], f"{field}.title", 4, 220)
                https_url(item["url"], f"{field}.url")

        community = report["community"]
        exact_keys(community, {"note", "positive", "negative", "themes"}, "community")
        text(community["note"], "community.note", 10, 1000)
        for list_name in ("positive", "negative", "themes"):
            if not isinstance(community[list_name], list):
                fail(f"community.{list_name} must be an array")
        for list_name in ("positive", "negative"):
            for index, item in enumerate(community[list_name]):
                field = f"community.{list_name}[{index}]"
                if not isinstance(item, dict) or "excerpt" not in item or "url" not in item:
                    fail(f"{field} must contain excerpt and url")
                text(item["excerpt"], f"{field}.excerpt", 10, 1000)
                https_url(item["url"], f"{field}.url")

        management = report["management_summary"]
        exact_keys(management, {"worked", "problems", "verify"}, "management_summary")
        for list_name in ("worked", "problems", "verify"):
            validate_unique_text_list(management[list_name], f"management_summary.{list_name}", 20, 500)

        return []
    except ValidationError as exc:
        return [f"{path.relative_to(ROOT)}: {exc}"]


def validate_legacy(path: Path, report: list) -> list[str]:
    warnings: list[str] = []
    for index, item in enumerate(report):
        if not isinstance(item, dict):
            warnings.append(f"{path.relative_to(ROOT)}[{index}] is not an object")
            continue
        for required in ("title", "content", "source", "genre", "image"):
            if required not in item:
                warnings.append(f"{path.relative_to(ROOT)}[{index}] missing {required}")
    return warnings


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--all", action="store_true")
    parser.add_argument("files", nargs="*")
    args = parser.parse_args()

    try:
        manifest = load_json(MANIFEST)
        exact_keys(manifest, {"schema_version", "briefings"}, "manifest")
        if manifest["schema_version"] != 1 or not isinstance(manifest["briefings"], list):
            fail("manifest has an unsupported structure")
    except ValidationError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    errors: list[str] = []
    warnings: list[str] = []
    seen_files: set[str] = set()
    seen_periods: set[tuple[int, int]] = set()
    for entry in manifest["briefings"]:
        try:
            exact_keys(entry, {"year", "week", "file"}, "manifest entry")
            period = (entry["year"], entry["week"])
            expected = f"news/{entry['year']}-week_{entry['week']}.json"
            allowed_files = {expected}
            if period == (2026, 31):
                allowed_files.add("news/2026-week_31-special.json")
            if entry["file"] not in allowed_files:
                fail(f"manifest expected one of {sorted(allowed_files)}, got {entry['file']}")
            if entry["file"] in seen_files or period in seen_periods:
                fail(f"duplicate manifest entry: {period}")
            seen_files.add(entry["file"])
            seen_periods.add(period)
        except ValidationError as exc:
            errors.append(str(exc))

    targets = [ROOT / entry["file"] for entry in manifest["briefings"]] if args.all or not args.files else [ROOT / item for item in args.files]
    for path in targets:
        try:
            report = load_json(path)
        except ValidationError as exc:
            errors.append(str(exc))
            continue
        if isinstance(report, list):
            warnings.extend(validate_legacy(path, report))
        elif isinstance(report, dict) and report.get("type") == "post_event_monitoring":
            errors.extend(validate_special(path, report))
        elif isinstance(report, dict) and report.get("schema_version") == 2:
            errors.extend(validate_v2(path, report))
        else:
            errors.append(f"{path.relative_to(ROOT)} has an unsupported structure")

    for warning in warnings:
        print(f"WARNING: {warning}")
    for error in errors:
        print(f"ERROR: {error}", file=sys.stderr)
    print(f"Validated {len(targets)} report(s): {len(errors)} error(s), {len(warnings)} legacy warning(s)")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
