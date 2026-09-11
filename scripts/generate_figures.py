"""Generate the documentation figures from their specs.

    python3 scripts/generate_figures.py          # rewrite changed figures
    python3 scripts/generate_figures.py --check  # exit 1 if a committed figure drifted

Every visible label reuses wording from the prose the figure illustrates; the
comment beside each label names its source. Both modes also fail when a page
embedding a figure uses different alt text from the figure's description. See
docs/images/README.md for the style and wording rules before changing a figure.
"""
from __future__ import annotations

import argparse
from collections.abc import Callable
from pathlib import Path
import sys
from typing import NamedTuple

from figure_kit import FRAME_INSET, Figure


REPO = Path(__file__).resolve().parents[1]

# Alt text for both embeds (README.md and docs/TECHNOLOGY.md) and the SVG <desc>.
ARCHITECTURE_DESCRIPTION = (
    'Your sample library and its index sit together on the sample drive. Library '
    'tools find sounds, let you listen in a browser to keep or skip candidates, and '
    'approve favourites; optional local AI organises listening. The approved '
    'collection passes to sample tools, which create checked WAV copies for '
    'Octatrack MKII, Digitakt MKI and TR-8S. Separately, Ableton tools rediscover '
    'saved projects without changing them. Optional Live tools inspect a running '
    'Set and apply edits after review, and let browser listening audition sounds in Live.'
)


def architecture() -> str:
    figure = Figure(832, 'Eidetic Sample Tools architecture', ARCHITECTURE_DESCRIPTION)
    box_height = 52

    # Columns: A holds what supports the path, M the path itself, R Ableton and devices.
    a_x, a_width = 40, 160
    m_x, m_width = 224, 188
    r_x, r_width = 576, 200
    left_frame_x, left_frame_right = a_x - FRAME_INSET, m_x + m_width + FRAME_INSET
    r_frame_x, r_frame_width = r_x - FRAME_INSET, r_width + 2 * FRAME_INSET
    a_mid, m_mid, r_mid = a_x + a_width / 2, m_x + m_width / 2, r_x + r_width / 2
    lane = r_frame_x + r_frame_width + 16

    # Rows. Listening and the Live bridge share a row so audition runs straight across.
    sources_y = 56
    find_y, listen_y, approve_y = 200, 288, 376
    create_y = 512

    def framed(y: float) -> tuple[float, float]:
        """Frame top and height around one row of boxes."""
        return y - 32, 32 + box_height + FRAME_INSET

    # On the sample drive.
    top, height = framed(sources_y)
    figure.frame(left_frame_x, top, left_frame_right - left_frame_x, height, 'Sample drive')
    # library-tools/README.md: "The library's index and decisions can travel with its drive"
    figure.box(a_x, sources_y, a_width, box_height,
               [('Library index', 'name'), ('with your decisions', 'detail')])
    # README.md: "Turn your sample library into sounds you want to play."
    figure.box(m_x, sources_y, m_width, box_height, [('Sample library', 'name')])

    # library-tools: find, listen, approve.
    library_top = find_y - 32
    figure.frame(left_frame_x, library_top, left_frame_right - left_frame_x,
                 approve_y + box_height + FRAME_INSET - library_top, 'library-tools')
    # README.md: "Search musical tags and pack origins, or find sounds with similar
    # acoustic characteristics"
    figure.box(m_x, find_y, m_width, box_height,
               [('Find sounds', 'name'), ('by tag, pack or similar sound', 'detail')])
    # README.md: "Listen in a browser, keep or skip candidates, and resume later."
    figure.box(m_x, listen_y, m_width, box_height,
               [('Listen in a browser', 'name'), ('keep or skip', 'detail')])
    # library-tools/README.md: "Give favourites useful roles and names"
    figure.box(m_x, approve_y, m_width, box_height,
               [('Approve favourites', 'name'), ('roles and names', 'detail')])
    # library-tools/README.md: "Use local AI to organise listening."
    figure.box(a_x, listen_y, a_width, box_height,
               [('Local AI', 'name'), ('organises listening', 'detail')], optional=True)

    # sample-tools: from the approved collection to device copies.
    top, height = framed(create_y)
    figure.frame(left_frame_x, top, left_frame_right - left_frame_x, height, 'sample-tools')
    # sample-tools/README.md: "Preview what will be exported, create copies and check
    # them before transfer."
    figure.box(m_x, create_y, m_width, box_height,
               [('Create WAV copies', 'name'), ('checked before transfer', 'detail')])

    # Ableton Live and the two packages that read it.
    # ableton-tools/README.md: "Rediscover saved Live projects without opening every Set."
    figure.box(r_frame_x, sources_y, r_frame_width, box_height, [('Ableton Live', 'name')])
    reports_y = listen_y - 32 - 16 - box_height - FRAME_INSET
    top, height = framed(reports_y)
    figure.frame(r_frame_x, top, r_frame_width, height, 'ableton-tools')
    # ableton-tools/README.md: "Sets and audio stay unchanged."
    figure.box(r_x, reports_y, r_width, box_height,
               [('Rediscover projects', 'name'), ('saved Sets stay unchanged', 'detail')])
    top, height = framed(listen_y)
    figure.frame(r_frame_x, top, r_frame_width, height, 'live-tools (optional)', optional=True)
    # live-tools/README.md: "Inspect a loaded Ableton Live Set and review small edits
    # before applying them."
    figure.box(r_x, listen_y, r_width, box_height,
               [('Inspect the running Set', 'name'), ('review edits before applying', 'detail')],
               optional=True)

    # sample-tools/README.md, "Supported devices": how each export reaches its device.
    devices = [('Octatrack MKII', 'CompactFlash card'), ('Digitakt MKI', 'Elektron Transfer'),
               ('TR-8S', 'SD card')]
    device_height, device_gap = 48, 8
    stack = len(devices) * device_height + (len(devices) - 1) * device_gap
    create_mid = create_y + box_height / 2
    first_y = create_mid - stack / 2
    figure.frame(r_frame_x, first_y - 32, r_frame_width, 32 + stack + FRAME_INSET,
                 'Supported devices')
    device_x = r_x + 16
    centres = []
    for index, (name, transfer) in enumerate(devices):
        y = first_y + index * (device_height + device_gap)
        figure.box(device_x, y, r_x + r_width - device_x, device_height,
                   [(name, 'name'), (transfer, 'detail')])
        centres.append(y + device_height / 2)

    # The sample path.
    figure.flow([(m_mid, sources_y + box_height), (m_mid, find_y)])
    figure.flow([(a_mid, sources_y + box_height), (a_mid, library_top)], both=True)
    figure.flow([(m_mid, find_y + box_height), (m_mid, listen_y)])
    # README.md: "keep or skip candidates"
    figure.label(m_mid + 8, find_y + box_height + 22, 'candidates')
    figure.flow([(m_mid, listen_y + box_height), (m_mid, approve_y)])
    # README.md: "keep the ones that work"
    figure.label(m_mid + 8, listen_y + box_height + 22, 'kept sounds')
    figure.flow([(a_x + a_width, listen_y + box_height / 2), (m_x, listen_y + box_height / 2)],
                optional=True)
    figure.flow([(m_mid, approve_y + box_height), (m_mid, create_y)])
    # library-tools/README.md: "Build an approved collection."
    figure.label(m_mid + 8, (approve_y + box_height + FRAME_INSET + create_y - 32) / 2 + 4,
                 'approved collection')
    figure.line([(m_x + m_width, create_mid), (r_x, create_mid)])
    figure.line([(r_x, centres[0]), (r_x, centres[-1])])
    figure.port(r_x, create_mid)
    for centre in centres:
        figure.flow([(r_x, centre), (device_x, centre)])

    # Ableton. Off centre so the connection clears the frame label.
    figure.flow([(r_mid + 48, sources_y + box_height), (r_mid + 48, reports_y)])
    figure.flow([(r_frame_x + r_frame_width, sources_y + box_height / 2),
                 (lane, sources_y + box_height / 2), (lane, listen_y + box_height / 2),
                 (r_x + r_width, listen_y + box_height / 2)], optional=True, both=True)
    # library-tools/README.md: "Optionally audition in Live."
    figure.flow([(m_x + m_width, listen_y + box_height / 2), (r_x, listen_y + box_height / 2)],
                optional=True)
    figure.label((left_frame_right + r_frame_x) / 2, listen_y + box_height / 2 - 8,
                 'audition in Live', anchor='middle')

    return figure.render()


class Spec(NamedTuple):
    path: str
    render: Callable[[], str]
    description: str
    # Markdown files whose image alt text must be the description, word for word.
    embeds: tuple[str, ...]


FIGURES = (
    Spec('docs/images/architecture.svg', architecture, ARCHITECTURE_DESCRIPTION,
         ('README.md', 'docs/TECHNOLOGY.md')),
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--check', action='store_true',
                        help='report drift without writing; exit 1 if any figure differs')
    args = parser.parse_args(argv)
    failed = 0
    for spec in FIGURES:
        for embed in spec.embeds:
            if f'![{spec.description}](' not in (REPO / embed).read_text(encoding='utf-8'):
                failed += 1
                print(f'  ALT TEXT {embed} does not use the {spec.path} description',
                      file=sys.stderr)
        path = REPO / spec.path
        expected = spec.render()
        current = path.read_text(encoding='utf-8') if path.exists() else None
        if current == expected:
            print(f'  ok       {spec.path}')
            continue
        if args.check:
            failed += 1
            print(f'  DRIFT    {spec.path} does not match its spec; '
                  'run python3 scripts/generate_figures.py', file=sys.stderr)
            continue
        path.write_text(expected, encoding='utf-8')
        print(f'  written  {spec.path}')
    return 1 if failed else 0


if __name__ == '__main__':
    raise SystemExit(main())
