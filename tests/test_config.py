from pathlib import Path

from print_explosion_3d.config import SPEC, env_template, load_settings


def test_defaults_when_env_is_empty():
    s = load_settings({})
    assert s.anthropic_api_key is None
    assert s.provider == "anthropic"
    assert s.model == "claude-sonnet-5-5"
    assert s.show_cost is False
    assert s.update_check is True
    assert s.effort == "medium"
    assert s.max_auto_fixes == 2
    assert s.show_cost is False
    assert s.workspace_dir == Path.home() / "Documents" / "Print Explosion 3D"
    assert s.openscad_bin is None
    assert s.render_timeout == 120
    assert s.update_check is True
    assert s.theme.model_color == "#f2a65a"


def test_overrides_apply():
    s = load_settings(
        {
            "ANTHROPIC_API_KEY": "sk-test",
            "PE_MODEL": "claude-opus-5-5",
            "PE_EFFORT": "HIGH",
            "PE_MAX_AUTO_FIXES": "1",
            "PE_SHOW_COST": "yes",
            "PE_WORKSPACE_DIR": "~/elsewhere",
            "PE_MODEL_COLOR": "#123abc",
            "PE_SPIN_SPEED": "1.5",
            "PE_UPDATE_CHECK": "off",
        }
    )
    assert s.anthropic_api_key == "sk-test"
    assert s.model == "claude-opus-5-5"
    assert s.effort == "high"
    assert s.max_auto_fixes == 1
    assert s.show_cost is True
    assert s.workspace_dir == Path.home() / "elsewhere"
    assert s.theme.model_color == "#123abc"
    assert s.theme.spin_speed == 1.5
    assert s.update_check is False


def test_bad_values_fall_back_instead_of_crashing():
    s = load_settings(
        {
            "PE_EFFORT": "turbo",
            "PE_MAX_AUTO_FIXES": "lots",
            "PE_MODEL_COLOR": "orange",
            "PE_SHADOW_OPACITY": "7",
            "PE_RENDER_TIMEOUT": "forever",
            "PE_MODEL": "   ",
            "PE_SHOW_COST": "maybe",
            "PE_UPDATE_CHECK": "sometimes",
        }
    )
    assert s.effort == "medium"
    assert s.max_auto_fixes == 2
    assert s.theme.model_color == "#f2a65a"
    assert s.theme.shadow_opacity == 1.0  # clamped
    assert s.render_timeout == 120
    assert s.model == "claude-sonnet-5-5"


def test_env_template_lists_every_setting():
    template = env_template()
    for setting in SPEC:
        assert f"{setting.env}={setting.default}" in template


def test_env_example_matches_spec():
    # .env.example is generated from SPEC; regenerate it after changing a setting.
    example = Path(__file__).parent.parent / ".env.example"
    assert example.read_text() == env_template(), (
        "Out of date. Run: uv run python -m print_explosion_3d.config > .env.example"
    )
