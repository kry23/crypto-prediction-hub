from configparser import ConfigParser
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
DEPLOY_DIR = REPO_ROOT / "deploy" / "systemd"
EXPECTED_UNITS = [
    "crypto-predictor-scheduler.service",
    "crypto-predictor-ui.service",
    "crypto-predictor-intel-bridge.service",
]


def test_all_three_units_exist():
    for u in EXPECTED_UNITS:
        assert (DEPLOY_DIR / u).exists(), f"missing unit: {u}"


def test_units_parse_as_valid_ini():
    """systemd unit files are INI-like. configparser parses them OK if the
    [Unit]/[Service]/[Install] sections are well-formed."""
    for u in EXPECTED_UNITS:
        parser = ConfigParser(strict=False)
        parser.read(DEPLOY_DIR / u, encoding="utf-8")
        assert "Unit" in parser
        assert "Service" in parser
        assert "Install" in parser


def test_every_unit_loads_secrets_env():
    """Critical: each unit must inherit the secrets file or runtime will
    miss DATABASE_URL / TELEGRAM_BOT_TOKEN."""
    for u in EXPECTED_UNITS:
        content = (DEPLOY_DIR / u).read_text(encoding="utf-8")
        assert "EnvironmentFile=/etc/crypto-predictor/secrets.env" in content, \
            f"unit {u} doesn't load secrets.env"


def test_every_unit_runs_as_deploy_user():
    for u in EXPECTED_UNITS:
        content = (DEPLOY_DIR / u).read_text(encoding="utf-8")
        assert "User=crypto-predictor" in content


def test_install_script_exists_and_is_executable_or_documented():
    """The install script exists. Mode is platform-dependent; just verify
    presence + shebang."""
    sh = REPO_ROOT / "deploy" / "install_systemd_units.sh"
    assert sh.exists()
    first_line = sh.read_text(encoding="utf-8").splitlines()[0]
    assert first_line.startswith("#!"), \
        f"install_systemd_units.sh missing shebang: {first_line}"


def test_readme_exists():
    assert (REPO_ROOT / "deploy" / "README.md").exists()
