"""Keys that are present and switched off.

THE DEPLOYMENT THIS COMES FROM. Real API keys were put into app.env on a live
host. The service read every one of them correctly and used none. The health
endpoint said `provider: off`, voice was unavailable, and the petition fell
back to its deterministic wording. Every obvious explanation — wrong path,
unmounted file, stale container, bad key — was wrong.

Three settings have to agree, and the template shipped two of them in the
position that turns everything off:

    LLM_PROVIDER=off  STREAM_ASR_PROVIDER=off  TTS_PROVIDER=off
    ALLOW_EXTERNAL_AI=false

None of that is a bug on its own. `off` is right for a service with no keys,
and refusing egress until it is explicitly permitted is the whole reason
`allow_external_ai` exists. The bug was that the combination was silent.

There are now three defences, tested here in the order they fire:

    write-env.sh   derives the switches from the keys, so the CI path
                   cannot express the contradiction at all
    preflight.sh   inspects the written file and fails the deploy
    credential_check   reports it at runtime for every other route in

The tests that matter most are the ones asserting nothing switches itself
on. A check that quietly "fixed" the configuration would be the
opt-in-by-accident the gate exists to prevent.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from app.config import Settings
from app.services import credential_check

GEMINI = "AIzaTESTKEYaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
SARVAM = "sk_test_one,sk_test_two"

SCRIPTS = Path("../deploy/scripts").resolve()
BASH = shutil.which("bash")
NEEDS_BASH = pytest.mark.skipif(BASH is None, reason="bash is not available")


def settings(**overrides) -> Settings:
    """A configuration with no .env underneath it, so the test is the input."""
    return Settings(_env_file=None, **overrides)


def shipped(**overrides) -> Settings:
    """What the template ships, plus whatever the operator added."""
    base = {"allow_external_ai": False, "llm_provider": "off",
            "stream_asr_provider": "off", "tts_provider": "off"}
    base.update(overrides)
    return settings(**base)


class TestTheConfigurationThatFailedInProduction:
    def test_keys_added_to_the_shipped_template_are_reported_as_unused(self):
        assert credential_check.find(shipped(gemini_api_keys=GEMINI,
                                             sarvam_api_keys=SARVAM)), \
            "the exact live failure produced no report at all"

    def test_every_switch_that_defeats_a_key_is_named(self):
        blamed = {(c.setting, c.keys) for c in credential_check.find(
            shipped(gemini_api_keys=GEMINI, sarvam_api_keys=SARVAM))}

        assert ("LLM_PROVIDER", "GEMINI_API_KEYS") in blamed
        assert ("STREAM_ASR_PROVIDER", "SARVAM_API_KEYS") in blamed
        # One key drives both halves of the voice agent. Reporting only the
        # first leaves the operator fixing dictation and still having no
        # spoken replies.
        assert ("TTS_PROVIDER", "SARVAM_API_KEYS") in blamed

    def test_the_egress_gate_is_named_separately(self):
        """Turning the three switches on is not sufficient on its own, so it
        must not be reported as if it were."""
        assert any(c.setting == "ALLOW_EXTERNAL_AI"
                   for c in credential_check.find(shipped(gemini_api_keys=GEMINI)))

    def test_each_report_carries_the_line_to_change(self):
        for found in credential_check.find(shipped(gemini_api_keys=GEMINI,
                                                   sarvam_api_keys=SARVAM)):
            assert found.fix.split("=")[0] == found.setting

    def test_a_correctly_configured_deployment_reports_nothing(self):
        assert not credential_check.find(settings(
            allow_external_ai=True, llm_provider="auto",
            stream_asr_provider="auto", tts_provider="auto",
            gemini_api_keys=GEMINI, sarvam_api_keys=SARVAM))


class TestWhatItMustNotDo:
    def test_it_never_switches_anything_on(self):
        """A check that repaired the configuration would opt a deployment
        into egress because a key appeared in a file, which is exactly what
        `allow_external_ai` exists to refuse."""
        configured = shipped(gemini_api_keys=GEMINI, sarvam_api_keys=SARVAM)

        credential_check.find(configured)
        credential_check.summary(configured)

        assert configured.allow_external_ai is False
        assert configured.llm_provider == "off"
        assert configured.stream_asr_provider == "off"
        assert configured.tts_provider == "off"

    def test_no_key_or_fragment_of_one_appears_in_the_report(self):
        """This reaches a CI log and a health endpoint, both far more widely
        readable than app.env."""
        blob = json.dumps(credential_check.summary(
            shipped(gemini_api_keys=GEMINI, sarvam_api_keys=SARVAM)))

        assert GEMINI not in blob
        assert SARVAM not in blob
        for fragment in (GEMINI[:8], SARVAM[:8], "sk_test", "AIzaTEST"):
            assert fragment not in blob, fragment

    def test_not_even_how_long_a_key_is(self):
        short = credential_check.summary(shipped(gemini_api_keys="k"))
        long = credential_check.summary(shipped(gemini_api_keys="k" * 400))

        assert json.dumps(short) == json.dumps(long)

    def test_a_deployment_with_no_keys_is_not_nagged(self):
        """Local-only is the default and a supported, deliberate choice."""
        assert not credential_check.find(shipped())
        assert credential_check.summary(shipped())["ok"] is True


class TestTheSwitchValuesThatCount:
    def test_only_off_disables(self):
        for value in ("auto", "gemini", "AUTO"):
            assert not [c for c in credential_check.find(settings(
                allow_external_ai=True, llm_provider=value,
                gemini_api_keys=GEMINI)) if c.setting == "LLM_PROVIDER"], value

    def test_off_is_matched_whatever_its_case(self):
        for value in ("off", "OFF", "Off"):
            assert [c for c in credential_check.find(settings(
                allow_external_ai=True, llm_provider=value,
                gemini_api_keys=GEMINI)) if c.setting == "LLM_PROVIDER"], value


class TestTheHealthReport:
    def test_it_says_ok_when_there_is_nothing_to_say(self):
        report = credential_check.summary(settings(
            allow_external_ai=True, llm_provider="auto", gemini_api_keys=GEMINI))

        assert report["ok"] is True
        assert report["unused_credentials"] == []

    def test_it_contradicts_the_conclusion_the_operator_has_reached(self):
        """Which is that the key is bad. The sentence has to say otherwise."""
        report = credential_check.summary(shipped(sarvam_api_keys=SARVAM))

        assert report["ok"] is False
        assert "read correctly" in report["note"]


@NEEDS_BASH
class TestTheGeneratorCannotExpressTheContradiction:
    """write-env.sh derives the switches, so the bug is unreachable by the
    route that caused it."""

    @staticmethod
    def run(tmp_path: Path, **env) -> tuple[int, dict[str, str]]:
        supplied = {"APP_DIR": str(tmp_path), "OPERATOR_TOKEN": "tok",
                    "PUBLIC_ORIGIN": "https://example.gov.in"}
        supplied.update({k: v for k, v in env.items() if v is not None})
        done = subprocess.run(
            [BASH, str(SCRIPTS / "write-env.sh")],
            capture_output=True, text=True, env={**supplied, "PATH": "/usr/bin:/bin"})
        written: dict[str, str] = {}
        target = tmp_path / "app.env"
        if target.is_file():
            for line in target.read_text(encoding="utf-8").splitlines():
                if "=" in line and not line.startswith("#"):
                    name, _, value = line.partition("=")
                    written[name] = value
        return done.returncode, written

    def test_a_voice_key_switches_both_halves_of_voice_on(self, tmp_path):
        code, env = self.run(tmp_path, SARVAM_API_KEYS="sk", ALLOW_EXTERNAL_AI="true")

        assert code == 0
        assert env["STREAM_ASR_PROVIDER"] == "auto"
        assert env["TTS_PROVIDER"] == "auto"

    def test_a_language_key_switches_the_model_on(self, tmp_path):
        code, env = self.run(tmp_path, GEMINI_API_KEYS="g", ALLOW_EXTERNAL_AI="true")

        assert code == 0
        assert env["LLM_PROVIDER"] == "auto"

    def test_no_keys_leaves_everything_off(self, tmp_path):
        code, env = self.run(tmp_path)

        assert code == 0
        assert env["LLM_PROVIDER"] == "off"
        assert env["STREAM_ASR_PROVIDER"] == "off"
        assert env["TTS_PROVIDER"] == "off"

    def test_egress_is_never_derived_from_a_key(self, tmp_path):
        """The one thing a key must not switch on by existing."""
        code, env = self.run(tmp_path, GEMINI_API_KEYS="g", SARVAM_API_KEYS="s")

        assert code == 0
        assert env["ALLOW_EXTERNAL_AI"] == "false"

    def test_the_result_never_contradicts_itself(self, tmp_path):
        """The property the whole design exists for: whatever combination is
        supplied, no key is ever left governed by a switch that is off."""
        for keys in ({"GEMINI_API_KEYS": "g"}, {"SARVAM_API_KEYS": "s"},
                     {"GEMINI_API_KEYS": "g", "SARVAM_API_KEYS": "s"}, {}):
            code, env = self.run(tmp_path, ALLOW_EXTERNAL_AI="true", **keys)
            assert code == 0
            if "GEMINI_API_KEYS" in keys:
                assert env["LLM_PROVIDER"] != "off", keys
            if "SARVAM_API_KEYS" in keys:
                assert env["STREAM_ASR_PROVIDER"] != "off", keys
                assert env["TTS_PROVIDER"] != "off", keys

    def test_a_missing_required_secret_does_not_blank_a_working_file(self, tmp_path):
        """A secret someone deleted must stop the deploy, not overwrite a
        running configuration with an empty one."""
        self.run(tmp_path, SARVAM_API_KEYS="sk", ALLOW_EXTERNAL_AI="true")
        before = (tmp_path / "app.env").read_text(encoding="utf-8")

        done = subprocess.run(
            [BASH, str(SCRIPTS / "write-env.sh")], capture_output=True, text=True,
            env={"APP_DIR": str(tmp_path), "PUBLIC_ORIGIN": "https://x",
                 "PATH": "/usr/bin:/bin"})

        assert done.returncode != 0
        assert (tmp_path / "app.env").read_text(encoding="utf-8") == before

    def test_a_misspelled_egress_value_stops_the_deploy(self, tmp_path):
        """Rather than resolving to false, which would be this same bug in a
        new costume: a setting that looks enabled and is not."""
        code, _ = self.run(tmp_path, GEMINI_API_KEYS="g", ALLOW_EXTERNAL_AI="tru")

        assert code != 0

    def test_ordinary_spellings_of_yes_are_understood(self, tmp_path):
        for value in ("true", "TRUE", "True", "yes", "1"):
            code, env = self.run(tmp_path, GEMINI_API_KEYS="g",
                                 ALLOW_EXTERNAL_AI=value)
            assert code == 0, value
            assert env["ALLOW_EXTERNAL_AI"] == "true", value

    def test_the_android_app_origin_is_always_permitted(self, tmp_path):
        """A property of the client, not a deployment choice. Leaving it out
        makes the APK fail with a message that blames the network."""
        _, env = self.run(tmp_path)

        assert "https://localhost" in env["CORS_ORIGINS"]
        assert "https://example.gov.in" in env["CORS_ORIGINS"]

    def test_no_value_is_quoted(self, tmp_path):
        """docker compose env_file keeps quotes as part of the value."""
        _, env = self.run(tmp_path, SARVAM_API_KEYS="sk", ALLOW_EXTERNAL_AI="true")

        for name, value in env.items():
            assert not value.startswith(('"', "'")), name

    def test_ownership_is_derived_from_the_app_dir_not_hardcoded_to_root(self):
        """The bug that failed a live deploy AFTER the image had been pulled
        and the databases backed up:

            ==> Recreating service (project-scoped)
            open /opt/ai-petition-generator/app.env: permission denied

        write-env.sh runs under sudo, so without an explicit chown the file
        landed root:root — and the deploy step runs docker compose as the SSH
        user, which could not read it.

        Asserted against the SOURCE, not against a written file, and that is
        deliberate. A runtime check cannot catch this: `chown root:root`
        fails silently for any non-root test process, so the file stays
        correctly owned and the test passes whether the bug is present or
        not. Checking the instruction is the only assertion with teeth here.
        """
        script = (SCRIPTS / "write-env.sh").read_text(encoding="utf-8")

        assert 'chown "$owner"' in script, "the owner is not derived"
        assert 'stat -c' in script and '"$APP_DIR"' in script, (
            "the owner is not taken from the application directory")
        assert "chown root:root" not in script, (
            "a root-owned app.env cannot be read by the account that runs "
            "docker compose")
