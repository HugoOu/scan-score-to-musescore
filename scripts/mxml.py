#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""minimal MusicXML 4.0 writer (partwise) used by scan-score-to-musescore.

Only what this toolkit needs: one part, one voice, notes/rests/chords,
hyphmony & direction injection via Measure.extra_before_end (see mxml_ext.py).

Duration unit is the quarter note: 1 = quarter, 0.5 = eighth, 1.5 = dotted
quarter, 2 = half, 3 = dotted half, 4 = whole. Internally 8 divisions per
quarter, so dotted/16th values are exact.

API kept deliberately small and close to MuseScore-friendly output; if you need
full MusicXML, use a real library (music21, musicxml, ...).
"""
from __future__ import annotations

from xml.sax.saxutils import escape

DIVS = 8  # divisions per quarter note
_UNITS_TO_TYPE = {
    32: ("whole", 0), 48: ("whole", 1),
    16: ("half", 0), 24: ("half", 1),
    8: ("quarter", 0), 12: ("quarter", 1),
    4: ("eighth", 0), 6: ("eighth", 1),
    2: ("16th", 0), 3: ("16th", 1),
    1: ("32nd", 0),
}
_STEPS = {"C": 0, "D": 1, "E": 2, "F": 3, "G": 4, "A": 5, "B": 6}


def parse_pitch(text: str):
    text = text.strip()
    if not text:
        raise ValueError("empty pitch")
    step = text[0].upper()
    if step not in _STEPS:
        raise ValueError(f"bad pitch {text!r}: must start with A-G")
    i, alter = 1, 0
    while i < len(text) and text[i] in "#b":
        alter += 1 if text[i] == "#" else -1
        i += 1
    try:
        octave = int(text[i:])
    except ValueError:
        raise ValueError(f"bad pitch {text!r}: missing octave (e.g. C4)") from None
    return step, alter, octave


def units(dur_q: float) -> int:
    u = round(dur_q * DIVS)
    if abs(dur_q * DIVS - u) > 1e-6:
        raise ValueError(f"duration {dur_q} cannot be written exactly (min 1/32)")
    if u not in _UNITS_TO_TYPE:
        raise ValueError(f"duration {dur_q} has no MusicXML type "
                         f"(use 4 3 2 1.5 1 0.75 0.5 0.375 0.25 0.125)")
    return u


class Note:
    def __init__(self, pitches, dur_q, staff=1, voice=1):
        self.pitches = list(pitches)          # [] = rest
        self.units = units(dur_q)
        self.ntype, self.dots = _UNITS_TO_TYPE[self.units]
        self.staff, self.voice = staff, voice
        self.tie = None
        self.slur = None
        self.fermata = False
        self.articulations: list[str] = []
        self.accidental = None
        self.lyrics: list[tuple[int, str]] = []

    @property
    def is_rest(self) -> bool:
        return not self.pitches


class Measure:
    def __init__(self, part, number):
        self.part, self.number = part, number
        self.streams: dict[tuple[int, int], list[Note]] = {}
        self.tempo = None
        self.dynamics: list[tuple[int, str]] = []
        self.rehearsal = None
        self.attributes: list[str] = []
        self.new_system = False
        self.new_page = False
        self.repeat = None
        self.barlines: list[str] = []
        self.coda = False
        self.segno = False

    # ---- writing helpers ----
    def line(self, text: str, staff=1, voice=1):
        made = []
        for token in text.split():
            body, _, dur_s = token.partition(":")
            dur = float(dur_s) if dur_s else 1.0
            if body.upper() in ("R", "REST"):
                n = Note([], dur, staff, voice)
            else:
                n = Note([parse_pitch(p) for p in body.split("+") if p], dur, staff, voice)
            self.streams.setdefault((staff, voice), []).append(n)
            made.append(n)
        return made

    def note(self, pitch, dur=1.0, staff=1, voice=1) -> Note:
        return self.line(f"{pitch}:{dur}", staff, voice)[0]

    def rest(self, dur=1.0, staff=1, voice=1) -> Note:
        return self.line(f"R:{dur}", staff, voice)[0]

    def chord(self, pitches, dur=1.0, staff=1, voice=1) -> Note:
        return self.line(f"{'+'.join(pitches)}:{dur}", staff, voice)[0]

    def mark(self, text: str):
        self.rehearsal = text
        return self

    def system_break(self):
        self.new_system = True
        return self

    def page_break(self):
        self.new_page = True
        return self

    # ---- MusicXML ----
    def _emit_note(self, n: Note, out: list[str]) -> None:
        heads = n.pitches or [None]
        for idx, head in enumerate(heads):
            out.append("      <note>")
            if head is None:
                out.append("        <rest/>")
            else:
                if idx:
                    out.append("        <chord/>")
                step, alter, octave = head
                out.append("        <pitch>")
                out.append(f"          <step>{step}</step>")
                if alter:
                    out.append(f"          <alter>{alter}</alter>")
                out.append(f"          <octave>{octave}</octave>")
                out.append("        </pitch>")
            out.append(f"        <duration>{n.units}</duration>")
            if n.tie:
                out.append(f'        <tie type="{n.tie}"/>')
            out.append(f"        <voice>{n.voice}</voice>")
            out.append(f"        <type>{n.ntype}</type>")
            for _ in range(n.dots):
                out.append("        <dot/>")
            if idx == 0 and n.accidental:
                out.append(f"        <accidental>{n.accidental}</accidental>")
            if idx == 0:
                bits = []
                if n.slur:
                    bits.append(f'<slur type="{n.slur}" number="1"/>')
                if n.tie:
                    bits.append(f'<tied type="{n.tie}"/>')
                if n.fermata:
                    bits.append('<fermata type="upright"/>')
                if n.articulations:
                    bits.append("<articulations>" + "".join(f"<{a}/>" for a in n.articulations)
                                + "</articulations>")
                if bits:
                    out.append("        <notations>" + "".join(bits) + "</notations>")
                for verse, text in n.lyrics:
                    out.append(f'        <lyric number="{verse}"><syllabic>single</syllabic>'
                               f"<text>{escape(text)}</text></lyric>")
            out.append(f"        <staff>{n.staff}</staff>")
            out.append("      </note>")

    def _emit(self, out: list[str]) -> None:
        out.append(f'    <measure number="{self.number}">')
        if self.new_page:
            out.append('      <print new-page="yes"/>')
        elif self.new_system:
            out.append('      <print new-system="yes"/>')

        if self.number == 1:
            out.append("      <attributes>")
            out.append(f"        <divisions>{DIVS}</divisions>")
            out.append(f"        <key><fifths>{self.part.score.key}</fifths></key>")
            beats, beat_type = self.part.score.time
            out.append(f"        <time><beats>{beats}</beats><beat-type>{beat_type}</beat-type></time>")
            if self.part.staves > 1:
                out.append(f"        <staves>{self.part.staves}</staves>")
            for i, (sign, line) in enumerate(self.part.clefs, start=1):
                num = f' number="{i}"' if self.part.staves > 1 else ""
                out.append(f"        <clef{num}><sign>{sign}</sign><line>{line}</line></clef>")
            out.append("      </attributes>")
            if self.part.score.tempo:
                bpm = self.part.score.tempo
                out.append('      <direction placement="above"><direction-type>'
                           "<metronome><beat-unit>quarter</beat-unit>"
                           f"<per-minute>{bpm}</per-minute></metronome></direction-type>"
                           f'<sound tempo="{bpm}"/></direction>')
        elif self.attributes:
            out.append("      <attributes>" + "".join(self.attributes) + "</attributes>")

        if self.tempo and self.number != 1:
            out.append('      <direction placement="above"><direction-type>'
                       "<metronome><beat-unit>quarter</beat-unit>"
                       f"<per-minute>{self.tempo}</per-minute></metronome></direction-type>"
                       f'<sound tempo="{self.tempo}"/></direction>')
        for staff, dyn in self.dynamics:
            out.append(f'      <direction placement="below"><direction-type>'
                       f"<dynamics><{dyn}/></dynamics></direction-type>"
                       f"<staff>{staff}</staff></direction>")
        if self.rehearsal:
            out.append('      <direction placement="above"><direction-type>'
                       f"<rehearsal>{escape(self.rehearsal)}</rehearsal></direction-type></direction>")

        if self.repeat == "start":
            out.append('      <barline location="left"><repeat direction="forward"/></barline>')

        prev = None
        for key in sorted(self.streams):
            notes = self.streams[key]
            if prev is not None:
                out.append(f"      <backup><duration>{prev}</duration></backup>")
            total = sum(n.units for n in notes)
            for n in notes:
                self._emit_note(n, out)
            prev = total

        if self.repeat == "end":
            out.append('      <barline location="right"><repeat direction="backward"/></barline>')
        if self.coda:
            out.append('      <direction placement="above"><direction-type><coda/></direction-type></direction>')
        if self.segno:
            out.append('      <direction placement="above"><direction-type><segno/></direction-type></direction>')
        for style in self.barlines:
            out.append(f'      <barline location="right"><bar-style>{style}</bar-style></barline>')
        out.append("    </measure>")


class Part:
    def __init__(self, score, ident, name, program=1, staves=1, clefs=(("G", 2),)):
        self.score, self.ident, self.name = score, ident, name
        self.program, self.staves, self.clefs = program, staves, list(clefs)
        self.measures: list[Measure] = []

    def add_measure(self) -> Measure:
        m = Measure(self, len(self.measures) + 1)
        self.measures.append(m)
        return m

    def _part_list_xml(self) -> list[str]:
        return [
            f'    <score-part id="{self.ident}">',
            f"      <part-name>{escape(self.name)}</part-name>",
            f'      <score-instrument id="{self.ident}-I1"><instrument-name>{escape(self.name)}'
            "</instrument-name></score-instrument>",
            f'      <midi-instrument id="{self.ident}-I1"><midi-channel>1</midi-channel>'
            f"<midi-program>{self.program}</midi-program></midi-instrument>",
            "    </score-part>",
        ]


class Score:
    def __init__(self, title="", composer="", key=0, time=(4, 4), tempo=None, subtitle=""):
        self.title, self.subtitle, self.composer = title, subtitle, composer
        self.key, self.time, self.tempo = key, time, tempo
        self.parts: list[Part] = []

    def add_part(self, name="Flute", program=74, staves=1, clefs=None) -> Part:
        clefs = clefs or ((("G", 2),) if staves == 1 else (("G", 2), ("F", 4)))
        part = Part(self, f"P{len(self.parts) + 1}", name, program, staves, clefs)
        self.parts.append(part)
        return part

    def to_xml(self) -> str:
        out = ['<?xml version="1.0" encoding="UTF-8"?>',
               '<!DOCTYPE score-partwise PUBLIC "-//Recordare//DTD MusicXML 4.0 Partwise//EN" '
               '"http://www.musicxml.org/dtds/partwise.dtd">',
               '<score-partwise version="4.0">']
        if self.title:
            out.append(f"  <work><work-title>{escape(self.title)}</work-title></work>")
        out.append("  <identification>")
        if self.composer:
            out.append(f'    <creator type="composer">{escape(self.composer)}</creator>')
        out.append("    <encoding><software>scan-score-to-musescore</software></encoding>")
        out.append("  </identification>")
        out.append("  <part-list>")
        for p in self.parts:
            out.extend(p._part_list_xml())
        out.append("  </part-list>")
        for p in self.parts:
            out.append(f'  <part id="{p.ident}">')
            for m in p.measures:
                m._emit(out)
            out.append("  </part>")
        out.append("</score-partwise>")
        return "\n".join(out) + "\n"

    def write(self, path: str) -> str:
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            f.write(self.to_xml())
        return path
