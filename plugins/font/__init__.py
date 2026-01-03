# coding: utf-8

from logging import getLogger

from pydantic import BaseModel

import plugin as pl


class _FontFace(BaseModel):
    family: str
    src: str
    format: str


class FontConfig(BaseModel):
    google_fonts: bool = True
    family: list[str] = ['Inter', 'sans-serif']
    faces: list[_FontFace] = []
    all_html: bool = False


l = getLogger(__name__)
p = pl.Plugin(
    __name__,
    require_version_min=(5, 0, 0),
    require_version_max=(6, 0, 0),
    config=FontConfig
)

c: FontConfig = p.config


def hook(*, event: pl.AfterRequestHook):
    if 'html' not in event.response.content_type:
        return event

    data = event.response.get_data(True)

    html_end = ''
    if '</html>' in data:
        data = data.replace('</html>', '')
        html_end = '</html>'
    
    inject_content = '\n'.join([
        google_inject if c.google_fonts else '',
        fonts_inject
    ]).strip()

    new_data = f'{data}\n{inject_content}\n{html_end}'
    event.response.set_data(new_data)

    return event


def init():
    # process injects
    injects = []
    for f in c.faces:
        injects.append('''
@font-face {
  font-family: 'FAMILY';
  src: url('SOURCE') format('FORMAT');
}
'''[1:-1]
            .replace('FAMILY', f.family)
            .replace('SOURCE', f.src)
            .replace('FORMAT', f.format)
        )

    # inject css
    injects.append('''
body {
  font-family: FONTS;
}
'''[1:-1]
        .replace('FONTS', ', '.join(f"'{i}'" for i in c.family))
    )
    global fonts_inject
    fonts_inject = f"<style>\n{'\n'.join(injects)}\n</style>"

    if c.all_html:
        p.register_event(pl.AfterRequestHook, hook)

    else:
        # load google font
        if c.google_fonts:
            p.add_index_inject(google_inject)
            p.add_panel_inject(google_inject)

        p.add_index_inject(fonts_inject)
        p.add_panel_inject(fonts_inject)


google_inject = '''
<head>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
</head>
'''[1:-1]

p.init = init
