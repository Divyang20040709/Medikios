"""
Static regression tests for the MediKiosk frontend notification system
(Phase 10: "Replace Browser Alerts with Theme-Matched UI").

These tests deliberately perform NO database writes, NO network calls and NO
process launches - they only read source files - so they are safe to run
against a live environment, unlike the API-flow tests.

They guard three promises made in that work:
  1. No user-facing native browser popup (alert / confirm / prompt) survives in
     frontend source (comments and doc references are allowed).
  2. The reusable in-app system exists and is wired app-wide (ToastProvider in
     the root layout, accessible Toast viewport + NotificationModal dialog).
  3. The emergency / red-flag assistance copy is honest (it never claims staff
     were dispatched by a live station) and is translated in all three UI
     languages supported by the kiosk (en / hi / gu).
"""

import re
from pathlib import Path

import pytest

FRONTEND_SRC = Path(__file__).resolve().parents[2] / "frontend" / "src"

SOURCE_GLOBS = ("**/*.ts", "**/*.tsx", "**/*.js", "**/*.jsx")

# Call forms of the primitives. Requires a token boundary before the name so
# `clinicalStore.confirm(...)`-style property calls would still match as
# `.confirm(` - hence we also reject a leading '.' or word character.
NATIVE_POPUP_RE = re.compile(r"(?<![\w.$])(?:window\.)?(alert|confirm|prompt)\s*\(")

COMMENT_PREFIXES = ("//", "*", "/*", "{/*")


def iter_source_files():
    seen = set()
    for pattern in SOURCE_GLOBS:
        for path in FRONTEND_SRC.glob(pattern):
            if path in seen:
                continue
            # Skip generated / cache output.
            parts = set(path.parts)
            if {"node_modules", ".next"} & parts:
                continue
            seen.add(path)
            yield path


def strip_comments(line: str) -> str:
    """Remove full-line comments and inline `// ...` trailing comments."""
    stripped = line.strip()
    for prefix in COMMENT_PREFIXES:
        if stripped.startswith(prefix):
            return ""
    # Cut trailing // comment (no URL scheme handling needed in this codebase's
    # popup calls; the primitives would never legitimately appear after one).
    idx = line.find("//")
    if idx != -1 and (idx == 0 or line[idx - 1] not in (":",)):
        line = line[:idx]
    return line


I18N_FILE = FRONTEND_SRC / "lib" / "i18n.ts"


def load_i18n_dict(language: str) -> dict:
    """Parse one language block (`const <lang>: Dict = { ... }`) from i18n.ts.

    Returns a {key: value} map for the simple single-quoted 'key': 'value'
    entries used by the kiosk dictionary. Intentionally minimal - it exists
    only to assert translation coverage, not to reimplement the runtime.
    """
    text = I18N_FILE.read_text(encoding="utf-8")
    block = re.search(rf"const {language}: Dict = \{{(.*?)\n\}};", text, re.S)
    assert block, f"language block '{language}' not found in i18n.ts"
    return dict(re.findall(r"'([^']+)':\s*'([^']*)'", block.group(1)))


class TestNoNativePopups:
    def test_no_native_popup_calls_remain(self):
        offenders = []
        for path in iter_source_files():
            text = path.read_text(encoding="utf-8")
            for lineno, line in enumerate(text.splitlines(), start=1):
                if NATIVE_POPUP_RE.search(strip_comments(line)):
                    offenders.append(f"{path.relative_to(FRONTEND_SRC)}:{lineno}: {line.strip()}")
        assert not offenders, (
            "Native browser popups are forbidden in user-facing code; use "
            "components/common/Toast.tsx or NotificationModal.tsx instead.\n"
            + "\n".join(offenders)
        )

    def test_notification_system_files_exist(self):
        assert (FRONTEND_SRC / "components" / "common" / "Toast.tsx").is_file()
        assert (FRONTEND_SRC / "components" / "common" / "NotificationModal.tsx").is_file()

    def test_toast_provider_is_mounted_in_root_layout(self):
        layout = (FRONTEND_SRC / "app" / "layout.tsx").read_text(encoding="utf-8")
        assert "ToastProvider" in layout
        assert "<ToastProvider>{children}</ToastProvider>" in layout


class TestAccessibilityContract:
    def test_toast_viewport_is_live_region_and_dismissible(self):
        src = (FRONTEND_SRC / "components" / "common" / "Toast.tsx").read_text(encoding="utf-8")
        assert 'aria-label="Notifications"' in src
        assert 'role="region"' in src
        # assertive for error/warning, polite for the rest
        assert "'alert'" in src and "'status'" in src
        assert "Dismiss notification" in src

    def test_modal_is_labelled_modal_trapped_and_escape_closable(self):
        src = (FRONTEND_SRC / "components" / "common" / "NotificationModal.tsx").read_text(encoding="utf-8")
        assert 'role="dialog"' in src
        assert 'aria-modal="true"' in src
        assert "aria-labelledby" in src
        assert "aria-describedby" in src
        assert "Escape" in src
        assert "'Tab'" in src
        # focus is restored to the trigger on close
        assert "lastFocused" in src

    def test_critical_toasts_outlast_routine_ones(self):
        src = (FRONTEND_SRC / "components" / "common" / "Toast.tsx").read_text(encoding="utf-8")
        match = re.search(r"DEFAULT_DURATION[^=]*=\s*\{(.*?)\}", src, re.S)
        assert match, "DEFAULT_DURATION map not found"
        durations = dict(
            (k, int(v))
            for k, v in re.findall(r"(\w+):\s*(\d+)", match.group(1))
        )
        assert durations["error"] >= 6000, "error toasts must not disappear too quickly"
        assert durations["warning"] >= 5000
        assert durations["error"] > durations["success"]

    def test_toasts_are_deduplicated(self):
        src = (FRONTEND_SRC / "components" / "common" / "Toast.tsx").read_text(encoding="utf-8")
        assert "isDuplicate" in src


class TestEmergencyAssistanceFlows:
    """Rule 5: the UI must never claim a live dispatch it cannot perform."""

    def test_accessibility_banner_emergency_uses_modal_not_alert(self):
        src = (FRONTEND_SRC / "components" / "kiosk" / "AccessibilityBanner.tsx").read_text(encoding="utf-8")
        assert "NotificationModal" in src
        assert "setEmergencyOpen(true)" in src
        assert 'title="Assistance requested"' in src
        # Honest disclaimer - must state that no staff were paged.
        assert "no staff have been paged" in src
        # The old false claim must be gone.
        assert "Counter assistance dispatched" not in src

    def test_banner_still_prefers_a_real_host_handler(self):
        src = (FRONTEND_SRC / "components" / "kiosk" / "AccessibilityBanner.tsx").read_text(encoding="utf-8")
        assert "onEmergencyCall" in src
        body = src[src.index("const handleEmergency"):src.index("const handleEmergency") + 400]
        assert "onEmergencyCall();" in body

    @pytest.mark.parametrize("language", ["en", "hi", "gu"])
    def test_red_flag_notify_copy_is_translated_and_honest(self, language):
        d = load_i18n_dict(language)
        required = ["iv.notifyModalTitle", "iv.notifyModalBody", "iv.notifyModalOk"]
        missing = [k for k in required if not d.get(k)]
        assert not missing, f"{language} is missing keys: {missing}"
        # Must disclose that the kiosk does not page a live nurse station.
        assert "nurse" in d["iv.notifyModalBody"].lower() or language != "en"

    def test_interview_notify_opens_modal(self):
        src = (FRONTEND_SRC / "components" / "kiosk" / "SymptomHistoryInterview.tsx").read_text(encoding="utf-8")
        assert "setNotifyModalOpen(true)" in src
        assert "iv.notifyModalTitle" in src

    @pytest.mark.parametrize("file", ["app/chat/page.tsx", "components/common/AIChatbotDrawer.tsx"])
    def test_speech_unsupported_uses_non_blocking_toast(self, file):
        src = (FRONTEND_SRC / file).read_text(encoding="utf-8")
        assert "toast.warning('Voice input unavailable'" in src
