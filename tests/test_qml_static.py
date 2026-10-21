"""Static checks on the QML sources: contrast, naming, honest labelling, and the 'no ordering' guarantee.

These run in milliseconds and catch whole classes of regressions before anything is launched.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
QML = ROOT / 'desktop' / 'qml'
ALL_QML = sorted(QML.rglob('*.qml'))


def theme() -> dict[str, str]:
    return dict(re.findall(r'readonly property color (\w+): "(#[0-9a-fA-F]{6})"', (QML / 'Theme.qml').read_text()))


def luminance(hex_color: str) -> float:
    r, g, b = (int(hex_color[i:i + 2], 16) / 255 for i in (1, 3, 5))
    lin = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in (r, g, b)]
    return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]


def contrast(a: str, b: str) -> float:
    la, lb = sorted((luminance(a), luminance(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


# ------------------------------------------------------------------ WCAG AA contrast
TEXT_ON_SURFACE = ['ink', 'muted', 'faint', 'accent', 'accent2', 'gain', 'loss', 'warn', 'danger', 'sample']
SURFACES = ['bg', 'sidebar', 'panel', 'panelAlt', 'panelHover', 'panelSelected', 'input']


@pytest.mark.parametrize('fg', TEXT_ON_SURFACE)
@pytest.mark.parametrize('bg', SURFACES)
def test_text_colours_meet_wcag_aa_on_every_surface(fg, bg):
    t = theme()
    assert contrast(t[fg], t[bg]) >= 4.5, f'{fg} on {bg}: {contrast(t[fg], t[bg]):.2f}:1 is below WCAG AA (4.5:1)'


@pytest.mark.parametrize('fg,bg', [('warn', 'warnBg'), ('danger', 'dangerBg'), ('sample', 'sampleBg'), ('accent', 'accentBg')])
def test_banner_text_meets_wcag_aa(fg, bg):
    t = theme()
    assert contrast(t[fg], t[bg]) >= 4.5, f'{fg} on {bg}: {contrast(t[fg], t[bg]):.2f}:1'


def test_input_borders_are_visible_against_their_surface():
    t = theme()
    assert contrast(t['borderStrong'], t['input']) >= 1.8 and contrast(t['accent'], t['input']) >= 3.0


# ------------------------------------------------------------------ structure
def test_every_page_in_the_navigation_has_a_qml_file():
    bridge = (ROOT / 'desktop' / 'bridge.py').read_text()
    pages = re.search(r"PAGES = \[(.*?)\]", bridge).group(1)
    names = re.findall(r"'(\w+)'", pages)
    main = (QML / 'Main.qml').read_text()
    block = re.search(r'pageFiles: \(\{(.*?)\}\)', main, re.S).group(1)
    files = dict(re.findall(r'"?(\w+)"?\s*:\s*"(\w+Page)"', block))
    assert len(names) == 10
    for page in names:
        assert page in files, f'{page} has no entry in Main.qml pageFiles'
        assert (QML / 'pages' / f'{files[page]}.qml').exists(), files[page]


def test_no_component_shadows_a_qtquick_controls_type():
    """A local 'Action.qml' silently lost to QtQuick.Controls.Action in every file that imports Controls."""
    controls = {'Action', 'ActionGroup', 'Button', 'CheckBox', 'ComboBox', 'Dialog', 'Label', 'Menu', 'MenuItem', 'Page', 'Pane', 'Popup',
                'RadioButton', 'ScrollBar', 'ScrollView', 'Slider', 'Switch', 'TabBar', 'TabButton', 'TextArea', 'TextField', 'ToolTip', 'Frame', 'GroupBox'}
    clash = [p.stem for p in (QML / 'components').glob('*.qml') if p.stem in controls]
    assert clash == []
    assert not (QML / 'components' / 'Action.qml').exists()


def test_every_component_is_used_somewhere():
    names = [p.stem for p in (QML / 'components').glob('*.qml')]
    corpus = '\n'.join(p.read_text() for p in ALL_QML)
    unused = [n for n in names if len(re.findall(rf'\b{n}\s*\{{', corpus)) == 0]
    assert unused == [], f'dead components: {unused}'


def test_qml_does_not_use_absolute_paths_or_remote_urls():
    for p in ALL_QML:
        text = p.read_text()
        assert not re.search(r'["\'](https?|ftp|wss?)://', text), f'{p.name} references a remote URL'
        assert 'file:///' not in text, f'{p.name} hardcodes an absolute file URL'


# ------------------------------------------------------------------ honest labelling
def strings(p: Path):
    return re.findall(r'"((?:[^"\\]|\\.)*)"', p.read_text())


def test_nothing_is_labelled_live_unless_it_negates_it():
    """Archived data must never be presented as live. 'LIVE' may appear only in a negation or as a future/approved item."""
    allowed = re.compile(r'(NO LIVE|NOT LIVE|NOT A LIVE|not live|no live|Live research|live research|live account|live connection|live feed|live integration)', re.I)
    offenders = []
    for p in ALL_QML:
        for s in strings(p):
            if re.search(r'\blive\b', s, re.I) and not allowed.search(s):
                offenders.append((p.name, s[:90]))
    assert offenders == [], offenders


def test_every_forecast_surface_carries_the_experimental_or_paper_label():
    for page in ('ForecastPage.qml', 'AccuracyPage.qml'):
        text = (QML / 'pages' / page).read_text().lower()
        assert 'experimental' in text or 'no advantage' in text or 'inconclusive' in text, page
    assert 'paper' in (QML / 'components' / 'ForecastCard.qml').read_text().lower()


def test_the_paper_side_tag_cannot_be_misread_as_no_paper_entry():
    """Regression: the tag once read 'NO PAPER ENTRY' for a paper entry on the NO side."""
    text = (QML / 'components' / 'ForecastCard.qml').read_text()
    assert '" paper entry"' not in text and 'Paper: buy' in text


def test_standing_disclaimer_is_always_on_screen():
    main = (QML / 'Main.qml').read_text()
    assert 'No trading advantage has been demonstrated' in main and 'You place every trade yourself' in main
    assert 'PAPER ≠ ACTUAL ACCOUNT' in main and 'NO SCANNER STARTED' in main


def test_sample_mode_is_always_flagged_and_paper_is_never_shown_as_account_profit():
    main = (QML / 'Main.qml').read_text()
    assert 'SAMPLE DATA' in main and 'SAMPLE ACCOUNT' in main
    overview = (QML / 'pages' / 'OverviewPage.qml').read_text()
    assert 'SAMPLE realized P&L' in overview and 'Your realized P&L (ledger)' in overview


# ------------------------------------------------------------------ no ordering capability
FORBIDDEN = re.compile(r'(place[_ ]?order|create[_ ]?order|submit[_ ]?order|cancel[_ ]?order|buy now|sell now|execute trade|auto[- ]?trade|portfolio/orders|trade-api|api\.elections\.kalshi|private[_ ]?key|api[_ ]?secret|password)', re.I)


def test_no_ordering_or_credential_surface_exists_in_qml_or_python():
    files = ALL_QML + list((ROOT / 'desktop').glob('*.py')) + list((ROOT / 'kh' / 'ledger').glob('*.py'))
    hits = []
    for p in files:
        for n, line in enumerate(p.read_text().splitlines(), 1):
            negated = re.search(r'\b(cannot|can not|never|does not|do not|will not|no )\b', line, re.I)   # a disclaimer ("cannot cancel orders") is the opposite of a capability
            if FORBIDDEN.search(line) and not negated and not line.lstrip().startswith(('#', '//', '"""', "'''")):
                hits.append(f'{p.relative_to(ROOT)}:{n}: {line.strip()[:100]}')
    assert hits == [], hits


def test_account_actions_are_about_recording_not_trading():
    record = (QML / 'components' / 'RecordDialog.qml').read_text()
    assert 'never places an order' in record.lower() or 'does not place' in record.lower() or 'already executed' in record.lower()


def test_every_document_the_ui_points_at_exists():
    """The pages and importers cite docs/…md; a citation must never dangle."""
    cited = set()
    for f in list((ROOT / 'desktop').rglob('*.py')) + list((ROOT / 'desktop').rglob('*.qml')) + list((ROOT / 'kh').rglob('*.py')):
        cited.update(re.findall(r'docs/([A-Z][A-Z_]*\.md)', f.read_text()))
    assert cited, 'expected the UI to cite at least one document'
    missing = sorted(name for name in cited if not (ROOT / 'docs' / name).exists())
    assert missing == [], f'docs cited but missing: {missing}'
