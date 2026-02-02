"""Transfer settings service - configuration for COROS->Garmin sync."""

import logging
import re
from copy import deepcopy
from datetime import datetime
from string import Formatter
from typing import Any

from fitness_toolkit.database import get_transfer_settings, save_transfer_settings

logger = logging.getLogger(__name__)

# Current settings schema version
SETTINGS_VERSION = 1

# COROS sport type code -> Chinese name mapping
COROS_SPORT_NAMES: dict[int, str] = {
    100: "跑步",
    101: "室内跑",
    102: "越野跑",
    103: "铁人三项跑",
    200: "骑行",
    201: "室内骑行",
    300: "泳池游泳",
    301: "开放水域游泳",
    302: "铁人三项游泳",
    400: "铁人三项",
    500: "有氧运动",
    501: "力量训练",
    502: "有氧健身操",
    503: "高强度间歇",
    504: "健身瑜伽",
    600: "健走",
    601: "室内健走",
    700: "徒步",
    800: "登山",
    900: "滑雪",
    901: "单板滑雪",
    902: "越野滑雪",
    1000: "划船",
    1001: "室内划船",
    1100: "跳绳",
    1200: "飞盘",
    1300: "水上运动",
    1301: "皮划艇",
    1302: "帆船",
    1303: "冲浪",
    1400: "速降",
    1500: "攀岩",
    1600: "网球",
    1700: "跑步机",
    1800: "综合训练",
    9999: "其他",
}


def get_default_settings() -> dict[str, Any]:
    """Return default transfer settings."""
    return {
        "version": SETTINGS_VERSION,
        "concurrency": 2,
        "retry": {
            "max_attempts": 3,
            "base_delay_seconds": 1,
            "max_delay_seconds": 60,
        },
        "naming": {
            "title_template": "{sport} {start_local:%Y-%m-%d %H:%M}",
            "description_template": "",
        },
        "privacy": {
            "visibility": "default",  # "default" | "private" | "public"
        },
        "sport_mapping": {},  # COROS sportType -> Garmin activityType key
        "gear": {
            "enabled": False,
            "gear_id": None,
        },
    }


# Allowed variables for template rendering (whitelist for security)
ALLOWED_TEMPLATE_VARS = {
    "label_id",
    "sport",
    "sport_type",
    "start_time",
    "start_local",
    "duration_seconds",
    "duration_formatted",
    "distance_km",
    "distance_m",
    "name",
    "calories",
}


class TemplateRenderer:
    """Safe template renderer using str.format_map with whitelisted variables."""

    def __init__(self, template: str):
        self.template = template
        self._validate_template()

    def _validate_template(self) -> None:
        """Validate that template only uses allowed variables."""
        formatter = Formatter()
        for _, field_name, _, _ in formatter.parse(self.template):
            if field_name is None:
                continue
            # Extract base variable name (before any format spec or attribute access)
            base_name = field_name.split(".")[0].split("[")[0].split(":")[0]
            if base_name and base_name not in ALLOWED_TEMPLATE_VARS:
                raise ValueError(
                    f"Template variable '{base_name}' is not allowed. "
                    f"Allowed: {', '.join(sorted(ALLOWED_TEMPLATE_VARS))}"
                )

    def render(self, context: dict[str, Any]) -> str:
        """Render template with given context."""
        # Filter context to only allowed variables
        safe_context = {k: v for k, v in context.items() if k in ALLOWED_TEMPLATE_VARS}
        try:
            return self.template.format_map(safe_context)
        except KeyError as e:
            logger.warning(f"Template rendering missing variable: {e}")
            return self.template
        except Exception as e:
            logger.warning(f"Template rendering failed: {e}")
            return self.template


class TransferSettingsService:
    """Service for managing transfer settings."""

    def get_settings(self) -> dict[str, Any]:
        """Get current settings, creating defaults if not exist."""
        settings = get_transfer_settings()
        if settings is None:
            settings = get_default_settings()
            save_transfer_settings(settings)
            logger.info("Created default transfer settings")
        return settings

    def save_settings(self, settings: dict[str, Any]) -> tuple[dict[str, Any], dict[str, str]]:
        """
        Validate and save settings.

        Returns:
            Tuple of (normalized_settings, validation_errors)
            If validation_errors is non-empty, settings were not saved.
        """
        errors = self._validate_settings(settings)
        if errors:
            return settings, errors

        # Normalize and merge with defaults
        normalized = self._normalize_settings(settings)
        save_transfer_settings(normalized)
        logger.info("Saved transfer settings")
        return normalized, {}

    def _validate_settings(self, settings: dict[str, Any]) -> dict[str, str]:
        """Validate settings and return field-level errors."""
        errors: dict[str, str] = {}

        # Validate concurrency
        concurrency = settings.get("concurrency")
        if concurrency is not None:
            if not isinstance(concurrency, int) or concurrency < 1 or concurrency > 10:
                errors["concurrency"] = "Must be an integer between 1 and 10"

        # Validate retry settings
        retry = settings.get("retry", {})
        if retry:
            max_attempts = retry.get("max_attempts")
            if max_attempts is not None:
                if not isinstance(max_attempts, int) or max_attempts < 1 or max_attempts > 10:
                    errors["retry.max_attempts"] = "Must be an integer between 1 and 10"

            base_delay = retry.get("base_delay_seconds")
            if base_delay is not None:
                if not isinstance(base_delay, (int, float)) or base_delay < 0 or base_delay > 60:
                    errors["retry.base_delay_seconds"] = "Must be a number between 0 and 60"

            max_delay = retry.get("max_delay_seconds")
            if max_delay is not None:
                if not isinstance(max_delay, (int, float)) or max_delay < 1 or max_delay > 300:
                    errors["retry.max_delay_seconds"] = "Must be a number between 1 and 300"

        # Validate naming templates
        naming = settings.get("naming", {})
        if naming:
            title_template = naming.get("title_template")
            if title_template is not None:
                if not isinstance(title_template, str):
                    errors["naming.title_template"] = "Must be a string"
                elif len(title_template) > 200:
                    errors["naming.title_template"] = "Must be at most 200 characters"
                else:
                    try:
                        TemplateRenderer(title_template)
                    except ValueError as e:
                        errors["naming.title_template"] = str(e)

            desc_template = naming.get("description_template")
            if desc_template is not None:
                if not isinstance(desc_template, str):
                    errors["naming.description_template"] = "Must be a string"
                elif len(desc_template) > 1000:
                    errors["naming.description_template"] = "Must be at most 1000 characters"
                else:
                    try:
                        TemplateRenderer(desc_template)
                    except ValueError as e:
                        errors["naming.description_template"] = str(e)

        # Validate privacy
        privacy = settings.get("privacy", {})
        if privacy:
            visibility = privacy.get("visibility")
            if visibility is not None:
                if visibility not in ("default", "private", "public"):
                    errors["privacy.visibility"] = "Must be one of: default, private, public"

        # Validate gear
        gear = settings.get("gear", {})
        if gear:
            enabled = gear.get("enabled")
            if enabled is not None and not isinstance(enabled, bool):
                errors["gear.enabled"] = "Must be a boolean"

            gear_id = gear.get("gear_id")
            if gear_id is not None and not isinstance(gear_id, (str, type(None))):
                errors["gear.gear_id"] = "Must be a string or null"

        return errors

    def _normalize_settings(self, settings: dict[str, Any]) -> dict[str, Any]:
        """Normalize settings by merging with defaults."""
        defaults = get_default_settings()

        # Deep merge
        normalized = deepcopy(defaults)
        for key, value in settings.items():
            if key in normalized and isinstance(normalized[key], dict) and isinstance(value, dict):
                normalized[key].update(value)
            else:
                normalized[key] = value

        # Ensure version is current
        normalized["version"] = SETTINGS_VERSION
        return normalized

    def preview(
        self, activity: dict[str, Any], settings: "dict[str, Any] | None" = None
    ) -> dict[str, Any]:
        """
        Preview rendered metadata for an activity.

        Args:
            activity: COROS activity data (minimal: labelId, sportType, name, startTime)
            settings: Optional settings override; uses current settings if None

        Returns:
            {
                "rendered": {"title": "...", "description": "..."},
                "patch": {"activityName": "...", "description": "...", ...}
            }
        """
        if settings is None:
            settings = self.get_settings()

        context = self._build_template_context(activity)
        naming = settings.get("naming", {})

        # Render title
        title_template = naming.get("title_template", "")
        title = ""
        if title_template:
            try:
                renderer = TemplateRenderer(title_template)
                title = renderer.render(context)
            except Exception as e:
                logger.warning(f"Failed to render title template: {e}")
                title = activity.get("name", "")

        # Render description
        desc_template = naming.get("description_template", "")
        description = ""
        if desc_template:
            try:
                renderer = TemplateRenderer(desc_template)
                description = renderer.render(context)
            except Exception as e:
                logger.warning(f"Failed to render description template: {e}")

        # Build patch (intended metadata operations)
        patch: dict[str, Any] = {}
        if title:
            patch["activityName"] = title
        if description:
            patch["description"] = description

        # Privacy
        privacy = settings.get("privacy", {})
        visibility = privacy.get("visibility", "default")
        if visibility != "default":
            # Garmin uses different field names
            patch["privacy"] = {"typeKey": visibility}

        # Gear
        gear = settings.get("gear", {})
        if gear.get("enabled") and gear.get("gear_id"):
            patch["gear_id"] = gear["gear_id"]

        return {
            "rendered": {"title": title, "description": description},
            "patch": patch,
            "context": context,  # Include context for debugging
        }

    def _build_template_context(self, activity: dict[str, Any]) -> dict[str, Any]:
        """Build template context from COROS activity data."""
        label_id = activity.get("labelId", "")
        sport_type = activity.get("sportType", 9999)
        name = activity.get("name", "")
        start_time_str = activity.get("startTime", "")

        # Parse start time
        start_time = None
        start_local = None
        if start_time_str:
            try:
                # COROS returns time like "2024-01-15 08:30:00"
                start_time = datetime.strptime(start_time_str, "%Y-%m-%d %H:%M:%S")
                start_local = start_time  # Assume local time
            except ValueError:
                try:
                    # Try ISO format
                    start_time = datetime.fromisoformat(start_time_str.replace("Z", "+00:00"))
                    start_local = start_time
                except ValueError:
                    pass

        # Get sport name
        sport = COROS_SPORT_NAMES.get(sport_type, "运动")

        # Duration
        duration_seconds = activity.get("duration", 0) or activity.get("totalTime", 0) or 0
        hours, remainder = divmod(int(duration_seconds), 3600)
        minutes, seconds = divmod(remainder, 60)
        if hours > 0:
            duration_formatted = f"{hours}:{minutes:02d}:{seconds:02d}"
        else:
            duration_formatted = f"{minutes}:{seconds:02d}"

        # Distance
        distance_m = activity.get("distance", 0) or activity.get("totalDistance", 0) or 0
        distance_km = distance_m / 1000.0 if distance_m else 0

        return {
            "label_id": label_id,
            "sport": sport,
            "sport_type": sport_type,
            "start_time": start_time,
            "start_local": start_local,
            "duration_seconds": duration_seconds,
            "duration_formatted": duration_formatted,
            "distance_km": round(distance_km, 2),
            "distance_m": distance_m,
            "name": name,
            "calories": activity.get("calorie", 0) or activity.get("calories", 0) or 0,
        }
