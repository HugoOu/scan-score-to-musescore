# -*- coding: utf-8 -*-
"""Extend the bundled minimal mxml writer with notation it does not cover.

Adds:
  * <harmony> chord symbols (incl. slash chords / offsets)
  * <ending> volta brackets (1st/2nd endings)
  * <words> directions: To Coda / D.S. al Coda / Coda
  * <segno> / <coda> signs
  * repeat barlines, final barline

These are injected by monkey-patching Measure._emit; the injected chunks are
placed at the right position (harmony/directions before the first <note>,
barlines after it) so MuseScore reads them correctly.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mxml
from xml.sax.saxutils import escape


_orig_emit = mxml.Measure._emit

def _emit(self, out):
    _orig_emit(self, out)
    assert out[-1].strip() == "</measure>"
    out.pop()
    # 需要落在小节线起点的内容（和弦符号、文字、Segno、Coda）
    start = [c for c in getattr(self, "extra_before_end", []) if c.startswith("<harmony") or c.startswith("<direction")]
    end = [c for c in getattr(self, "extra_before_end", []) if c not in start]
    # 找到第一个 <note>，把 start 插到它前面
    # 只在本小节范围内找第一个 <note>
    mstart = 0
    for i in range(len(out) - 1, -1, -1):
        if out[i].strip().startswith("<measure "):
            mstart = i
            break
    pos = None
    for i in range(mstart, len(out)):
        if out[i].strip().startswith("<note>"):
            pos = i
            break
    if pos is None:
        pos = len(out)
    for chunk in start:
        out.insert(pos, chunk)
        pos += 1
    for chunk in end:
        out.append(chunk)
    out.append("    </measure>")

mxml.Measure._emit = _emit


def extra(m, xml):
    if not hasattr(m, "extra_before_end"):
        m.extra_before_end = []
    m.extra_before_end.append(xml)
    return m


def harmony_xml(text, placement="above", offset=None):
    """'C' 'Dm' 'Bb' 'F/A' 'Gm' -> <harmony>"""
    bass = None
    if "/" in text:
        text, bass = text.split("/", 1)
    step = text[0].upper()
    alter = 0
    kind = "major"
    rest = text[1:]
    if rest.startswith("b"):
        alter = -1
        rest = rest[1:]
    elif rest.startswith("#"):
        alter = 1
        rest = rest[1:]
    low = rest.lower()
    if low in ("m", "min"):
        kind = "minor"
    elif low in ("7",):
        kind = "dominant"
    elif low in ("maj7",):
        kind = "major-seventh"
    elif low in ("m7",):
        kind = "minor-seventh"
    elif low in ("dim",):
        kind = "diminished"
    parts = [f'<harmony placement="{placement}">']
    if offset:
        parts.append(f"<offset>{offset}</offset>")
    parts += ["<root>", f"<root-step>{step}</root-step>"]
    if alter:
        parts.append(f"<root-alter>{alter}</root-alter>")
    parts.append("</root>")
    parts.append(f"<kind>{kind}</kind>")
    if bass:
        bstep = bass[0].upper()
        balter = 0
        if bass[1:].startswith("b"):
            balter = -1
        elif bass[1:].startswith("#"):
            balter = 1
        parts.append("<bass>")
        parts.append(f"<bass-step>{bstep}</bass-step>")
        if balter:
            parts.append(f"<bass-alter>{balter}</bass-alter>")
        parts.append("</bass>")
    parts.append("</harmony>")
    return "".join(parts)


def words_xml(text, placement="above", sound=None, italic=False):
    style = ' font-style="italic"' if italic else ""
    s = f'<sound {sound}/>' if sound else ""
    return (f'<direction placement="{placement}"><direction-type>'
            f'<words{style}>{escape(text)}</words></direction-type>{s}</direction>')


def direction_xml(inner, placement="above", sound=None):
    s = f"<sound {sound}/>" if sound else ""
    return f'<direction placement="{placement}"><direction-type>{inner}</direction-type>{s}</direction>'


def segno_xml(placement="above"):
    return direction_xml("<segno/>", placement)


def coda_xml(placement="above"):
    return direction_xml("<coda/>", placement)


def ending_start(number):
    return (f'<barline location="left"><ending number="{number}" type="start"/>'
            '</barline>')


def ending_stop(number):
    return (f'<barline location="right"><ending number="{number}" type="stop"/>'
            '</barline>')


def repeat_start():
    return '<barline location="left"><repeat direction="forward"/></barline>'


def repeat_end():
    return '<barline location="right"><repeat direction="backward"/></barline>'


def final_barline():
    return '<barline location="right"><bar-style>light-heavy</bar-style></barline>'
